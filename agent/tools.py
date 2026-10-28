"""도구 1(수집)과 도구 2(라벨링)를 부르는 자리. 지금은 가짜 함수이고, 실제 도구가 생기면 안쪽만 바꾼다."""

import csv
from pathlib import Path

# 레포 루트 기준 기본 경로. 호출할 때 인자로 바꿀 수 있다.
DATA_DIR = Path("data")
IMAGES_DIR = DATA_DIR / "images"
LABELS_DIR = DATA_DIR / "labels"
METADATA_CSV = DATA_DIR / "metadata.csv"
REVIEW_QUEUE_CSV = DATA_DIR / "review_queue.csv"


# 가정: 함수 이름과 인자는 민철·성진과 아직 합의 전이다. 합의되면 여기를 맞춘다.
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
    """도구 2(가짜). images_dir의 사진에 YOLO 라벨을 붙여 labels_dir에 저장하고, 신뢰도 낮은 것은 검수 대기열로 뺀다고 가정한다."""
    print(f"[가짜 도구 2] 라벨링: {images_dir} -> {labels_dir}")
    return {
        "fake": True,
        "images_dir": str(images_dir),
        "labels_dir": str(labels_dir),
        "review_queue_csv": str(review_queue_csv),
        "labeled": 0,
        "review": 0,
    }


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
