"""감지한 박스를 거리 단계(5.5m / 3m / 2m)로 바꾸고, 연속 프레임으로 경보 단계를 정한다.

Jetson 에서 카메라 프레임을 모델에 넣어 나온 박스를 이 모듈에 주면 된다. 카메라·모델·스피커와 상관없이
PC 에서 시험할 수 있게 일부러 순수 함수로 만들었다.

단계(level)
  0  경보 없음
  1  5.5m 이내  삐
  2  3m 이내    삐삐
  3  2m 이내    삐삐삐

거리를 어떻게 아나 — 박스 아래(발) 위치
- 카메라 높이와 기울기를 고정해 두면 바닥에 서 있는 물체는 가까울수록 화면 아래쪽에 찍힌다.
  그래서 박스 아래 끝의 높이(0=맨 위, 1=맨 아래)만 보고 거리를 3단계로 나눈다. 정확한 거리 측정이 아니다.
- 기준값(Calibration)은 거리 기준 영상(촬영 계획표 9번: 5.5m → 3m → 2m 위에 차례로 서기)에서
  발 위치를 재서 `calibrate_from_samples` 로 만든다. 카메라 높이를 바꾸면 다시 만든다.
- 잰 값은 코드에 박지 않고 `save_calibration`/`load_calibration` 으로 JSON 파일에 둔다.
  `calibration.example.json` 은 `estimate_calibration` 의 **추정치 예시**이고 실측값이 아니다.
- 영상으로 재기 전 임시값이 필요하면 `estimate_calibration` 으로 기하학 계산값을 얻는다.
  이 값은 렌즈 화각을 가정한 **추정**이라 실제 영상으로 반드시 보정한다.
- 발이 화면 아래에서 잘린 박스는 아주 가깝다고 보고 3단계(2m 이내)로 처리한다.
- 한계: 자전거를 탄 사람은 발이 페달 위(바닥보다 높은 곳)에 있어서 실제보다 멀게 읽힌다. 자전거 박스를 잡으면
  바퀴가 바닥에 닿아 정확하지만, 어두워서 자전거를 놓치고 사람만 잡으면 단계가 늦게(낮게) 나온다.

경보를 언제 내나 — 연속 프레임
- 한 프레임에서 잠깐 잡힌 것으로 울리지 않게 최근 `window` 프레임 중 `need` 번 이상 그 단계 이상이
  나올 때만 그 단계를 알린다(기본 3프레임 중 2번). 오경보를 줄이려는 규칙이다.

박스 형식: (x1, y1, x2, y2, conf, cls) 픽셀 좌표. cls 는 0=person, 1=bicycle (프로젝트 규칙).
"""

from __future__ import annotations

import json
import math
from collections import deque
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Iterable, Sequence

LEVEL_NAMES = {0: "없음", 1: "5.5m 이내", 2: "3m 이내", 3: "2m 이내"}
DEFAULT_DISTANCES_M = (5.5, 3.0, 2.0)
# 경보에 넣는 클래스: person=0, bicycle=1 (프로젝트 규칙). COCO 모델의 car=2 등은 거른다
ALARM_CLASSES = (0, 1)

Box = Sequence[float]  # (x1, y1, x2, y2, conf, cls)


@dataclass(frozen=True)
class Calibration:
    """박스 아래 끝의 높이 비율(0=맨 위, 1=맨 아래)로 거리 단계를 나누는 기준.

    foot_5_5 < foot_3 < foot_2 여야 한다(가까울수록 화면 아래).
    """

    foot_5_5: float
    foot_3: float
    foot_2: float
    frame_height: int = 1080
    camera_height_cm: int = 70
    # 박스 아래 끝이 화면 맨 아래에서 이 비율 이내면 발이 잘린 것으로 본다
    cut_margin: float = 0.01

    def __post_init__(self) -> None:
        if not (0.0 <= self.foot_5_5 < self.foot_3 < self.foot_2 <= 1.0):
            raise ValueError(
                "기준값은 0 <= foot_5_5 < foot_3 < foot_2 <= 1 이어야 한다(가까울수록 화면 아래): "
                f"{self.foot_5_5}, {self.foot_3}, {self.foot_2}"
            )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Calibration:
        """저장한 기준값(JSON 에서 읽은 dict)으로 되돌린다. 모르는 키는 무시한다."""
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in names})


