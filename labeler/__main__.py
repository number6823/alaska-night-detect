import argparse
import json

from .autolabel import run_labeler
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
    ev.add_argument("--discard-threshold", type=float, default=0.25, help="이 미만 박스는 버림")
    ev.add_argument("--model", default="yolo11n.pt", help="YOLO 가중치")
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
    else:
        run_labeler(args.images, args.pred, args.review_queue, discard_threshold=args.discard_threshold, model=args.model)
        summary = evaluate(args.pred, args.gt, args.report, args.iou)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
