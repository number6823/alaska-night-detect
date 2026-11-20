"""후방 감지 기록 서버. Jetson 이 올린 캡처와 감지 정보를 모아 두고 web/ 화면에 보여 준다.

실행: python -m server [--host 127.0.0.1] [--port 8000] [--data data/server]
      (web/dist 가 있으면 같은 주소에서 화면도 열린다. 개발 중에는 web/ 에서 npm run dev 가 /api 를 여기로 넘긴다)

API (web/README.md 의 약속과 같다)
  GET   /api/detections         기록 목록. 최신이 먼저. ?limit=200
  POST  /api/detections         Jetson 이 올린다(multipart: image 와 person, bicycle, top, ms, level, dist, at)
  PATCH /api/detections/<id>    {"false_alarm": true} 오경보 표시
  GET   /api/shots/<파일>        캡처 이미지(박스와 거리선이 그려진 것)
  GET   /api/export/false-alarms  오경보로 표시한 기록의 원본 사진 + 빈 라벨(YOLO 배경) + 목록(zip). 재학습 자료용
  GET   /api/health             살아 있는지와 기록 수

저장: <data>/detections.db(SQLite) 와 <data>/shots/. data/ 는 레포에 올리지 않는다.
      runner 가 박스 없는 원본 프레임(raw)도 같이 올리면 shots/RAW-<번호>.jpg 로 저장한다(내보내기용, 직접 열람 API 는 없다).
      기록이 max_records 를 넘으면 오래된 것부터 지우지만 오경보로 표시한 기록은 지우지 않는다(재학습 자료).
      원본 프레임에는 얼굴이 찍힐 수 있다. 팀 안에서만 쓰고 외부 사이트에 올리기 전에는 모자이크한다.
주의: 로그인이 없다. 시연 노트북이나 Jetson 안에서, 같은 네트워크 안에서만 쓴다.
      인터넷에 열려면 먼저 인증을 붙인다(--host 0.0.0.0 으로 열기 전에 확인한다).
"""

import csv
import io
import os
import re
import sqlite3
import time
import zipfile
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
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
    false_alarm INTEGER NOT NULL DEFAULT 0,
    raw TEXT NOT NULL DEFAULT ''
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
    """표시 안 한 기록이 max_records 를 넘으면 오래된 것부터 지운다(캡처·원본 파일도). 디스크가 가득 차지 않게 한다.

    오경보로 표시한 기록은 재학습 자료라서 지우지 않는다(표시를 취소하면 다시 지우는 대상이 된다)."""
    old = con.execute(
        "SELECT n, shot, raw FROM detections WHERE false_alarm=0 ORDER BY n DESC LIMIT -1 OFFSET ?",
        (max_records,),
    ).fetchall()
    for r in old:
        for name in (r["shot"], r["raw"]):
            if name:
                try:
                    (shots / Path(name).name).unlink()
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
        # 예전에 만든 DB(raw 열이 없음)는 열만 더한다. 기록은 그대로 남는다.
        if "raw" not in {r["name"] for r in con.execute("PRAGMA table_info(detections)")}:
            con.execute("ALTER TABLE detections ADD COLUMN raw TEXT NOT NULL DEFAULT ''")
        con.commit()
    finally:
        con.close()  # sqlite3 의 with 는 닫지 않는다. 열어 두면 Windows 에서 파일이 잠긴다

    app = FastAPI(title="alaska 후방 감지 기록 서버")

    @app.get("/api/health")
    def health() -> dict:
        con = connect()
        try:
            n = con.execute("SELECT COUNT(*) FROM detections").fetchone()[0]
            flagged = con.execute(
                "SELECT COUNT(*) FROM detections WHERE false_alarm=1"
            ).fetchone()[0]
        finally:
            con.close()
        return {"ok": True, "count": n, "flagged": flagged}

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
        raw: Optional[UploadFile] = File(None),
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
        raw_data = b""
        raw_ext = None
        if raw is not None:  # 박스를 그리지 않은 원본 프레임(재학습 자료용). 없어도 된다
            raw_data = await raw.read(MAX_IMAGE_BYTES + 1)
            if len(raw_data) > MAX_IMAGE_BYTES:
                raise HTTPException(status_code=413, detail="원본이 5MB 를 넘는다")
            raw_ext = _image_ext(raw_data[:8])
            if raw_ext is None:
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
            if raw_ext is not None:
                raw_name = f"RAW-{n}.{raw_ext}"
                try:
                    (shots / raw_name).write_bytes(raw_data)
                except OSError:
                    con.rollback()
                    raise HTTPException(
                        status_code=500, detail="원본을 저장하지 못했다"
                    )
                con.execute("UPDATE detections SET raw=? WHERE n=?", (raw_name, n))
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

    @app.get("/api/export/false-alarms")
    def export_false_alarms() -> Response:
        """오경보로 표시한 기록을 재학습 자료 묶음(zip)으로 내려준다.

        images/<id>.jpg  박스 없는 원본 프레임(없으면 박스가 그려진 캡처)
        labels/<id>.txt  빈 파일 = YOLO 에서 "이 사진에는 사람도 자전거도 없다"(배경)
        manifest.csv     id, 시각, 단계, 박스 수, 신뢰도, 사진 종류(raw 원본 / shot 캡처 / none)
        사람이 실제로 있는 사진을 오경보로 표시하면 빈 라벨이 틀린 정답이 되므로 표시할 때 주의한다."""
        con = connect()
        try:
            rows = con.execute(
                "SELECT * FROM detections WHERE false_alarm=1 ORDER BY n"
            ).fetchall()
        finally:
            con.close()
        if not rows:
            raise HTTPException(status_code=404, detail="오경보로 표시한 기록이 없다")
        manifest = io.StringIO()
        w = csv.writer(manifest)
        w.writerow(["id", "at", "level", "person", "bicycle", "top", "dist", "image"])
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for r in rows:
                det_id = f"CAP-{r['n']}"
                src, kind = None, "none"
                for name, k in ((r["raw"], "raw"), (r["shot"], "shot")):
                    p = shots / Path(name).name if name else None
                    if p is not None and p.is_file():
                        src, kind = p, k
                        break
                if src is not None:
                    z.write(str(src), f"images/{det_id}{src.suffix}")
                    z.writestr(f"labels/{det_id}.txt", "")
                w.writerow([det_id, r["at"], r["level"], r["person"], r["bicycle"], r["top"], r["dist"], kind])
            z.writestr("manifest.csv", manifest.getvalue())
        return Response(
            content=buf.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="false_alarms.zip"'},
        )

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
        index = dist_dir / "index.html"
        if index.is_file():
            # / 는 운전자 화면, /admin 은 관리자 화면. 같은 index.html 을 주고 화면은 주소를 보고 정한다.
            @app.get("/admin", include_in_schema=False)
            def admin_page():
                return FileResponse(str(index))

            @app.get("/admin/", include_in_schema=False)
            def admin_page_slash():
                # 뒤에 /가 붙으면 화면 파일의 상대 경로가 깨지므로 /admin 으로 돌린다
                return RedirectResponse("/admin")

        # 반드시 API 경로를 다 등록한 뒤에 붙인다(먼저 붙이면 / 가 모든 경로를 가로챈다)
        app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="web")

    return app
