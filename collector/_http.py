"""일시 오류(429·5xx)는 서버가 알려 준 시간만큼 기다렸다가 다시 시도한다."""
import time

import requests

MAX_RETRIES = 2
MAX_WAIT = 60
DEFAULT_WAIT = 5


def _retry_after(resp):
    try:
        return int(resp.headers.get("Retry-After", DEFAULT_WAIT))
    except ValueError:  # 날짜 형식으로 오는 경우
        return DEFAULT_WAIT


def get(url, **kwargs):
    """requests.get과 같지만, 일시 오류는 최대 MAX_RETRIES번 다시 시도하고 끝내 실패하면 예외를 낸다."""
    kwargs.setdefault("timeout", 30)
    for attempt in range(MAX_RETRIES + 1):
        resp = requests.get(url, **kwargs)
        temporary = resp.status_code == 429 or resp.status_code >= 500
        if not temporary or attempt == MAX_RETRIES:
            resp.raise_for_status()
            return resp
        wait = min(_retry_after(resp), MAX_WAIT)
        print(f"[재시도] {resp.status_code} 응답, {wait}초 뒤 다시 시도 ({attempt + 1}/{MAX_RETRIES})")
        time.sleep(wait)
