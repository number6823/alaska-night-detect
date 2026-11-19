"""runner 시험. 실행: python -m unittest runner.test_runner -v

모델·카메라·서버·스피커는 가짜로 바꿔 끼워서 로직만 확인한다(ultralytics 를 불러오지 않는다).
"""

import io
import json
import tempfile
import time
import unittest
import wave
from pathlib import Path

import cv2
import numpy as np

from alarm.levels import Calibration
from runner.app import run
from runner.config import RunnerConfig, build_config, load_config_file
from runner.pipeline import LEVEL_DISTANCE_M, Pipeline
from runner.sound import PATTERNS, Beeper, pattern_duration_s, pattern_wav
from runner.sources import VideoSource, parse_source
from runner.spool import Reporter, Spool
from runner.status import StatusWriter, atomic_write, draw_overlay, encode_jpeg

H, W = 240, 320
CAL = Calibration(foot_5_5=0.55, foot_3=0.70, foot_2=0.85, frame_height=H)


def box(foot_ratio, conf=0.9, cls=0):
    y2 = foot_ratio * H
    return (100, y2 - 80, 160, y2, conf, cls)


def make_video(path, frames=30, fps=10):
    w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H))
    for i in range(frames):
        img = np.full((H, W, 3), 40 + i, np.uint8)
        w.write(img)
    w.release()


class ConfigTest(unittest.TestCase):
    def test_defaults_and_validation(self):
        cfg = build_config({}, {"source": "a.mp4"})
        self.assertEqual(cfg.model, "yolo11n.pt")
        for bad in (
            {"min_conf": 1.5},
            {"camera_height_m": 9},
            {"tilt_deg": -1},
            {"need": 5, "window": 3},
        ):
            with self.assertRaises(ValueError, msg=str(bad)):
                build_config({}, dict({"source": "a.mp4"}, **bad))
        with self.assertRaises(ValueError):
            build_config({}, {})  # source 가 없다

    def test_cli_beats_file_and_none_is_ignored(self):
        cfg = build_config(
            {"source": "file.mp4", "min_conf": 0.5},
            {"source": "cli.mp4", "min_conf": None},
        )
        self.assertEqual((cfg.source, cfg.min_conf), ("cli.mp4", 0.5))

    def test_unknown_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.json"
            p.write_text(
                json.dumps({"source": "a", "mute_sound": True}), encoding="utf-8"
            )
            with self.assertRaises(ValueError):
                load_config_file(str(p))
            p.write_text(json.dumps({"source": "a", "mute": True}), encoding="utf-8")
            self.assertTrue(load_config_file(str(p))["mute"])


class PipelineTest(unittest.TestCase):
    def pipe(self, **kw):
        self.now = 0.0
        return Pipeline(CAL, clock=lambda: self.now, **kw)

    def test_levels_follow_foot_position_with_two_of_three_rule(self):
        p = self.pipe()
        self.assertEqual(p.process([box(0.40)]).alarm_level, 0)
        self.assertEqual(p.process([box(0.90)]).alarm_level, 0)  # 한 번만 잡힘
        self.assertEqual(p.process([box(0.90)]).alarm_level, 3)  # 두 번째에 울림

    def test_counts_filter_class_and_confidence(self):
        p = self.pipe()
        r = p.process(
            [box(0.9, 0.9, 0), box(0.9, 0.8, 1), box(0.9, 0.9, 2), box(0.9, 0.1, 0)]
        )
        self.assertEqual(
            (r.person, r.bicycle), (1, 1)
        )  # 자동차(2)와 낮은 신뢰도는 센다
        self.assertAlmostEqual(r.top, 0.9)

    def test_car_only_never_alarms(self):
        p = self.pipe()
        for _ in range(5):
            self.assertEqual(p.process([box(0.9, 0.95, 2)]).alarm_level, 0)

    def test_post_on_rising_then_throttled(self):
        p = self.pipe(post_interval_s=2.0)
        self.assertFalse(p.process([box(0.60)]).should_post)  # 아직 경보 아님
        r = p.process([box(0.60)])
        self.assertTrue(r.should_post)  # 0 -> 1 바로 올린다
        self.assertFalse(p.process([box(0.60)]).should_post)  # 같은 단계, 간격 안
        self.now += 2.1
        self.assertTrue(p.process([box(0.60)]).should_post)  # 간격이 지났다
        # 단계가 올라가면 간격과 상관없이 바로
        p.process([box(0.90)])
        r = p.process([box(0.90)])
        self.assertEqual(r.alarm_level, 3)
        self.assertTrue(r.should_post)

    def test_new_event_after_quiet(self):
        p = self.pipe(post_interval_s=100)
        for _ in range(2):
            p.process([box(0.9)])
        for _ in range(3):
            self.assertFalse(p.process([]).should_post)  # 사라짐
        p.process([box(0.9)])
        self.assertTrue(
            p.process([box(0.9)]).should_post
        )  # 새 사건이라 간격과 상관없이

    def test_distance_names(self):
        self.assertEqual(LEVEL_DISTANCE_M, {0: 0.0, 1: 5.5, 2: 3.0, 3: 2.0})


