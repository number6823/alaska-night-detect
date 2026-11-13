"""Roboflow 같은 외부 라벨링 사이트에 올릴 사본의 얼굴(머리)을 모자이크한다. 원본은 건드리지 않는다.

실행: python -m training.blur_for_upload --src <프레임 폴더> --out <사본 폴더> [--yunet <모델.onnx>]

왜 이렇게 하나
- 박스 좌표는 사진을 흐려도 바뀌지 않는다. 그래서 라벨링은 모자이크한 사본으로 하고,
  내보낸 라벨은 `python -m training.merge_labels` 로 같은 프레임의 원본에 붙여 학습·평가한다.

사람이 있는 곳을 찾는 방법(둘을 합친다)
1. YOLO 를 낮은 신뢰도(0.05)로 돌려 사람 박스를 찾고 박스 위쪽 약 30%를 가린다.
2. OpenCV 얼굴 검출기 YuNet(face_detection_yunet_2023mar.onnx)이 찾은 얼굴을 가린다.
   --yunet 으로 모델 파일을 주면 켜진다. 없으면 1번만 한다. (OpenCV 5 에는 예전 Haar 검출기가 없다)

한계: 아주 작거나 어두워서 둘 다 못 찾은 얼굴은 가려지지 않는다. 결과 사진을 눈으로 확인한 뒤 올린다.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}


def pixelate(img, x1: int, y1: int, x2: int, y2: int) -> None:
    h, w = img.shape[:2]
    x1, y1, x2, y2 = max(0, x1), max(0, y1), min(w, x2), min(h, y2)
    if x2 - x1 < 4 or y2 - y1 < 4:
        return
    roi = img[y1:y2, x1:x2]
    bw = max(2, (x2 - x1) // 8)  # 가로 약 8칸 모자이크
    bh = max(2, (y2 - y1) // 8)
    small = cv2.resize(
        roi,
        (max(1, (x2 - x1) // bw), max(1, (y2 - y1) // bh)),
        interpolation=cv2.INTER_LINEAR,
    )
    img[y1:y2, x1:x2] = cv2.resize(
        small, (x2 - x1, y2 - y1), interpolation=cv2.INTER_NEAREST
    )


def blur_folder(
    src: str | Path,
    out: str | Path,
    model: str = "yolo11n.pt",
    conf: float = 0.05,
    imgsz: int = 960,
    yunet: str | None = None,
) -> dict:
    from ultralytics import YOLO  # 무거워서 쓸 때만 불러온다

    src, out = Path(src), Path(out)
    if out.exists():
        raise FileExistsError(f"이미 있다: {out} (지우고 다시 실행)")
    paths = sorted(p for p in src.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    if not paths:
        raise FileNotFoundError(f"사진이 없다: {src}")
    out.mkdir(parents=True)

    detector = YOLO(model)
    face = None
    if yunet and Path(yunet).exists():
        face = cv2.FaceDetectorYN.create(yunet, "", (320, 320), 0.4, 0.3, 5000)
    elif yunet:
        print(f"[얼굴 검출기 모델 없음: {yunet}] YOLO 머리 모자이크만 한다.")
    else:
        print(
            "[--yunet 을 안 줬다] YOLO 머리 모자이크만 한다. 얼굴 검출기를 켜는 것이 안전하다."
        )

    heads = faces = 0
    for p in paths:
        img = cv2.imdecode(np.fromfile(str(p), dtype=np.uint8), cv2.IMREAD_COLOR)
        h, w = img.shape[:2]
        res = detector.predict(img, conf=conf, imgsz=imgsz, classes=[0], verbose=False)[
            0
        ]
        for x1, y1, x2, y2 in res.boxes.xyxy.cpu().numpy():
            bw, bh = x2 - x1, y2 - y1
            head_h = max(
                0.30 * bh, 0.6 * bw
            )  # 박스 위쪽 30% (키가 작게 잡혔을 때를 위해 폭 기준도 둔다)
            pixelate(
                img,
                int(x1 - 0.15 * bw),
                int(y1 - 0.10 * head_h),
                int(x2 + 0.15 * bw),
                int(y1 + head_h),
            )
            heads += 1
        if face is not None:
            face.setInputSize((w, h))
            _, found = face.detect(img)
            for f in found if found is not None else []:
                fx, fy, fw, fh = f[:4]
                pixelate(
                    img,
                    int(fx - 0.2 * fw),
                    int(fy - 0.2 * fh),
                    int(fx + 1.2 * fw),
                    int(fy + 1.2 * fh),
                )
                faces += 1
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 95])
        if not ok:
            raise RuntimeError(f"인코딩 실패: {p.name}")
        buf.tofile(str(out / (p.stem + ".jpg")))  # 한글 경로에서도 되도록 tofile
    return {"images": len(paths), "heads": heads, "faces": faces, "out": str(out)}


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m training.blur_for_upload")
    parser.add_argument("--src", required=True, help="원본 프레임 폴더")
    parser.add_argument(
        "--out", required=True, help="모자이크 사본을 쓸 폴더 (없어야 함)"
    )
    parser.add_argument("--model", default="yolo11n.pt")
    parser.add_argument("--conf", type=float, default=0.05)
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument(
        "--yunet", default=None, help="face_detection_yunet_2023mar.onnx 경로"
    )
    args = parser.parse_args()
    result = blur_folder(
        args.src, args.out, args.model, args.conf, args.imgsz, args.yunet
    )
    print(
        f"사진 {result['images']}장: 사람 머리 {result['heads']}곳 + 얼굴 {result['faces']}곳을 모자이크 -> {result['out']}"
    )
    print("결과 사진을 눈으로 확인한 뒤 올린다.")


if __name__ == "__main__":
    main()
