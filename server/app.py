"""후방 감지 기록 서버. Jetson 이 올린 캡처와 감지 정보를 모아 두고 web/ 화면에 보여 준다.

실행: python -m server [--host 127.0.0.1] [--port 8000] [--data data/server]
      (web/dist 가 있으면 같은 주소에서 화면도 열린다. 개발 중에는 web/ 에서 npm run dev 가 /api 를 여기로 넘긴다)

API (web/README.md 의 약속과 같다)
  GET   /api/detections         기록 목록. 최신이 먼저. ?limit=200
  POST  /api/detections         Jetson 이 올린다(multipart: image 와 person, bicycle, top, ms, level, dist, at)
  PATCH /api/detections/<id>    {"false_alarm": true} 오경보 표시
  GET   /api/shots/<파일>        캡처 이미지
  GET   /api/health             살아 있는지와 기록 수

저장: <data>/detections.db(SQLite) 와 <data>/shots/. data/ 는 레포에 올리지 않는다.
주의: 로그인이 없다. 시연 노트북이나 Jetson 안에서, 같은 네트워크 안에서만 쓴다.
      인터넷에 열려면 먼저 인증을 붙인다(--host 0.0.0.0 으로 열기 전에 확인한다).
"""

import os
import re
import sqlite3
import time
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .runner_api import build_router

MAX_IMAGE_BYTES = 5 * 1024 * 1024
SHOT_NAME = re.compile(r"^CAP-\d+\.(jpg|png)$")
TIME_RE = re.compile(r"^\d{2}:\d{2}:\d{2}$")
JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

SCHEMA = """
CREATE TABLE IF NOT EXISTS detections (
    n INTEGER PRIMARY KEY AUTOINCREMENT,
    shot TEXT NOT NULL DEFAULT '',
    at TEXT NOT NULL,
    person INTEGER NOT NULL,
    bicycle INTEGER NOT NULL,
    top REAL NOT NULL,
    ms INTEGER NOT NULL,
    level INTEGER NOT NULL,
    dist REAL NOT NULL,
    false_alarm INTEGER NOT NULL DEFAULT 0
)
"""


class Detection(BaseModel):
    """web/src/types.ts 의 Detection 과 같은 모양(false_alarm 이 더 있다)."""

    id: str
    shot: str
    at: str
    person: int
    bicycle: int
    top: float
    ms: int
    level: int
    dist: float
    false_alarm: bool = False


class FlagBody(BaseModel):
    false_alarm: bool


def _row(r) -> Detection:
    return Detection(
        id=f"CAP-{r['n']}",
        shot=r["shot"],
        at=r["at"],
        person=r["person"],
        bicycle=r["bicycle"],
        top=r["top"],
        ms=r["ms"],
        level=r["level"],
        dist=r["dist"],
        false_alarm=bool(r["false_alarm"]),
    )


def _image_ext(head: bytes) -> Optional[str]:
    if head.startswith(JPEG_MAGIC):
        return "jpg"
    if head.startswith(PNG_MAGIC):
        return "png"
    return None


def _prune(con, shots: Path, max_records: int) -> int:
    """기록이 max_records 를 넘으면 오래된 것부터 지운다(캡처 파일도). 디스크가 가득 차지 않게 한다."""
    old = con.execute(
        "SELECT n, shot FROM detections ORDER BY n DESC LIMIT -1 OFFSET ?", (max_records,)
    ).fetchall()
    for r in old:
        if r["shot"]:
            try:
                (shots / Path(r["shot"]).name).unlink()
            except FileNotFoundError:
                pass
        con.execute("DELETE FROM detections WHERE n=?", (r["n"],))
    return len(old)


