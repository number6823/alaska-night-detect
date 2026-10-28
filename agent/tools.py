"""도구 1(수집)과 도구 2(라벨링)를 부르는 자리. 도구 1은 아직 가짜 함수이고, 올라오면 안쪽만 바꾼다."""

import csv
from pathlib import Path

# 레포 루트 기준 기본 경로. 호출할 때 인자로 바꿀 수 있다.
DATA_DIR = Path("data")
IMAGES_DIR = DATA_DIR / "images"
LABELS_DIR = DATA_DIR / "labels"
METADATA_CSV = DATA_DIR / "metadata.csv"
REVIEW_QUEUE_CSV = DATA_DIR / "review_queue.csv"


# 민철 문서의 규약: run_collector(queries, images_dir, metadata_csv, count_per_query=10)
# 반환은 images_dir, metadata_csv 둘뿐이다. 도구 1이 올라오면 이 가짜를 바꾼다.
def run_collector(queries, images_dir=IMAGES_DIR, metadata_csv=METADATA_CSV):
    """도구 1(가짜). 검색어로 사진을 모아 images_dir에 저장하고 metadata_csv를 쓴다고 가정한다."""
    print(f"[가짜 도구 1] 수집: 검색어={list(queries)} -> {images_dir}")
    return {
        "fake": True,
        "queries": list(queries),
        "images_dir": str(images_dir),
        "metadata_csv": str(metadata_csv),
        "collected": 0,
    }


def run_labeler(
    images_dir=IMAGES_DIR, labels_dir=LABELS_DIR, review_queue_csv=REVIEW_QUEUE_CSV
):
    """도구 2. labeler.run_labeler를 부른다.

    ultralytics가 있어야 해서, 설치 전에도 나머지 단계가 돌도록 호출할 때 불러온다.
    반환: labels_dir, review_queue_csv, images, labeled(자동 통과 + 검수 대기), review, discarded.
    """
    from labeler import run_labeler as labeler_run

    return labeler_run(images_dir, labels_dir, review_queue_csv)


def read_metadata_summary(metadata_csv=METADATA_CSV):
    """metadata.csv(읽기 전용)에서 단계별 장수를 센다. 파일이 없으면 None.

    전체 줄 수 = 수집한 장수, removed_reason이 빈 줄 = 남은 장수.
    열 순서가 아니라 열 이름으로 읽고, 모르는 제거 사유도 그대로 센다.
    """
    path = Path(metadata_csv)
    if not path.exists():
        return None
    removed = {}
    total = 0
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            total += 1
            reason = (row.get("removed_reason") or "").strip()
            if reason:
                removed[reason] = removed.get(reason, 0) + 1
    return {"total": total, "passed": total - sum(removed.values()), "removed": removed}
