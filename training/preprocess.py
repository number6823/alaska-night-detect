"""감지 전에 어두운 사진을 밝혀 본다(감마, CLAHE).

실행: python -m training.preprocess <입력 폴더> <출력 폴더> --method gamma --gamma 1.5
      python -m training.preprocess <입력 폴더> <출력 폴더> --method clahe --clip 2.0 --grid 8

젯슨에서 카메라 프레임을 모델에 넣기 전에 부를 수 있게 함수로 만든다.
`enhance(img, method=...)` 하나만 쓰면 된다.

- 감마: 화소값을 (v/255)**(1/gamma) 로 펴서 어두운 쪽을 들어 올린다. gamma > 1 이면 밝아진다.
  곱셈이 아니라 지수라서, 이미 밝은 가로등은 덜 타고 어두운 사람 쪽이 더 올라간다.
- CLAHE: 사진을 작은 칸으로 나눠 칸마다 명암 분포를 고르게 편다(대비 제한 적응 히스토그램 평활).
  밝기(L) 채널에만 걸어서 색이 변하지 않게 한다. 가로등 주변만 밝고 나머지는 깜깜한 야간 사진에 쓴다.
- 노이즈까지 같이 커진다. 어두운 사진은 원래 노이즈가 많아서, 밝혀도 좋아진다는 보장이 없다.
  실제로 gt100(수집 사진)에서는 차이가 ±0.01 이내였다. 후방 영상처럼 더 어두운 데서 다시 재 본다.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from .image_io import read_image, write_image

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
METHODS = ("gamma", "clahe", "both")


def apply_gamma(img: np.ndarray, gamma: float = 1.5) -> np.ndarray:
    """감마 보정. gamma > 1 이면 어두운 쪽이 밝아진다. 1.0 이면 그대로."""
    if gamma <= 0:
        raise ValueError(f"gamma 는 0보다 커야 한다: {gamma}")
    # 화소값 256개의 답을 미리 만들어 두고 찾아 쓴다(한 장마다 거듭제곱을 다시 하지 않게)
    table = np.array([((i / 255.0) ** (1.0 / gamma)) * 255 for i in range(256)], dtype=np.uint8)
    return cv2.LUT(img, table)


def apply_clahe(img: np.ndarray, clip: float = 2.0, grid: int = 8) -> np.ndarray:
    """LAB 의 L(밝기) 채널에만 CLAHE 를 건다. 색은 그대로 둔다."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = cv2.createCLAHE(clipLimit=clip, tileGridSize=(grid, grid)).apply(l)
    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


def enhance(img: np.ndarray, method: str = "gamma", gamma: float = 1.5,
            clip: float = 2.0, grid: int = 8) -> np.ndarray:
    """젯슨에서 프레임 하나를 밝힐 때 부르는 함수. method 는 gamma / clahe / both."""
    if method == "gamma":
        return apply_gamma(img, gamma)
    if method == "clahe":
        return apply_clahe(img, clip, grid)
    if method == "both":
        return apply_clahe(apply_gamma(img, gamma), clip, grid)
    raise ValueError(f"method 는 {METHODS} 중 하나다: {method!r}")


def mean_brightness(img: np.ndarray) -> float:
    """평균 밝기(0~255). 보정 전후를 숫자로 보려고 쓴다."""
    return float(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).mean())


def preprocess_dir(src: str | Path, dst: str | Path, method: str = "gamma", gamma: float = 1.5,
                   clip: float = 2.0, grid: int = 8, labels_src: str | Path | None = None,
                   labels_dst: str | Path | None = None) -> dict:
    """폴더 하나를 통째로 보정해 다른 폴더에 쓴다. 파일 이름은 그대로 둔다.

    보정은 화소만 건드리고 박스 위치는 그대로라, 라벨은 그냥 복사하면 된다.
    labels_src 를 주면 같은 이름의 txt 를 labels_dst 로 복사한다(학습/평가에 바로 쓰려고).
    못 읽은 사진은 조용히 넘기지 않고 세어서 `skipped_unreadable` 로 돌려준다.
    """
    src, dst = Path(src), Path(dst)
    dst.mkdir(parents=True, exist_ok=True)
    if labels_src:
        labels_src = Path(labels_src)
        labels_dst = Path(labels_dst or (dst.parent / "labels"))
        labels_dst.mkdir(parents=True, exist_ok=True)

    n = copied = 0
    unreadable: list[str] = []
    before = after = 0.0
    for p in sorted(src.iterdir()):
        if p.suffix.lower() not in IMAGE_EXTS:
            continue
        img = read_image(p)
        if img is None:
            # 한 장이라도 빠지면 보정본과 원본의 장수가 달라져 평가가 어긋난다
            unreadable.append(p.name)
            continue
        out = enhance(img, method, gamma, clip, grid)
        write_image(dst / p.name, out)
        before += mean_brightness(img)
        after += mean_brightness(out)
        n += 1
        if labels_src:
            txt = labels_src / f"{p.stem}.txt"
            if txt.exists():
                (labels_dst / txt.name).write_text(txt.read_text(encoding="utf-8"), encoding="utf-8")
                copied += 1
    return {"images": n, "labels_copied": copied,
            "skipped_unreadable": len(unreadable), "unreadable": unreadable[:5], "method": method,
            "gamma": gamma, "clip": clip, "grid": grid,
            "mean_brightness_before": round(before / n, 2) if n else 0.0,
            "mean_brightness_after": round(after / n, 2) if n else 0.0}


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m training.preprocess")
    parser.add_argument("src", help="원본 사진 폴더")
    parser.add_argument("dst", help="보정한 사진을 쓸 폴더")
    parser.add_argument("--method", choices=list(METHODS), default="gamma")
    parser.add_argument("--gamma", type=float, default=1.5, help="1보다 크면 밝아진다")
    parser.add_argument("--clip", type=float, default=2.0, help="CLAHE 대비 제한. 크면 더 세게 편다")
    parser.add_argument("--grid", type=int, default=8, help="CLAHE 칸 수(가로·세로)")
    parser.add_argument("--labels", default=None, help="같이 복사할 라벨 폴더")
    parser.add_argument("--labels-out", default=None, help="라벨을 쓸 폴더 (기본: dst 옆 labels)")
    args = parser.parse_args()
    r = preprocess_dir(args.src, args.dst, args.method, args.gamma, args.clip,
                       args.grid, args.labels, args.labels_out)
    print(json.dumps(r, ensure_ascii=False))
    if r["skipped_unreadable"]:
        print(f"[확인] 못 읽어서 빠진 사진 {r['skipped_unreadable']}장: {r['unreadable']}")


if __name__ == "__main__":
    main()
