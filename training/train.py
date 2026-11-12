"""labeler.split으로 나눈 데이터로 YOLO를 학습하고 gt100 v2로 평가한다.

실행: python -m training.train [--model yolo11n.pt] [--data data/dataset/data.yaml] [--name n_f10]
                              [--freeze 10] [--seed 0] [--epochs 100] [--imgsz 640] [--batch 8] [--skip-eval]
                              [--lr0 0.01] [--patience 100]
결과: data/train_full/runs/<name>/weights/best.pt, 평가 리포트 data/train_full/<name>_gt100v2.md
- gt100 v2는 평가 전용이라 학습·val에 넣지 않는다. 학습 자체에는 필요 없다.
- 평가는 python -m labeler eval을 그대로 부른다(IoU 0.5, F1·AP50·자동 확정 정답률).
- gt100 v2가 없으면 --skip-eval 로 학습만 한다. val 점수(val_map50)는 split이 떼어 둔 val로 나온다.
- 사진이 적으면 1~2에포크 뒤부터 val이 나빠진다. --lr0 을 낮추고 --patience 를 줄여 일찍 멈추는 쪽이 낫다.
- 주의: --optimizer 가 기본값 auto면 Ultralytics가 lr0를 무시하고 AdamW와 자동 lr을 쓴다.
  lr0를 실제로 바꾸려면 --optimizer SGD 처럼 직접 지정한다. 예: --optimizer SGD --lr0 0.001 --patience 20
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
          freeze: int = 10, seed: int = 0, epochs: int = 100, imgsz: int = 640, batch: int = 8,
          skip_eval: bool = False, lr0: float = 0.01, patience: int = 100,
          optimizer: str = "auto") -> dict:
    # 학습을 끝낸 뒤에 정답 세트가 없는 걸 알면 몇십 분을 버리므로 먼저 본다
    if not skip_eval:
        missing = [p for p in (GT_IMAGES, GT_LABELS) if not Path(p).is_dir()]
        if missing:
            raise FileNotFoundError(
                f"gt100 v2 정답 세트가 없다: {', '.join(missing)}. "
                "평가 없이 학습만 하려면 --skip-eval (함수는 skip_eval=True) 을 준다")

    res = YOLO(model).train(data=data, epochs=epochs, imgsz=imgsz, batch=batch, seed=seed, deterministic=True,
                            freeze=freeze, project=str((OUT / "runs").resolve()), name=name, exist_ok=True,
                            plots=False, verbose=False, lr0=lr0, patience=patience, optimizer=optimizer)
    best = OUT / "runs" / name / "weights" / "best.pt"
    out = {"best": str(best), "val_map50": round(float(res.box.map50), 4), "evaluated": not skip_eval,
           "lr0": lr0, "patience": patience, "optimizer": optimizer}
    if skip_eval:
        return out

    ev = subprocess.run([sys.executable, "-m", "labeler", "eval", "--images", GT_IMAGES, "--gt", GT_LABELS,
                         "--pred", str(OUT / f"{name}_gt_pred"), "--review-queue", str(OUT / f"{name}_gt_review.csv"),
                         "--report", str(OUT / f"{name}_gt100v2.md"), "--model", str(best)],
                        capture_output=True, text=True, encoding="utf-8", check=True)
    r = json.loads(ev.stdout.strip().splitlines()[-1])
    out.update({"f1": r["f1"], "ap50": r["ap50"]["mAP50"],
                "confirmed": r["confirmed"]["precision"], "miss": r["errors"]["Miss"]})
    return out


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
    parser.add_argument("--skip-eval", action="store_true",
                        help="gt100 v2 평가를 건너뛰고 학습만 한다 (정답 세트가 없을 때)")
    # optimizer=auto면 Ultralytics가 lr0를 무시하고 AdamW와 자동 lr을 쓴다
    # (engine/trainer.py: "'optimizer=auto' found, ignoring 'lr0=...'"). lr0를 비교하려면 SGD나 AdamW를 직접 준다
    parser.add_argument("--optimizer", default="auto",
                        choices=["auto", "SGD", "Adam", "AdamW", "NAdam", "RAdam", "RMSprop"],
                        help="auto면 lr0가 무시된다. lr0를 쓰려면 SGD나 AdamW를 직접 지정한다")
    parser.add_argument("--lr0", type=float, default=0.01, help="시작 학습률 (--optimizer를 auto가 아닌 값으로 줘야 적용된다)")
    parser.add_argument("--patience", type=int, default=100,
                        help="val이 좋아지지 않아도 참는 에포크 수. 줄이면 일찍 멈춘다")
    args = parser.parse_args()
    print(json.dumps(train(args.model, args.data, args.name, args.freeze, args.seed, args.epochs, args.imgsz,
                           args.batch, args.skip_eval, args.lr0, args.patience, args.optimizer)))


# Windows는 dataloader worker가 이 파일을 다시 import하므로 가드가 없으면 멈춘다
if __name__ == "__main__":
    main()
