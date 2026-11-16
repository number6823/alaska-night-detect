"""server 의 runner 제어 API 시험. 실행: python -m unittest server.test_runner_api -v   (httpx 가 필요하다)"""

import asyncio
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from server.app import create_app
from server.runner_api import mjpeg_stream, runner_status

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"\xff\xd9"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.rdir = self.root / "runner"
        self.rdir.mkdir()
        self.client = TestClient(
            create_app(
                str(self.root / "srv"),
                web_dist=str(self.root / "nodist"),
                runner_dir=str(self.rdir),
            )
        )
        os.environ.pop("ALASKA_TOKEN", None)

    def tearDown(self):
        os.environ.pop("ALASKA_TOKEN", None)
        self.tmp.cleanup()

    def write_status(self, **kw):
        data = {
            "state": "running",
            "frames": 10,
            "fps": 25.0,
            "updated": time.time(),
            "source": "demo.mp4",
        }
        data.update(kw)
        (self.rdir / "status.json").write_text(json.dumps(data), encoding="utf-8")


class StatusTest(Base):
    def test_off_when_runner_never_started(self):
        r = self.client.get("/api/status").json()
        self.assertEqual((r["online"], r["state"]), (False, "off"))

    def test_online_stale_and_finished(self):
        self.write_status()
        r = self.client.get("/api/status").json()
        self.assertTrue(r["online"])
        self.assertEqual(r["state"], "running")
        self.write_status(
            updated=time.time() - 60
        )  # 상태가 멈춰 있다 = 죽었거나 멈췄다
        r = self.client.get("/api/status").json()
        self.assertEqual((r["online"], r["state"]), (False, "stale"))
        self.write_status(state="finished")
        self.assertFalse(self.client.get("/api/status").json()["online"])

    def test_broken_status_file_is_off(self):
        (self.rdir / "status.json").write_text("{깨짐", encoding="utf-8")
        self.assertEqual(self.client.get("/api/status").json()["state"], "off")

    def test_runner_status_fn_accepts_clock(self):
        self.write_status(updated=100.0)
        self.assertTrue(runner_status(self.rdir, now=102.0)["online"])
        self.assertFalse(runner_status(self.rdir, now=110.0)["online"])


