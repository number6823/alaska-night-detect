"""runner 본체. 영상 → 감지 → 경보 단계 → 경고음 → 기록 전송을 한 번에 돌린다.

모델·소리·서버는 밖에서 바꿔 끼울 수 있게 인자로 받는다(시험할 때 가짜를 넣는다).
서버가 죽어도, 소리가 안 나도, 카메라가 끊겨도 이 루프는 죽지 않는다.

server 와는 파일로 주고받는다(data_dir 아래).
  config.json  server 가 쓴 설정. 바뀌면 실행 중에 반영한다(LIVE_KEYS). source·model 은 다시 시작해야 한다.
  control.json server 가 쓴 명령 한 건(소리 시험 등). 새 id 만 한 번 실행한다.
  status.json  runner 가 쓴다. 상태, FPS, 현재 단계, 마지막 명령 결과, 다시 시작이 필요한 설정.
  preview.jpg  runner 가 쓴다. 박스와 거리선을 그린 최신 화면.
"""

from __future__ import annotations

import dataclasses
import os
import time
from typing import Callable, Optional

from alarm.levels import Calibration, estimate_calibration, load_calibration

from .config import RunnerConfig
from .control import ControlWatcher, FileWatcher, apply_config_changes
from .pipeline import LEVEL_DISTANCE_M, Pipeline
from .sound import PATTERNS, Beeper
from .sources import VideoSource
from .spool import Reporter, Spool
from .status import StatusWriter, draw_overlay, encode_jpeg

CAL_KEYS = {"calibration", "camera_height_m", "tilt_deg", "vfov_deg"}


def make_calibration(cfg: RunnerConfig, frame_height: int) -> Calibration:
    """파일이 있으면 그 기준값, 없으면 높이·기울기·화각으로 계산한 추정치. frame_height 는 실제 영상에 맞춘다."""
    if cfg.calibration:
        return dataclasses.replace(
            load_calibration(cfg.calibration), frame_height=frame_height
        )
    return estimate_calibration(
        cfg.camera_height_m, cfg.tilt_deg, cfg.vfov_deg, frame_height
    )


class Live:
    """실행 중에 바뀌는 것들을 한곳에 모은다: 설정 반영, 명령 처리, 상태에 실을 정보."""

    def __init__(
        self, cfg, pipe, beeper, detector, frame_height, config_path, cli_keys, log
    ) -> None:
        self.cfg, self.pipe, self.beeper, self.detector = cfg, pipe, beeper, detector
        self.frame_height = frame_height
        self.cli_keys = frozenset(cli_keys)
        self.log = log
        self.config_watch = FileWatcher(config_path) if config_path else None
        self.control_watch = ControlWatcher(os.path.join(cfg.data_dir, "control.json"))
        self.restart_required = []
        self.ignored = []
        self.last_control = None
        self.cal = pipe.cal

    def poll(self) -> None:
        if self.config_watch is not None:
            values = self.config_watch.poll()
            if values is not None:
                self._apply_config(values)
        cmd = self.control_watch.poll()
        if cmd is not None:
            self._run_command(cmd)

    def _apply_config(self, values: dict) -> None:
        res = apply_config_changes(self.cfg, values, self.cli_keys)
        self.ignored = res["ignored"]
        for key in res["restart_required"]:
            if key not in self.restart_required:
                self.restart_required.append(key)
        applied = res["applied"]
        if not applied:
            if res["ignored"] or res["restart_required"]:
                self.log(
                    f"설정 변경 일부만 처리: 무시={res['ignored']}, 다시 시작 필요={res['restart_required']}"
                )
            return
        try:
            cal = (
                make_calibration(self.cfg, self.frame_height)
                if CAL_KEYS & set(applied)
                else None
            )
        except (OSError, ValueError) as exc:
            self.log(f"거리 기준값을 다시 만들지 못해 이전 값을 쓴다: {exc}")
            cal = None
        self.pipe.reconfigure(
            cal=cal,
            min_conf=self.cfg.min_conf if "min_conf" in applied else None,
            min_conf_bicycle=self.cfg.min_conf_bicycle
            if "min_conf_bicycle" in applied and self.cfg.min_conf_bicycle is not None
            else None,
            clear_min_conf_bicycle="min_conf_bicycle" in applied
            and self.cfg.min_conf_bicycle is None,
            window=self.cfg.window if "window" in applied else None,
            need=self.cfg.need if "need" in applied else None,
            post_interval_s=self.cfg.post_interval_s
            if "post_interval_s" in applied
            else None,
        )
        if cal is not None:
            self.cal = cal
        if "mute" in applied:
            self.beeper.mute = self.cfg.mute
        if {"min_conf", "min_conf_bicycle"} & set(applied) and hasattr(
            self.detector, "min_conf"
        ):
            self.detector.min_conf = self.pipe.floor_conf()  # 감지기는 낮은 쪽 기준으로 내보낸다
        self.log(f"설정을 실행 중에 반영했다: {applied}")

    def _run_command(self, cmd: dict) -> None:
        name = cmd.get("cmd")
        result = "unknown"
        if name == "test_sound":
            level = cmd.get("level")
            if isinstance(level, int) and level in PATTERNS:
                if self.beeper.mute:
                    result = "muted"
                else:
                    self.beeper.play_now(level)
                    result = "played"
            else:
                result = "bad_level"
        self.last_control = {
            "id": cmd.get("id"),
            "cmd": name,
            "result": result,
            "at": time.strftime("%H:%M:%S"),
        }
        self.log(f"명령 처리: {self.last_control}")

    def extras(self) -> dict:
        c = self.cal
        return {
            "device": self.detector.describe()
            if hasattr(self.detector, "describe")
            else "",
            "calibration": {
                "foot_5_5": round(c.foot_5_5, 4),
                "foot_3": round(c.foot_3, 4),
                "foot_2": round(c.foot_2, 4),
            },
            "restart_required": list(self.restart_required),
            "last_control": self.last_control,
            "mute": self.cfg.mute,
            "min_conf": self.cfg.min_conf,
            "min_conf_bicycle": self.cfg.min_conf_bicycle,
            "imgsz": self.cfg.imgsz,
        }


