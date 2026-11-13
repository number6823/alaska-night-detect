"""한글(비ASCII) 경로에서도 사진을 읽고 쓴다.

`cv2.imread` 는 한글 경로에서 **None** 을 돌려주고 `cv2.imwrite` 는 **False** 를 돌려준다.
둘 다 예외를 던지지 않아서, 쓰는 쪽이 신경 쓰지 않으면 조용히 빠진다.
촬영 원본 프레임 이름에 한글이 들어간다(`20261112_R6_01_자유촬영_밝기미확인_f00000.jpg`).

numpy 로 파일을 직접 읽고 쓰면 경로를 타지 않는다. `training/extract_frames.py` 가 쓰는 방식과 같다.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def read_image(path: str | Path, flags: int = cv2.IMREAD_COLOR) -> np.ndarray | None:
    """사진을 읽는다. 파일이 없거나 사진으로 읽히지 않으면 None."""
    try:
        buf = np.fromfile(str(path), dtype=np.uint8)
    except OSError:
        return None
    if buf.size == 0:
        return None
    return cv2.imdecode(buf, flags)


def write_image(path: str | Path, img: np.ndarray, params: list[int] | None = None) -> None:
    """사진을 쓴다. 실패하면 조용히 넘어가지 않고 예외를 던진다."""
    path = Path(path)
    ok, buf = cv2.imencode(path.suffix or ".jpg", img, params or [])
    if not ok:
        raise RuntimeError(f"사진 인코딩 실패: {path}")
    buf.tofile(str(path))
