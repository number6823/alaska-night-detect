import argparse
import json

from .autolabel import label_images


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m labeler")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="이미지 폴더를 자동 라벨링한다")
    run.add_argument("--images", default="data/images", help="입력 이미지 폴더")
    run.add_argument("--labels", default="data/labels", help="YOLO .txt 저장 폴더")
    run.add_argument("--model", default="yolo11n.pt", help="YOLO 가중치")
    run.add_argument("--conf", type=float, default=0.25, help="최소 신뢰도")
    args = parser.parse_args()

    summary = label_images(args.images, args.labels, args.model, args.conf)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
