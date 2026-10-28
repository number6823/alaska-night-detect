"""UserPromptSubmit 훅: 수집 요청처럼 보이는 말일 때만 한 줄을 출력한다. 아닌 말에는 아무것도 하지 않는다."""

import json
import sys
from pathlib import Path

# 어느 폴더에서 불려도 agent 패키지를 찾도록 레포 루트를 경로에 넣는다.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.keywords import build_queries, extract_terms

# 수집 요청이라고 볼 동사. 사전 단어(야간, 자전거, 사람)와 함께 있어야 반응한다.
COLLECT_VERBS = ("수집", "모아", "모으", "찾아")


def is_collect_request(text):
    """수집 동사가 있고, 검색어까지 만들어지는 말이면 True."""
    has_verb = any(verb in text for verb in COLLECT_VERBS)
    return has_verb and bool(build_queries(extract_terms(text)))


def read_prompt():
    """인자가 있으면 그 문장을, 없으면 훅이 stdin으로 주는 JSON의 prompt 값을 읽는다."""
    if len(sys.argv) > 1:
        return " ".join(sys.argv[1:])
    raw = sys.stdin.read()
    try:
        return json.loads(raw).get("prompt", "")
    except (ValueError, AttributeError):
        return raw


def main():
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    prompt = read_prompt()
    if is_collect_request(prompt):
        queries = build_queries(extract_terms(prompt))
        print(f"[agent] 수집 요청 감지: 검색어 후보 {', '.join(queries)}")


if __name__ == "__main__":
    main()
