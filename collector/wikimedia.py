"""Wikimedia Commons에서 사진을 받아 data/images/ 에 저장하고 출처를 metadata.csv 에 기록한다."""
import re
from pathlib import Path

from ._http import get
from ._metadata import append_rows

API_URL = "https://commons.wikimedia.org/w/api.php"
# Wikimedia는 연락처가 담긴 User-Agent를 요구한다
HEADERS = {"User-Agent": "alaska-night-detect/0.1 (https://github.com/number6823/alaska-night-detect)"}
ALLOWED_MIME = {"image/jpeg": "jpg", "image/png": "png"}


def _strip_html(text):
    return re.sub(r"<[^>]+>", "", text or "").strip()


def collect_wikimedia(query, count=10,
                      images_dir="data/images", metadata_csv="data/metadata.csv"):
    """query로 검색해 최대 count장을 받고, 새로 받은 사진의 메타데이터 목록을 돌려준다."""
    resp = get(API_URL, headers=HEADERS, params={
        "action": "query", "format": "json",
        "generator": "search", "gsrsearch": f"{query} filetype:bitmap",
        "gsrnamespace": 6, "gsrlimit": count,
        "prop": "imageinfo", "iiprop": "url|extmetadata|mime", "iiurlwidth": 1280,
    })
    pages = resp.json().get("query", {}).get("pages", {})

    images_dir = Path(images_dir)
    images_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for page in pages.values():
        info = page["imageinfo"][0]
        ext = ALLOWED_MIME.get(info["mime"])
        if not ext:
            continue
        filename = f"wikimedia_{page['pageid']}.{ext}"
        path = images_dir / filename
        if path.exists():  # 다시 돌리거나 검색어끼리 겹쳐도 같은 줄이 두 번 쌓이지 않게
            continue
        img = get(info["thumburl"], headers=HEADERS)
        path.write_bytes(img.content)

        meta = info.get("extmetadata", {})
        rows.append({
            "filename": filename,
            "source": "Wikimedia Commons",
            "source_url": info["descriptionurl"],
            "author": _strip_html(meta.get("Artist", {}).get("value")),
            "license": meta.get("LicenseShortName", {}).get("value", ""),
            "license_url": meta.get("LicenseUrl", {}).get("value", ""),
            "query": query,
            "brightness": "",
            "blur": "",
            "removed_reason": "",
        })

    append_rows(metadata_csv, rows)
    return rows


if __name__ == "__main__":
    saved = collect_wikimedia("night bicycle")
    print(f"새로 받은 사진: {len(saved)}장")