def run(
    cfg: RunnerConfig,
    detector=None,
    post_fn: Optional[Callable[..., dict]] = None,
    beeper: Optional[Beeper] = None,
    source: Optional[VideoSource] = None,
    log: Callable[[str], None] = print,
    config_path: Optional[str] = None,
    cli_keys=frozenset(),
    watch_interval_s: float = 0.5,
    lost_retry_s: float = 1.0,
) -> dict:
    cfg.validate()
    src = source or VideoSource(cfg.source, realtime=cfg.realtime)
    if not src.opened:
        raise RuntimeError(f"입력을 열지 못했다: {cfg.source}")
    # 모델은 첫 프레임을 읽기 전에 만든다. --realtime 영상 파일의 시계는 첫 프레임을 읽을 때 시작하는데,
    # Jetson 에서 TensorRT 엔진을 올리는 데 약 100초가 걸려서 그 뒤에 만들면 영상 시계가 먼저 흘러가
    # 프레임을 천 개 넘게 건너뛰고 끝나 버린다.
    if detector is None:
        from .detector import Detector

        floor = min(
            cfg.min_conf,
            cfg.min_conf_bicycle if cfg.min_conf_bicycle is not None else cfg.min_conf,
        )
        detector = Detector(cfg.model, floor, cfg.device, cfg.imgsz)
    first = src.read()
    if first is None:
        raise RuntimeError(f"입력에서 프레임을 읽지 못했다: {cfg.source}")
    cal = make_calibration(cfg, first.shape[0])
    pipe = Pipeline(cal, cfg.min_conf, cfg.window, cfg.need, cfg.post_interval_s)
    pipe.min_conf_bicycle = cfg.min_conf_bicycle
    own_beeper = beeper is None
    beeper = beeper or Beeper(mute=cfg.mute)
    spool = Spool(os.path.join(cfg.data_dir, "spool"))
    reporter = Reporter(cfg.server_url, spool, post_fn=post_fn)
    writer = StatusWriter(cfg.data_dir)
    live = Live(cfg, pipe, beeper, detector, first.shape[0], config_path, cli_keys, log)
    if live.config_watch is not None:
        live.config_watch.min_interval_s = watch_interval_s
    live.control_watch._watch.min_interval_s = watch_interval_s

    frames = 0
    max_level = 0
    posts = 0
    errors = 0
    consecutive_errors = 0
    lost_notified = False
    last_error = ""
    MAX_CONSECUTIVE_ERRORS = 50
    last_detect_at = ""
    started = time.monotonic()
    state = "running"
    frame = first
    where = detector.describe() if hasattr(detector, "describe") else "?"
    log(
        f"시작: 입력={cfg.source}, 모델={cfg.model}, 장치={where}, 화면 높이={first.shape[0]}, 서버={cfg.server_url}"
    )

    def status(level, fps=0.0):
        data = _status(
            state, cfg, frames, started, level, last_detect_at, reporter, spool, fps
        )
        data.update(live.extras())
        data["errors"] = errors
        data["dropped_frames"] = getattr(src, "dropped", 0)  # 처리가 느려서 건너뛴 프레임 수
        data["last_error"] = last_error
        return data

    beeper.play_event("ready")  # 입력이 열리고 첫 프레임을 읽었다. 이제 쓸 수 있다는 알림

    try:
        while True:
            live.poll()
            if frame is None:
                if src.is_file:
                    state = "finished"
                    break
                if not lost_notified:
                    # 끊긴 순간 한 번만 알린다(다시 연결했다가 또 읽지 못해도 소리를 반복하지 않는다)
                    beeper.play_event("lost")
                    log("카메라(입력)가 끊겼다. 다시 연결을 시도한다")
                    lost_notified = True
                state = "camera_lost"
                writer.write_status(status(0), force=True)
                time.sleep(lost_retry_s)
                if src.reopen():
                    log("카메라를 다시 연결했다")
                frame = src.read() if src.opened else None
                if frame is not None:
                    state = "running"  # 프레임이 실제로 읽혀야 정상으로 돌아온다
                continue
            lost_notified = False

            t0 = time.monotonic()
            try:
                boxes = detector.detect(frame)
                consecutive_errors = 0
            except Exception as exc:  # 모델 오류(메모리 부족, 장치 오류)로 루프가 죽으면 경고가 통째로 멈춘다
                errors += 1
                consecutive_errors += 1
                last_error = f"{type(exc).__name__}: {exc}"[:200]
                if consecutive_errors == 1 or consecutive_errors % 25 == 0:
                    log(f"감지 오류({consecutive_errors}번째 연속): {last_error}")
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    state = "error"
                    log("감지가 계속 실패해서 멈춘다. 모델과 장치를 확인한다")
                    break
                frame = src.read()
                if frame is None and src.is_file:
                    state = "finished"
                    break
                continue
            ms = int((time.monotonic() - t0) * 1000)
            res = pipe.process(boxes)
            beeper.update(res.alarm_level)
            frames += 1
            max_level = max(max_level, res.alarm_level)

            shown = None
            if res.should_post:
                shown = draw_overlay(
                    frame,
                    boxes,
                    pipe.cal,
                    res.alarm_level,
                    cfg.min_conf,
                    cfg.min_conf_bicycle,
                )
                last_detect_at = time.strftime("%H:%M:%S")
                meta = {
                    "person": res.person,
                    "bicycle": res.bicycle,
                    "top": round(min(1.0, res.top), 3),
                    "ms": ms,
                    "level": res.alarm_level,
                    "dist": LEVEL_DISTANCE_M[res.alarm_level],
                    "at": last_detect_at,
                }
                reporter.submit(encode_jpeg(shown), meta)
                posts += 1
            if cfg.preview and writer.preview_due():
                shown = (
                    shown
                    if shown is not None
                    else draw_overlay(
                        frame,
                    boxes,
                    pipe.cal,
                    res.alarm_level,
                    cfg.min_conf,
                    cfg.min_conf_bicycle,
                    )
                )
                writer.write_preview(encode_jpeg(shown, 75))
            if writer.status_due():
                fps = frames / max(1e-6, time.monotonic() - started)
                writer.write_status(status(res.alarm_level, fps))

            if cfg.max_frames and frames >= cfg.max_frames:
                state = "finished"
                break
            frame = src.read()
            if frame is None and src.is_file:
                state = "finished"
                break
    except KeyboardInterrupt:
        state = "stopped"
        log("사용자가 멈췄다")
    finally:
        elapsed = time.monotonic() - started
        writer.write_status(status(0, frames / max(1e-6, elapsed)), force=True)
        reporter.close()
        if own_beeper:
            beeper.close()
        src.release()
    summary = {
        "state": state,
        "frames": frames,
        "seconds": round(elapsed, 2),
        "fps": round(frames / max(1e-6, elapsed), 2),
        "max_alarm_level": max_level,
        "posts_submitted": posts,
        "posted_ok": reporter.sent,
        "post_failed": reporter.failed,
        "spooled_left": spool.count(),
        "beeps": len(beeper.played),
        "errors": errors,
        "dropped_frames": getattr(src, "dropped", 0),
    }
    log(f"끝: {summary}")
    return summary


def _status(
    state, cfg, frames, started, level, last_detect_at, reporter, spool, fps=0.0
) -> dict:
    return {
        "state": state,  # running / camera_lost / finished / stopped
        "source": cfg.source,
        "frames": frames,
        "fps": round(fps, 1),
        "alarm_level": level,
        "last_detection_at": last_detect_at,
        "posted_ok": reporter.sent,
        "spooled": spool.count(),
        "pid": os.getpid(),
        "uptime_s": round(time.monotonic() - started, 1),
    }
