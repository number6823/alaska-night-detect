"""FLIR 정답(COCO JSON)을 우리 형식(사진마다 YOLO txt, person=0, bicycle=1)으로 바꾼다."""

import argparse
import json
from pathlib import Path

# COCO 카테고리 이름 -> 우리 클래스 번호. 번호가 아니라 JSON 안의 이름으로 연결한다.
# FLIR가 자전거를 "bike"라고 부르는지는 데이터를 받아서 확인해야 한다(아직 확인 못 함).
CLASS_BY_NAME = {"person": 0, "bike": 1}


def coco_to_yolo(coco_json, out_dir, class_by_name=CLASS_BY_NAME):
    """COCO JSON의 박스를 사진마다 YOLO txt로 저장하고, 센 결과를 dict로 돌려준다.

    class_by_name에 없는 클래스(car 등)와 군중(iscrowd) 박스는 버린다.
    대상이 하나도 없는 사진도 빈 txt를 만든다(평가에서 오탐을 세려면 필요).
    """
    data = json.loads(Path(coco_json).read_text(encoding="utf-8"))

    names = {c["name"] for c in data["categories"]}
    missing = sorted(set(class_by_name) - names)
    if missing:
        raise ValueError(
            f"JSON에 없는 클래스 이름: {missing}. JSON의 이름: {sorted(names)}. "
            "CLASS_BY_NAME을 실제 이름에 맞춰 고쳐야 한다."
        )
    cls_by_id = {
        c["id"]: class_by_name[c["name"]]
        for c in data["categories"]
        if c["name"] in class_by_name
    }
    images = {im["id"]: im for im in data["images"]}
    lines = {im_id: [] for im_id in images}
    dropped = 0

    for ann in data["annotations"]:
        cls = cls_by_id.get(ann["category_id"])
        im = images.get(ann["image_id"])
        if cls is None or im is None or ann.get("iscrowd"):
            dropped += 1
            continue
        w, h = im["width"], im["height"]
        x, y, bw, bh = ann["bbox"]
        # 사진 밖으로 나간 부분은 잘라낸다.
        x1, y1, x2, y2 = (
            max(0.0, x),
            max(0.0, y),
            min(float(w), x + bw),
            min(float(h), y + bh),
        )
        if x2 <= x1 or y2 <= y1:
            dropped += 1
            continue
        cx, cy = (x1 + x2) / 2 / w, (y1 + y2) / 2 / h
        lines[im["id"]].append(
            f"{cls} {cx:.6f} {cy:.6f} {(x2 - x1) / w:.6f} {(y2 - y1) / h:.6f}"
        )

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for im_id, im in images.items():
        text = "\n".join(lines[im_id]) + "\n" if lines[im_id] else ""
        # file_name에 폴더가 붙어 있을 수 있어 파일 이름 부분만 쓴다.
        (out_dir / f"{Path(im['file_name']).stem}.txt").write_text(
            text, encoding="utf-8"
        )

    return {
        "images": len(images),
        "boxes": sum(len(v) for v in lines.values()),
        "dropped": dropped,
        "out_dir": str(out_dir),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FLIR COCO JSON을 YOLO txt로 바꾼다")
    parser.add_argument("coco_json")
    parser.add_argument("out_dir")
    args = parser.parse_args()
    print(json.dumps(coco_to_yolo(args.coco_json, args.out_dir), ensure_ascii=False))
