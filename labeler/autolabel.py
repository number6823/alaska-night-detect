from __future__ import annotations

import csv
from pathlib import Path

from ultralytics import YOLO

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
# COCO 클래스 id가 팀 클래스(person=0, bicycle=1)와 같아서 변환 없이 쓴다.
CLASS_IDS = [0, 1]
IMGSZ = 640
# gt100에서 iou 0.5가 기본값 0.7보다 겹친 중복 박스를 더 지워 F1이 올랐다(0.602 → 0.610).
NMS_IOU = 0.5
REVIEW_COLUMNS = ["filename", "status", "boxes", "low_conf_boxes", "min_conf"]


def run_labeler(
    images_dir: str | Path = "data/images",
    labels_dir: str | Path = "data/labels",
    review_queue_csv: str | Path = "data/review_queue.csv",
    conf_threshold: float = 0.7,
    discard_threshold: float = 0.25,
    model: str = "yolo11n.pt",
) -> dict:
    """이미지 폴더를 YOLO로 라벨링하고 자동 통과 / 검수 대기 / 폐기로 나눈다.

    - conf_threshold 이상 박스는 자동 확정 (검수 사진 안에 있어도)
    - conf_threshold 미만 박스가 하나라도 있음: 검수 대기 (txt 저장 + csv 기록)
    - 박스가 모두 conf_threshold 이상: 자동 통과 (txt 저장)
    - discard_threshold 이상 박스가 없음: 폐기 (txt 없음 + csv 기록)
    """
    images_dir = Path(images_dir)
    labels_dir = Path(labels_dir)
    review_queue_csv = Path(review_queue_csv)
    labels_dir.mkdir(parents=True, exist_ok=True)
    review_queue_csv.parent.mkdir(parents=True, exist_ok=True)

    images = sorted(p for p in images_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    yolo = YOLO(model)
    rows = []
    labeled = 0
    boxes = 0
    confirmed_boxes = 0

    for path in images:
        result = yolo.predict(
            str(path), classes=CLASS_IDS, conf=discard_threshold, imgsz=IMGSZ, iou=NMS_IOU, verbose=False
        )[0]
        label_path = labels_dir / f"{path.stem}.txt"
        confs = result.boxes.conf.tolist()

        if not confs:
            # 이전 실행에서 남은 라벨이 있으면 지워서 폐기 상태와 맞춘다.
            label_path.unlink(missing_ok=True)
            rows.append({"filename": path.name, "status": "discard", "boxes": 0, "low_conf_boxes": 0, "min_conf": ""})
            continue

        lines = [
            f"{int(cls)} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}"
            for cls, (cx, cy, w, h) in zip(result.boxes.cls.tolist(), result.boxes.xywhn.tolist())
        ]
        label_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        labeled += 1

        low = sum(c < conf_threshold for c in confs)
        boxes += len(confs)
        confirmed_boxes += len(confs) - low
        if low:
            rows.append({
                "filename": path.name,
                "status": "review",
                "boxes": len(confs),
                "low_conf_boxes": low,
                "min_conf": f"{min(confs):.3f}",
            })

    with review_queue_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    review = sum(r["status"] == "review" for r in rows)
    return {
        "labels_dir": str(labels_dir),
        "review_queue_csv": str(review_queue_csv),
        "images": len(images),
        "labeled": labeled,
        "review": review,
        "discarded": sum(r["status"] == "discard" for r in rows),
        "review_ratio": round(review / labeled, 4) if labeled else 0.0,
        "boxes": boxes,
        "confirmed_boxes": confirmed_boxes,
    }
