"""Jetson 에서 감지 결과를 서버로 올리는 함수. 표준 라이브러리만 쓴다(Jetson 에 requests 가 없어도 된다).

    from server.client import post_detection
    post_detection("http://192.168.0.10:8000", jpeg_bytes, person=1, bicycle=0, top=0.91, ms=24, level=2, dist=3.1)

실패하면 예외를 던진다. 경고음은 서버와 상관없이 울려야 하므로, 부르는 쪽에서 try/except 로 감싸
서버가 죽어도 경보가 멈추지 않게 한다.
"""

import json
import urllib.request
import uuid
from typing import Optional


def _multipart(fields: dict, image: Optional[bytes], boundary: str) -> bytes:
    parts = []
    for key, value in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode(
                "utf-8"
            )
        )
    if image is not None:
        parts.append(
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="shot.jpg"\r\n'
                "Content-Type: image/jpeg\r\n\r\n"
            ).encode("utf-8")
        )
        parts.append(image + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts)


def post_detection(
    base_url: str,
    image_jpeg: Optional[bytes],
    person: int = 0,
    bicycle: int = 0,
    top: float = 0.0,
    ms: int = 0,
    level: int = 0,
    dist: float = 0.0,
    at: Optional[str] = None,
    timeout: float = 3.0,
) -> dict:
    """캡처(JPEG 바이트)와 감지 정보를 올리고, 서버가 만든 기록(dict)을 돌려준다."""
    fields = {
        "person": person,
        "bicycle": bicycle,
        "top": top,
        "ms": ms,
        "level": level,
        "dist": dist,
    }
    if at:
        fields["at"] = at
    boundary = uuid.uuid4().hex
    body = _multipart(fields, image_jpeg, boundary)
    req = urllib.request.Request(
        base_url.rstrip("/") + "/api/detections",
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.loads(res.read().decode("utf-8"))
