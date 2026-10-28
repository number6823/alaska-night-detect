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
