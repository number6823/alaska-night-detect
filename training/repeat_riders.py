"""YOLO 데이터셋의 train 폴더에서 자전거(탑승자) 사진을 N배로 복사해 자전거 비중을 올린다.

실행: python -m training.repeat_riders <데이터셋 폴더> [--repeat 3] [--keys rider_ ext_] [--bicycle-id 1]

- <데이터셋 폴더>/train/images, train/labels 구조(Roboflow YOLOv8 export, 또는 같은 모양)를 읽는다.
- **train에만** 복사한다. valid·test는 건드리지 않는다(점수가 부풀려지면 안 된다).
- --keys 를 주면 파일 이름에 그 글자가 들어간 사진만 반복한다. Roboflow 는 파일명을
  `원래이름_jpg.rf.해시.jpg` 로 바꾸므로 원래 이름의 일부로 찾으면 된다.
  주지 않으면 자전거 박스가 있는 train 사진 전부를 반복한다.
- 복사본은 `<이름>_dup1`, `_dup2` ... 로 만든다. 다시 실행해도 늘지 않게, 먼저 예전 `_dup` 복사본을 지운다.
- 라벨 캐시(*.cache)와 이미지 캐시(*.npy)도 같이 지운다. 복사본이 생기면 예전 캐시가 어긋난다.
- **복사본은 같은 사진이라 학습에서 자전거 비중만 올라간다. 새 정보는 아니다.**
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
DUP_RE = re.compile(r"_dup\d+$")


def clean_duplicates(train_dir: Path) -> int:
    """예전 `_dup` 복사본과 캐시를 지운다. 지운 복사본 수(사진+라벨)를 돌려준다."""
    removed = 0
    for sub in ("images", "labels"):
        folder = train_dir / sub
        if not folder.is_dir():
            continue
        for p in folder.iterdir():
            if p.is_file() and DUP_RE.search(p.stem):
                p.unlink()
                removed += 1
        for p in folder.glob("*.npy"):
            p.unlink()
    for p in train_dir.glob("*.cache"):
        p.unlink()
    return removed


def has_class(label: Path, class_id: int) -> bool:
    """라벨 txt에 class_id 박스(또는 폴리곤)가 한 줄이라도 있는가."""
    if not label.is_file():
        return False
    for line in label.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if parts and parts[0] == str(class_id):
            return True
    return False


def repeat_riders(dataset: str | Path, repeat: int = 3, keys: list[str] | None = None,
                  bicycle_id: int = 1) -> dict:
    """train의 탑승자 사진을 총 `repeat`배로 만든다(원본 1장 + 복사본 repeat-1장)."""
    if repeat < 1:
        raise ValueError("repeat 는 1 이상이어야 한다")
    train = Path(dataset) / "train"
    img_dir, lbl_dir = train / "images", train / "labels"
    if not img_dir.is_dir() or not lbl_dir.is_dir():
        raise FileNotFoundError(f"{train} 아래에 images/ 와 labels/ 가 있어야 한다")

    removed = clean_duplicates(train)

    riders = []
    for img in sorted(img_dir.iterdir()):
        if not img.is_file() or img.suffix.lower() not in IMAGE_EXTS:
            continue
        lbl = lbl_dir / f"{img.stem}.txt"
        ok = any(k in img.stem for k in keys) if keys else has_class(lbl, bicycle_id)
        if ok:
            riders.append((img, lbl))

    for img, lbl in riders:
        for k in range(1, repeat):
            shutil.copy(img, img_dir / f"{img.stem}_dup{k}{img.suffix}")
            if lbl.is_file():
                shutil.copy(lbl, lbl_dir / f"{img.stem}_dup{k}.txt")

    return {
        "riders": len(riders),
        "copies": len(riders) * (repeat - 1),
        "removed_old_copies": removed,
        "train_images": sum(1 for p in img_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS),
        "by": f"파일명 {keys}" if keys else "자전거 박스가 있는 사진",
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m training.repeat_riders")
    parser.add_argument("dataset", help="train/images, train/labels 가 있는 데이터셋 폴더")
    parser.add_argument("--repeat", type=int, default=3, help="탑승자 사진을 총 몇 배로 (2~3)")
    parser.add_argument("--keys", nargs="*", default=None,
                        help="파일 이름에 이 글자가 들어간 사진만 반복. 안 주면 자전거 박스가 있는 사진 전부")
    parser.add_argument("--bicycle-id", type=int, default=1, help="자전거 클래스 번호 (우리 규칙 1)")
    args = parser.parse_args()
    print(json.dumps(repeat_riders(args.dataset, args.repeat, args.keys, args.bicycle_id), ensure_ascii=False))


if __name__ == "__main__":
    main()
