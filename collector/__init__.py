"""도구 1 자동 수집·정리. agent는 run_collector 하나만 부른다."""
from pathlib import Path

import requests

from ._metadata import read_rows
from .dedup import find_duplicates
from .quality import measure_quality
from .relevance import filter_irrelevant
from .unsplash_lite import collect_unsplash_lite
from .wikimedia import collect_wikimedia

# 오프라인인 Unsplash Lite를 뒤에 둬서, Wikimedia가 실패하면 그 몫까지 받게 한다
SOURCES = [("wikimedia", collect_wikimedia), ("unsplash_lite", collect_unsplash_lite)]


def _move_removed(images_dir, metadata_csv):
    """걸러진 사진을 images_dir 옆 removed/로 옮긴다. labeler가 images_dir를 통째로 읽기 때문이다."""
    removed_dir = Path(images_dir).parent / "removed"
    for row in read_rows(metadata_csv):
        path = Path(images_dir) / row["filename"]
        if row["removed_reason"] and path.exists():
            removed_dir.mkdir(parents=True, exist_ok=True)
            path.replace(removed_dir / row["filename"])


def run_collector(queries, images_dir="data/images", metadata_csv="data/metadata.csv",
                  count_per_query=10):
    """검색어 목록으로 사진을 모으고, 저장 경로와 건너뛴 출처를 돌려준다."""
    skipped = []
    for query in queries:
        alive = [(name, collect) for name, collect in SOURCES if name not in skipped]
        remaining = count_per_query
        for i, (name, collect) in enumerate(alive):
            share = -(-remaining // (len(alive) - i))  # 남은 장수를 남은 출처끼리 나눔(올림)
            try:
                collect(query, share, images_dir, metadata_csv)
                remaining -= share
            except (requests.RequestException, OSError) as e:
                print(f"[건너뜀] {name}: {e}")
                skipped.append(name)
    if Path(metadata_csv).exists():  # 모든 출처가 처음부터 실패하면 파일이 없다
        measure_quality(images_dir, metadata_csv)
        find_duplicates(images_dir, metadata_csv)
        filter_irrelevant(images_dir, metadata_csv)
        _move_removed(images_dir, metadata_csv)
    return {"images_dir": images_dir, "metadata_csv": metadata_csv, "skipped": skipped}
