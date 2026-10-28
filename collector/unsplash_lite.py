"""미리 내려받은 Unsplash Lite 데이터셋에서 사진을 골라 data/images/ 에 저장하고 출처를 metadata.csv 에 기록한다.
약관(3.A)상 이 사진과 메타데이터는 data/ 밖으로 내보내지 않는다(레포·슬라이드·시연 영상 금지)."""
import csv
import re
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from ._http import get
from ._metadata import append_rows

SOURCE = "Unsplash Lite Dataset"
LICENSE = "Unsplash Dataset Terms (Lite, 비공개)"
LICENSE_URL = "https://github.com/unsplash/datasets/blob/master/TERMS.md"
MIN_CONFIDENCE = 50  # 확신도가 낮은 AI 키워드에는 관계없는 사진이 많이 섞여 있었다


def _confidence(value, scale):
    try:
        return float(value) * scale
    except ValueError:
        return 0.0


@lru_cache(maxsize=None)
def _load(dataset_dir):
    """사진 목록과 사진별 검색 단어를 읽는다. 파일이 커서 한 번만 읽는다."""
    csv.field_size_limit(10**8)
    words = defaultdict(set)
    with open(Path(dataset_dir) / "keywords.tsv000", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            # 확신도 열 두 개는 단위가 다르다(0~100, 0~1)
            conf = max(_confidence(r["ai_service_1_confidence"], 1),
                       _confidence(r["ai_service_2_confidence"], 100))
            if r["suggested_by_user"] == "t" or conf >= MIN_CONFIDENCE:
                words[r["photo_id"]].update(re.findall(r"[a-z]+", (r["keyword"] or "").lower()))
    photos = []
    with open(Path(dataset_dir) / "photos.tsv000", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            text = f"{r['photo_description']} {r['ai_description']}".lower()
            words[r["photo_id"]].update(re.findall(r"[a-z]+", text))
            photos.append(r)
    return photos, words


def collect_unsplash_lite(query, count=10, images_dir="data/images",
                          metadata_csv="data/metadata.csv", dataset_dir="data/unsplash_lite"):
    """query의 단어가 모두 키워드나 설명에 있는 사진을 최대 count장 새로 받고, 그 메타데이터 목록을 돌려준다."""
    photos, words = _load(str(dataset_dir))
    need = set(query.lower().split())
    images_dir = Path(images_dir)
    images_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for photo in photos:
        if len(rows) >= count:
            break
        if not need <= words[photo["photo_id"]]:
            continue
        filename = f"unsplash_{photo['photo_id']}.jpg"
        path = images_dir / filename
        if path.exists():
            continue
        img = get(photo["photo_image_url"], params={"w": 1280, "fm": "jpg"})
        path.write_bytes(img.content)
        name = f"{photo['photographer_first_name']} {photo['photographer_last_name']}".strip()
        rows.append({
            "filename": filename,
            "source": SOURCE,
            "source_url": photo["photo_url"],
            "author": name or photo["photographer_username"],
            "license": LICENSE,
            "license_url": LICENSE_URL,
            "query": query,
            "brightness": "",
            "blur": "",
            "removed_reason": "",
        })

    append_rows(metadata_csv, rows)
    return rows
