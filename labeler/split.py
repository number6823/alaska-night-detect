"""검수를 마친 라벨을 학습용(train)과 검증용(val)으로 나누고 Ultralytics data.yaml을 만든다.

실행: python -m labeler.split [--images data/images] [--labels data/labels] [--out data/dataset]
                             [--val-ratio 0.2] [--seed 0] [--group-by round] [--exclude-rounds R5] [--portable]
- 라벨 txt가 있는 사진만 쓴다. 폐기된 사진(txt 없음)은 넣지 않는다.
- gt100은 평가 전용이라 여기에 넣지 않는다.
- 빈 txt 가 있는 사진은 배경(물체 없음)으로 학습에 들어간다. --max-background-ratio 로 비율을 제한한다.
- 후방 영상 프레임은 같은 영상이 train과 val에 섞이면 val 점수가 올라가 보인다.
  `--group-by round`를 주면 사진 한 장씩이 아니라 라운드 단위로 나눈다.
"""
import argparse
import json
import random
import re
import shutil
from pathlib import Path

from .autolabel import IMAGE_EXTS

NAMES = {0: "person", 1: "bicycle"}
# 촬영 파일명 예: 20261112_R1_01_보행접근.mp4 -> 프레임 이름 안의 _R1_ 을 라운드로 본다
ROUND_RE = re.compile(r"_(R\d+)_", re.IGNORECASE)


def round_of(stem: str) -> str | None:
    """파일 이름에서 라운드(R1, R2...)를 꺼낸다. 없으면 None (수집 사진 등)."""
    m = ROUND_RE.search(stem)
    return m.group(1).upper() if m else None


