"""사진의 밝기와 흐림을 재서 metadata.csv에 적고, 기준값이 있으면 못 쓰는 사진에 removed_reason을 적는다."""
from pathlib import Path

import cv2
import numpy as np

from ._metadata import read_rows, write_rows

BLUR_WIDTH = 640  # 사진 크기가 달라도 흐림 점수를 비교할 수 있게 같은 폭으로 맞춘다
TILE_W, TILE_H, COLS = 240, 180, 6


def _read(path, flag=cv2.IMREAD_GRAYSCALE):
    # cv2.imread는 한글 경로를 못 읽어서 imdecode로 읽는다
    return cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), flag)


def _blur(gray):
    h, w = gray.shape
    gray = cv2.resize(gray, (BLUR_WIDTH, round(h * BLUR_WIDTH / w)), interpolation=cv2.INTER_AREA)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def measure_quality(images_dir="data/images", metadata_csv="data/metadata.csv",
                    dark_threshold=None, blur_threshold=None):
    """아직 걸러지지 않은 사진의 밝기·흐림을 기록한다. 기준값이 None이면 점수만 적고 거르지 않는다."""
    rows = read_rows(metadata_csv)
    for row in rows:
        path = Path(images_dir) / row["filename"]
        if row["removed_reason"] or not path.exists():
            continue
        gray = _read(path)
        if gray is None:
            print(f"[읽기 실패] {row['filename']}")
            continue
        row["brightness"] = f"{gray.mean():.1f}"
        if dark_threshold is not None and gray.mean() < dark_threshold:
            row["removed_reason"] = "too_dark"
            continue
        blur = _blur(gray)
        row["blur"] = f"{blur:.1f}"
        if blur_threshold is not None and blur < blur_threshold:
            row["removed_reason"] = "blurry"
    write_rows(metadata_csv, rows)
    return rows


def _tile(path, label):
    img = _read(path, cv2.IMREAD_COLOR)
    scale = min(TILE_W / img.shape[1], TILE_H / img.shape[0])
    img = cv2.resize(img, (int(img.shape[1] * scale), int(img.shape[0] * scale)))
    tile = np.zeros((TILE_H, TILE_W, 3), np.uint8)
    tile[:img.shape[0], :img.shape[1]] = img
    # 어두운 사진 위에서도 보이게 검은 테두리를 먼저 그린다
    for color, thick in (((0, 0, 0), 4), ((0, 255, 255), 1)):
        cv2.putText(tile, label, (5, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, thick)
    return tile


def make_review_sheets(images_dir="data/images", metadata_csv="data/metadata.csv",
                       review_dir="data/review", count=30):
    """점수 낮은 순 count장을 격자로 모은 이미지를 밝기용·흐림용으로 만든다. 기준값을 눈으로 정하는 용도."""
    review_dir = Path(review_dir)
    review_dir.mkdir(parents=True, exist_ok=True)
    rows = [r for r in read_rows(metadata_csv) if not r["removed_reason"]]
    for col in ("brightness", "blur"):
        low = sorted((r for r in rows if r[col]), key=lambda r: float(r[col]))[:count]
        tiles = [_tile(Path(images_dir) / r["filename"], r[col]) for r in low]
        tiles += [np.zeros((TILE_H, TILE_W, 3), np.uint8)] * (-len(tiles) % COLS)
        sheet = cv2.vconcat([cv2.hconcat(tiles[i:i + COLS]) for i in range(0, len(tiles), COLS)])
        cv2.imencode(".jpg", sheet)[1].tofile(str(review_dir / f"{col}_low.jpg"))


if __name__ == "__main__":
    measure_quality()
    make_review_sheets()
