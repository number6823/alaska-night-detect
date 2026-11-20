"""server.app 시험. 실행: python -m unittest server.test_app -v   (httpx 가 필요하다: pip install httpx)"""

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from server.app import create_app

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"\xff\xd9"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.client = TestClient(
            create_app(str(self.root / "srv"), web_dist=str(self.root / "no_dist"))
        )

    def tearDown(self):
        self.tmp.cleanup()

    def post(self, image=JPEG, **fields):
        files = {"image": ("x.jpg", image, "image/jpeg")} if image is not None else None
        return self.client.post("/api/detections", data=fields, files=files)

    def test_health_starts_empty(self):
        self.assertEqual(
            self.client.get("/api/health").json(),
            {"ok": True, "count": 0, "flagged": 0},
        )
        self.assertEqual(self.client.get("/api/detections").json(), [])

    def test_post_saves_shot_and_returns_record(self):
        r = self.post(
            person=2, bicycle=1, top=0.91, ms=24, level=2, dist=3.1, at="21:48:12"
        )
        self.assertEqual(r.status_code, 201)
        d = r.json()
        self.assertEqual(d["id"], "CAP-1")
        self.assertEqual(d["at"], "21:48:12")
        self.assertEqual((d["person"], d["bicycle"], d["level"]), (2, 1, 2))
        self.assertFalse(d["false_alarm"])
        self.assertEqual(d["shot"], "api/shots/CAP-1.jpg")
        got = self.client.get("/" + d["shot"])
        self.assertEqual(got.status_code, 200)
        self.assertEqual(got.content, JPEG)

    def test_png_is_accepted(self):
        d = self.post(image=PNG, person=1).json()
        self.assertTrue(d["shot"].endswith(".png"))

    def test_post_without_image_works(self):
        d = self.post(image=None, person=1, level=1).json()
        self.assertEqual(d["shot"], "")

    def test_default_time_is_filled(self):
        d = self.post(person=1).json()
        self.assertRegex(d["at"], r"^\d{2}:\d{2}:\d{2}$")

    def test_list_is_newest_first_and_limited(self):
        for i in range(3):
            self.post(person=i)
        rows = self.client.get("/api/detections").json()
        self.assertEqual([r["id"] for r in rows], ["CAP-3", "CAP-2", "CAP-1"])
        self.assertEqual(len(self.client.get("/api/detections?limit=2").json()), 2)

    def test_patch_marks_false_alarm(self):
        self.post(person=1)
        r = self.client.patch("/api/detections/CAP-1", json={"false_alarm": True})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["false_alarm"])
        self.assertTrue(self.client.get("/api/detections").json()[0]["false_alarm"])
        r = self.client.patch("/api/detections/CAP-1", json={"false_alarm": False})
        self.assertFalse(r.json()["false_alarm"])

    def test_patch_unknown_is_404(self):
        self.assertEqual(
            self.client.patch(
                "/api/detections/CAP-99", json={"false_alarm": True}
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.patch(
                "/api/detections/abc", json={"false_alarm": True}
            ).status_code,
            404,
        )

    def test_bad_values_are_rejected(self):
        self.assertEqual(self.post(level=4).status_code, 422)
        self.assertEqual(self.post(person=-1).status_code, 422)
        self.assertEqual(self.post(top=1.5).status_code, 422)
        self.assertEqual(self.post(at="9:5").status_code, 422)
        # 거절된 요청은 기록을 남기지 않는다
        self.assertEqual(self.client.get("/api/health").json()["count"], 0)

    def test_non_image_is_rejected_and_leaves_nothing(self):
        self.assertEqual(self.post(image=b"not an image at all").status_code, 415)
        self.assertEqual(self.client.get("/api/health").json()["count"], 0)

    def test_oversize_is_rejected(self):
        big = b"\xff\xd8\xff" + b"\x00" * (5 * 1024 * 1024 + 10)
        self.assertEqual(self.post(image=big).status_code, 413)
        self.assertEqual(self.client.get("/api/health").json()["count"], 0)

    def test_shot_name_cannot_escape_folder(self):
        self.post(person=1)
        (self.root / "secret.txt").write_text("x")
        for bad in ("../secret.txt", "..%2Fsecret.txt", "CAP-1.jpg.exe", "x.jpg"):
            self.assertEqual(self.client.get(f"/api/shots/{bad}").status_code, 404, bad)

    def test_data_survives_restart(self):
        self.post(person=3)
        again = TestClient(
            create_app(str(self.root / "srv"), web_dist=str(self.root / "no_dist"))
        )
        self.assertEqual(again.get("/api/detections").json()[0]["person"], 3)

    def test_serves_built_web_without_hiding_api(self):
        dist = self.root / "dist"
        dist.mkdir()
        (dist / "index.html").write_text("<html>화면</html>", encoding="utf-8")
        client = TestClient(create_app(str(self.root / "srv2"), web_dist=str(dist)))
        self.assertIn("화면", client.get("/").text)
        self.assertEqual(client.get("/api/health").json()["ok"], True)

    def test_admin_path_serves_same_page_and_slash_redirects(self):
        dist = self.root / "dist_admin"
        dist.mkdir()
        (dist / "index.html").write_text("<html>화면</html>", encoding="utf-8")
        client = TestClient(create_app(str(self.root / "srv3"), web_dist=str(dist)))
        self.assertIn("화면", client.get("/admin").text)
        r = client.get("/admin/", follow_redirects=False)
        self.assertIn(r.status_code, (302, 307))
        self.assertEqual(r.headers["location"], "/admin")
        self.assertEqual(client.get("/api/health").json()["ok"], True)


class RawAndExportTest(unittest.TestCase):
    """원본 프레임 저장, 오경보 기록 보호, 재학습 자료 내보내기."""

    RAW = b"\xff\xd8\xff\xe1" + b"\x01" * 64 + b"\xff\xd9"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.srv = self.root / "srv"
        self.client = TestClient(
            create_app(
                str(self.srv), web_dist=str(self.root / "no_dist"), max_records=3
            )
        )

    def tearDown(self):
        self.tmp.cleanup()

    def post(self, raw=None, **fields):
        files = {"image": ("x.jpg", JPEG, "image/jpeg")}
        if raw is not None:
            files["raw"] = ("r.jpg", raw, "image/jpeg")
        return self.client.post("/api/detections", data=fields, files=files)

    def flag(self, det_id, on=True):
        return self.client.patch(f"/api/detections/{det_id}", json={"false_alarm": on})

    def test_raw_is_saved_but_not_listed_or_served(self):
        d = self.post(raw=self.RAW, person=1, level=1).json()
        self.assertTrue((self.srv / "shots" / "RAW-1.jpg").is_file())
        self.assertEqual(d["shot"], "api/shots/CAP-1.jpg")  # 목록에는 캡처만 나온다
        self.assertEqual(self.client.get("/api/shots/RAW-1.jpg").status_code, 404)

    def test_bad_raw_is_rejected_and_leaves_nothing(self):
        r = self.post(raw=b"not an image", person=1)
        self.assertEqual(r.status_code, 415)
        self.assertEqual(self.client.get("/api/health").json()["count"], 0)

    def test_old_database_is_migrated_and_keeps_records(self):
        import sqlite3

        old = self.root / "old"
        old.mkdir()
        con = sqlite3.connect(str(old / "detections.db"))
        con.execute(
            "CREATE TABLE detections (n INTEGER PRIMARY KEY AUTOINCREMENT, shot TEXT NOT NULL DEFAULT '', "
            "at TEXT NOT NULL, person INTEGER NOT NULL, bicycle INTEGER NOT NULL, top REAL NOT NULL, "
            "ms INTEGER NOT NULL, level INTEGER NOT NULL, dist REAL NOT NULL, "
            "false_alarm INTEGER NOT NULL DEFAULT 0)"
        )
        con.execute(
            "INSERT INTO detections (at, person, bicycle, top, ms, level, dist) VALUES ('10:00:00',1,0,0.9,20,2,3.0)"
        )
        con.commit()
        con.close()
        client = TestClient(create_app(str(old), web_dist=str(self.root / "no_dist")))
        rows = client.get("/api/detections").json()
        self.assertEqual([r["id"] for r in rows], ["CAP-1"])
        r = client.post(
            "/api/detections",
            data={"person": 1},
            files={"raw": ("r.jpg", self.RAW, "image/jpeg")},
        )
        self.assertEqual(r.status_code, 201)

    def test_flagged_records_survive_pruning(self):
        self.post(raw=self.RAW, person=1, level=1)  # CAP-1
        self.flag("CAP-1")
        for _ in range(6):  # max_records=3 이라 표시 안 한 오래된 기록은 지워진다
            self.post(person=1, level=1)
        ids = [r["id"] for r in self.client.get("/api/detections").json()]
        self.assertIn("CAP-1", ids)
        self.assertEqual(len(ids), 4)  # 표시한 1개 + 표시 안 한 최근 3개
        self.assertTrue((self.srv / "shots" / "RAW-1.jpg").is_file())
        self.assertEqual(self.client.get("/api/health").json()["flagged"], 1)

    def test_unflagged_record_is_pruned_with_its_raw_file(self):
        self.post(raw=self.RAW, person=1)  # CAP-1
        for _ in range(3):
            self.post(person=1)
        self.assertFalse((self.srv / "shots" / "RAW-1.jpg").exists())
        self.assertFalse((self.srv / "shots" / "CAP-1.jpg").exists())

    def test_export_zip_has_raw_images_empty_labels_and_manifest(self):
        import csv
        import io
        import zipfile

        self.post(raw=self.RAW, person=2, level=2, at="21:00:00")  # CAP-1 원본 있음
        self.post(person=1, level=1, at="21:00:05")  # CAP-2 원본 없음(캡처로 대체)
        self.post(person=1, level=1)  # CAP-3 표시 안 함
        self.flag("CAP-1")
        self.flag("CAP-2")
        r = self.client.get("/api/export/false-alarms")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["content-type"], "application/zip")
        z = zipfile.ZipFile(io.BytesIO(r.content))
        names = set(z.namelist())
        self.assertEqual(
            names,
            {
                "images/CAP-1.jpg",
                "images/CAP-2.jpg",
                "labels/CAP-1.txt",
                "labels/CAP-2.txt",
                "manifest.csv",
            },
        )
        self.assertEqual(z.read("images/CAP-1.jpg"), self.RAW)  # 원본
        self.assertEqual(z.read("images/CAP-2.jpg"), JPEG)  # 원본이 없어 캡처로 대체
        self.assertEqual(z.read("labels/CAP-1.txt"), b"")  # 빈 라벨 = 배경
        rows = list(csv.DictReader(io.StringIO(z.read("manifest.csv").decode("utf-8"))))
        self.assertEqual(
            [(x["id"], x["image"], x["level"]) for x in rows],
            [("CAP-1", "raw", "2"), ("CAP-2", "shot", "1")],
        )

    def test_export_without_flagged_is_404(self):
        self.post(person=1)
        self.assertEqual(self.client.get("/api/export/false-alarms").status_code, 404)

    def test_unflag_removes_from_export(self):
        self.post(person=1)
        self.flag("CAP-1")
        self.flag("CAP-1", on=False)
        self.assertEqual(self.client.get("/api/export/false-alarms").status_code, 404)

    def test_client_sends_raw_part(self):
        from server.client import _multipart

        body = _multipart({"person": 1}, JPEG, "BND", raw=self.RAW)
        self.assertIn(b'name="image"', body)
        self.assertIn(b'name="raw"', body)
        self.assertIn(self.RAW, body)
        self.assertNotIn(b'name="raw"', _multipart({"person": 1}, JPEG, "BND"))


if __name__ == "__main__":
    unittest.main()
