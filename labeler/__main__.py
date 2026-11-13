import argparse
import json

from .autolabel import predict_scored, run_labeler
from .evaluate import evaluate


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m labeler")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="이미지 폴더를 자동 라벨링한다")
    run.add_argument("--images", default="data/images", help="입력 이미지 폴더")
    run.add_argument("--labels", default="data/labels", help="YOLO .txt 저장 폴더")
    run.add_argument("--review-queue", default="data/review_queue.csv", help="검수 대기 목록 csv")
    run.add_argument("--conf-threshold", type=float, default=0.7, help="이 이상 박스는 자동 확정, 미만 박스가 있으면 검수")
    run.add_argument("--discard-threshold", type=float, default=0.25, help="이 미만 박스는 버림")
    run.add_argument("--model", default="yolo11n.pt", help="YOLO 가중치")

    ev = sub.add_parser("eval", help="정답 사진을 자동 라벨링한 뒤 정답 라벨과 비교한다")
    ev.add_argument("--images", default="data/gt100/images", help="정답 사진 폴더")
    ev.add_argument("--gt", default="data/gt100/labels", help="정답 YOLO .txt 폴더")
    ev.add_argument("--pred", default="data/gt100/pred", help="자동 라벨 저장 폴더")
    ev.add_argument("--review-queue", default="data/gt100/review_queue.csv", help="정답 사진의 검수 대기 목록 csv")
    ev.add_argument("--report", default="data/accuracy_report.md", help="정확도 리포트")
    ev.add_argument("--iou", type=float, default=0.5, help="맞음으로 볼 IoU 기준")
    ev.add_argument("--conf-threshold", type=float, default=0.7, help="이 이상 박스는 자동 확정, 미만 박스가 있으면 검수")
    ev.add_argument("--discard-threshold", type=float, default=0.25, help="이 미만 박스는 버림")
    ev.add_argument("--model", default="yolo11n.pt", help="YOLO 가중치")
    ev.add_argument("--no-predict", action="store_true",
                    help="자동 라벨링을 하지 않고 --pred 폴더에 이미 있는 라벨을 --gt와 비교한다. "
                         "두 사람이 따로 라벨한 같은 사진의 일치율을 볼 때 쓴다")
    args = parser.parse_args()

    if args.command == "run":
        summary = run_labeler(
            args.images,
            args.labels,
            args.review_queue,
            args.conf_threshold,
            args.discard_threshold,
            args.model,
        )
    elif args.no_predict:
        # 모델을 부르지 않는다. --pred 에 있는 라벨을 그대로 --gt 와 맞춰 본다.
        # 사람이 그린 라벨 두 벌을 비교할 때 쓴다(일치율 = F1, 어느 쪽을 pred로 놔도 같다).
        summary = evaluate(args.pred, args.gt, args.report, args.iou)
    else:
        run_labeler(args.images, args.pred, args.review_queue, args.conf_threshold, args.discard_threshold, args.model)
        scored = predict_scored(args.images, args.model)
        summary = evaluate(args.pred, args.gt, args.report, args.iou, scored, args.discard_threshold, args.conf_threshold)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
