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
            self.client.get("/api/health").json(), {"ok": True, "count": 0}
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


if __name__ == "__main__":
    unittest.main()
