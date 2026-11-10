"""검수를 마친 라벨을 학습용(train)과 검증용(val)으로 나누고 Ultralytics data.yaml을 만든다.

실행: python -m labeler.split [--images data/images] [--labels data/labels] [--out data/dataset] [--val-ratio 0.2] [--seed 0]
- 라벨 txt가 있는 사진만 쓴다. 폐기된 사진(txt 없음)은 넣지 않는다.
- gt100은 평가 전용이라 여기에 넣지 않는다.
"""
import argparse
import json
import random
import shutil
from pathlib import Path

from .autolabel import IMAGE_EXTS

NAMES = {0: "person", 1: "bicycle"}


def split_dataset(images_dir: str | Path = "data/images", labels_dir: str | Path = "data/labels",
                  out_dir: str | Path = "data/dataset", val_ratio: float = 0.2, seed: int = 0) -> dict:
    images_dir, labels_dir, out_dir = Path(images_dir), Path(labels_dir), Path(out_dir)
    if out_dir.exists():
        # 지난 결과와 섞이지 않게 한다. 다시 나누려면 폴더를 직접 지운다
        raise FileExistsError(f"{out_dir} 가 이미 있다. 지우고 다시 실행한다")

    pairs = []
    for img in sorted(p for p in images_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS):
        txt = labels_dir / f"{img.stem}.txt"
        if txt.exists():
            pairs.append((img, txt))

    random.Random(seed).shuffle(pairs)
    n_val = round(len(pairs) * val_ratio)
    parts = {"val": pairs[:n_val], "train": pairs[n_val:]}

    boxes = {}
    for part, items in parts.items():
        (out_dir / "images" / part).mkdir(parents=True)
        (out_dir / "labels" / part).mkdir(parents=True)
        count = {name: 0 for name in NAMES.values()}
        for img, txt in items:
            shutil.copy2(img, out_dir / "images" / part / img.name)
            shutil.copy2(txt, out_dir / "labels" / part / txt.name)
            for line in txt.read_text().splitlines():
                if line.strip():
                    count[NAMES[int(line.split()[0])]] += 1
        boxes[part] = count

    yaml_path = out_dir / "data.yaml"
    names = "\n".join(f"  {k}: {v}" for k, v in NAMES.items())
    yaml_path.write_text(
        f"path: {out_dir.resolve().as_posix()}\ntrain: images/train\nval: images/val\nnames:\n{names}\n",
        encoding="utf-8",
    )
    return {
        "data_yaml": str(yaml_path),
        "train": len(parts["train"]),
        "val": len(parts["val"]),
        "boxes": boxes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m labeler.split")
    parser.add_argument("--images", default="data/images", help="사진 폴더")
    parser.add_argument("--labels", default="data/labels", help="검수를 마친 YOLO .txt 폴더")
    parser.add_argument("--out", default="data/dataset", help="나눈 결과 폴더 (없어야 함)")
    parser.add_argument("--val-ratio", type=float, default=0.2, help="검증용 비율")
    parser.add_argument("--seed", type=int, default=0, help="섞는 순서 고정값")
    args = parser.parse_args()
    print(json.dumps(split_dataset(args.images, args.labels, args.out, args.val_ratio, args.seed), ensure_ascii=False))


if __name__ == "__main__":
    main()
