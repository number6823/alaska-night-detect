import argparse
import json

from .autolabel import run_labeler


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m labeler")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="이미지 폴더를 자동 라벨링한다")
    run.add_argument("--images", default="data/images", help="입력 이미지 폴더")
    run.add_argument("--labels", default="data/labels", help="YOLO .txt 저장 폴더")
    run.add_argument("--review-queue", default="data/review_queue.csv", help="검수 대기 목록 csv")
    run.add_argument("--conf-threshold", type=float, default=0.5, help="자동 통과 신뢰도")
    run.add_argument("--discard-threshold", type=float, default=0.25, help="이 미만 박스는 버림")
    run.add_argument("--model", default="yolo11n.pt", help="YOLO 가중치")
    args = parser.parse_args()

    summary = run_labeler(
        args.images,
        args.labels,
        args.review_queue,
        args.conf_threshold,
        args.discard_threshold,
        args.model,
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
