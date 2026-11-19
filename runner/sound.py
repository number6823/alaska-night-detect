"""경고음. 표준 라이브러리만 쓴다(Jetson 에 따로 설치하지 않아도 되게).

단계마다 소리가 다르다: 1단계 삐, 2단계 삐삐, 3단계 삐삐삐. 높은 단계일수록 빠르게 반복한다.
  - Windows: winsound (PC 시연)
  - Linux / Jetson: aplay (ALSA). WAV 를 표준입력으로 넘긴다
  - 둘 다 없으면 터미널 벨(\\a)
경고음은 영상 처리를 막으면 안 되므로 따로 스레드에서 재생한다.
"""

from __future__ import annotations

import io
import math
import os
import queue
import shutil
import struct
import subprocess
import sys
import threading
import time
import wave
from typing import Callable, List, Optional, Tuple

SAMPLE_RATE = 22050
# (소리 높이 Hz, 한 번 길이 초, 사이 간격 초, 다음 묶음까지 쉬는 시간 초) 를 단계마다 정한다
PATTERNS = {
    1: {"freq": 880, "beeps": 1, "beep_s": 0.18, "gap_s": 0.10, "repeat_s": 1.6},
    2: {"freq": 1100, "beeps": 2, "beep_s": 0.14, "gap_s": 0.08, "repeat_s": 1.1},
    3: {"freq": 1400, "beeps": 3, "beep_s": 0.11, "gap_s": 0.06, "repeat_s": 0.7},
}


def tone_samples(freq: float, seconds: float, volume: float = 0.6) -> List[int]:
    n = int(SAMPLE_RATE * seconds)
    fade = max(
        1, int(SAMPLE_RATE * 0.008)
    )  # 소리가 뚝 끊기며 나는 잡음(클릭)을 줄이려고 가장자리를 서서히
    out = []
    for i in range(n):
        env = min(1.0, i / fade, (n - 1 - i) / fade)
        out.append(
            int(32767 * volume * env * math.sin(2 * math.pi * freq * i / SAMPLE_RATE))
        )
    return out


# 경보가 아닌 알림 소리. 경보(높은 삐 소리)와 헷갈리지 않게 음색과 길이가 다르다.
#  ready: 켜졌고 카메라가 열렸다(올라가는 세 음), lost: 카메라가 끊겼다(낮고 긴 두 음)
EVENTS = {
    "ready": [(660, 0.12), (880, 0.12), (1100, 0.20)],
    "lost": [(300, 0.30), (300, 0.30)],
}


def event_wav(name: str) -> bytes:
    if name not in EVENTS:
        raise ValueError(f"모르는 알림: {name}")
    samples: List[int] = []
    gap = [0] * int(SAMPLE_RATE * 0.06)
    for i, (freq, seconds) in enumerate(EVENTS[name]):
        samples += tone_samples(freq, seconds, volume=0.5)
        if i < len(EVENTS[name]) - 1:
            samples += gap
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(struct.pack("<%dh" % len(samples), *samples))
    return buf.getvalue()


def pattern_wav(level: int) -> bytes:
    """단계에 맞는 소리 묶음(삐 N번)을 WAV 바이트로 만든다."""
    if level not in PATTERNS:
        raise ValueError(f"단계는 1~3 이다: {level}")
    p = PATTERNS[level]
    samples: List[int] = []
    silence = [0] * int(SAMPLE_RATE * p["gap_s"])
    for i in range(p["beeps"]):
        samples += tone_samples(p["freq"], p["beep_s"])
        if i < p["beeps"] - 1:
            samples += silence
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(struct.pack("<%dh" % len(samples), *samples))
    return buf.getvalue()


def pattern_duration_s(level: int) -> float:
    p = PATTERNS[level]
    return p["beeps"] * p["beep_s"] + (p["beeps"] - 1) * p["gap_s"]