def create_app(
    data_dir: Optional[str] = None,
    web_dist: Optional[str] = None,
    runner_dir: Optional[str] = None,
    max_records: int = 1000,
) -> FastAPI:
    """data_dir 에 DB 와 캡처를 둔다. web_dist 가 있으면 화면도 같이 보여 준다.

    runner_dir 은 runner(감지 프로그램)가 상태·미리보기를 쓰고 설정·명령을 읽는 폴더다(기본 data/runner).
    max_records 를 넘는 오래된 기록과 캡처는 자동으로 지운다."""
    root = Path(data_dir or os.environ.get("ALASKA_SERVER_DIR", "data/server"))
    shots = root / "shots"
    shots.mkdir(parents=True, exist_ok=True)
    db_path = root / "detections.db"

    def connect() -> sqlite3.Connection:
        con = sqlite3.connect(str(db_path))
        con.row_factory = sqlite3.Row
        return con

    con = connect()
    try:
        con.execute(SCHEMA)
        con.commit()
    finally:
        con.close()  # sqlite3 의 with 는 닫지 않는다. 열어 두면 Windows 에서 파일이 잠긴다

    app = FastAPI(title="alaska 후방 감지 기록 서버")

    @app.get("/api/health")
    def health() -> dict:
        con = connect()
        try:
            n = con.execute("SELECT COUNT(*) FROM detections").fetchone()[0]
        finally:
            con.close()
        return {"ok": True, "count": n}

    @app.get("/api/detections", response_model=List[Detection])
    def list_detections(limit: int = 200) -> List[Detection]:
        limit = max(1, min(limit, 1000))
        con = connect()
        try:
            rows = con.execute(
                "SELECT * FROM detections ORDER BY n DESC LIMIT ?", (limit,)
            ).fetchall()
        finally:
            con.close()
        return [_row(r) for r in rows]

    @app.post("/api/detections", response_model=Detection, status_code=201)
    async def add_detection(
        person: int = Form(0, ge=0),
        bicycle: int = Form(0, ge=0),
        top: float = Form(0.0, ge=0.0, le=1.0),
        ms: int = Form(0, ge=0),
        level: int = Form(0, ge=0, le=3),
        dist: float = Form(0.0, ge=0.0),
        at: Optional[str] = Form(None),
        image: Optional[UploadFile] = File(None),
    ) -> Detection:
        if at is not None and not TIME_RE.match(at):
            raise HTTPException(
                status_code=422, detail="at 은 HH:MM:SS 모양이어야 한다"
            )
        data = b""
        ext = None
        if image is not None:
            data = await image.read(MAX_IMAGE_BYTES + 1)
            if len(data) > MAX_IMAGE_BYTES:
                raise HTTPException(status_code=413, detail="캡처가 5MB 를 넘는다")
            ext = _image_ext(data[:8])
            if ext is None:
                raise HTTPException(status_code=415, detail="jpg 나 png 만 받는다")
        when = at or time.strftime("%H:%M:%S")

        con = connect()
        try:
            cur = con.execute(
                "INSERT INTO detections (at, person, bicycle, top, ms, level, dist) VALUES (?,?,?,?,?,?,?)",
                (when, person, bicycle, top, ms, level, dist),
            )
            n = cur.lastrowid
            if ext is not None:
                # 파일 이름은 서버가 정한다. 올린 사람이 준 이름은 쓰지 않는다(경로 조작 방지)
                name = f"CAP-{n}.{ext}"
                try:
                    (shots / name).write_bytes(data)
                except OSError:
                    con.rollback()
                    raise HTTPException(
                        status_code=500, detail="캡처를 저장하지 못했다"
                    )
                con.execute(
                    "UPDATE detections SET shot=? WHERE n=?", (f"api/shots/{name}", n)
                )
            _prune(con, shots, max_records)
            con.commit()
            row = con.execute("SELECT * FROM detections WHERE n=?", (n,)).fetchone()
        finally:
            con.close()
        return _row(row)

    @app.patch("/api/detections/{det_id}", response_model=Detection)
    def flag_detection(det_id: str, body: FlagBody) -> Detection:
        m = re.fullmatch(r"CAP-(\d+)", det_id)
        if not m:
            raise HTTPException(status_code=404, detail="없는 기록")
        n = int(m.group(1))
        con = connect()
        try:
            cur = con.execute(
                "UPDATE detections SET false_alarm=? WHERE n=?",
                (int(body.false_alarm), n),
            )
            con.commit()
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="없는 기록")
            row = con.execute("SELECT * FROM detections WHERE n=?", (n,)).fetchone()
        finally:
            con.close()
        return _row(row)

    @app.get("/api/shots/{name}")
    def get_shot(name: str):
        if not SHOT_NAME.match(name):
            raise HTTPException(status_code=404, detail="없는 캡처")
        path = shots / name
        if not path.is_file():
            raise HTTPException(status_code=404, detail="없는 캡처")
        return FileResponse(str(path))

    rdir = Path(runner_dir or os.environ.get("ALASKA_RUNNER_DIR", "data/runner"))
    app.include_router(build_router(rdir))

    dist_dir = Path(web_dist) if web_dist else Path("web/dist")
    if dist_dir.is_dir():
        # 반드시 API 경로를 다 등록한 뒤에 붙인다(먼저 붙이면 / 가 모든 경로를 가로챈다)
        app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="web")

    return app