def save_calibration(cal: Calibration, path: str | Path) -> None:
    """기준값을 JSON 파일로 저장한다. 거리 기준 영상으로 잰 값을 코드가 아니라 파일에 둔다."""
    Path(path).write_text(
        json.dumps(cal.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def load_calibration(path: str | Path) -> Calibration:
    """JSON 파일에서 기준값을 읽는다. 경계 값은 코드에 박지 않고 이 파일에서 온다."""
    return Calibration.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def estimate_calibration(
    camera_height_m: float = 0.7,
    tilt_deg: float = 15.0,
    vfov_deg: float = 60.0,
    frame_height: int = 1080,
    distances_m: Sequence[float] = DEFAULT_DISTANCES_M,
) -> Calibration:
    """카메라 높이·아래 기울기·세로 화각으로 기준값을 계산한다(추정치, 실제 영상으로 보정할 것).

    바닥의 한 점이 수평선 아래 atan(h/d) 각도에 있고, 카메라 축이 tilt 만큼 아래를 본다.
    축에서 얼마나 아래인지 θ = atan(h/d) - tilt 로 화면 높이 비율을 구한다(핀홀 모델).
    """
    if len(distances_m) != 3 or not all(
        a > b for a, b in zip(distances_m, distances_m[1:])
    ):
        raise ValueError(f"distances_m 은 큰 거리부터 3개여야 한다: {distances_m}")
    half = math.tan(math.radians(vfov_deg) / 2)
    ys = []
    for d in distances_m:
        theta = math.atan(camera_height_m / d) - math.radians(tilt_deg)
        ys.append(0.5 + math.tan(theta) / (2 * half))
    ys = [min(1.0, max(0.0, y)) for y in ys]
    return Calibration(ys[0], ys[1], ys[2], frame_height, round(camera_height_m * 100))


def _median(values: Sequence[float]) -> float:
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def calibrate_from_samples(
    samples_5_5: Sequence[Box],
    samples_3: Sequence[Box],
    samples_2: Sequence[Box],
    frame_height: int = 1080,
    camera_height_cm: int = 70,
    margin: float = 0.0,
) -> Calibration:
    """거리 기준 영상에서 모은 박스로 기준값을 만든다.

    각 거리(5.5m, 3m, 2m)에 사람이 서 있는 동안의 박스 목록을 준다.
    각 거리의 박스 아래 끝 높이(화면 높이 비율)의 **중앙값**을 그 단계의 경계로 쓴다.
    5.5m 이내(1단계)는 5.5m 대표값 이상, 3m 이내(2단계)는 3m 대표값 이상, 2m 이내(3단계)는 2m 대표값 이상이다.
    그래서 "5.5m 삐 / 3m 삐삐 / 2m 삐삐삐"가 말한 거리에서 바뀐다.

    margin: 서 있는 자리의 흔들림에 대한 여유(화면 높이 비율). 경계를 이만큼 **위로**(멀리로) 당겨서
    말한 거리보다 조금 일찍 울리게 한다. 기본 0(여유 없음)이고, 거리 기준 영상으로 재 본 뒤 정한다.
    너무 키우면 먼 사람에게도 울려 쓰는 사람이 경보를 꺼 버리니, 단계 사이 간격의 절반보다 작아야 한다.
    """
    if margin < 0:
        raise ValueError(f"margin 은 0 이상이다: {margin}")
    reps = []
    for name, group in (("5.5m", samples_5_5), ("3m", samples_3), ("2m", samples_2)):
        if not group:
            raise ValueError(f"{name} 박스가 없다")
        reps.append(_median([b[3] / frame_height for b in group]))
    r55, r3, r2 = reps
    if not (r55 < r3 < r2):
        raise ValueError(
            "거리 순서와 박스 위치가 안 맞는다(가까울수록 아래여야 함): "
            f"5.5m={r55:.3f}, 3m={r3:.3f}, 2m={r2:.3f}. 영상 구간이나 박스를 확인한다"
        )
    return Calibration(
        foot_5_5=max(0.0, r55 - margin),
        foot_3=r3 - margin,
        foot_2=r2 - margin,
        frame_height=frame_height,
        camera_height_cm=camera_height_cm,
    )


def box_level(
    box: Box,
    cal: Calibration,
    min_conf: float = 0.25,
    classes: Sequence[int] | None = ALARM_CLASSES,
) -> int:
    """박스 하나의 거리 단계(0~3).

    신뢰도가 min_conf 보다 낮거나 클래스가 classes(기본 person=0, bicycle=1)에 없으면 0.
    COCO 모델처럼 자동차 등 다른 클래스도 내놓는 모델로 시험할 때 경보에 안 들어가게 한다.
    박스에 클래스 값이 없으면(길이 5 이하) 거를 수 없어서 그대로 통과한다. classes=None 이면 거르지 않는다.
    """
    if classes is not None and len(box) > 5 and round(box[5]) not in classes:
        return 0
    conf = box[4] if len(box) > 4 else 1.0
    if conf < min_conf:
        return 0
    foot = box[3] / cal.frame_height
    if foot >= 1.0 - cal.cut_margin:  # 발이 화면 아래에서 잘렸다 → 아주 가까움
        return 3
    if foot >= cal.foot_2:
        return 3
    if foot >= cal.foot_3:
        return 2
    if foot >= cal.foot_5_5:
        return 1
    return 0


def frame_level(
    boxes: Iterable[Box],
    cal: Calibration,
    min_conf: float = 0.25,
    classes: Sequence[int] | None = ALARM_CLASSES,
) -> int:
    """한 프레임의 단계: 박스들 중 가장 가까운 것(가장 높은 단계). person·bicycle 만 센다."""
    return max((box_level(b, cal, min_conf, classes) for b in boxes), default=0)


class AlarmState:
    """연속 프레임으로 경보 단계를 정한다. 프레임마다 update() 를 부른다."""

    def __init__(self, window: int = 3, need: int = 2) -> None:
        if not 1 <= need <= window:
            raise ValueError(
                f"1 <= need <= window 여야 한다: need={need}, window={window}"
            )
        self.window, self.need = window, need
        self._recent: deque[int] = deque(maxlen=window)

    def update(self, level: int) -> int:
        """이번 프레임 단계를 넣고, 지금 알릴 경보 단계(0~3)를 돌려준다.

        최근 window 프레임 중 need 번 이상 level 이상이 나온 가장 높은 단계를 알린다.
        """
        self._recent.append(level)
        for candidate in (3, 2, 1):
            if sum(1 for x in self._recent if x >= candidate) >= self.need:
                return candidate
        return 0

    def reset(self) -> None:
        self._recent.clear()
