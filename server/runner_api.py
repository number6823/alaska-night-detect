"""server 가 runner(감지 프로그램)를 다루는 API. 프로세스끼리 직접 부르지 않고 파일로 주고받는다.

  GET  /api/status            runner 상태(켜짐 여부, FPS, 현재 경보 단계, 마지막 명령 결과, 다시 시작이 필요한 설정)
  GET  /api/config            현재 설정과 기본값, 실행 중에 바로 반영되는 설정과 다시 시작이 필요한 설정의 목록
  PUT  /api/config            바꿀 설정만 보낸다. 검사를 통과하면 저장하고, 실행 중이면 runner 가 읽어서 반영한다
  POST /api/test-sound        경고음 시험 {"level": 1|2|3}
  POST /api/calibration       높이·기울기·화각으로 5.5m·3m·2m 거리선 위치를 계산한다(저장은 선택)
  POST /api/calibration/fit   한 지점에서 잰 발 위치로 화각을 맞추고 거리선을 계산한다(저장은 선택)
  GET  /api/cameras           연결된 카메라 목록
  GET  /api/preview           박스와 거리선이 그려진 최신 화면(MJPEG 스트림), /api/preview.jpg 는 한 장

설정을 바꾸는 요청(PUT config, test-sound, 저장하는 calibration)은 환경변수 ALASKA_TOKEN 이 있으면
`X-Token` 헤더가 같아야 한다. 없으면 같은 네트워크 안의 누구나 바꿀 수 있다(로그인이 없는 시연용).
"""

import asyncio
import json
import os
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Callable, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from alarm.levels import estimate_calibration, fit_vfov
from runner.config import LIVE_KEYS, RESTART_KEYS, RunnerConfig, check_types

ONLINE_STATES = ("running", "camera_lost")
STATUS_FRESH_S = 5.0  # status.json 이 이 시간보다 오래됐으면 runner 가 꺼진 것으로 본다


def read_json(path: Path) -> Optional[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)  # 쓰는 도중의 반쪽 파일을 runner 가 읽지 못하게


def runner_status(runner_dir: Path, now: Optional[float] = None) -> dict:
    data = read_json(runner_dir / "status.json")
    if data is None:
        return {
            "online": False,
            "state": "off",
            "detail": "runner 가 아직 시작되지 않았다",
        }
    now = time.time() if now is None else now
    age = max(0.0, now - float(data.get("updated", 0)))
    data["age_s"] = round(age, 1)
    data["online"] = data.get("state") in ONLINE_STATES and age < STATUS_FRESH_S
    if data.get("state") in ONLINE_STATES and age >= STATUS_FRESH_S:
        data["state"] = "stale"  # 상태가 멈춰 있다. 죽었거나 멈췄다
    return data


def lines_for(cal, frame_height: int) -> list:
    return [
        {"name": name, "ratio": round(r, 4), "y_px": int(round(r * frame_height))}
        for name, r in (("5.5m", cal.foot_5_5), ("3m", cal.foot_3), ("2m", cal.foot_2))
    ]


async def mjpeg_stream(
    path: Path,
    is_disconnected: Callable,
    interval_s: float = 0.15,
    max_frames: Optional[int] = None,
):
    """preview.jpg 가 바뀔 때마다 한 장씩 흘려 보낸다. 연결이 끊기면 멈춘다."""
    last = None
    sent = 0
    while True:
        if await is_disconnected():
            return
        try:
            st = path.stat()
            sig = (st.st_mtime_ns, st.st_size)
        except OSError:
            await asyncio.sleep(0.5)
            continue
        if sig != last:
            try:
                data = path.read_bytes()
            except OSError:
                await asyncio.sleep(interval_s)
                continue
            last = sig
            head = (
                b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n"
                % len(data)
            )
            yield head + data + b"\r\n"
            sent += 1
            if max_frames is not None and sent >= max_frames:
                return
        await asyncio.sleep(interval_s)


def probe_cameras(max_index: int = 4, in_use: Optional[int] = None) -> list:
    """카메라 번호 0..max_index 를 열어 본다. runner 가 쓰고 있는 번호는 열 수 없어서 in_use 로 표시만 한다."""
    import cv2

    out = []
    for i in range(max_index + 1):
        if in_use is not None and i == in_use:
            out.append({"index": i, "ok": True, "in_use": True})
            continue
        cap = cv2.VideoCapture(i)
        try:
            if cap.isOpened():
                out.append(
                    {
                        "index": i,
                        "ok": True,
                        "in_use": False,
                        "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                        "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                    }
                )
        finally:
            cap.release()
    return out


class ConfigBody(BaseModel):
    values: dict


class SoundBody(BaseModel):
    level: int


class CalibrationBody(BaseModel):
    camera_height_m: float = 0.7
    tilt_deg: float = 15.0
    vfov_deg: float = 60.0
    frame_height: int = 1080
    save: bool = False


class FitBody(BaseModel):
    distance_m: float
    foot_ratio: float
    camera_height_m: float = 0.7
    tilt_deg: float = 15.0
    frame_height: int = 1080
    save: bool = False


