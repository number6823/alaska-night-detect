"""감지한 박스 → 경보 단계 → 기록을 올릴지 결정. 카메라·모델·소리 없이 시험할 수 있는 순수 로직이다.

단계 판단은 alarm.levels 를 그대로 쓴다(거리 단계, 연속 3프레임 중 2번 규칙).
여기서 더하는 것은 "기록을 서버에 언제 올리나"이다.
  - 경보 단계가 올라가는 순간(0→1, 1→2, 2→3)은 바로 올린다.
  - 같은 단계가 계속되면 post_interval_s 초에 한 번만 올린다(같은 사람을 수십 장 올리지 않게).
  - 경보가 꺼졌다가(0) 다시 켜지면 새 사건이다.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from alarm.levels import ALARM_CLASSES, AlarmState, Calibration, frame_level

# 단계별 대표 거리(m). 정확한 거리가 아니라 3단계 구분이라 단계의 이름 거리를 쓴다.
LEVEL_DISTANCE_M = {0: 0.0, 1: 5.5, 2: 3.0, 3: 2.0}


@dataclass
class FrameResult:
    frame_level: int  # 이 프레임 하나만 본 단계
    alarm_level: int  # 연속 프레임 규칙을 거친 경보 단계(소리를 내는 기준)
    person: int
    bicycle: int
    top: float  # 사람·자전거 박스 중 가장 높은 신뢰도 (없으면 0)
    should_post: bool


class Pipeline:
    def __init__(
        self,
        cal: Calibration,
        min_conf: float = 0.25,
        window: int = 3,
        need: int = 2,
        post_interval_s: float = 2.0,
        classes: Sequence[int] = ALARM_CLASSES,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.cal = cal
        self.min_conf = min_conf
        self.classes = tuple(classes)
        self.post_interval_s = post_interval_s
        self._state = AlarmState(window=window, need=need)
        self._clock = clock
        self._last_post_level = 0
        self._last_post_time: Optional[float] = None

    def reconfigure(
        self,
        cal: Optional[Calibration] = None,
        min_conf: Optional[float] = None,
        window: Optional[int] = None,
        need: Optional[int] = None,
        post_interval_s: Optional[float] = None,
    ) -> None:
        """실행 중에 설정을 바꾼다. 연속 프레임 규칙을 바꾸면 쌓아 둔 프레임 기록은 버리고 새로 센다."""
        if cal is not None:
            self.cal = cal
        if min_conf is not None:
            self.min_conf = min_conf
        if post_interval_s is not None:
            self.post_interval_s = post_interval_s
        if window is not None or need is not None:
            self._state = AlarmState(
                window=window if window is not None else self._state.window,
                need=need if need is not None else self._state.need,
            )

    def process(self, boxes: Sequence[Sequence[float]]) -> FrameResult:
        keep = [
            b
            for b in boxes
            if len(b) > 5 and round(b[5]) in self.classes and b[4] >= self.min_conf
        ]
        lvl = frame_level(keep, self.cal, self.min_conf, self.classes)
        alarm = self._state.update(lvl)
        person = sum(1 for b in keep if round(b[5]) == 0)
        bicycle = sum(1 for b in keep if round(b[5]) == 1)
        top = max((float(b[4]) for b in keep), default=0.0)
        return FrameResult(lvl, alarm, person, bicycle, top, self._decide_post(alarm))

    def _decide_post(self, alarm: int) -> bool:
        if alarm == 0:
            self._last_post_level = 0
            self._last_post_time = None
            return False
        now = self._clock()
        rising = alarm > self._last_post_level
        waited = (
            self._last_post_time is None
            or now - self._last_post_time >= self.post_interval_s
        )
        if rising or waited:
            self._last_post_level = max(self._last_post_level, alarm)
            self._last_post_time = now
            return True
        return False
