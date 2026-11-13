"""Roboflow에서 내보낸 YOLO 라벨을 우리 형식으로 되돌린다.

실행: python -m labeler.from_roboflow <export 폴더> [--labels data/labels] [--images data/images]
                                       [--copy-images] [--out-reviewed data/labels_reviewed]

Roboflow export는 두 가지가 우리와 다르다.

1. 클래스 번호가 알파벳 순서다. bicycle < person 이라 **항상** bicycle=0, person=1 로 나온다.
   우리 규칙은 person=0, bicycle=1 이므로 그대로 쓰면 사람과 자전거가 통째로 뒤바뀐다.
   이 변환을 사람이 매번 기억해서 하면 언젠가 놓치고, 틀려도 조용히 틀린다.
2. 파일 이름에 `_jpg.rf.<해시>` 가 붙는다. 원래 이름으로 되돌려야 사진과 짝이 맞는다.

이 도구는 export의 data.yaml 에 적힌 이름 순서를 **읽어서** 번호를 맞추므로,
Roboflow가 순서를 바꾸더라도 맞게 들어간다.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

# 우리 규칙. labeler 전체가 이 번호를 쓴다
OUR_IDS = {"person": 0, "bicycle": 1}
IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
# Roboflow가 붙이는 꼬리표: <원래이름>_<확장자>.rf.<해시>
RF_SUFFIX = re.compile(r"^(?P<stem>.+?)_(?P<ext>jpg|jpeg|png)\.rf\.[0-9a-f]+$", re.IGNORECASE)
# data.yaml 의 names 가 한 줄인 경우: names: ['bicycle', 'person']
INLINE_NAMES = re.compile(r"^\s*names\s*:\s*\[(?P<body>[^\]]*)\]", re.MULTILINE)
# 여러 줄인 경우:  0: person
BLOCK_NAME = re.compile(r"^\s+(?P<idx>\d+)\s*:\s*(?P<name>\S+)\s*$", re.MULTILINE)


def original_name(stem: str) -> tuple[str, str] | None:
    """`wikimedia_1_jpg.rf.abc123` → `("wikimedia_1", "jpg")`. 꼬리표가 없으면 None."""
    m = RF_SUFFIX.match(stem)
    return (m["stem"], m["ext"].lower()) if m else None


def read_class_order(export_dir: Path) -> list[str]:
    """export의 data.yaml에서 클래스 이름을 번호 순서대로 읽는다."""
    yaml_path = export_dir / "data.yaml"
    if not yaml_path.exists():
        raise FileNotFoundError(f"{yaml_path} 가 없다. Roboflow export 폴더가 맞는지 본다")
    text = yaml_path.read_text(encoding="utf-8")

    inline = INLINE_NAMES.search(text)
    if inline:
        names = [n.strip().strip("'\"") for n in inline["body"].split(",") if n.strip()]
    else:
        pairs = sorted((int(m["idx"]), m["name"].strip("'\"")) for m in BLOCK_NAME.finditer(text))
        names = [n for _, n in pairs]

    if not names:
        raise ValueError(f"{yaml_path} 에서 클래스 이름을 못 읽었다")
    return names


def build_remap(names: list[str]) -> dict[int, int]:
    """export 번호 → 우리 번호. 모르는 클래스가 있으면 멈춘다(조용히 틀리지 않게)."""
    unknown = [n for n in names if n not in OUR_IDS]
    if unknown:
        raise ValueError(f"우리가 쓰지 않는 클래스가 있다: {unknown}. 기대한 것은 {list(OUR_IDS)}")
    return {i: OUR_IDS[name] for i, name in enumerate(names)}


def import_export(export_dir: str | Path, labels_dir: str | Path = "data/labels",
                  images_dir: str | Path = "data/images", copy_images: bool = False,
                  out_reviewed: str | Path | None = None) -> dict:
    """export 폴더의 라벨을 우리 번호·이름으로 바꿔 labels_dir 에 쓴다.

    - 빈 라벨은 txt 를 만들지 않는다(labeler 의 폐기 규칙과 같게).
    - copy_images 면 images_dir 에 없는 사진을 export 에서 가져온다.
    - out_reviewed 를 주면 이번에 들어온 라벨만 따로 한 벌 더 쓴다(split 에 바로 넘기려고).
    """
    export_dir = Path(export_dir)
    labels_dir = Path(labels_dir)
    images_dir = Path(images_dir)
    labels_dir.mkdir(parents=True, exist_ok=True)

    names = read_class_order(export_dir)
    remap = build_remap(names)
    flipped = any(k != v for k, v in remap.items())

    reviewed_dir = Path(out_reviewed) if out_reviewed else None
    if reviewed_dir:
        if reviewed_dir.exists():
            shutil.rmtree(reviewed_dir)
        reviewed_dir.mkdir(parents=True)

    local = {p.name for p in images_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS} \
        if images_dir.exists() else set()

    written = empty = skipped = copied = 0
    boxes = {name: 0 for name in OUR_IDS}
    unnamed: list[str] = []

    # train/valid/test 를 모두 합친다. 학습용 분할은 labeler.split 이 다시 한다
    for txt in sorted(export_dir.rglob("labels/*.txt")):
        parsed = original_name(txt.stem)
        if parsed is None:
            unnamed.append(txt.name)
            continue
        stem, ext = parsed

        lines = []
        for line in txt.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if not parts:
                continue
            cid = int(parts[0])
            if cid not in remap:
                raise ValueError(f"{txt.name}: data.yaml 에 없는 클래스 번호 {cid}")
            ours = remap[cid]
            lines.append(" ".join([str(ours)] + parts[1:]))
            boxes["person" if ours == 0 else "bicycle"] += 1

        if not lines:
            empty += 1
            continue

        img_name = f"{stem}.{ext}"
        if img_name not in local:
            src = next((p for p in (txt.parent.parent / "images").iterdir() if p.stem == txt.stem), None)
            if src is None:
                skipped += 1
                continue
            if copy_images:
                images_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, images_dir / img_name)
                copied += 1

        body = "\n".join(lines) + "\n"
        (labels_dir / f"{stem}.txt").write_text(body, encoding="utf-8")
        if reviewed_dir:
            (reviewed_dir / f"{stem}.txt").write_text(body, encoding="utf-8")
        written += 1

    return {
        "export_names": names,
        "flipped": flipped,
        "labels": written,
        "boxes": sum(boxes.values()),
        "person": boxes["person"],
        "bicycle": boxes["bicycle"],
        "empty": empty,
        "images_copied": copied,
        "skipped_no_image": skipped,
        "unnamed": unnamed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m labeler.from_roboflow")
    parser.add_argument("export", help="Roboflow YOLO export 폴더 (data.yaml 이 있는 곳)")
    parser.add_argument("--labels", default="data/labels", help="라벨을 쓸 폴더")
    parser.add_argument("--images", default="data/images", help="사진 폴더")
    parser.add_argument("--copy-images", action="store_true",
                        help="사진 폴더에 없는 사진을 export 에서 가져온다")
    parser.add_argument("--out-reviewed", default=None,
                        help="이번에 들어온 라벨만 따로 쓸 폴더 (예: data/labels_reviewed)")
    args = parser.parse_args()

    result = import_export(args.export, args.labels, args.images, args.copy_images, args.out_reviewed)

    order = " ".join(f"{i}={n}" for i, n in enumerate(result["export_names"]))
    print(f"export 클래스 순서: {order}")
    print("→ 우리 순서(person=0, bicycle=1)로 " + ("뒤집었다" if result["flipped"] else "그대로 뒀다"))
    print(json.dumps({k: v for k, v in result.items() if k != "export_names"}, ensure_ascii=False))
    if result["unnamed"]:
        print(f"[확인] .rf 꼬리표가 없어 건너뛴 파일 {len(result['unnamed'])}개: {result['unnamed'][:5]}")
    if result["skipped_no_image"]:
        print(f"[확인] 사진이 없어 건너뛴 라벨 {result['skipped_no_image']}개 (--copy-images 로 가져올 수 있다)")


if __name__ == "__main__":
    main()
