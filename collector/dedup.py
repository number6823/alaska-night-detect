"""같은 사진을 찾아 removed_reason에 적는다. 파일이 똑같으면 duplicate, pHash·dHash가 모두 가까우면 near_duplicate.
품질 단계 뒤에 부른다. 새까만 사진끼리는 해시가 비슷해져 중복으로 잘못 잡히기 때문이다."""
import hashlib
import itertools
from pathlib import Path

import cv2
import imagehash
from PIL import Image

from ._metadata import read_rows, write_rows
from .quality import _tile

# 2026-10-30 우리 사진 117장(6,786쌍)을 보고 정했다. 실제 중복은 같은 포스터 두 판(14) 한 쌍뿐이고
# 다른 사진끼리는 17부터 나왔다
DUP_THRESHOLD = 10
REVIEW_THRESHOLD = 16


def _hashes(path):
    with Image.open(path) as img:
        return imagehash.phash(img), imagehash.dhash(img)


def _distance(a, b):
    # 두 거리가 모두 기준 이하여야 중복이므로 큰 쪽만 보면 된다
    return max(a[0] - b[0], a[1] - b[1])


def find_duplicates(images_dir="data/images", metadata_csv="data/metadata.csv",
                    dup_threshold=DUP_THRESHOLD):
    """먼저 받은 사진을 남기고, 뒤에 받은 중복 사진에 사유를 적는다."""
    rows = read_rows(metadata_csv)
    seen_md5, kept = set(), []
    for row in rows:
        path = Path(images_dir) / row["filename"]
        if row["removed_reason"] or not path.exists():
            continue
        md5 = hashlib.md5(path.read_bytes()).hexdigest()
        if md5 in seen_md5:
            row["removed_reason"] = "duplicate"
            continue
        try:
            h = _hashes(path)
        except OSError:  # OpenCV는 읽었지만 PIL은 못 읽는 파일이 있을 수 있다
            row["removed_reason"] = "unreadable"
            continue
        if any(_distance(h, k) <= dup_threshold for k in kept):
            row["removed_reason"] = "near_duplicate"
            continue
        seen_md5.add(md5)
        kept.append(h)
    write_rows(metadata_csv, rows)
    return rows


def make_duplicate_sheet(images_dir="data/images", metadata_csv="data/metadata.csv",
                         review_dir="data/review", low=DUP_THRESHOLD, high=REVIEW_THRESHOLD):
    """중복 기준보다 멀고 high 이하인 쌍을 나란히 모은다. 사람이 보고 기준값을 다시 정하는 용도."""
    names = [r["filename"] for r in read_rows(metadata_csv) if not r["removed_reason"]]
    hashes = {n: _hashes(Path(images_dir) / n) for n in names}
    pairs = sorted((_distance(hashes[a], hashes[b]), a, b) for a, b in itertools.combinations(names, 2))
    pairs = [p for p in pairs if low < p[0] <= high]
    if not pairs:
        print("확인할 쌍 없음")
        return pairs
    sheet = cv2.vconcat([cv2.hconcat([_tile(Path(images_dir) / a, str(d)), _tile(Path(images_dir) / b, str(d))])
                         for d, a, b in pairs])
    Path(review_dir).mkdir(parents=True, exist_ok=True)
    cv2.imencode(".jpg", sheet)[1].tofile(str(Path(review_dir) / "duplicate_pairs.jpg"))
    return pairs


if __name__ == "__main__":
    find_duplicates()
    print(f"사람 확인할 쌍: {len(make_duplicate_sheet())}")
