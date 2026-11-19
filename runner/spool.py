"""서버로 기록을 올리는 일. 서버가 죽어 있어도 기록을 잃지 않고, 경고음과 영상 처리를 막지 않는다.

흐름
  1. 감지 루프는 기록을 Reporter.submit() 에 넘기기만 한다(바로 돌아온다).
  2. 별도 스레드가 서버에 올린다. 성공하면 끝, 실패하면 Spool(디스크)에 쌓는다.
  3. 서버가 살아나면 쌓인 것을 오래된 것부터 다시 올린다. 새 기록이 없어도 일정 간격으로 다시 시도한다.
디스크가 무한히 차지 않게 최대 max_items 개만 보관한다(넘으면 오래된 것부터 버린다).
"""

from __future__ import annotations

import json
import queue
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional


class Spool:
    def __init__(self, directory: str, max_items: int = 500) -> None:
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.max_items = max_items
        self._seq = 0

    def put(
        self, jpeg: Optional[bytes], meta: dict, raw: Optional[bytes] = None
    ) -> Path:
        self._seq += 1
        stem = f"{time.time_ns()}_{self._seq:04d}"
        if jpeg:
            (self.dir / f"{stem}.jpg").write_bytes(jpeg)
        if raw:  # 박스를 그리지 않은 원본 프레임(재학습 자료용). 없는 기록도 그대로 올라간다
            (self.dir / f"{stem}.raw.jpg").write_bytes(raw)
        path = self.dir / f"{stem}.json"
        path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        self._trim()
        return path

    def pending(self) -> List[Path]:
        return sorted(self.dir.glob("*.json"))

    def count(self) -> int:
        return len(self.pending())

    def _trim(self) -> None:
        items = self.pending()
        for old in items[: max(0, len(items) - self.max_items)]:
            self._remove(old)

    @staticmethod
    def _remove(json_path: Path) -> None:
        for p in (
            json_path,
            json_path.with_suffix(".jpg"),
            json_path.with_name(json_path.stem + ".raw.jpg"),
        ):
            try:
                p.unlink()
            except FileNotFoundError:
                pass

    def flush(
        self, send: Callable[[Optional[bytes], dict], object], limit: int = 20
    ) -> int:
        """쌓인 것을 오래된 것부터 올린다. 하나라도 실패하면 거기서 멈춘다. 올린 개수를 돌려준다."""
        sent = 0
        for path in self.pending()[:limit]:
            try:
                meta = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self._remove(path)  # 깨진 기록은 다시 올려도 소용없다
                continue
            jpg = path.with_suffix(".jpg")
            data = jpg.read_bytes() if jpg.exists() else None
            raw_path = path.with_name(path.stem + ".raw.jpg")
            try:
                if raw_path.exists():
                    send(data, meta, raw_path.read_bytes())
                else:
                    send(data, meta)
            except (
                Exception
            ):  # 서버 문제는 종류가 많다. 어떤 것이든 나중에 다시 시도한다
                break
            self._remove(path)
            sent += 1
        return sent


class Reporter:
    """기록을 서버로 올리는 스레드. submit() 은 기다리지 않는다."""

    def __init__(
        self,
        server_url: str,
        spool: Spool,
        post_fn: Optional[Callable[..., dict]] = None,
        timeout: float = 2.0,
        retry_s: float = 3.0,
    ) -> None:
        if post_fn is None:
            from server.client import post_detection

            post_fn = post_detection
        self.server_url = server_url
        self.spool = spool
        self._post = post_fn
        self.timeout = timeout
        self.retry_s = retry_s
        self._q: "queue.Queue[Optional[tuple]]" = queue.Queue(maxsize=50)
        self.sent = 0
        self.failed = 0
        self.dropped_to_spool = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def submit(
        self, jpeg: Optional[bytes], meta: dict, raw: Optional[bytes] = None
    ) -> None:
        try:
            self._q.put_nowait((jpeg, meta, raw))
        except queue.Full:
            self.spool.put(
                jpeg, meta, raw
            )  # 서버가 느리면 디스크로 넘겨서 영상 처리를 막지 않는다
            self.dropped_to_spool += 1

    def _send(
        self, jpeg: Optional[bytes], meta: dict, raw: Optional[bytes] = None
    ) -> dict:
        if raw is not None:  # 원본이 있을 때만 넘긴다(원본을 모르는 옛 post 함수도 그대로 동작)
            return self._post(
                self.server_url, jpeg, timeout=self.timeout, raw_jpeg=raw, **meta
            )
        return self._post(self.server_url, jpeg, timeout=self.timeout, **meta)

    def _worker(self) -> None:
        while not self._stop.is_set():
            try:
                item = self._q.get(timeout=self.retry_s)
            except queue.Empty:
                # 새 기록이 없어도 서버가 살아났는지 보려고 쌓인 것을 다시 시도한다
                if self.spool.count():
                    self.sent += self.spool.flush(self._send, limit=5)
                continue
            if item is None:
                return
            jpeg, meta, raw = item
            try:
                self._send(jpeg, meta, raw)
                self.sent += 1
                if self.spool.count():
                    self.sent += self.spool.flush(self._send, limit=5)
            except Exception:
                self.failed += 1
                self.spool.put(jpeg, meta, raw)

    def close(self, wait_s: float = 3.0) -> None:
        """남은 기록을 올려 보고, 안 되면 디스크에 남긴 채 끝낸다."""
        self._q.put(None)
        self._thread.join(timeout=wait_s)
        self._stop.set()
        # 아직 큐에 남은 것은 잃지 않게 디스크로 옮긴다
        while True:
            try:
                item = self._q.get_nowait()
            except queue.Empty:
                break
            if item is not None:
                self.spool.put(*item)
