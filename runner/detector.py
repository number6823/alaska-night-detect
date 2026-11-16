"""감지. ultralytics YOLO 로 사람·자전거 박스를 찾는다.

박스는 alarm.levels 가 받는 (x1, y1, x2, y2, conf, cls) 픽셀 좌표 그대로 돌려준다.
(Ultralytics 의 r.boxes.data.tolist() 와 같은 모양이다.)
모델은 .pt 도 되고 Jetson 에서 변환한 TensorRT .engine 도 된다(같은 YOLO() 로 연다).
"""

from __future__ import annotations

from typing import List, Sequence


class Detector:
    def __init__(self, model: str = "yolo11n.pt", min_conf: float = 0.25) -> None:
        # 무거운 import 는 쓸 때만 한다(순수 로직 시험이 느려지지 않게). 상수는 labeler 와 같은 값을 쓴다.
        from labeler.autolabel import CLASS_IDS, IMGSZ, NMS_IOU
        from ultralytics import YOLO

        self._yolo = YOLO(model)
        self.min_conf = min_conf
        self._kw = dict(classes=CLASS_IDS, imgsz=IMGSZ, iou=NMS_IOU, verbose=False)

    def detect(self, frame) -> List[Sequence[float]]:
        r = self._yolo.predict(frame, conf=self.min_conf, **self._kw)[0]
        return r.boxes.data.tolist()
