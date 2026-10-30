"""CLIP 영점 분류로 도표·그림·지도·포스터는 not_photo, 낮·실내 사진은 not_night를 removed_reason에 적는다.
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
# 해 질 녘·노을은 저조도 학습에 쓰려고 남긴다(팀 결정). "밤 / 낮 / 실내"만 두면 해 질 녘이 낮 사진과
# 같은 점수대(0.01~0.17)에 섞여서 기준값으로 가를 수 없었다
NIGHT_KEEP = ["a photo taken at night", "a photo taken at dusk, sunset or twilight", "a low light photo"]
NIGHT_DROP = ["a photo taken in bright daylight", "a photo taken indoors"]
# 2026-10-30 우리 사진 117장을 보고 정했다. 0.4이면 약 19장이 걸리고, 남는 오탐은 밤 보행로(0.06)와
# 해가 떠 있는 역광 노을 거리(0.01), 놓치는 것은 흐린 낮 거리(0.43)다
NIGHT_THRESHOLD = 0.4


@lru_cache(maxsize=None)
def _model():
    # torch·open_clip은 불러오는 데 몇 초 걸려서, 이 단계에 와서야 한 번만 불러온다
    import open_clip
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, _, preprocess = open_clip.create_model_and_transforms(MODEL, pretrained=PRETRAINED, device=device)
    model.eval()
    tokenizer = open_clip.get_tokenizer(MODEL)
    texts = []
    with torch.no_grad():
        for prompts in ([KEEP] + DROP, NIGHT_KEEP + NIGHT_DROP):
            text = model.encode_text(tokenizer(prompts).to(device))
            texts.append(text / text.norm(dim=-1, keepdim=True))
    return model, preprocess, texts, device


def _scores(path):
    """(사진 아님 점수, 밤 점수). 사진 아님은 거를 쪽 네 문장, 밤은 남길 쪽 세 문장의 확률 합(0~1)."""
    import torch
    model, preprocess, (photo_text, night_text), device = _model()
    with Image.open(path) as img:
        x = preprocess(img.convert("RGB")).unsqueeze(0).to(device)
    with torch.no_grad():
        image = model.encode_image(x)
        image /= image.norm(dim=-1, keepdim=True)
        scale = model.logit_scale.exp()
        photo = (scale * image @ photo_text.T).softmax(dim=-1)[0]
        night = (scale * image @ night_text.T).softmax(dim=-1)[0]
    return float(photo[1:].sum()), float(night[:len(NIGHT_KEEP)].sum())


def not_photo_score(path):
    """거를 쪽 문장 네 개의 확률 합(0~1). 높을수록 사진이 아니다."""
    return _scores(path)[0]


def filter_irrelevant(images_dir="data/images", metadata_csv="data/metadata.csv",
                      threshold=NOT_PHOTO_THRESHOLD, night_threshold=NIGHT_THRESHOLD):
    """아직 걸러지지 않은 사진에 not_photo(사진 아님 점수 > threshold) 또는
    not_night(밤 점수 < night_threshold)를 적는다."""
    rows = read_rows(metadata_csv)
    for row in rows:
        path = Path(images_dir) / row["filename"]
        if row["removed_reason"] or not path.exists():
            continue
        not_photo, night = _scores(path)
        if not_photo > threshold:
            row["removed_reason"] = "not_photo"
        elif night < night_threshold:
            row["removed_reason"] = "not_night"
    write_rows(metadata_csv, rows)
    return rows


def _sheet(images_dir, scored, path):
    tiles = [_tile(Path(images_dir) / n, f"{s:.2f}") for s, n in scored]
    tiles += [np.zeros((TILE_H, TILE_W, 3), np.uint8)] * (-len(tiles) % COLS)
    sheet = cv2.vconcat([cv2.hconcat(tiles[i:i + COLS]) for i in range(0, len(tiles), COLS)])
    cv2.imencode(".jpg", sheet)[1].tofile(str(path))


def make_relevance_sheet(images_dir="data/images", metadata_csv="data/metadata.csv",
                         review_dir="data/review", count=30):
    """사진 아님 점수 높은 순, 밤 점수 낮은 순으로 count장씩 격자로 모은다. 기준값을 눈으로 정하는 용도."""
    names = [r["filename"] for r in read_rows(metadata_csv) if not r["removed_reason"]]
    scores = {n: _scores(Path(images_dir) / n) for n in names}
    Path(review_dir).mkdir(parents=True, exist_ok=True)
    not_photo = sorted(((s[0], n) for n, s in scores.items()), reverse=True)[:count]
    night = sorted((s[1], n) for n, s in scores.items())[:count]
    _sheet(images_dir, not_photo, Path(review_dir) / "not_photo_high.jpg")
    _sheet(images_dir, night, Path(review_dir) / "night_low.jpg")
    return scores


if __name__ == "__main__":
    make_relevance_sheet()
