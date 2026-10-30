"""검수 시간 시험(11/5)에서 건너뛰기 조가 쓸 미리보기를 만든다.

사진마다 박스를 conf 기준으로 색칠해 data/ 안에 저장한다. 초록 = 확정(건너뜀), 빨강 = 확인 필요.
실행: python -m agent.preview [--images data/gt100/images] [--out data/preview] [--conf-threshold 0.7] [--model yolo11n.pt]
"""

import argparse
from pathlib import Path

import cv2
import numpy as np

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
CLASS_NAMES = {0: "person", 1: "bicycle"}
GREEN = (0, 200, 0)
RED = (0, 0, 255)


def _read(path):
    # cv2.imread는 한글 경로를 못 읽어서 imdecode로 읽는다
    return cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)


def _draw(img, boxes, conf_threshold):
    h, w = img.shape[:2]
    thick = max(2, round(min(h, w) / 300))
    scale = max(0.5, min(h, w) / 900)
    for cls, cx, cy, bw, bh, conf in boxes:
        x1, y1 = int((cx - bw / 2) * w), int((cy - bh / 2) * h)
        x2, y2 = int((cx + bw / 2) * w), int((cy + bh / 2) * h)
        color = GREEN if conf >= conf_threshold else RED
        cv2.rectangle(img, (x1, y1), (x2, y2), color, thick)
        cv2.putText(
            img,
            f"{CLASS_NAMES.get(cls, cls)} {conf:.2f}",
            (x1, max(y1 - 4, 12)),
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            color,
            thick,
        )


def make_previews(
    images_dir="data/gt100/images",
    out_dir="data/preview",
    conf_threshold=0.7,
    model="yolo11n.pt",
    discard_threshold=0.25,
):
    """사진마다 박스를 그린 미리보기를 out_dir에 저장하고 장수를 돌려준다.

    박스는 labeler가 실제로 내보내는 것(discard_threshold 이상)과 같은 설정으로 예측한다.
    ultralytics가 있어야 해서, 설치 전에도 다른 기능이 돌도록 호출할 때 불러온다.
    반환: out_dir, images, boxes, confirmed(초록), to_check(빨강).
    """
    from labeler.autolabel import predict_scored

    images_dir, out_dir = Path(images_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    scored = predict_scored(images_dir, model, discard_threshold)
    images = sorted(p for p in images_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    boxes = confirmed = 0
    for path in images:
        img = _read(path)
        if img is None:
            print(f"[읽기 실패] {path.name}")
            continue
        found = scored.get(path.stem, [])
        _draw(img, found, conf_threshold)
        cv2.imencode(".jpg", img)[1].tofile(str(out_dir / f"{path.stem}.jpg"))
        boxes += len(found)
        confirmed += sum(b[5] >= conf_threshold for b in found)
    return {
        "out_dir": str(out_dir),
        "images": len(images),
        "boxes": boxes,
        "confirmed": confirmed,
        "to_check": boxes - confirmed,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="conf 기준으로 박스를 초록·빨강으로 그린 미리보기를 만든다"
    )
    parser.add_argument(
        "--images", default="data/gt100/images", help="입력 이미지 폴더"
    )
    parser.add_argument(
        "--out", default="data/preview", help="미리보기 저장 폴더(data/ 안에 둔다)"
    )
    parser.add_argument(
        "--conf-threshold", type=float, default=0.7, help="이 이상 박스는 초록(확정)"
    )
    parser.add_argument("--model", default="yolo11n.pt", help="YOLO 가중치")
    args = parser.parse_args()
    print(make_previews(args.images, args.out, args.conf_threshold, args.model))