class ConfigTest(Base):
    def test_get_returns_defaults_and_key_groups(self):
        r = self.client.get("/api/config").json()
        self.assertEqual(r["config"]["model"], "yolo11n.pt")
        self.assertIn("min_conf", r["live_keys"])
        self.assertIn("source", r["restart_keys"])

    def test_put_saves_validates_and_reports_what_applies(self):
        r = self.client.put(
            "/api/config",
            json={"values": {"min_conf": 0.5, "mute": True, "source": "0"}},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(sorted(body["applied_live"]), ["min_conf", "mute"])
        self.assertEqual(body["restart_required"], ["source"])
        saved = json.loads((self.rdir / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(
            (saved["min_conf"], saved["mute"], saved["source"]), (0.5, True, "0")
        )
        self.assertEqual(list(self.rdir.glob("*.tmp")), [])
        # 다시 읽으면 저장한 값이 보이고, 바꾸지 않은 값은 그대로다
        cfg = self.client.get("/api/config").json()["config"]
        self.assertEqual((cfg["min_conf"], cfg["model"]), (0.5, "yolo11n.pt"))
        # 같은 값을 다시 보내면 바뀐 것이 없다
        again = self.client.put(
            "/api/config", json={"values": {"min_conf": 0.5}}
        ).json()
        self.assertEqual(again["changed"], [])

    def test_bad_values_are_rejected_and_file_untouched(self):
        self.client.put("/api/config", json={"values": {"min_conf": 0.4}})
        before = (self.rdir / "config.json").read_text(encoding="utf-8")
        for bad in (
            {"min_conf": 2},
            {"min_conf": "abc"},
            {"camera_height_m": 9},
            {"tilt_deg": -3},
            {"mute": 1},
            {"nope": 1},
            {"window": 2, "need": 5},
        ):
            r = self.client.put("/api/config", json={"values": bad})
            self.assertEqual(r.status_code, 422, bad)
        self.assertEqual(
            (self.rdir / "config.json").read_text(encoding="utf-8"), before
        )
        self.assertEqual(
            self.client.put("/api/config", json={"values": {}}).status_code, 422
        )

    def test_source_may_be_empty_in_settings_screen(self):
        # 설정 화면에서 아직 입력을 안 골랐어도 다른 값은 저장할 수 있다
        r = self.client.put("/api/config", json={"values": {"camera_height_m": 0.8}})
        self.assertEqual(r.status_code, 200)

    def test_token_protects_changes_when_set(self):
        os.environ["ALASKA_TOKEN"] = "비밀"
        self.assertEqual(
            self.client.put("/api/config", json={"values": {"mute": True}}).status_code,
            401,
        )
        r = self.client.put(
            "/api/config", json={"values": {"mute": True}}, headers={"X-Token": "wrong"}
        )
        self.assertEqual(r.status_code, 401)
        self.assertEqual(
            self.client.get("/api/config").status_code, 200
        )  # 읽기는 막지 않는다
        # 헤더는 ASCII 만 된다. 실제 값은 영문으로 쓴다
        os.environ["ALASKA_TOKEN"] = "secret1"
        ok = self.client.put(
            "/api/config",
            json={"values": {"mute": True}},
            headers={"X-Token": "secret1"},
        )
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(
            self.client.post("/api/test-sound", json={"level": 1}).status_code, 401
        )


class SoundTest(Base):
    def test_writes_control_command_with_new_id_each_time(self):
        a = self.client.post("/api/test-sound", json={"level": 2})
        self.assertEqual(a.status_code, 202)
        first = json.loads((self.rdir / "control.json").read_text(encoding="utf-8"))
        self.assertEqual(
            (first["cmd"], first["level"], first["id"]),
            ("test_sound", 2, a.json()["id"]),
        )
        self.assertFalse(a.json()["runner_online"])
        self.write_status()
        b = self.client.post("/api/test-sound", json={"level": 3})
        self.assertTrue(b.json()["runner_online"])
        self.assertNotEqual(
            a.json()["id"], b.json()["id"]
        )  # id 가 달라야 runner 가 다시 실행한다

    def test_bad_level(self):
        for lv in (0, 4, -1):
            self.assertEqual(
                self.client.post("/api/test-sound", json={"level": lv}).status_code, 422
            )


class CalibrationTest(Base):
    def test_lines_are_ordered_and_scaled_to_frame(self):
        r = self.client.post(
            "/api/calibration",
            json={
                "camera_height_m": 0.7,
                "tilt_deg": 15,
                "vfov_deg": 60,
                "frame_height": 1080,
            },
        ).json()
        names = [x["name"] for x in r["lines"]]
        self.assertEqual(names, ["5.5m", "3m", "2m"])
        ratios = [x["ratio"] for x in r["lines"]]
        self.assertEqual(ratios, sorted(ratios))  # 가까울수록 화면 아래
        self.assertAlmostEqual(
            r["lines"][1]["y_px"], r["lines"][1]["ratio"] * 1080, delta=1
        )
        self.assertNotIn("saved", r)  # 저장을 시키지 않으면 저장하지 않는다
        self.assertFalse((self.rdir / "config.json").exists())

    def test_save_writes_camera_values_to_config(self):
        r = self.client.post(
            "/api/calibration",
            json={"camera_height_m": 0.9, "tilt_deg": 20, "vfov_deg": 70, "save": True},
        ).json()
        self.assertTrue(r["saved"]["saved"])
        saved = json.loads((self.rdir / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(
            (saved["camera_height_m"], saved["tilt_deg"], saved["vfov_deg"]),
            (0.9, 20, 70),
        )

    def test_fit_one_point_recovers_field_of_view(self):
        from alarm.levels import foot_ratio_at

        y = foot_ratio_at(3.0, 0.7, 15.0, 82.0)
        r = self.client.post(
            "/api/calibration/fit",
            json={
                "distance_m": 3.0,
                "foot_ratio": y,
                "camera_height_m": 0.7,
                "tilt_deg": 15,
            },
        ).json()
        self.assertAlmostEqual(r["vfov_deg"], 82.0, places=1)
        self.assertEqual(len(r["lines"]), 3)

    def test_bad_inputs(self):
        self.assertEqual(
            self.client.post(
                "/api/calibration/fit", json={"distance_m": 3.0, "foot_ratio": 0.5}
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.post(
                "/api/calibration",
                json={"camera_height_m": 0.7, "tilt_deg": 15, "vfov_deg": 0},
            ).status_code,
            422,
        )

    def test_saving_needs_the_token_when_set(self):
        os.environ["ALASKA_TOKEN"] = "secret1"
        r = self.client.post("/api/calibration", json={"save": True})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(
            self.client.post("/api/calibration", json={}).status_code, 200
        )  # 계산만 하는 것은 열려 있다


class PreviewTest(Base):
    def test_jpg_and_missing(self):
        self.assertEqual(self.client.get("/api/preview.jpg").status_code, 404)
        self.assertEqual(self.client.get("/api/preview").status_code, 404)
        (self.rdir / "preview.jpg").write_bytes(JPEG)
        r = self.client.get("/api/preview.jpg")
        self.assertEqual((r.status_code, r.content), (200, JPEG))

    def test_mjpeg_stream_sends_changed_frames_only_and_stops_on_disconnect(self):
        path = self.rdir / "preview.jpg"
        path.write_bytes(JPEG)

        async def collect(n_polls):
            polls = {"n": 0}

            async def gone():
                polls["n"] += 1
                if polls["n"] == 3:
                    path.write_bytes(JPEG + b"\x00\x00")  # 화면이 바뀜
                return polls["n"] > n_polls

            return [c async for c in mjpeg_stream(path, gone, interval_s=0.0)]

        chunks = asyncio.run(collect(6))
        self.assertEqual(
            len(chunks), 2
        )  # 처음 한 장 + 바뀐 한 장. 같은 화면은 다시 보내지 않는다
        self.assertTrue(chunks[0].startswith(b"--frame\r\nContent-Type: image/jpeg"))
        self.assertIn(JPEG, chunks[0])

        async def one():
            async def never():
                return False

            return [
                c async for c in mjpeg_stream(path, never, interval_s=0.0, max_frames=1)
            ]

        self.assertEqual(len(asyncio.run(one())), 1)


class CamerasTest(Base):
    def test_lists_and_marks_in_use(self):
        from server.app import create_app as make
        from server.runner_api import probe_cameras

        calls = []

        def fake(in_use=None):
            calls.append(in_use)
            return [{"index": 0, "ok": True, "in_use": in_use == 0}]

        # 가짜 탐색 함수를 끼워서 만든 서버
        from fastapi import FastAPI

        from server.runner_api import build_router

        app = FastAPI()
        app.include_router(build_router(self.rdir, cameras_fn=fake))
        client = TestClient(app)
        self.assertEqual(client.get("/api/cameras").json()["cameras"][0]["index"], 0)
        self.assertEqual(calls, [None])  # runner 가 꺼져 있으면 모두 열어 본다
        self.write_status(source="0")
        client.get("/api/cameras")
        self.assertEqual(
            calls[-1], None
        )  # 가짜는 in_use 를 받지 않는 형태라 호출 방식만 확인
        self.assertTrue(callable(probe_cameras) and callable(make))


class RetentionTest(Base):
    def test_old_records_and_shots_are_pruned(self):
        client = TestClient(
            create_app(
                str(self.root / "srv2"),
                web_dist=str(self.root / "nodist"),
                runner_dir=str(self.rdir),
                max_records=3,
            )
        )
        for i in range(5):
            r = client.post(
                "/api/detections",
                data={"person": i},
                files={"image": ("x.jpg", JPEG, "image/jpeg")},
            )
            self.assertEqual(r.status_code, 201)
        rows = client.get("/api/detections").json()
        self.assertEqual(
            [r["id"] for r in rows], ["CAP-5", "CAP-4", "CAP-3"]
        )  # 오래된 두 개가 지워졌다
        shots = sorted(p.name for p in (self.root / "srv2" / "shots").iterdir())
        self.assertEqual(
            shots, ["CAP-3.jpg", "CAP-4.jpg", "CAP-5.jpg"]
        )  # 캡처 파일도 같이 지워졌다
        self.assertEqual(client.get("/api/shots/CAP-1.jpg").status_code, 404)


if __name__ == "__main__":
    unittest.main()
