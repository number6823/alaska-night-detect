"""metadata.csv 형식(열 10개)과 기록. 모든 출처가 같이 쓴다."""
import csv
from pathlib import Path

FIELDS = ["filename", "source", "source_url", "author", "license",
          "license_url", "query", "brightness", "blur", "removed_reason"]


def append_rows(metadata_csv, rows):
    metadata_csv = Path(metadata_csv)
    write_header = not metadata_csv.exists()
    # utf-8-sig: 엑셀에서 열어도 한글이 깨지지 않게
    with metadata_csv.open("a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def read_rows(metadata_csv):
    with Path(metadata_csv).open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def known_filenames(metadata_csv):
    """이미 기록된 파일 이름. 걸러져 removed/로 옮긴 사진을 다시 받지 않게 한다."""
    if not Path(metadata_csv).exists():
        return set()
    return {r["filename"] for r in read_rows(metadata_csv)}


def write_rows(metadata_csv, rows):
    """점수를 채운 뒤 파일 전체를 다시 쓴다."""
    with Path(metadata_csv).open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
