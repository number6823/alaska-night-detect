"""CLIP 영점 분류로 도표·그림·지도·포스터를 찾아 removed_reason에 not_photo를 적는다.
사람·자전거가 없는 사진은 여기서 거르지 않는다. 도구 2가 YOLO로 폐기해서 YOLO를 두 번 돌리지 않는다."""
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from ._metadata import read_rows, write_rows
from .quality import COLS, TILE_H, TILE_W, _tile

MODEL, PRETRAINED = "ViT-B-32", "laion2b_s34b_b79k"
# "a photo taken outdoors at night"로 했더니 낮·실내의 진짜 사진 15장이 걸렸다. 밤인지가 아니라 사진인지만 묻는다
KEEP = "a photograph of a real scene"
DROP = ["a chart or diagram", "a drawing, painting or illustration", "a map", "a poster or text graphic"]
# 2026-10-30 우리 사진 117장과 Wikimedia의 지도·도표·그림·포스터 26장을 보고 정했다.
# 0.8이면 우리 사진은 3장(포스터 2, 밤 보행자 버튼 사진 1)이 걸리고 거를 사진은 23장을 잡는다
NOT_PHOTO_THRESHOLD = 0.8


@lru_cache(maxsize=None)
def _model():
    # torch·open_clip은 불러오는 데 몇 초 걸려서, 이 단계에 와서야 한 번만 불러온다
    import open_clip
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, _, preprocess = open_clip.create_model_and_transforms(MODEL, pretrained=PRETRAINED, device=device)
    model.eval()
    with torch.no_grad():
        text = model.encode_text(open_clip.get_tokenizer(MODEL)([KEEP] + DROP).to(device))
        text /= text.norm(dim=-1, keepdim=True)
    return model, preprocess, text, device


def not_photo_score(path):
    """거를 쪽 문장 네 개의 확률 합(0~1). 높을수록 사진이 아니다."""
    import torch
    model, preprocess, text, device = _model()
    with Image.open(path) as img:
        x = preprocess(img.convert("RGB")).unsqueeze(0).to(device)
    with torch.no_grad():
        image = model.encode_image(x)
        image /= image.norm(dim=-1, keepdim=True)
        probs = (model.logit_scale.exp() * image @ text.T).softmax(dim=-1)[0]
    return float(probs[1:].sum())


def filter_irrelevant(images_dir="data/images", metadata_csv="data/metadata.csv",
                      threshold=NOT_PHOTO_THRESHOLD):
    """아직 걸러지지 않은 사진 중 점수가 threshold보다 높은 사진에 not_photo를 적는다."""
    rows = read_rows(metadata_csv)
    for row in rows:
        path = Path(images_dir) / row["filename"]
        if row["removed_reason"] or not path.exists():
            continue
        if not_photo_score(path) > threshold:
            row["removed_reason"] = "not_photo"
    write_rows(metadata_csv, rows)
    return rows


def make_relevance_sheet(images_dir="data/images", metadata_csv="data/metadata.csv",
                         review_dir="data/review", count=30):
    """점수 높은 순 count장을 격자로 모은다. 기준값을 눈으로 정하는 용도."""
    names = [r["filename"] for r in read_rows(metadata_csv) if not r["removed_reason"]]
    scored = sorted(((not_photo_score(Path(images_dir) / n), n) for n in names), reverse=True)
    tiles = [_tile(Path(images_dir) / n, f"{s:.2f}") for s, n in scored[:count]]
    tiles += [np.zeros((TILE_H, TILE_W, 3), np.uint8)] * (-len(tiles) % COLS)
    sheet = cv2.vconcat([cv2.hconcat(tiles[i:i + COLS]) for i in range(0, len(tiles), COLS)])
    Path(review_dir).mkdir(parents=True, exist_ok=True)
    cv2.imencode(".jpg", sheet)[1].tofile(str(Path(review_dir) / "not_photo_high.jpg"))
    return scored


if __name__ == "__main__":
    make_relevance_sheet()
