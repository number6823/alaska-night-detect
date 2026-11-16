"""runner 설정. 명령줄 인자와 설정 파일(JSON)을 합쳐 한 곳에서 검사한다.

설정 파일 예(data/runner/config.json):
    {"source": "demo.mp4", "model": "yolo11n.pt", "camera_height_m": 0.7, "tilt_deg": 15, "mute": false}

우선순위: 명령줄 인자 > 설정 파일 > 기본값. 잘못된 값은 시작할 때 바로 멈춘다(돌다가 틀어지지 않게).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Optional


@dataclass
class RunnerConfig:
    # 입력: 영상 파일 경로 / 카메라 번호(0, 1, ...) / rtsp:// 나 http:// 주소
    source: str = ""
    model: str = "yolo11n.pt"
    # 빈 값이면 GPU(CUDA)가 되는 환경에서는 GPU, 아니면 CPU. "0" 은 첫 GPU, "cpu" 는 CPU 강제
    device: str = ""
    min_conf: float = 0.25
    # 거리 기준값: calibration 파일이 있으면 그것을, 없으면 높이·기울기·화각으로 계산한 추정치를 쓴다
    calibration: Optional[str] = None
    camera_height_m: float = 0.7
    tilt_deg: float = 15.0
    vfov_deg: float = 60.0
    # 연속 window 프레임 중 need 번 이상 잡혀야 경보 (오경보를 줄이는 규칙)
    window: int = 3
    need: int = 2
    server_url: str = "http://127.0.0.1:8000"
    # 같은 단계가 계속될 때 기록을 올리는 최소 간격(초). 올라가는 순간(새 단계)은 바로 올린다
    post_interval_s: float = 2.0
    data_dir: str = "data/runner"
    mute: bool = False
    realtime: bool = False
    preview: bool = True
    max_frames: int = 0  # 0이면 끝까지

    def validate(self, require_source: bool = True) -> "RunnerConfig":
        """값 범위를 검사한다. 설정 화면에서 저장할 때는 아직 입력을 안 골랐을 수 있어 require_source=False 로 부른다."""
        if require_source and not str(self.source).strip():
            raise ValueError(
                "source 가 비었다. 영상 파일, 카메라 번호, 또는 rtsp:// 주소를 준다"
            )
        if not 0.0 <= self.min_conf <= 1.0:
            raise ValueError(f"min_conf 는 0~1 이다: {self.min_conf}")
        if not 0.2 <= self.camera_height_m <= 3.0:
            raise ValueError(
                f"camera_height_m 는 0.2~3.0 (미터) 이다: {self.camera_height_m}"
            )
        if not 0.0 <= self.tilt_deg <= 60.0:
            raise ValueError(
                f"tilt_deg 는 0~60 (아래로 기울인 각도) 이다: {self.tilt_deg}"
            )
        if not 20.0 <= self.vfov_deg <= 150.0:
            raise ValueError(f"vfov_deg 는 20~150 이다: {self.vfov_deg}")
        if not 1 <= self.need <= self.window:
            raise ValueError(
                f"1 <= need <= window 여야 한다: need={self.need}, window={self.window}"
            )
        if self.post_interval_s < 0:
            raise ValueError(f"post_interval_s 는 0 이상이다: {self.post_interval_s}")
        if self.max_frames < 0:
            raise ValueError(f"max_frames 는 0 이상이다: {self.max_frames}")
        return self


# 실행 중에 바꿔도 바로 반영되는 설정(재시작 없이). 나머지는 다시 시작해야 반영된다.
LIVE_KEYS = frozenset(
    {
        "min_conf",
        "calibration",
        "camera_height_m",
        "tilt_deg",
        "vfov_deg",
        "window",
        "need",
        "post_interval_s",
        "mute",
    }
)
RESTART_KEYS = frozenset({"source", "model", "device", "server_url", "data_dir", "realtime", "preview", "max_frames"})


def check_types(values: dict) -> dict:
    """설정 값의 종류가 맞는지 본다(JSON 으로 온 "abc" 같은 값이 비교 연산에서 터지지 않게). 숫자는 정수와 실수를 모두 받는다."""
    types = {f.name: f.type for f in fields(RunnerConfig)}
    out = {}
    for key, value in values.items():
        if key not in types:
            raise ValueError(f"모르는 설정: {key}")
        want = str(types[key]).replace("typing.", "")
        if key == "source" and isinstance(value, int) and not isinstance(value, bool):
            value = str(value)  # 카메라 번호를 숫자로 적어도 된다
        if value is None:
            if want.startswith("Optional"):
                out[key] = None
                continue
            raise ValueError(f"{key} 는 비울 수 없다")
        if want in ("bool", "<class 'bool'>"):
            ok = isinstance(value, bool)
        elif want in ("int", "<class 'int'>"):
            ok = isinstance(value, int) and not isinstance(value, bool)
        elif want in ("float", "<class 'float'>"):
            ok = isinstance(value, (int, float)) and not isinstance(value, bool)
        else:  # str, Optional[str]
            ok = isinstance(value, str)
        if not ok:
            raise ValueError(f"{key} 의 값 종류가 맞지 않는다: {value!r}")
        out[key] = float(value) if "float" in want else value
    return out


def load_config_file(path: str) -> dict:
    """설정 파일을 읽는다. 모르는 키는 오타일 수 있어서 거절한다."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"설정 파일이 없다: {path}")
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} 는 JSON 객체여야 한다")
    known = {f.name for f in fields(RunnerConfig)}
    unknown = sorted(set(data) - known)
    if unknown:
        raise ValueError(
            f"{path} 에 모르는 키가 있다: {unknown}. 쓸 수 있는 키: {sorted(known)}"
        )
    return data


def build_config(
    file_values: Optional[dict] = None, cli_values: Optional[dict] = None
) -> RunnerConfig:
    """기본값 < 설정 파일 < 명령줄 인자 순으로 합치고 검사한다. 명령줄 값이 None 이면 주지 않은 것이다."""
    merged = dict(file_values or {})
    for key, value in (cli_values or {}).items():
        if value is not None:
            merged[key] = value
    known = {f.name for f in fields(RunnerConfig)}
    unknown = sorted(set(merged) - known)
    if unknown:
        raise ValueError(f"모르는 설정: {unknown}")
    cfg = RunnerConfig(**check_types(merged))
    cfg.source = str(cfg.source)
    return cfg.validate()
