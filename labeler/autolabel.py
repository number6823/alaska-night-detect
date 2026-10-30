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
REVIEW_COLUMNS = ["filename", "status", "boxes", "score", "min_conf"]


def box_uncertainty(conf: float) -> float:
    """conf가 0.5에 가까울수록 1, 0이나 1에 가까울수록 0 (Brust et al. 2019)."""
    return (1 - abs(2 * conf - 1)) ** 2


def run_labeler(
    images_dir: str | Path = "data/images",
    labels_dir: str | Path = "data/labels",
    review_queue_csv: str | Path = "data/review_queue.csv",
    discard_threshold: float = 0.25,
    model: str = "yolo11n.pt",
    review_top: float = 0.4,
) -> dict:
    """이미지 폴더를 YOLO로 라벨링하고 자동 통과 / 검수 대기 / 폐기로 나눈다.

    - discard_threshold 이상 박스가 없음: 폐기 (txt 없음 + csv 기록)
    - 나머지는 txt 저장. 사진 점수(박스 불확실성의 합)가 높은 순으로
      라벨이 만들어진 사진의 review_top 비율만큼 검수 대기 (csv 기록), 나머지는 자동 통과
    """
    if not 0 <= review_top <= 1:
        raise ValueError(f"review_top은 0~1 사이여야 합니다: {review_top}")
    images_dir = Path(images_dir)
    labels_dir = Path(labels_dir)
    review_queue_csv = Path(review_queue_csv)
    labels_dir.mkdir(parents=True, exist_ok=True)
    review_queue_csv.parent.mkdir(parents=True, exist_ok=True)

    images = sorted(p for p in images_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    yolo = YOLO(model)
    labeled_rows = []
    discard_rows = []

    for path in images:
        result = yolo.predict(
            str(path), classes=CLASS_IDS, conf=discard_threshold, imgsz=IMGSZ, iou=NMS_IOU, verbose=False
        )[0]
        label_path = labels_dir / f"{path.stem}.txt"
        confs = result.boxes.conf.tolist()

        if not confs:
            # 이전 실행에서 남은 라벨이 있으면 지워서 폐기 상태와 맞춘다.
            label_path.unlink(missing_ok=True)
            discard_rows.append({"filename": path.name, "status": "discard", "boxes": 0, "score": "", "min_conf": ""})
            continue

        lines = [
            f"{int(cls)} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}"
            for cls, (cx, cy, w, h) in zip(result.boxes.cls.tolist(), result.boxes.xywhn.tolist())
        ]
        label_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        labeled_rows.append({
            "filename": path.name,
            "status": "review",
            "boxes": len(confs),
            "score": sum(box_uncertainty(c) for c in confs),
            "min_conf": f"{min(confs):.3f}",
        })

    # 상위 비율이 review_top을 넘지 않게 내림한다.
    review_count = int(len(labeled_rows) * review_top)
    review_rows = sorted(labeled_rows, key=lambda r: r["score"], reverse=True)[:review_count]
    for r in review_rows:
        r["score"] = f"{r['score']:.4f}"

    with review_queue_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        writer.writerows(review_rows + discard_rows)

    return {
        "labels_dir": str(labels_dir),
        "review_queue_csv": str(review_queue_csv),
        "images": len(images),
        "labeled": len(labeled_rows),
        "review": len(review_rows),
        "discarded": len(discard_rows),
        "review_ratio": round(len(review_rows) / len(labeled_rows), 4) if labeled_rows else 0.0,
    }