class SoundTest(unittest.TestCase):
    def test_wav_is_valid_and_levels_differ(self):
        lengths = []
        for lvl in PATTERNS:
            with wave.open(io.BytesIO(pattern_wav(lvl)), "rb") as w:
                self.assertEqual((w.getnchannels(), w.getsampwidth()), (1, 2))
                lengths.append(w.getnframes() / w.getframerate())
            self.assertAlmostEqual(lengths[-1], pattern_duration_s(lvl), delta=0.01)
        self.assertEqual(
            len(set(round(x, 2) for x in lengths)), 3
        )  # 단계마다 길이(삐 개수)가 다르다

    def test_beep_cadence_and_mute(self):
        now = [0.0]
        heard = []
        b = Beeper(
            player=lambda wav: heard.append(len(wav)) or True, clock=lambda: now[0]
        )
        try:
            self.assertTrue(b.update(3))
            time.sleep(0.2)
            self.assertFalse(b.update(3))  # 간격 안이라 또 울리지 않는다
            now[0] += 5.0
            self.assertTrue(b.update(1))
            time.sleep(0.2)
            self.assertEqual(len(heard), 2)
            self.assertFalse(b.update(0))
        finally:
            b.close()
        quiet = []
        m = Beeper(mute=True, player=lambda wav: quiet.append(1) or True)
        try:
            m.update(3)
            time.sleep(0.1)
            self.assertEqual(quiet, [])
            self.assertEqual(len(m.played), 1)  # 기록은 남기되 재생은 안 한다
        finally:
            m.close()

    def test_escalation_beeps_immediately_but_same_level_waits(self):
        b = Beeper(player=lambda wav: True, clock=lambda: 0.0)  # 시계가 멈춰 있어도
        try:
            self.assertTrue(b.update(1))
            self.assertFalse(b.update(1))  # 같은 단계는 간격을 기다린다
            self.assertTrue(b.update(2))  # 단계가 올라가면 바로
            self.assertTrue(b.update(3))
            self.assertFalse(b.update(2))  # 내려갈 때는 기다린다
            b.update(0)  # 경보가 꺼졌다
            self.assertTrue(b.update(1))  # 새 사건은 바로
        finally:
            b.close()
        self.assertEqual([lvl for _, lvl in b.played], [1, 2, 3, 1])

    def test_player_failure_does_not_break(self):
        def boom(_):
            raise OSError("스피커 없음")

        b = Beeper(player=boom, clock=lambda: 0.0)
        try:
            b.update(2)
            time.sleep(0.2)
        finally:
            b.close()


class SourceTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_source("0"), ("camera", 0))
        self.assertEqual(parse_source("rtsp://1.2.3.4/x")[0], "stream")
        self.assertEqual(parse_source("http://phone:8080/video")[0], "stream")
        self.assertEqual(parse_source("C:/a/b.mp4")[0], "file")

    def test_file_with_korean_path_and_end(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / "자유촬영_밝기미확인"
            folder.mkdir()
            vid = folder / "20261116_R5_01_보행접근.mp4"
            make_video(vid, frames=12)
            src = VideoSource(str(vid))
            n = 0
            while src.read() is not None:
                n += 1
            self.assertEqual(n, 12)
            self.assertTrue(src.is_file)
            self.assertFalse(src.reopen())
            src.release()

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            VideoSource("없는파일.mp4")


class SpoolTest(unittest.TestCase):
    def test_order_flush_and_failure_stops(self):
        with tempfile.TemporaryDirectory() as d:
            sp = Spool(d)
            for i in range(3):
                sp.put(b"\xff\xd8\xff" + bytes([i]), {"person": i})
            self.assertEqual(sp.count(), 3)
            got = []

            def ok(jpeg, meta):
                got.append(meta["person"])

            self.assertEqual(sp.flush(ok), 3)
            self.assertEqual(got, [0, 1, 2])  # 오래된 것부터
            self.assertEqual(sp.count(), 0)
            self.assertEqual(list(Path(d).glob("*.jpg")), [])  # 사진도 같이 지운다

            for i in range(3):
                sp.put(None, {"person": i})
            calls = []

            def fail_on_second(jpeg, meta):
                calls.append(meta["person"])
                if meta["person"] == 1:
                    raise ConnectionError("서버 꺼짐")

            self.assertEqual(sp.flush(fail_on_second), 1)
            self.assertEqual(sp.count(), 2)  # 실패한 것부터 남는다

    def test_cap_drops_oldest(self):
        with tempfile.TemporaryDirectory() as d:
            sp = Spool(d, max_items=3)
            for i in range(5):
                sp.put(None, {"n": i})
            kept = [json.loads(p.read_text())["n"] for p in sp.pending()]
            self.assertEqual(kept, [2, 3, 4])


class ReporterTest(unittest.TestCase):
    def wait(self, cond, seconds=3.0):
        end = time.time() + seconds
        while time.time() < end:
            if cond():
                return True
            time.sleep(0.02)
        return False

    def test_server_down_then_back(self):
        with tempfile.TemporaryDirectory() as d:
            up = [False]
            received = []

            def post(url, jpeg, timeout=0, **meta):
                if not up[0]:
                    raise ConnectionError("서버 꺼짐")
                received.append(meta["person"])
                return {}

            rep = Reporter("http://x", Spool(d), post_fn=post, retry_s=0.05)
            try:
                rep.submit(b"\xff\xd8\xff", {"person": 1})
                rep.submit(b"\xff\xd8\xff", {"person": 2})
                self.assertTrue(
                    self.wait(lambda: rep.spool.count() == 2)
                )  # 서버가 죽어 있어 쌓인다
                up[0] = True  # 서버가 살아났다 — 새 기록 없이도 다시 올라가야 한다
                self.assertTrue(self.wait(lambda: sorted(received) == [1, 2]))
                self.assertTrue(self.wait(lambda: rep.spool.count() == 0))
            finally:
                rep.close()

    def test_submit_does_not_block_on_slow_server(self):
        with tempfile.TemporaryDirectory() as d:

            def slow(url, jpeg, timeout=0, **meta):
                time.sleep(0.5)
                return {}

            rep = Reporter("http://x", Spool(d), post_fn=slow, retry_s=0.05)
            try:
                t0 = time.time()
                for i in range(5):
                    rep.submit(None, {"person": i})
                self.assertLess(
                    time.time() - t0, 0.2
                )  # 영상 처리를 기다리게 하지 않는다
            finally:
                rep.close(wait_s=0.1)


class StatusTest(unittest.TestCase):
    def test_atomic_write_and_throttle(self):
        with tempfile.TemporaryDirectory() as d:
            now = [0.0]
            w = StatusWriter(d, status_interval_s=1.0, clock=lambda: now[0])
            self.assertTrue(w.write_status({"state": "running"}))
            self.assertFalse(
                w.write_status({"state": "running"})
            )  # 1초 안이라 쓰지 않는다
            now[0] = 1.5
            self.assertTrue(w.write_status({"state": "running", "frames": 9}))
            data = json.loads((Path(d) / "status.json").read_text(encoding="utf-8"))
            self.assertEqual(data["frames"], 9)
            self.assertIn("updated", data)
            self.assertEqual(list(Path(d).glob("*.tmp")), [])
            atomic_write(Path(d) / "x.bin", b"abc")
            self.assertEqual((Path(d) / "x.bin").read_bytes(), b"abc")

    def test_overlay_keeps_original_and_encodes(self):
        frame = np.zeros((H, W, 3), np.uint8)
        out = draw_overlay(frame, [box(0.9), box(0.9, 0.05)], CAL, 3)
        self.assertEqual(out.shape, frame.shape)
        self.assertEqual(int(frame.sum()), 0)  # 원본은 그대로
        self.assertGreater(int(out.sum()), 0)
        self.assertTrue(encode_jpeg(out).startswith(b"\xff\xd8\xff"))


class EndToEndTest(unittest.TestCase):
    """가짜 감지기·서버·스피커로 영상 한 편을 끝까지 돌린다."""

    class Fake:
        """프레임 번호별로 정해 둔 박스를 돌려준다."""

        def __init__(self, plan):
            self.plan, self.i = plan, 0

        def detect(self, frame):
            out = self.plan(self.i)
            self.i += 1
            return out

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.video = self.root / "영상" / "시연_보행접근.mp4"
        self.video.parent.mkdir()
        make_video(self.video, frames=30)
        self.posts = []

    def tearDown(self):
        self.tmp.cleanup()

    def post(self, url, jpeg, timeout=0, **meta):
        self.posts.append((jpeg, meta))
        return {}

    def cfg(self, **kw):
        base = dict(
            source=str(self.video),
            data_dir=str(self.root / "data"),
            post_interval_s=0.0,
        )
        base.update(kw)
        return RunnerConfig(**base)

    def test_approach_raises_levels_and_posts(self):
        # 멀다 -> 5.5m -> 3m -> 2m 로 다가오는 사람.
        # 기준값 파일이 없으면 높이 0.7m·기울기 15도·화각 60도로 계산한 추정치(발 높이 0.38 / 0.47 / 0.56)를 쓴다
        def plan(i):
            if i < 5:
                return []
            ratio = 0.30 if i < 10 else 0.42 if i < 15 else 0.50 if i < 20 else 0.60
            return [box(ratio)]

        heard = []
        beeper = Beeper(player=lambda w: heard.append(len(w)) or True)
        summary = run(
            self.cfg(),
            detector=self.Fake(plan),
            post_fn=self.post,
            beeper=beeper,
            log=lambda s: None,
        )
        beeper.close()
        self.assertEqual(summary["state"], "finished")
        self.assertEqual(summary["frames"], 30)
        self.assertEqual(summary["max_alarm_level"], 3)
        self.assertGreaterEqual(summary["posts_submitted"], 3)
        self.assertEqual(summary["posted_ok"], len(self.posts))
        levels = [m["level"] for _, m in self.posts]
        self.assertEqual(levels, sorted(levels))  # 다가올수록 단계가 올라간다
        self.assertEqual(levels[-1], 3)
        self.assertEqual(self.posts[-1][1]["dist"], 2.0)
        self.assertTrue(
            all(j and j.startswith(b"\xff\xd8\xff") for j, _ in self.posts)
        )  # 박스 그린 캡처가 같이 간다
        self.assertGreaterEqual(summary["beeps"], 3)
        data = Path(self.root / "data")
        self.assertEqual(
            json.loads((data / "status.json").read_text(encoding="utf-8"))["state"],
            "finished",
        )
        self.assertTrue((data / "preview.jpg").read_bytes().startswith(b"\xff\xd8\xff"))

    def test_nobody_means_silence_and_no_posts(self):
        beeper = Beeper(player=lambda w: True)
        summary = run(
            self.cfg(),
            detector=self.Fake(lambda i: []),
            post_fn=self.post,
            beeper=beeper,
            log=lambda s: None,
        )
        beeper.close()
        self.assertEqual(
            (summary["max_alarm_level"], summary["posts_submitted"], summary["beeps"]),
            (0, 0, 0),
        )
        self.assertEqual(self.posts, [])

    def test_server_down_keeps_alarm_and_spools(self):
        def dead(url, jpeg, timeout=0, **meta):
            raise ConnectionError("서버 꺼짐")

        beeper = Beeper(player=lambda w: True)
        summary = run(
            self.cfg(max_frames=0),
            detector=self.Fake(lambda i: [box(0.9)]),
            post_fn=dead,
            beeper=beeper,
            log=lambda s: None,
        )
        beeper.close()
        self.assertEqual(summary["state"], "finished")  # 서버가 죽어도 끝까지 돈다
        self.assertEqual(summary["max_alarm_level"], 3)
        self.assertGreaterEqual(summary["beeps"], 1)  # 경고음은 그대로 난다
        self.assertEqual(summary["posted_ok"], 0)
        self.assertGreaterEqual(summary["spooled_left"], 1)  # 기록은 디스크에 남는다

    def test_max_frames_and_calibration_file(self):
        from alarm.levels import save_calibration

        calfile = self.root / "cal.json"
        save_calibration(
            Calibration(0.30, 0.40, 0.50, frame_height=1080), calfile
        )  # 다른 화면 높이로 저장된 기준값
        summary = run(
            self.cfg(max_frames=7, calibration=str(calfile)),
            detector=self.Fake(
                lambda i: [box(0.55)]
            ),  # 이 기준값에서는 3단계(0.50 이상)
            post_fn=self.post,
            beeper=Beeper(mute=True),
            log=lambda s: None,
        )
        self.assertEqual(summary["frames"], 7)
        self.assertEqual(
            summary["max_alarm_level"], 3
        )  # 기준값의 높이 비율을 실제 영상 높이에 맞춰 쓴다

    def test_empty_source_fails_clearly(self):
        bad = self.root / "빈.mp4"
        bad.write_bytes(b"not a video")
        with self.assertRaises(RuntimeError):
            run(
                self.cfg(source=str(bad)),
                detector=self.Fake(lambda i: []),
                post_fn=self.post,
                log=lambda s: None,
            )


class ControlTest(unittest.TestCase):
    def test_watcher_reads_only_changes_and_survives_garbage(self):
        from runner.control import FileWatcher

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "config.json"
            p.write_text(json.dumps({"mute": False}), encoding="utf-8")
            now = [0.0]
            w = FileWatcher(str(p), min_interval_s=0.0, clock=lambda: now[0])
            self.assertIsNone(w.poll())  # 시작할 때 이미 있던 내용은 변경이 아니다
            p.write_text(json.dumps({"mute": True, "pad": "x" * 5}), encoding="utf-8")
            self.assertEqual(w.poll()["mute"], True)
            self.assertIsNone(w.poll())  # 같은 내용을 두 번 주지 않는다
            p.write_text("{깨진 json", encoding="utf-8")
            self.assertIsNone(w.poll())  # 쓰는 중이거나 깨졌다
            p.write_text(json.dumps({"mute": False, "pad": "yy"}), encoding="utf-8")
            self.assertEqual(w.poll()["mute"], False)

    def test_apply_live_vs_restart_vs_invalid(self):
        from runner.control import apply_config_changes

        cfg = RunnerConfig(source="a.mp4")
        res = apply_config_changes(cfg, {"min_conf": 0.6, "mute": True, "source": "b.mp4", "model": "x.pt"})
        self.assertEqual(sorted(res["applied"]), ["min_conf", "mute"])
        self.assertEqual(sorted(res["restart_required"]), ["model", "source"])
        self.assertEqual((cfg.min_conf, cfg.mute, cfg.source), (0.6, True, "a.mp4"))  # source 는 아직 그대로
        before = dict(cfg.__dict__)
        res = apply_config_changes(cfg, {"min_conf": 5, "mute": False})  # 하나라도 틀리면 아무것도 바꾸지 않는다
        self.assertEqual(res["applied"], [])
        self.assertTrue(res["ignored"])
        self.assertEqual(cfg.__dict__, before)
        res = apply_config_changes(cfg, {"min_conf": "abc"})
        self.assertEqual(res["applied"], [])
        res = apply_config_changes(cfg, {"mute": False}, cli_keys={"mute"})  # 명령줄 값이 우선
        self.assertEqual(res["applied"], [])
        self.assertTrue(cfg.mute)

    def test_control_command_runs_once(self):
        from runner.control import ControlWatcher

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "control.json"
            p.write_text(json.dumps({"id": "old", "cmd": "test_sound", "level": 1}), encoding="utf-8")
            w = ControlWatcher(str(p), min_interval_s=0.0)
            self.assertIsNone(w.poll())  # 시작 전에 남은 명령은 실행하지 않는다
            p.write_text(json.dumps({"id": "a1", "cmd": "test_sound", "level": 2}), encoding="utf-8")
            self.assertEqual(w.poll()["id"], "a1")
            self.assertIsNone(w.poll())
            p.write_text(json.dumps({"id": "a1", "cmd": "test_sound", "level": 3, "pad": 1}), encoding="utf-8")
            self.assertIsNone(w.poll())  # 같은 id 는 다시 실행하지 않는다

    def test_pipeline_reconfigure(self):
        p = Pipeline(CAL, clock=lambda: 0.0)
        for _ in range(2):
            p.process([box(0.60)])
        self.assertEqual(p.process([box(0.60)]).alarm_level, 1)
        p.reconfigure(cal=Calibration(0.20, 0.30, 0.40, frame_height=H))
        self.assertEqual(p.process([box(0.60)]).frame_level, 3)  # 새 기준값이 바로 쓰인다
        p.reconfigure(min_conf=0.95)
        self.assertEqual(p.process([box(0.60, 0.9)]).frame_level, 0)
        p.reconfigure(window=5, need=5)
        self.assertEqual(p._state.window, 5)


class LiveRunTest(unittest.TestCase):
    """실행 도중 config.json 과 control.json 이 바뀌면 반영되는지 끝까지 돌려서 본다."""

    def test_config_and_command_take_effect_mid_run(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            video = root / "v.mp4"
            make_video(video, frames=40)
            data = root / "data"
            data.mkdir()
            cfgfile = data / "config.json"
            cfgfile.write_text(json.dumps({"mute": False}), encoding="utf-8")

            levels_seen = []
            heard = []
            beeper = Beeper(player=lambda w: heard.append(1) or True)

            class Det:
                i = 0
                min_conf = 0.25

                def detect(self, frame):
                    Det.i += 1
                    if Det.i == 10:
                        # 10번째 프레임에서 설정과 명령을 바꾼다(server 가 하는 일)
                        cfgfile.write_text(
                            json.dumps({"mute": True, "model": "other.pt", "calibration": None, "tilt_deg": 40.0}),
                            encoding="utf-8",
                        )
                        (data / "control.json").write_text(
                            json.dumps({"id": "t1", "cmd": "test_sound", "level": 2}), encoding="utf-8"
                        )
                    levels_seen.append(self.min_conf)
                    return [box(0.9)]

            cfg = RunnerConfig(source=str(video), data_dir=str(data), post_interval_s=0.0, preview=False)
            summary = run(
                cfg,
                detector=Det(),
                post_fn=lambda *a, **k: {},
                beeper=beeper,
                log=lambda s: None,
                config_path=str(cfgfile),
                watch_interval_s=0.0,
            )
            beeper.close()
            self.assertEqual(summary["frames"], 40)
            self.assertTrue(cfg.mute)  # 실행 중에 반영됐다
            self.assertEqual(cfg.tilt_deg, 40.0)
            status = json.loads((data / "status.json").read_text(encoding="utf-8"))
            self.assertIn("model", status["restart_required"])  # source·model 은 다시 시작해야 한다
            self.assertEqual(status["last_control"]["id"], "t1")
            self.assertEqual(status["last_control"]["result"], "muted")  # mute 가 먼저 반영돼 소리를 내지 않았다
            self.assertTrue(status["mute"])
            self.assertIn("foot_5_5", status["calibration"])


class ResilienceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.video = self.root / "v.mp4"
        make_video(self.video, frames=30)

    def tearDown(self):
        self.tmp.cleanup()

    def cfg(self, **kw):
        base = {"source": str(self.video), "data_dir": str(self.root / "data"), "post_interval_s": 0.0, "preview": False}
        base.update(kw)
        return RunnerConfig(**base)

    def test_detector_errors_do_not_kill_the_loop(self):
        class Flaky:
            i = 0

            def detect(self, frame):
                Flaky.i += 1
                if Flaky.i in (3, 4, 5):
                    raise RuntimeError("CUDA out of memory")
                return [box(0.9)]

        beeper = Beeper(player=lambda w: True)
        summary = run(self.cfg(), detector=Flaky(), post_fn=lambda *a, **k: {}, beeper=beeper, log=lambda s: None)
        beeper.close()
        self.assertEqual(summary["state"], "finished")  # 중간에 3번 실패해도 끝까지 간다
        self.assertEqual(summary["errors"], 3)
        self.assertGreaterEqual(summary["max_alarm_level"], 1)
        status = json.loads((self.root / "data" / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["errors"], 3)
        self.assertIn("CUDA", status["last_error"])

    def test_permanent_failure_stops_with_error_state(self):
        class Broken:
            def detect(self, frame):
                raise RuntimeError("모델 파일이 깨졌다")

        big = self.root / "long.mp4"
        make_video(big, frames=120)
        beeper = Beeper(player=lambda w: True)
        summary = run(self.cfg(source=str(big)), detector=Broken(), post_fn=lambda *a, **k: {}, beeper=beeper, log=lambda s: None)
        beeper.close()
        self.assertEqual(summary["state"], "error")  # 계속 실패하면 헛돌지 않고 이유와 함께 멈춘다
        self.assertEqual(summary["errors"], 50)

    def test_ready_tone_at_start_and_mute_respected(self):
        class Quiet:
            def detect(self, frame):
                return []

        loud = Beeper(player=lambda w: True)
        run(self.cfg(), detector=Quiet(), post_fn=lambda *a, **k: {}, beeper=loud, log=lambda s: None)
        loud.close()
        self.assertEqual(loud.events, ["ready"])
        muted = Beeper(mute=True, player=lambda w: True)
        run(self.cfg(mute=True), detector=Quiet(), post_fn=lambda *a, **k: {}, beeper=muted, log=lambda s: None)
        muted.close()
        self.assertEqual(muted.events, ["ready"])  # 기록은 남기지만 재생은 안 한다

    def test_camera_lost_tone_once_and_reconnect(self):
        class Flicker:
            """처음 5프레임은 읽히고, 끊겼다가, 다시 연결되면 또 읽힌다."""

            is_file = False
            fps = 30.0
            opened = True

            def __init__(self):
                self.calls = 0
                self.reopens = 0

            def read(self):
                self.calls += 1
                if self.calls <= 5 or self.calls > 8:
                    return np.full((H, W, 3), 50, np.uint8)
                return None  # 6~8번째 읽기는 실패(끊김)

            def reopen(self):
                self.reopens += 1
                return True

            def release(self):
                pass

        class Quiet:
            def detect(self, frame):
                return []

        src = Flicker()
        beeper = Beeper(player=lambda w: True)
        summary = run(
            self.cfg(max_frames=10),
            detector=Quiet(),
            post_fn=lambda *a, **k: {},
            beeper=beeper,
            source=src,
            log=lambda s: None,    lost_retry_s=0.0,
        )
        beeper.close()
        self.assertEqual(summary["frames"], 10)
        self.assertEqual(beeper.events.count("lost"), 1)  # 끊긴 순간 한 번만 알린다
        self.assertGreaterEqual(src.reopens, 1)


class SoundEventTest(unittest.TestCase):
    def test_event_tones_are_valid_and_distinct_from_alarms(self):
        from runner.sound import EVENTS, event_wav

        for name in EVENTS:
            with wave.open(io.BytesIO(event_wav(name)), "rb") as w:
                self.assertGreater(w.getnframes() / w.getframerate(), 0.3)
        with self.assertRaises(ValueError):
            event_wav("nope")
        b = Beeper(player=lambda w: True)
        try:
            self.assertFalse(b.play_event("nope"))
            self.assertTrue(b.play_event("ready"))
        finally:
            b.close()


class FakeCap:
    """프레임 번호를 화소값에 넣어 돌려주는 가짜 카메라."""

    def __init__(self, n, fps=30.0, delay=0.0):
        self.n, self.fps, self.delay = n, fps, delay
        self.i = 0
        self.closed = False

    def isOpened(self):
        return not self.closed

    def read(self):
        if self.i >= self.n:
            return False, None
        self.i += 1
        if self.delay:
            time.sleep(self.delay)
        return True, np.full((2, 2, 3), self.i % 256, np.uint8)

    def grab(self):
        if self.i >= self.n:
            return False
        self.i += 1
        return True

    def get(self, prop):
        return self.fps

    def release(self):
        self.closed = True


class FakeClock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds


class LatestFrameTest(unittest.TestCase):
    def test_file_realtime_skips_frames_when_processing_is_slow(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "x.mp4"
            path.write_bytes(b"x")
            clock = FakeClock()
            cap = FakeCap(400, fps=30.0)
            src = VideoSource(str(path), realtime=True, capture_factory=lambda p: cap, clock=clock, sleep=clock.sleep)
            delivered = 0
            for _ in range(30):
                self.assertIsNotNone(src.read())
                delivered += 1
                clock.t += 0.1  # 한 프레임 처리에 0.1초(영상은 프레임당 0.033초)
            # 3초 동안 처리했으니 영상도 약 3초(90프레임) 지점에 와 있어야 한다. 하나씩 처리했다면 30프레임에 머문다
            self.assertGreater(cap.i, 80)
            self.assertGreater(src.dropped, 50)
            self.assertEqual(src.frames_read, 30)
            self.assertEqual(src.frames_read + src.dropped, cap.i)

    def test_file_realtime_does_not_drop_when_fast_enough(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "x.mp4"
            path.write_bytes(b"x")
            clock = FakeClock()
            cap = FakeCap(40, fps=20.0)
            src = VideoSource(str(path), realtime=True, capture_factory=lambda p: cap, clock=clock, sleep=clock.sleep)
            t_start = clock.t
            while src.read() is not None:
                clock.t += 0.01  # 아주 빠른 처리
            self.assertEqual(src.dropped, 0)
            self.assertAlmostEqual(clock.t - t_start, 40 / 20.0, delta=0.5)  # 영상 속도(20fps)에 맞춰 재생했다

    def test_file_without_realtime_processes_every_frame(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "x.mp4"
            path.write_bytes(b"x")
            cap = FakeCap(25)
            src = VideoSource(str(path), realtime=False, capture_factory=lambda p: cap)
            n = 0
            while src.read() is not None:
                n += 1
                time.sleep(0.001)
            self.assertEqual((n, src.dropped), (25, 0))  # 시험·평가용은 하나도 버리지 않는다

    def test_live_source_returns_latest_frame_and_counts_drops(self):
        cap = FakeCap(300, fps=30.0, delay=0.002)
        src = VideoSource("0", capture_factory=lambda v: cap)
        try:
            first = src.read()
            self.assertIsNotNone(first)
            # 느린 처리: 그 사이 카메라가 새 프레임을 40장 더 만들 때까지 기다린다(시간이 아니라 장수로 기다려 환경에 안 흔들리게)
            target = int(first[0, 0, 0]) + 40
            end = time.time() + 10
            while cap.i < target and time.time() < end:
                time.sleep(0.005)
            second = src.read()
            # 읽기 스레드가 마지막 한두 장을 저장하기 직전일 수 있어서 여유를 둔다
            self.assertGreater(int(second[0, 0, 0]), int(first[0, 0, 0]) + 30)  # 밀린 것을 하나씩 주지 않고 최신을 준다
            # 끝까지 읽으면(카메라가 끊김) 받은 것과 버린 것의 합이 카메라가 만든 전부다
            while src.read() is not None:
                pass
            self.assertEqual(src.frames_read + src.dropped, 300)
            self.assertGreater(src.dropped, 20)
        finally:
            src.release()

    def test_live_source_reports_loss_and_recovers_on_reopen(self):
        caps = [FakeCap(5, delay=0.001), FakeCap(50, delay=0.001)]
        made = []

        def factory(v):
            made.append(1)
            return caps[len(made) - 1]

        src = VideoSource("rtsp://x/y", capture_factory=factory)
        try:
            got = 0
            while src.read() is not None:  # 첫 카메라는 5프레임 만들고 끊긴다
                got += 1
            self.assertGreaterEqual(got, 1)
            self.assertTrue(src.reopen())
            self.assertIsNotNone(src.read())  # 다시 연결한 카메라에서 프레임이 온다
        finally:
            src.release()
        self.assertEqual(len(made), 2)


class PerClassConfTest(unittest.TestCase):
    def test_bicycle_has_its_own_threshold(self):
        p = Pipeline(CAL, min_conf=0.25, clock=lambda: 0.0)
        p.min_conf_bicycle = 0.35
        r = p.process([box(0.9, 0.30, 1), box(0.9, 0.26, 0)])
        self.assertEqual((r.person, r.bicycle), (1, 0))  # 자전거 0.30 은 기준 0.35 미만이라 버려진다
        self.assertAlmostEqual(p.floor_conf(), 0.25)
        r = p.process([box(0.9, 0.40, 1)])
        self.assertEqual(r.bicycle, 1)

    def test_bicycle_threshold_lower_than_person_and_reconfigure(self):
        p = Pipeline(CAL, min_conf=0.5, clock=lambda: 0.0)
        p.reconfigure(min_conf_bicycle=0.2)
        self.assertAlmostEqual(p.floor_conf(), 0.2)  # 감지기는 낮은 쪽 기준으로 내보내야 한다
        self.assertEqual(p.process([box(0.9, 0.3, 1)]).bicycle, 1)
        self.assertEqual(p.process([box(0.9, 0.3, 0)]).person, 0)  # 사람은 0.5 기준
        p.reconfigure(clear_min_conf_bicycle=True)
        self.assertEqual(p.process([box(0.9, 0.3, 1)]).bicycle, 0)  # 자전거도 다시 0.5 기준

    def test_config_accepts_and_validates_new_keys(self):
        cfg = build_config({}, {"source": "a", "min_conf_bicycle": 0.35, "imgsz": 480})
        self.assertEqual((cfg.min_conf_bicycle, cfg.imgsz), (0.35, 480))
        self.assertIsNone(build_config({}, {"source": "a"}).min_conf_bicycle)
        for bad in ({"imgsz": 500}, {"imgsz": 64}, {"min_conf_bicycle": 1.5}, {"min_conf_bicycle": "x"}):
            with self.assertRaises(ValueError, msg=str(bad)):
                build_config({}, dict({"source": "a"}, **bad))

    def test_live_apply_bicycle_conf_and_imgsz_needs_restart(self):
        from runner.control import apply_config_changes

        cfg = RunnerConfig(source="a.mp4")
        res = apply_config_changes(cfg, {"min_conf_bicycle": 0.35, "imgsz": 480})
        self.assertEqual(res["applied"], ["min_conf_bicycle"])
        self.assertEqual(res["restart_required"], ["imgsz"])
        self.assertEqual((cfg.min_conf_bicycle, cfg.imgsz), (0.35, 640))


class AplayDeviceTest(unittest.TestCase):
    """HDMI·보드 오디오처럼 기본 장치가 스피커가 아닐 때 ALASKA_AUDIO_DEVICE 로 장치를 고른다."""

    def test_default_has_no_device_option(self):
        import os
        from unittest import mock

        from runner.sound import aplay_command

        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ALASKA_AUDIO_DEVICE", None)
            self.assertEqual(aplay_command(), ["aplay", "-q", "-"])

    def test_env_device_is_passed_to_aplay(self):
        import os
        from unittest import mock

        from runner.sound import aplay_command

        with mock.patch.dict(os.environ, {"ALASKA_AUDIO_DEVICE": " plughw:1,0 "}):
            self.assertEqual(aplay_command(), ["aplay", "-q", "-D", "plughw:1,0", "-"])


if __name__ == "__main__":
    unittest.main()