def split_dataset(images_dir: str | Path = "data/images", labels_dir: str | Path = "data/labels",
                  out_dir: str | Path = "data/dataset", val_ratio: float = 0.2, seed: int = 0,
                  group_by: str | None = None, exclude_rounds: tuple[str, ...] = ("R5",),
                  portable: bool = False, max_background_ratio: float = 0.1) -> dict:
    images_dir, labels_dir, out_dir = Path(images_dir), Path(labels_dir), Path(out_dir)
    if group_by not in (None, "round"):
        raise ValueError(f"group_by는 None이나 'round'만 된다: {group_by!r}")
    if out_dir.exists():
        # 지난 결과와 섞이지 않게 한다. 다시 나누려면 폴더를 직접 지운다
        raise FileExistsError(f"{out_dir} 가 이미 있다. 지우고 다시 실행한다")

    excluded = {r.upper(): 0 for r in exclude_rounds}
    pairs = []
    for img in sorted(p for p in images_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS):
        txt = labels_dir / f"{img.stem}.txt"
        if not txt.exists():
            continue
        rnd = round_of(img.stem)
        # 평가 전용 라운드는 group_by와 상관없이 뺀다. 학습에 섞이면 평가가 못 쓰게 된다
        if rnd in excluded:
            excluded[rnd] += 1
            continue
        pairs.append((img, txt, rnd))

    # 빈 txt = 배경 사진(물체 없음). 너무 많으면 모델이 "아무것도 없다"에 치우치므로 상한을 둔다.
    # 팀 규칙(2026-11-13): 진짜 아무도 없는 프레임만 빈 라벨로 두므로 빈 txt 는 전부 배경이다.
    labeled = [p for p in pairs if p[1].stat().st_size > 0]
    backgrounds = [p for p in pairs if p[1].stat().st_size == 0]
    dropped_background = 0
    if backgrounds:
        r = max(0.0, min(1.0, max_background_ratio))
        # 최종 세트에서 배경이 r 을 넘지 않게: keep / (labeled + keep) <= r
        allowed = len(labeled) * r / (1 - r) if r < 1 else len(backgrounds)
        keep = min(len(backgrounds), int(allowed))
        if keep < len(backgrounds):
            random.Random(seed).shuffle(backgrounds)
            dropped_background = len(backgrounds) - keep
            backgrounds = backgrounds[:keep]
        pairs = labeled + backgrounds
        pairs.sort(key=lambda p: p[0].name)  # seed 를 쓰기 전에 순서를 되돌려 재현되게 한다

    if group_by == "round":
        # 라운드가 없는 사진(수집 사진)은 한 장이 한 묶음이라 전과 같게 나뉜다
        groups: dict[str, list] = {}
        for img, txt, rnd in pairs:
            groups.setdefault(rnd or f"single:{img.stem}", []).append((img, txt))
        keys = sorted(groups)
        random.Random(seed).shuffle(keys)
        n_val = round(len(keys) * val_ratio)
        # 라운드가 적을 때 val이 비면 학습이 안 돌아간다
        if n_val == 0 and len(keys) >= 2:
            n_val = 1
        chosen = {"val": keys[:n_val], "train": keys[n_val:]}
        parts = {part: [item for k in ks for item in groups[k]] for part, ks in chosen.items()}
    else:
        items = [(img, txt) for img, txt, _ in pairs]
        random.Random(seed).shuffle(items)
        n_val = round(len(items) * val_ratio)
        chosen = None
        parts = {"val": items[:n_val], "train": items[n_val:]}

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
    # portable이면 path 줄을 뺀다. Ultralytics는 path가 없으면 data.yaml이 있는 폴더를 기준으로 삼으므로
    # (ultralytics/data/utils.py: path = data.get("path") or Path(yaml_file).parent)
    # 폴더째 Colab이나 다른 PC로 옮겨도 그대로 돌아간다.
    head = "" if portable else f"path: {out_dir.resolve().as_posix()}\n"
    yaml_path.write_text(
        f"{head}train: images/train\nval: images/val\nnames:\n{names}\n",
        encoding="utf-8",
    )
    result = {
        "data_yaml": str(yaml_path),
        "train": len(parts["train"]),
        "val": len(parts["val"]),
        "boxes": boxes,
        "group_by": group_by,
        "excluded_rounds": {r: n for r, n in excluded.items() if n},
        "background": len(backgrounds),
        "background_dropped": dropped_background,
        "background_ratio": round(len(backgrounds) / len(pairs), 4) if pairs else 0.0,
    }
    if chosen is not None:
        # 어느 라운드가 val로 갔는지 남겨야 나중에 같은 분할인지 확인할 수 있다
        result["groups"] = {"train": sorted(chosen["train"]), "val": sorted(chosen["val"])}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m labeler.split")
    parser.add_argument("--images", default="data/images", help="사진 폴더")
    parser.add_argument("--labels", default="data/labels", help="검수를 마친 YOLO .txt 폴더")
    parser.add_argument("--out", default="data/dataset", help="나눈 결과 폴더 (없어야 함)")
    parser.add_argument("--val-ratio", type=float, default=0.2, help="검증용 비율")
    parser.add_argument("--seed", type=int, default=0, help="섞는 순서 고정값")
    parser.add_argument("--group-by", choices=["round"], default=None,
                        help="round면 사진 한 장씩이 아니라 라운드(파일 이름의 _R1_) 단위로 나눈다")
    parser.add_argument("--exclude-rounds", nargs="*", default=["R5"], metavar="R5",
                        help="아예 빼는 평가 전용 라운드. 빼지 않으려면 값 없이 --exclude-rounds")
    parser.add_argument("--portable", action="store_true",
                        help="data.yaml에 절대 경로를 넣지 않는다. 폴더째 Colab 등으로 옮겨 쓸 때")
    parser.add_argument("--max-background-ratio", type=float, default=0.1,
                        help="빈 라벨(배경) 사진이 전체에서 차지할 상한. 넘으면 무작위로 덜어낸다")
    args = parser.parse_args()
    print(json.dumps(split_dataset(args.images, args.labels, args.out, args.val_ratio, args.seed,
                                   args.group_by, tuple(args.exclude_rounds), args.portable,
                                   args.max_background_ratio),
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