def aplay_command() -> List[str]:
    """aplay 명령. 환경변수 ALASKA_AUDIO_DEVICE 가 있으면 그 장치로 낸다(`aplay -L` 로 이름을 확인).

    Jetson 의 HDMI·보드 오디오는 기본 장치가 스피커가 아닐 수 있다. 22050Hz 모노를 바로 받지 않는 장치가 많아
    `plughw:<카드>,<장치>` 처럼 plughw 로 주면 알아서 바꿔 준다.
    """
    cmd = ["aplay", "-q"]
    device = os.environ.get("ALASKA_AUDIO_DEVICE", "").strip()
    if device:
        cmd += ["-D", device]
    return cmd + ["-"]


def play_wav(data: bytes) -> bool:
    """WAV 를 재생하고(끝날 때까지 기다림) 성공 여부를 돌려준다."""
    if sys.platform.startswith("win"):
        try:
            import winsound

            winsound.PlaySound(data, winsound.SND_MEMORY)
            return True
        except Exception:
            return False
    if shutil.which("aplay"):
        try:
            subprocess.run(aplay_command(), input=data, check=True, timeout=10)
            return True
        except Exception:
            return False
    sys.stdout.write("\a")
    sys.stdout.flush()
    return False


class Beeper:
    """경보 단계가 정해질 때마다 update(level) 을 부르면, 단계에 맞는 소리를 알맞은 간격으로 낸다."""

    def __init__(
        self,
        mute: bool = False,
        player: Callable[[bytes], bool] = play_wav,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.mute = mute
        self._player = player
        self._clock = clock
        self._wavs = {lvl: pattern_wav(lvl) for lvl in PATTERNS}
        self._wavs.update({name: event_wav(name) for name in EVENTS})
        self._q: "queue.Queue[Optional[int]]" = queue.Queue(maxsize=2)
        self._busy = threading.Event()
        self._next_ok = 0.0
        self._last_level = 0
        self.events: List[str] = []  # 낸 알림 이름(시험과 요약에 쓴다)
        self.played: List[Tuple[float, int]] = []  # (시각, 단계). 시험과 요약에 쓴다
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def update(self, level: int) -> bool:
        """이번 프레임의 경보 단계. 소리를 내기로 했으면 True."""
        if level not in PATTERNS:
            self._last_level = 0  # 경보가 꺼졌다. 다음에 울리면 새 사건이라 바로 낸다
            return False
        now = self._clock()
        # 단계가 올라가면(예: 5.5m 에서 3m 로) 간격을 기다리지 않고 바로 알린다. 주차 센서처럼 가까워지는 순간이 중요하다
        escalated = level > self._last_level
        self._last_level = level
        if not escalated and (now < self._next_ok or self._busy.is_set()):
            return False
        self._next_ok = now + pattern_duration_s(level) + PATTERNS[level]["repeat_s"]
        self.played.append((now, level))
        if self.mute:
            return True
        try:
            self._q.put_nowait(level)
        except queue.Full:
            if not escalated:
                return False
            # 소리가 밀려 있으면 오래된 낮은 단계를 버리고 올라간 단계를 알린다
            try:
                self._q.get_nowait()
            except queue.Empty:
                pass  # 그 사이 재생 스레드가 가져갔다
            try:
                self._q.put_nowait(level)
            except queue.Full:
                return False
        return True

    def play_event(self, name: str) -> bool:
        """켜짐("ready")이나 카메라 끊김("lost") 알림. 경보 간격 규칙과 상관없이 낸다. mute 면 내지 않는다."""
        if name not in EVENTS:
            return False
        self.events.append(name)
        if self.mute:
            return False
        try:
            self._q.put_nowait(name)
        except queue.Full:
            return False
        return True

    def play_now(self, level: int) -> None:
        """소리 시험용. 간격 규칙과 상관없이 바로 낸다."""
        if level in PATTERNS and not self.mute:
            try:
                self._q.put_nowait(level)
            except queue.Full:
                pass

    def _worker(self) -> None:
        while True:
            level = self._q.get()
            if level is None:
                return
            self._busy.set()
            try:
                self._player(self._wavs[level])
            except Exception:
                pass  # 소리가 안 나도 감지는 계속된다
            finally:
                self._busy.clear()

    def close(self) -> None:
        try:
            self._q.put_nowait(None)
        except queue.Full:
            pass
        self._thread.join(timeout=2.0)