def build_router(
    runner_dir: Path,
    cameras_fn: Callable = probe_cameras,
) -> APIRouter:
    router = APIRouter()
    config_path = runner_dir / "config.json"

    def require_token(x_token: Optional[str] = Header(None)) -> None:
        wanted = os.environ.get("ALASKA_TOKEN")
        if wanted and x_token != wanted:
            raise HTTPException(status_code=401, detail="X-Token 이 맞지 않는다")

    def current_file_config() -> dict:
        return read_json(config_path) or {}

    def save_values(values: dict) -> dict:
        """값을 검사하고 config.json 에 합쳐 저장한다. 돌려주는 값: 저장 결과."""
        try:
            typed = check_types(values)
            merged = {**current_file_config(), **typed}
            full = RunnerConfig(**check_types(merged))
            full.validate(require_source=False)
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        before = current_file_config()
        changed = [
            k
            for k, v in typed.items()
            if before.get(k, getattr(RunnerConfig(), k)) != v
        ]
        atomic_write_json(config_path, merged)
        return {
            "saved": True,
            "changed": changed,
            "applied_live": [k for k in changed if k in LIVE_KEYS],
            "restart_required": [k for k in changed if k in RESTART_KEYS],
        }

    @router.get("/api/status")
    def status() -> dict:
        return runner_status(runner_dir)

    @router.get("/api/config")
    def get_config() -> dict:
        defaults = asdict(RunnerConfig())
        return {
            "config": {**defaults, **current_file_config()},
            "defaults": defaults,
            "live_keys": sorted(LIVE_KEYS),
            "restart_keys": sorted(RESTART_KEYS),
        }

    @router.put("/api/config", dependencies=[Depends(require_token)])
    def put_config(body: ConfigBody) -> dict:
        if not body.values:
            raise HTTPException(status_code=422, detail="바꿀 설정이 비었다")
        return save_values(body.values)

    @router.post(
        "/api/test-sound", status_code=202, dependencies=[Depends(require_token)]
    )
    def test_sound(body: SoundBody) -> dict:
        if body.level not in (1, 2, 3):
            raise HTTPException(status_code=422, detail="level 은 1, 2, 3 중 하나다")
        cmd_id = uuid.uuid4().hex[:12]
        atomic_write_json(
            runner_dir / "control.json",
            {"id": cmd_id, "cmd": "test_sound", "level": body.level},
        )
        online = runner_status(runner_dir).get("online", False)
        return {"id": cmd_id, "runner_online": online}

    @router.post("/api/calibration")
    def calibration(
        body: CalibrationBody, x_token: Optional[str] = Header(None)
    ) -> dict:
        try:
            cal = estimate_calibration(
                body.camera_height_m, body.tilt_deg, body.vfov_deg, body.frame_height
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        out = {"lines": lines_for(cal, body.frame_height), "vfov_deg": body.vfov_deg}
        if body.save:
            require_token(x_token)
            out["saved"] = save_values(
                {
                    "camera_height_m": body.camera_height_m,
                    "tilt_deg": body.tilt_deg,
                    "vfov_deg": body.vfov_deg,
                    "calibration": None,
                }
            )
        return out

    @router.post("/api/calibration/fit")
    def calibration_fit(body: FitBody, x_token: Optional[str] = Header(None)) -> dict:
        try:
            vfov = fit_vfov(
                body.distance_m, body.foot_ratio, body.camera_height_m, body.tilt_deg
            )
            cal = estimate_calibration(
                body.camera_height_m, body.tilt_deg, vfov, body.frame_height
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        out = {"vfov_deg": round(vfov, 2), "lines": lines_for(cal, body.frame_height)}
        if body.save:
            require_token(x_token)
            out["saved"] = save_values(
                {
                    "camera_height_m": body.camera_height_m,
                    "tilt_deg": body.tilt_deg,
                    "vfov_deg": round(vfov, 2),
                    "calibration": None,
                }
            )
        return out

    @router.get("/api/cameras")
    def cameras() -> dict:
        st = runner_status(runner_dir)
        in_use = None
        if st.get("online") and str(st.get("source", "")).isdigit():
            in_use = int(st["source"])
        try:
            items = (
                cameras_fn(in_use=in_use)
                if cameras_fn is probe_cameras
                else cameras_fn()
            )
        except ImportError:
            raise HTTPException(
                status_code=501, detail="이 환경에는 카메라를 찾을 OpenCV 가 없다"
            )
        return {"cameras": items}

    @router.get("/api/preview.jpg")
    def preview_jpg():
        path = runner_dir / "preview.jpg"
        if not path.is_file():
            raise HTTPException(
                status_code=404, detail="미리보기가 없다(감지가 꺼져 있다)"
            )
        return FileResponse(
            str(path), media_type="image/jpeg", headers={"Cache-Control": "no-store"}
        )

    @router.get("/api/preview")
    async def preview(request: Request):
        path = runner_dir / "preview.jpg"
        if not path.is_file():
            raise HTTPException(
                status_code=404, detail="미리보기가 없다(감지가 꺼져 있다)"
            )
        return StreamingResponse(
            mjpeg_stream(path, request.is_disconnected),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={"Cache-Control": "no-store"},
        )

    return router
