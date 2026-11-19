"""화면에 박스와 거리선을 그리고, 상태(status.json)와 미리보기(preview.jpg)를 파일로 내보낸다.

server 는 이 파일들을 읽어서 화면에 보여 준다. 파일을 쓰는 중에 읽히면 깨진 파일을 보게 되므로
임시 파일에 쓴 뒤 이름을 바꾸는 방식(원자적 쓰기)으로 덮어쓴다.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional, Sequence

import cv2

from alarm.levels import Calibration

# BGR. 단계 색: 0 초록, 1 노랑, 2 주황, 3 빨강
LEVEL_COLORS = {0: (80, 200, 80), 1: (0, 220, 240), 2: (0, 150, 255), 3: (60, 60, 240)}
CLASS_COLORS = {0: (255, 160, 0), 1: (255, 90, 200)}  # person 파랑 계열, bicycle 분홍
LEVEL_TEXT = {0: "OK", 1: "5.5m", 2: "3m", 3: "2m"}


def atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)  # 같은 폴더 안에서 이름을 바꾸면 중간 상태가 보이지 않는다


def encode_jpeg(frame, quality: int = 85) -> bytes:
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("JPEG 인코딩 실패")
    return buf.tobytes()


def draw_overlay(
    frame,
    boxes: Sequence[Sequence[float]],
    cal: Calibration,
    alarm_level: int,
    min_conf: float = 0.25,
    min_conf_bicycle: Optional[float] = None,
):
    """박스, 5.5m·3m·2m 거리선, 경보 단계를 그린 사본을 돌려준다(원본 프레임은 그대로)."""
    out = frame.copy()
    h, w = out.shape[:2]
    thick = max(1, round(h / 540))
    scale = max(0.5, h / 1080 * 0.9)
    for ratio, name in ((cal.foot_5_5, "5.5m"), (cal.foot_3, "3m"), (cal.foot_2, "2m")):
        y = int(ratio * h)
        cv2.line(out, (0, y), (w, y), (200, 200, 200), thick, cv2.LINE_AA)
        cv2.putText(
            out,
            name,
            (8, max(18, y - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            (230, 230, 230),
            thick,
            cv2.LINE_AA,
        )
    for b in boxes:
        need = min_conf_bicycle if (round(b[5]) == 1 and min_conf_bicycle is not None) else min_conf
        if len(b) < 6 or b[4] < need:
            continue
        x1, y1, x2, y2, conf, cls = b[:6]
        color = CLASS_COLORS.get(round(cls), (200, 200, 200))
        cv2.rectangle(out, (int(x1), int(y1)), (int(x2), int(y2)), color, thick * 2)
        label = f"{'person' if round(cls) == 0 else 'bicycle'} {conf:.2f}"
        cv2.putText(
            out,
            label,
            (int(x1), max(18, int(y1) - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            color,
            thick,
            cv2.LINE_AA,
        )
    banner = f"LEVEL {alarm_level}  {LEVEL_TEXT.get(alarm_level, '')}"
    cv2.rectangle(out, (0, 0), (int(w * 0.32), int(h * 0.07) + 6), (20, 20, 20), -1)
    cv2.putText(
        out,
        banner,
        (10, int(h * 0.05)),
        cv2.FONT_HERSHEY_SIMPLEX,
        scale * 1.1,
        LEVEL_COLORS.get(alarm_level, (255, 255, 255)),
        thick + 1,
        cv2.LINE_AA,
    )
    return out


class StatusWriter:
    def __init__(
        self,
        directory: str,
        status_interval_s: float = 0.25,  # 웹 화면의 막대가 끊기지 않게 자주 쓴다(작은 파일 한 개)
        preview_interval_s: float = 0.2,
        clock=time.monotonic,
    ) -> None:
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.status_path = self.dir / "status.json"
        self.preview_path = self.dir / "preview.jpg"
        self.status_interval_s = status_interval_s
        self.preview_interval_s = preview_interval_s
        self._clock = clock
        self._last_status: Optional[float] = None
        self._last_preview: Optional[float] = None

    def status_due(self) -> bool:
        return (
            self._last_status is None
            or self._clock() - self._last_status >= self.status_interval_s
        )

    def preview_due(self) -> bool:
        return (
            self._last_preview is None
            or self._clock() - self._last_preview >= self.preview_interval_s
        )

    def write_status(self, data: dict, force: bool = False) -> bool:
        if not force and not self.status_due():
            return False
        data = dict(data, updated=time.time())
        atomic_write(
            self.status_path, json.dumps(data, ensure_ascii=False).encode("utf-8")
        )
        self._last_status = self._clock()
        return True

    def write_preview(self, jpeg: bytes) -> None:
        atomic_write(self.preview_path, jpeg)
        self._last_preview = self._clock()
