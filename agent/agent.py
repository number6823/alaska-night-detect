"""에이전트 흐름: 요청 해석 -> 검색어 승인 -> 도구 1 -> 도구 2 -> 보고."""

import sys

from agent.keywords import UNRESOLVED, build_queries, extract_terms
from agent.tools import read_metadata_summary, run_collector, run_labeler

# 기획서 성공 지표(중복·불량 제거율)의 제안 목표치. 팀 합의로 바뀔 수 있다.
REMOVAL_RATE_GOAL = 50


def ask_confirm(queries):
    """검색어를 보여주고 y/n 으로 승인받는다. 웹에서는 이 함수만 바꿔 끼우면 된다."""
    print("검색어:", ", ".join(queries))
    return input("이 검색어로 수집할까요? (y/n) ").strip().lower() == "y"


def print_report(report):
    """결과를 한눈에 보이게 출력한다."""
    collected = report["collected"]
    labeled = report["labeled"]
    print("--- 결과 ---")
    print(f"검색어: {', '.join(report['queries'])}")
    summary = report.get("metadata")
    if summary:
        print(
            f"수집: {summary['total']}장 -> 남은 {summary['passed']}장 ({collected['images_dir']})"
        )
        for reason, count in summary["removed"].items():
            print(f"  제거 {reason}: {count}장")
        if summary["total"]:
            rate = (summary["total"] - summary["passed"]) / summary["total"] * 100
            print(f"제거율: {rate:.1f}% (목표 {REMOVAL_RATE_GOAL}% 이상)")
    else:
        print(f"수집: {collected['collected']}장 ({collected['images_dir']})")
    # labeled는 검수 대기까지 포함한 값이라, 자동 통과는 빼서 구한다.
    print(f"라벨: {labeled['labeled']}장 ({labeled['labels_dir']})")
    print(f"  자동 통과: {labeled['labeled'] - labeled['review']}장")
    print(f"  검수 대기: {labeled['review']}장 ({labeled['review_queue_csv']})")
    print(f"폐기: {labeled['discarded']}장")
    if collected.get("fake") or labeled.get("fake"):
        print("※ 가짜 도구 결과입니다.")


def run(request, confirm=ask_confirm):
    """요청 한 줄을 처리한다. 해석 불가이거나 승인받지 못하면 None, 끝까지 가면 보고 dict."""
    queries = build_queries(extract_terms(request))
    if not queries:
        print(UNRESOLVED)
        return None
    if not confirm(queries):
        print("취소했어요.")
        return None

    collected = run_collector(queries)
    labeled = run_labeler(collected["images_dir"])
    metadata = read_metadata_summary(collected["metadata_csv"])
    report = {
        "queries": queries,
        "collected": collected,
        "labeled": labeled,
        "metadata": metadata,
    }
    print_report(report)
    return report


if __name__ == "__main__":
    request = " ".join(sys.argv[1:]) or input("요청: ")
    run(request)
