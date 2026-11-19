"""배포 conf 로 val(또는 test)을 돌려 실제 person 놓침·오탐 개수를 센다.

실행: python -m training.deploy_eval --model <best.pt> [--data data/dataset/data.yaml] [--split val]
                                     [--conf 0.37] [--imgsz 640] [--size n]

왜 따로 있나
- mAP·P·R 은 conf 를 낮게 잡고 계산해서 모델 자체 성능을 보여 준다. 실제 배포에서는 conf 를 올려 쓰므로
  "사람을 몇 명 놓치고 배경을 몇 번 잘못 잡는가" 는 그 conf 로 따로 세야 한다. 배포 판단은 이 개수로 한다.
- 이때 나오는 mAP 는 conf 를 올려서 왜곡되니 보지 않는다. mAP 는 기본 conf 로 따로 본다.
- `labeler eval`(gt100 v2 기준)과는 다른 평가다. 이쪽은 학습에 쓴 data.yaml 의 val/test 로 잰다.

배포 conf (모델 크기별): n 0.37, s 0.46. --conf 로 직접 줄 수도 있다.
모델 크기와 imgsz 는 best.pt 에 들어 있는 학습 설정에서 읽고, 못 읽으면 --size, --imgsz 를 쓴다.
센 값은 혼동행렬(IoU 0.45) 기준이다. 클래스는 person=0, bicycle=1.
"""
from __future__ import annotations

import argparse
import json
import os

DEPLOY_CONF = {"n": 0.37, "s": 0.46}  # 모델 크기별 배포 conf
P, B = 0, 1  # person=0, bicycle=1


def model_size(model_name: str) -> str:
    """`yolo11n.pt` → `n`. 알아볼 수 없으면 빈 문자열."""
    base = os.path.basename(str(model_name))
    return base.replace("yolo11", "").replace("yolo8", "")[:1]


def counts_from_matrix(mat) -> dict:
    """Ultralytics 혼동행렬(행=예측, 열=실제, 마지막 칸=배경)에서 개수를 뽑는다."""
    n_person = int(mat[:, P].sum())
    return {
        "person 총": n_person,
        "person 놓침": int(mat[-1, P]),
        "놓침 비율": round(float(mat[-1, P]) / max(n_person, 1), 3),
        "person→bicycle": int(mat[B, P]),
        "bicycle→person": int(mat[P, B]),
        "bicycle 놓침": int(mat[-1, B]),
        "오탐 person": int(mat[P, -1]),  # 배경을 person 으로
        "오탐 bicycle": int(mat[B, -1]),
    }


def deploy_counts(model: str, data: str = "data/dataset/data.yaml", split: str = "val",
                  conf: float | None = None, imgsz: int | None = None, size: str | None = None,
                  out_dir: str = "data/train_full/deploy_cm") -> dict:
    from ultralytics import YOLO

    yolo = YOLO(model)
    train_args = getattr(yolo, "ckpt", None) and yolo.ckpt.get("train_args") or {}
    size = size or model_size(train_args.get("model", ""))
    imgsz = imgsz or int(train_args.get("imgsz") or 640)
    if conf is None:
        if size not in DEPLOY_CONF:
            raise ValueError(f"모델 크기 '{size}' 의 배포 conf 를 모른다. --conf 나 --size {list(DEPLOY_CONF)} 를 준다")
        conf = DEPLOY_CONF[size]

    name = f"{os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(model))))}_{split}"
    r = yolo.val(data=data, split=split, imgsz=imgsz, conf=conf, plots=True, verbose=False,
                 project=os.path.abspath(out_dir), name=name, exist_ok=True)
    out = {"모델": model, "conf": conf, "imgsz": imgsz, "split": split,
           **counts_from_matrix(r.confusion_matrix.matrix),
           "추론 ms": round(float(r.speed["inference"]), 1), "save_dir": str(r.save_dir)}
    return out


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m training.deploy_eval")
    parser.add_argument("--model", required=True, help="학습한 가중치(.pt)")
    parser.add_argument("--data", default="data/dataset/data.yaml")
    parser.add_argument("--split", default="val", choices=["val", "test"])
    parser.add_argument("--conf", type=float, default=None, help="안 주면 모델 크기별 배포 conf")
    parser.add_argument("--imgsz", type=int, default=None, help="안 주면 학습 때 크기")
    parser.add_argument("--size", choices=sorted(DEPLOY_CONF), default=None, help="안 주면 학습 설정에서 읽는다")
    args = parser.parse_args()
    print(json.dumps(deploy_counts(args.model, args.data, args.split, args.conf, args.imgsz, args.size),
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
