"""감지. ultralytics YOLO 로 사람·자전거 박스를 찾는다.

박스는 alarm.levels 가 받는 (x1, y1, x2, y2, conf, cls) 픽셀 좌표 그대로 돌려준다.
(Ultralytics 의 r.boxes.data.tolist() 와 같은 모양이다.)
모델은 .pt 도 되고 Jetson 에서 변환한 TensorRT .engine 도 된다(같은 YOLO() 로 연다).

장치: device 를 안 주면 CUDA(GPU)가 되는 환경에서는 GPU 를, 아니면 CPU 를 쓴다.
"0" 은 첫 번째 GPU, "cpu" 는 CPU 를 강제한다.
"""

from __future__ import annotations

from typing import List, Optional, Sequence


class Detector:
    def __init__(
        self,
        model: str = "yolo11n.pt",
        min_conf: float = 0.25,
        device: Optional[str] = None,
        imgsz: Optional[int] = None,
    ) -> None:
        # 무거운 import 는 쓸 때만 한다(순수 로직 시험이 느려지지 않게). 상수는 labeler 와 같은 값을 쓴다.
        import torch
        from labeler.autolabel import CLASS_IDS, IMGSZ, NMS_IOU
        from ultralytics import YOLO

        self._yolo = YOLO(model)
        self.min_conf = min_conf
        self.device = (device or "").strip() or None
        if self.device and self.device != "cpu" and not torch.cuda.is_available():
            raise RuntimeError(
                f"device={self.device} 인데 이 환경의 PyTorch 는 CUDA(GPU)를 못 쓴다({torch.__version__}). "
                "GPU 용 PyTorch 가 설치된 환경에서 실행하거나 --device cpu 를 준다"
            )
        self._kw = {
            "classes": CLASS_IDS,
            "imgsz": imgsz or IMGSZ,  # TensorRT 엔진은 만든 크기(480 등)와 같아야 한다
            "iou": NMS_IOU,
            "verbose": False,
        }
        if self.device:
            self._kw["device"] = self.device
        self._describe = self._make_description(torch)

    def _make_description(self, torch) -> str:
        if self.device == "cpu" or (not self.device and not torch.cuda.is_available()):
            return "CPU"
        idx = int(self.device) if (self.device or "").isdigit() else 0
        return f"GPU({torch.cuda.get_device_name(idx)})"

    def describe(self) -> str:
        """실제로 쓰는 장치 설명. 시작할 때 화면에 보여 준다."""
        return self._describe

    def detect(self, frame) -> List[Sequence[float]]:
        r = self._yolo.predict(frame, conf=self.min_conf, **self._kw)[0]
        return r.boxes.data.tolist()
