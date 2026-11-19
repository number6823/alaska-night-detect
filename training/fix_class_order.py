"""Roboflow YOLOv8 export 의 클래스 번호를 우리 규칙(person=0, bicycle=1)으로 맞춘다. 폴더를 제자리에서 고친다.

실행: python -m training.fix_class_order <export 폴더>

- Roboflow 는 클래스를 알파벳 순으로 내보내서 `[bicycle, person]` 이 되기 쉽다. 그대로 학습하면
  사람과 자전거가 통째로 뒤바뀐다. data.yaml 의 names 순서를 읽어서 바꾼다(순서를 가정하지 않는다).
- train/valid/test 의 모든 라벨 txt 첫 숫자를 바꾸고, data.yaml 을 다시 쓴다.
  data.yaml 의 train/val/test 는 이 폴더 기준 상대 경로(`train/images` ...)로 고쳐 쓴다.
  Roboflow 가 쓴 `../train/images` 는 어디서 열어도 어긋나기 쉽다. `path` 는 넣지 않으므로 폴더째 옮겨도 된다.
- 이미 person=0, bicycle=1 이면 라벨은 건드리지 않는다(여러 번 실행해도 안전하다).
- 우리가 쓰지 않는 클래스가 있으면 멈춘다. Roboflow 의 Modify Classes 에서 먼저 뺀다.
- 라벨 캐시(labels.cache)는 지운다. 예전 번호로 만든 캐시가 남으면 학습이 틀린 번호를 읽는다.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from labeler.from_roboflow import OUR_IDS, build_remap, read_class_order

SPLITS = ("train", "valid", "test")


def _remap_label(path: Path, remap: dict[int, int]) -> int:
    """라벨 txt 한 개의 클래스 번호를 바꾼다. 바뀐 줄 수를 돌려준다."""
    out, changed = [], 0
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if not parts:
            continue
        new = str(remap[int(parts[0])])
        changed += new != parts[0]
        out.append(" ".join([new] + parts[1:]))
    path.write_text("\n".join(out) + ("\n" if out else ""), encoding="utf-8")
    return changed


def fix_class_order(export_dir: str | Path) -> dict:
    export = Path(export_dir)
    names = read_class_order(export)  # data.yaml 이 없으면 FileNotFoundError
    remap = build_remap(names)  # 모르는 클래스가 있으면 ValueError

    already = names == list(OUR_IDS)
    boxes = files = 0
    if not already:
        for split in SPLITS:
            for lbl in (export / split / "labels").glob("*.txt"):
                boxes += _remap_label(lbl, remap)
                files += 1

    # 라벨 번호가 바뀌었든 아니든 예전 캐시는 믿지 않는다
    for cache in export.glob("*/labels.cache"):
        cache.unlink()

    lines = []
    for key, split in (("train", "train"), ("val", "valid"), ("test", "test")):
        if (export / split / "images").is_dir():
            lines.append(f"{key}: {split}/images")
    lines += [f"nc: {len(OUR_IDS)}", f"names: {list(OUR_IDS)}"]
    (export / "data.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {"원래 순서": names, "바꾼 라벨 파일": files, "바뀐 박스": boxes, "이미 맞음": already}


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m training.fix_class_order")
    parser.add_argument("export", help="Roboflow YOLOv8 export 폴더 (data.yaml 이 있는 곳)")
    args = parser.parse_args()
    print(json.dumps(fix_class_order(args.export), ensure_ascii=False))


if __name__ == "__main__":
    main()
