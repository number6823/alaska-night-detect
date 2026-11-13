"""밝은 사진을 어둡게 만든 사본을 더해 야간 학습 데이터를 늘린다.

실행: python -m training.darken --images data/dataset/images/train --labels data/dataset/labels/train
     (기본값은 같은 폴더에 `_dark` 사본을 더한다. 장수가 두 배가 된다)

왜 하나: 수집 사진(Wikimedia)은 야간이라고 해도 가로등이 많아 꽤 밝다. 실제 후방 카메라
프레임(R6_04 골목)보다 훨씬 밝아서, 밝은 사진으로만 배우면 진짜 어두운 장면에서 놓친다.
사진을 더 찍는 게 제일 낫지만, 가진 사진을 어둡게 만들어 보태는 것도 공짜로 해 볼 수 있다.

어떻게 어둡게 하나 (한 장에 세 가지를 같이 건다)
1. 노출 낮추기: 화소값에 factor(기본 0.5)를 곱한다
2. 감마 낮추기: (v/255)**(1/gamma), gamma < 1 이면 어두운 쪽이 더 눌린다
3. 노이즈: 어두운 사진은 센서 노이즈가 늘어난다. 밝기만 낮추면 너무 깨끗해서 진짜 야간과 다르다

박스 위치는 그대로라 라벨은 그냥 복사한다.

주의: **train 폴더에만 쓴다.** val 폴더에 넣으면 같은 사진이 원본·사본으로 양쪽에 들어가
점수가 좋아 보인다. 폴더 이름이 val 이면 멈춘다.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}


def darken(img: np.ndarray, factor: float = 0.5, gamma: float = 0.7, noise: float = 3.0,
           seed: int | None = None) -> np.ndarray:
    """사진 한 장을 어둡게 만든다. factor 가 작을수록, gamma 가 작을수록 어두워진다."""
    if not 0 < factor <= 1:
        raise ValueError(f"factor 는 0보다 크고 1 이하다: {factor}")
    if gamma <= 0:
        raise ValueError(f"gamma 는 0보다 커야 한다: {gamma}")
    table = np.array([np.clip(((i / 255.0) ** (1.0 / gamma)) * 255 * factor, 0, 255)
                      for i in range(256)], dtype=np.uint8)
    out = cv2.LUT(img, table)
    if noise > 0:
        rng = np.random.default_rng(seed)
        out = np.clip(out.astype(np.int16) + rng.normal(0, noise, out.shape), 0, 255).astype(np.uint8)
    return out


def mean_brightness(img: np.ndarray) -> float:
    return float(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).mean())


def darken_dir(images: str | Path, labels: str | Path | None = None, factor: float = 0.5,
               gamma: float = 0.7, noise: float = 3.0, suffix: str = "_dark",
               out_images: str | Path | None = None, out_labels: str | Path | None = None,
               min_brightness: float = 0.0, seed: int = 0) -> dict:
    """폴더 안 사진마다 어두운 사본을 하나씩 만든다.

    - out_images 를 주지 않으면 같은 폴더에 더한다(장수가 두 배).
    - min_brightness 를 주면 그보다 밝은 사진만 어둡게 한다. 이미 깜깜한 프레임까지
      더 어둡게 만들면 사람이 아예 안 보이는 사진이 라벨만 달고 들어간다.
    - 이미 suffix 가 붙은 파일은 건너뛴다(두 번 돌려도 네 배가 되지 않게).
    """
    images = Path(images)
    if images.name == "val":
        raise ValueError("val 폴더에는 쓰지 않는다. 같은 사진이 원본·사본으로 들어가면 점수가 좋아 보인다")
    out_images = Path(out_images or images)
    out_images.mkdir(parents=True, exist_ok=True)
    labels = Path(labels) if labels else None
    out_labels = Path(out_labels or labels) if labels else None
    if out_labels:
        out_labels.mkdir(parents=True, exist_ok=True)

    made = skipped_bright = skipped_suffix = no_label = 0
    before = after = 0.0
    for i, p in enumerate(sorted(images.iterdir())):
        if p.suffix.lower() not in IMAGE_EXTS:
            continue
        if p.stem.endswith(suffix):
            skipped_suffix += 1
            continue
        img = cv2.imread(str(p))
        if img is None:
            continue
        b = mean_brightness(img)
        if b < min_brightness:
            skipped_bright += 1
            continue
        # 사진마다 다른 노이즈를 주되 다시 돌리면 같게 나오도록 seed 를 섞는다
        out = darken(img, factor, gamma, noise, seed=seed + i)
        cv2.imwrite(str(out_images / f"{p.stem}{suffix}{p.suffix}"), out)
        before += b
        after += mean_brightness(out)
        made += 1
        if labels:
            txt = labels / f"{p.stem}.txt"
            if txt.exists():
                (out_labels / f"{p.stem}{suffix}.txt").write_text(
                    txt.read_text(encoding="utf-8"), encoding="utf-8")
            else:
                no_label += 1
    return {"made": made, "skipped_already_dark": skipped_suffix,
            "skipped_too_dark": skipped_bright, "missing_label": no_label,
            "factor": factor, "gamma": gamma, "noise": noise, "suffix": suffix,
            "mean_brightness_before": round(before / made, 2) if made else 0.0,
            "mean_brightness_after": round(after / made, 2) if made else 0.0}


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m training.darken")
    parser.add_argument("--images", default="data/dataset/images/train", help="어둡게 할 사진 폴더(train)")
    parser.add_argument("--labels", default="data/dataset/labels/train", help="같이 복사할 라벨 폴더")
    parser.add_argument("--factor", type=float, default=0.5, help="노출 배수. 작을수록 어둡다")
    parser.add_argument("--gamma", type=float, default=0.7, help="1보다 작으면 어두운 쪽이 더 눌린다")
    parser.add_argument("--noise", type=float, default=3.0, help="더할 노이즈 세기(0이면 안 넣는다)")
    parser.add_argument("--suffix", default="_dark", help="사본 이름 꼬리표")
    parser.add_argument("--out-images", default=None, help="사본을 쓸 폴더 (기본: 같은 폴더)")
    parser.add_argument("--out-labels", default=None, help="사본 라벨을 쓸 폴더 (기본: 같은 폴더)")
    parser.add_argument("--min-brightness", type=float, default=0.0,
                        help="이보다 밝은 사진만 어둡게 한다. 이미 깜깜한 프레임을 또 누르지 않으려고")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    r = darken_dir(args.images, args.labels, args.factor, args.gamma, args.noise, args.suffix,
                   args.out_images, args.out_labels, args.min_brightness, args.seed)
    print(json.dumps(r, ensure_ascii=False))
    print(f"[확인] 평균 밝기 {r['mean_brightness_before']} → {r['mean_brightness_after']}")


if __name__ == "__main__":
    main()
