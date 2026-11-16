"""영상 입력. 영상 파일, USB 카메라, 네트워크 카메라(RTSP·HTTP, 스마트폰 카메라 앱 포함)를 같은 방식으로 읽는다.

`--source` 한 값으로 고른다.
  demo.mp4              영상 파일
  0                     카메라 번호 (USB 카메라, 영상 캡처 어댑터)
  rtsp://192.168.0.5/x  네트워크 카메라나 스마트폰 카메라 앱이 알려 주는 주소
  http://192.168.0.5:8080/video

모두 cv2.VideoCapture 로 열어서, 감지 이후의 코드는 입력이 무엇인지 모른다.
"""

from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path
from typing import Optional

import cv2

STREAM_PREFIXES = ("rtsp://", "rtmp://", "http://", "https://", "udp://", "tcp://")


def parse_source(source: str):
    """(종류, 값). 종류는 camera / stream / file."""
    s = str(source).strip()
    if s.isdigit():
        return "camera", int(s)
    if s.lower().startswith(STREAM_PREFIXES):
        return "stream", s
    return "file", s


class VideoSource:
    """프레임을 하나씩 읽는다. 카메라와 스트림은 끊기면 다시 연결을 시도하고, 파일은 끝나면 멈춘다."""

    def __init__(self, source: str, realtime: bool = False) -> None:
        self.kind, self.value = parse_source(source)
        self.realtime = realtime
        self._cap = None
        self._tmp: Optional[Path] = None
        self._next_t = 0.0
        self.fps = 30.0
        self.frames_read = 0
        self._open()

    @property
    def is_file(self) -> bool:
        return self.kind == "file"

    def _open(self) -> None:
        self.release()
        if self.kind == "file":
            path = Path(self.value)
            if not path.is_file():
                raise FileNotFoundError(f"영상 파일이 없다: {path}")
            cap = cv2.VideoCapture(str(path))
            if not cap.isOpened():
                # 한글 경로를 못 여는 OpenCV 빌드를 위해 영문 임시 이름으로 복사해 다시 연다
                self._tmp = Path(tempfile.mkdtemp()) / ("clip" + path.suffix.lower())
                shutil.copy(path, self._tmp)
                cap = cv2.VideoCapture(str(self._tmp))
        else:
            cap = cv2.VideoCapture(self.value)
        self._cap = cap
        if self.opened:
            self.fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            if self.fps < 1 or self.fps > 240:
                self.fps = 30.0

    @property
    def opened(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    def read(self):
        """프레임 한 장. 못 읽으면 None (파일은 끝, 카메라는 끊김)."""
        if not self.opened:
            return None
        if self.realtime and self.is_file:
            now = time.monotonic()
            if self._next_t > now:
                time.sleep(self._next_t - now)
            self._next_t = max(now, self._next_t) + 1.0 / self.fps
        ok, frame = self._cap.read()
        if not ok or frame is None:
            return None
        self.frames_read += 1
        return frame

    def reopen(self) -> bool:
        """카메라·스트림이 끊겼을 때 다시 연결을 시도한다. 파일은 다시 열지 않는다."""
        if self.is_file:
            return False
        self._open()
        return self.opened

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        if self._tmp is not None:
            shutil.rmtree(self._tmp.parent, ignore_errors=True)
            self._tmp = None
