"""labeler.split으로 나눈 데이터로 YOLO를 학습하고 gt100 v2로 평가한다.

실행: python -m training.train [--model yolo11n.pt] [--data data/dataset/data.yaml] [--name n_f10]
                              [--freeze 10] [--seed 0] [--epochs 100] [--imgsz 640] [--batch 8]
결과: data/train_full/runs/<name>/weights/best.pt, 평가 리포트 data/train_full/<name>_gt100v2.md
- gt100 v2는 평가 전용이라 학습·val에 넣지 않는다.
- 평가는 python -m labeler eval을 그대로 부른다(IoU 0.5, F1·AP50·자동 확정 정답률).
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from ultralytics import YOLO

OUT = Path("data/train_full")
GT_IMAGES = "data/gt100_v2/images"
GT_LABELS = "data/gt100_v2/labels"


def train(model: str = "yolo11n.pt", data: str = "data/dataset/data.yaml", name: str = "n_f10",
          freeze: int = 10, seed: int = 0, epochs: int = 100, imgsz: int = 640, batch: int = 8) -> dict:
    res = YOLO(model).train(data=data, epochs=epochs, imgsz=imgsz, batch=batch, seed=seed, deterministic=True,
                            freeze=freeze, project=str((OUT / "runs").resolve()), name=name, exist_ok=True,
                            plots=False, verbose=False)
    best = OUT / "runs" / name / "weights" / "best.pt"
    ev = subprocess.run([sys.executable, "-m", "labeler", "eval", "--images", GT_IMAGES, "--gt", GT_LABELS,
                         "--pred", str(OUT / f"{name}_gt_pred"), "--review-queue", str(OUT / f"{name}_gt_review.csv"),
                         "--report", str(OUT / f"{name}_gt100v2.md"), "--model", str(best)],
                        capture_output=True, text=True, encoding="utf-8", check=True)
    r = json.loads(ev.stdout.strip().splitlines()[-1])
    return {"best": str(best), "val_map50": round(float(res.box.map50), 4), "f1": r["f1"], "ap50": r["ap50"]["mAP50"],
            "confirmed": r["confirmed"]["precision"], "miss": r["errors"]["Miss"]}


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m training.train")
    parser.add_argument("--model", default="yolo11n.pt", help="시작 가중치")
    parser.add_argument("--data", default="data/dataset/data.yaml", help="labeler.split이 만든 data.yaml")
    parser.add_argument("--name", default="n_f10", help="결과 폴더 이름")
    # 사진이 수백 장이라 앞쪽 층을 고정해야 과적합이 덜하다 (freeze 0·5는 gt100 v2 F1이 더 낮았다)
    parser.add_argument("--freeze", type=int, default=10, help="앞에서부터 고정할 층 수")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=8, help="GTX 1060 3GB 기준")
    args = parser.parse_args()
    print(json.dumps(train(args.model, args.data, args.name, args.freeze, args.seed, args.epochs, args.imgsz, args.batch)))


# Windows는 dataloader worker가 이 파일을 다시 import하므로 가드가 없으면 멈춘다
if __name__ == "__main__":
    main()
