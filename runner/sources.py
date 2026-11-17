"""영상 입력. 영상 파일, USB 카메라, 네트워크 카메라(RTSP·HTTP, 스마트폰 카메라 앱 포함)를 같은 방식으로 읽는다.

`--source` 한 값으로 고른다.
  demo.mp4              영상 파일
  0                     카메라 번호 (USB 카메라, 영상 캡처 어댑터)
  rtsp://192.168.0.5/x  네트워크 카메라나 스마트폰 카메라 앱이 알려 주는 주소
  http://192.168.0.5:8080/video

모두 cv2.VideoCapture 로 열어서, 감지 이후의 코드는 입력이 무엇인지 모른다.

**항상 최신 프레임을 준다 (지연이 쌓이지 않게).** 감지가 카메라(보통 30fps)보다 느리면(Jetson Nano 는 약 6~17fps)
밀린 프레임을 하나하나 처리하다가 경고가 점점 늦어진다. 사람이 뒤에 다가오는데 몇 초 전 화면으로 경고하면 안 된다.
  - 카메라·네트워크 스트림: 별도 스레드가 계속 읽어 두고, read() 는 가장 최근 프레임만 준다(그 사이 프레임은 버린다).
  - 영상 파일을 --realtime 으로 재생할 때: 처리가 늦어지면 늦어진 만큼 프레임을 건너뛰어 영상 시간에 맞춘다.
  - --realtime 이 아닌 파일은 모든 프레임을 처리한다(시험·평가용).
건너뛴 프레임 수는 `dropped` 로 센다.
"""

from __future__ import annotations

import shutil
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

import cv2

STREAM_PREFIXES = ("rtsp://", "rtmp://", "http://", "https://", "udp://", "tcp://")
LIVE_WAIT_S = 1.0  # 새 프레임이 이 시간 동안 안 오면 끊긴 것으로 본다


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

    def __init__(
        self,
        source: str,
        realtime: bool = False,
        capture_factory=None,
        clock=time.monotonic,
        sleep=time.sleep,
    ) -> None:
        self.kind, self.value = parse_source(source)
        self.realtime = realtime
        self._factory = capture_factory or cv2.VideoCapture
        self._clock = clock
        self._sleep = sleep
        self._cap = None
        self._tmp: Optional[Path] = None
        self.fps = 30.0
        self.frames_read = 0  # 돌려준 프레임 수
        self.dropped = 0  # 최신 프레임을 주려고 건너뛰거나 버린 프레임 수
        self._position = 0  # 파일에서 지나온 프레임 수(건너뛴 것 포함)
        self._t0: Optional[float] = None
        # 카메라·스트림: 읽기 스레드와 최신 프레임
        self._pump: Optional[threading.Thread] = None
        self._pump_stop = threading.Event()
        self._lock = threading.Lock()
        self._new = threading.Event()
        self._latest = None
        self._pumped = 0
        self._delivered = 0
        self._pump_ended = False
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
            cap = self._factory(str(path))
            if not cap.isOpened():
                # 한글 경로를 못 여는 OpenCV 빌드를 위해 영문 임시 이름으로 복사해 다시 연다
                self._tmp = Path(tempfile.mkdtemp()) / ("clip" + path.suffix.lower())
                shutil.copy(path, self._tmp)
                cap = self._factory(str(self._tmp))
        else:
            cap = self._factory(self.value)
        self._cap = cap
        self._position = 0
        self._t0 = None
        if self.opened:
            self.fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            if self.fps < 1 or self.fps > 240:
                self.fps = 30.0
            if not self.is_file:
                self._start_pump()

    @property
    def opened(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    # ---- 카메라·스트림: 항상 가장 최근 프레임 ----
    def _start_pump(self) -> None:
        self._pump_stop.clear()
        self._new.clear()
        self._latest = None
        self._pumped = 0
        self._delivered = 0
        self._pump_ended = False
        cap = self._cap

        def pump() -> None:
            while not self._pump_stop.is_set():
                ok, frame = cap.read()
                if not ok or frame is None:
                    break
                with self._lock:
                    self._latest = frame
                    self._pumped += 1
                self._new.set()
            self._pump_ended = True
            self._new.set()  # 기다리던 read() 를 깨워서 끊김을 알게 한다

        self._pump = threading.Thread(target=pump, daemon=True)
        self._pump.start()

    def _read_live(self):
        if not self._new.wait(LIVE_WAIT_S):
            return None  # 새 프레임이 안 온다 = 끊김
        with self._lock:
            frame = self._latest
            pumped = self._pumped
            if pumped == self._delivered:  # 새로 온 것이 없다(읽기가 끝나서 깨운 것)
                frame = None
            else:
                self.dropped += (
                    pumped - self._delivered - 1
                )  # 이번 프레임 사이에 지나간 것은 버렸다
                self._delivered = pumped
            self._new.clear()
            if self._pump_ended and pumped != self._delivered:
                self._new.set()
        if frame is None:
            return None
        self.frames_read += 1
        return frame

    # ---- 영상 파일 ----
    def _read_file(self):
        if self.realtime:
            now = self._clock()
            if self._t0 is None:
                self._t0 = now
            due_pos = int(
                (now - self._t0) * self.fps
            )  # 영상 시간으로 지금쯤 와 있어야 할 프레임 번호
            behind = due_pos - self._position
            if behind > 1:
                # 처리가 늦어서 영상 시간에 뒤처졌다. 늦어진 만큼 건너뛰어 지금 화면을 처리한다
                for _ in range(behind - 1):
                    if not self._cap.grab():
                        break
                    self._position += 1
                    self.dropped += 1
            else:
                wait = self._t0 + self._position / self.fps - now
                if wait > 0:
                    self._sleep(wait)
        ok, frame = self._cap.read()
        if not ok or frame is None:
            return None
        self._position += 1
        self.frames_read += 1
        return frame

    def read(self):
        """가장 최근 프레임 한 장. 못 읽으면 None (파일은 끝, 카메라는 끊김)."""
        if self._cap is None:
            return None
        return self._read_file() if self.is_file else self._read_live()

    def reopen(self) -> bool:
        """카메라·스트림이 끊겼을 때 다시 연결을 시도한다. 파일은 다시 열지 않는다."""
        if self.is_file:
            return False
        self._open()
        return self.opened

    def release(self) -> None:
        self._pump_stop.set()
        if self._pump is not None:
            self._pump.join(timeout=2.0)
            self._pump = None
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        if self._tmp is not None:
            shutil.rmtree(self._tmp.parent, ignore_errors=True)
            self._tmp = None
