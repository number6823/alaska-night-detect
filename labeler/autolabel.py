from pathlib import Path

from ultralytics import YOLO

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
# COCO 클래스 id가 팀 클래스(person=0, bicycle=1)와 같아서 변환 없이 쓴다.
CLASS_NAMES = {0: "person", 1: "bicycle"}


def label_images(
    image_dir: str | Path,
    label_dir: str | Path,
    model: str = "yolo11n.pt",
    conf: float = 0.25,
) -> dict[str, int]:
    """이미지 폴더를 YOLO로 탐지해 이미지마다 같은 이름의 YOLO .txt 라벨을 저장한다."""
    image_dir = Path(image_dir)
    label_dir = Path(label_dir)
    label_dir.mkdir(parents=True, exist_ok=True)

    images = sorted(p for p in image_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    yolo = YOLO(model)
    summary = {"images": 0, "boxes": 0, "person": 0, "bicycle": 0}

    for path in images:
        result = yolo.predict(str(path), classes=list(CLASS_NAMES), conf=conf, verbose=False)[0]
        lines = []
        for cls, (cx, cy, w, h) in zip(result.boxes.cls.tolist(), result.boxes.xywhn.tolist()):
            cls = int(cls)
            lines.append(f"{cls} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
            summary[CLASS_NAMES[cls]] += 1
        # 박스가 없어도 빈 파일을 남긴다 (YOLO 학습에서 배경 이미지로 쓰임).
        text = "\n".join(lines) + "\n" if lines else ""
        (label_dir / f"{path.stem}.txt").write_text(text, encoding="utf-8")
        summary["images"] += 1
        summary["boxes"] += len(lines)

    return summary
