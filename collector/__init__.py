"""도구 1 자동 수집·정리. agent는 run_collector 하나만 부른다."""
from .wikimedia import collect_wikimedia


def run_collector(queries, images_dir="data/images", metadata_csv="data/metadata.csv",
                  count_per_query=10):
    """검색어 목록으로 사진을 모으고, 결과가 저장된 경로를 돌려준다."""
    for query in queries:
        collect_wikimedia(query, count_per_query, images_dir, metadata_csv)
    return {"images_dir": images_dir, "metadata_csv": metadata_csv}
