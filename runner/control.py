"""server 가 runner 에게 주는 것: 설정 변경(config.json)과 명령(control.json).

프로세스끼리 직접 부르지 않고 파일로 주고받는다. 그래야 한쪽이 죽어도 다른 쪽이 안 죽는다.
  - config.json : server 가 쓰고, runner 가 바뀐 것을 읽어 실행 중에 반영한다(LIVE_KEYS)
  - control.json: server 가 {"id", "cmd", ...} 한 건을 쓰고, runner 가 새 id 를 한 번만 실행한다

runner 는 읽기만 하고 이 파일들을 고치지 않는다. 결과는 status.json 의 last_control 로 알린다.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .config import LIVE_KEYS, RESTART_KEYS, RunnerConfig, check_types


class FileWatcher:
    """파일이 바뀌었을 때만 내용을 읽는다(mtime 과 크기가 달라졌을 때). 읽기 실패나 깨진 JSON 은 무시한다."""

    def __init__(
        self, path: str, min_interval_s: float = 0.5, clock: Callable[[], float] = None
    ) -> None:
        import time

        self.path = Path(path)
        self.min_interval_s = min_interval_s
        self._clock = clock or time.monotonic
        self._sig = self._signature()  # 시작할 때 이미 있는 내용은 새 변경이 아니다
        self._next_check = 0.0

    def _signature(self):
        try:
            st = os.stat(self.path)
        except OSError:
            return None
        return (st.st_mtime_ns, st.st_size)

    def poll(self) -> Optional[dict]:
        """바뀐 내용(dict) 또는 None."""
        now = self._clock()
        if now < self._next_check:
            return None
        self._next_check = now + self.min_interval_s
        sig = self._signature()
        if sig is None or sig == self._sig:
            return None
        self._sig = sig
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None  # 쓰는 중이거나 깨졌다. 다음에 다시 본다
        return data if isinstance(data, dict) else None


def apply_config_changes(
    cfg: RunnerConfig, values: dict, cli_keys=frozenset()
) -> Dict[str, List[str]]:
    """바뀐 설정을 cfg 에 반영한다. 돌려주는 값: {"applied": [...], "restart_required": [...], "ignored": [...]}.

    - LIVE_KEYS 는 바로 반영한다(값이 검사를 통과할 때만. 틀린 값이면 아무것도 바꾸지 않는다).
    - RESTART_KEYS 는 바뀌었다고만 알린다(source·model 등은 다시 시작해야 한다).
    - 명령줄로 직접 준 키(cli_keys)는 파일보다 우선이라 건드리지 않는다.
    """
    result = {"applied": [], "restart_required": [], "ignored": []}
    try:
        typed = check_types(values)
        trial = RunnerConfig(**{**cfg.__dict__, **typed})
        trial.validate(require_source=False)
    except (ValueError, TypeError) as exc:
        result["ignored"].append(f"검사 실패: {exc}")
        return result
    for key, value in typed.items():
        if key in cli_keys:
            result["ignored"].append(f"{key}(명령줄 값이 우선)")
            continue
        if getattr(cfg, key) == value:
            continue
        if key in LIVE_KEYS:
            setattr(cfg, key, value)
            result["applied"].append(key)
        elif key in RESTART_KEYS:
            result["restart_required"].append(key)
    return result


class ControlWatcher:
    """control.json 의 새 명령을 한 번씩만 돌려준다(같은 id 는 다시 실행하지 않는다)."""

    def __init__(self, path: str, min_interval_s: float = 0.3) -> None:
        self._watch = FileWatcher(path, min_interval_s)
        self._seen = None
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            self._seen = (
                data.get("id") if isinstance(data, dict) else None
            )  # 시작 전에 남은 명령은 실행하지 않는다
        except (OSError, ValueError):
            pass

    def poll(self) -> Optional[dict]:
        data = self._watch.poll()
        if not data or "id" not in data or data["id"] == self._seen:
            return None
        self._seen = data["id"]
        return data
