"""Roboflow에서 내보낸 라벨을 원본(모자이크 없는) 프레임에 붙여 학습용 폴더를 만든다.

실행: python -m training.merge_labels <Roboflow export 폴더> --originals data/rear_r6_label
                                      [--out data/merged] [--other-images data/images]

왜 필요한가
- 라벨링은 얼굴을 모자이크한 사본으로 했다(Roboflow 에는 사본만 올린다). 박스 좌표는 사진을 흐려도
  바뀌지 않으므로, 학습은 원본 프레임에 같은 라벨을 붙여 한다.
- Roboflow 는 한글을 `-` 로 바꾼다. `20261112_R6_04_자유촬영_밝기미확인_f08083` 은
  `20261112_R6_04_-_-_f08083` 이 된다. 그래서 이름 전체가 아니라 (날짜, 라운드, 영상 번호, 프레임 번호)
  로 원본을 찾는다. 이 값들은 ASCII 라서 그대로 살아남는다.

하는 일
1. labeler.from_roboflow 로 클래스 번호를 우리 규칙(person=0, bicycle=1)으로 바꾼다.
2. 영상 프레임(이름에 `_R6_04_..._f08083` 모양이 있는 것)은 --originals 에서 같은 프레임의 원본을 찾아
   그 이름으로 사진과 라벨을 --out 에 쓴다. 못 찾거나 겹치면 멈춘다.
3. 그 밖의 사진(Wikimedia 등)은 --other-images 에서 같은 이름을 찾고, 없으면 export 의 사진을 쓴다.
4. 사진 크기가 사본과 원본에서 다르면 멈춘다(크기가 다르면 같은 좌표가 같은 곳을 가리키지 않는다).

결과: <out>/images, <out>/labels. 이어서
    python -m labeler split --images <out>/images --labels <out>/labels --group-by video ...
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import tempfile
from pathlib import Path

from labeler.from_roboflow import IMAGE_EXTS, import_export

# 20261112_R6_04_자유촬영_밝기미확인_f08083 / 20261112_R6_04_-_-_f08083 -> (날짜, R6, 04, f08083)
FRAME_RE = re.compile(
    r"^(?P<date>\d{8})_(?P<round>R\d+)_(?P<no>\d+)_.*_(?P<frame>f\d+)$", re.IGNORECASE
)


def frame_key(stem: str) -> tuple[str, str, str, str] | None:
    """영상 프레임 이름에서 찾기 키를 꺼낸다. 영상 프레임이 아니면 None."""
    m = FRAME_RE.match(stem)
    if not m:
        return None
    return (m["date"], m["round"].upper(), m["no"], m["frame"].lower())


def _image_size(path: Path) -> tuple[int, int] | None:
    """(가로, 세로). 읽을 도구가 없으면 None."""
    try:
        import cv2
        import numpy as np

        img = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
        return None if img is None else (img.shape[1], img.shape[0])
    except ImportError:
        pass
    try:
        from PIL import Image

        with Image.open(path) as im:
            return im.size
    except ImportError:
        return None


def _find_image(directory: Path, stem: str) -> Path | None:
    for ext in IMAGE_EXTS:
        p = directory / f"{stem}{ext}"
        if p.exists():
            return p
    return None


def merge(
    export_dir: str | Path,
    originals_dir: str | Path,
    out_dir: str | Path = "data/merged",
    other_images_dir: str | Path = "data/images",
    keep_empty: bool = True,
    check_size: bool = True,
) -> dict:
    export_dir, originals_dir = Path(export_dir), Path(originals_dir)
    out_dir, other_dir = Path(out_dir), Path(other_images_dir)
    if out_dir.exists():
        raise FileExistsError(f"{out_dir} 가 이미 있다. 지우고 다시 실행한다")

    originals: dict[tuple, Path] = {}
    for p in sorted(originals_dir.iterdir()):
        if p.suffix.lower() not in IMAGE_EXTS:
            continue
        key = frame_key(p.stem)
        if key is None:
            continue
        if key in originals:
            raise ValueError(
                f"원본 프레임 키가 겹친다: {key} -> {originals[key].name}, {p.name}"
            )
        originals[key] = p
    if not originals:
        raise FileNotFoundError(f"{originals_dir} 에서 영상 프레임 원본을 못 찾았다")

    stats = {
        "labels": 0,
        "video_frames": 0,
        "other_images": 0,
        "other_from_export": 0,
        "empty_labels": 0,
        "person": 0,
        "bicycle": 0,
    }
    missing: list[str] = []
    size_mismatch: list[str] = []
    used_keys: set[tuple] = set()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_labels = Path(tmp) / "labels"
        res = import_export(
            export_dir, tmp_labels, Path(tmp) / "none", False, None, keep_empty
        )
        stats["flipped_classes"] = res["flipped"]
        img_out, lab_out = out_dir / "images", out_dir / "labels"
        staged: list[tuple[Path, Path, str]] = []  # (사진 원본, 라벨 txt, 쓸 사진 이름)

        for txt in sorted(tmp_labels.glob("*.txt")):
            stem = txt.stem
            export_img = next(
                (
                    p
                    for p in export_dir.rglob("images/*")
                    if p.suffix.lower() in IMAGE_EXTS
                    and re.sub(
                        r"_(jpg|jpeg|png)\.rf\.[0-9a-f]+$", "", p.stem, flags=re.IGNORECASE
                    )
                    == stem
                ),
                None,
            )
            key = frame_key(stem)
            if key is not None:
                orig = originals.get(key)
                if orig is None:
                    missing.append(stem)
                    continue
                if key in used_keys:
                    raise ValueError(f"export 에서 같은 프레임이 두 번 나왔다: {key}")
                used_keys.add(key)
                if check_size and export_img is not None:
                    a, b = _image_size(export_img), _image_size(orig)
                    if a is not None and b is not None and a != b:
                        size_mismatch.append(f"{orig.name}: 사본 {a} / 원본 {b}")
                        continue
                staged.append((orig, txt, orig.name))
                stats["video_frames"] += 1
            else:
                src = _find_image(other_dir, stem)
                if src is not None:
                    stats["other_images"] += 1
                elif export_img is not None:
                    src = export_img
                    stats["other_from_export"] += 1
                else:
                    missing.append(stem)
                    continue
                # export 의 사진 이름에는 _jpg.rf.<해시> 가 붙어 있다. 라벨 이름(stem)에 맞춘다
                staged.append((src, txt, f"{stem}{src.suffix.lower()}"))

        if missing or size_mismatch:
            raise ValueError(
                "붙이지 못한 것이 있어 멈춘다.\n"
                f"  원본을 못 찾음({len(missing)}): {missing[:5]}\n"
                f"  크기가 다름({len(size_mismatch)}): {size_mismatch[:3]}"
            )

        img_out.mkdir(parents=True)
        lab_out.mkdir(parents=True)
        for src_img, txt, target in staged:
            shutil.copy2(src_img, img_out / target)
            body = txt.read_text(encoding="utf-8")
            (lab_out / f"{Path(target).stem}.txt").write_text(body, encoding="utf-8")
            stats["labels"] += 1
            if not body.strip():
                stats["empty_labels"] += 1
            for line in body.splitlines():
                if line.strip():
                    stats["person" if line.split()[0] == "0" else "bicycle"] += 1

    unused = [p.name for k, p in originals.items() if k not in used_keys]
    stats["originals_not_in_export"] = len(unused)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m training.merge_labels")
    parser.add_argument(
        "export", help="Roboflow YOLO export 폴더 (data.yaml 이 있는 곳)"
    )
    parser.add_argument(
        "--originals", required=True, help="모자이크 없는 원본 프레임 폴더"
    )
    parser.add_argument("--out", default="data/merged", help="결과 폴더 (없어야 함)")
    parser.add_argument(
        "--other-images",
        default="data/images",
        help="Wikimedia 등 영상이 아닌 사진 폴더",
    )
    parser.add_argument(
        "--drop-empty",
        action="store_true",
        help="빈 라벨(배경)을 버린다. 기본은 남긴다",
    )
    parser.add_argument(
        "--no-size-check", action="store_true", help="사진 크기 비교를 건너뛴다"
    )
    args = parser.parse_args()
    stats = merge(
        args.export,
        args.originals,
        args.out,
        args.other_images,
        keep_empty=not args.drop_empty,
        check_size=not args.no_size_check,
    )
    print(json.dumps(stats, ensure_ascii=False))
    print(f"결과: {args.out}/images, {args.out}/labels")


if __name__ == "__main__":
    main()
