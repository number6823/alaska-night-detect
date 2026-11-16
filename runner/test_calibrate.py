"""runner.calibrate 시험. 실행: python -m unittest runner.test_calibrate -v

사람이 5.5m → 3m → 2m 에 차례로 서는 거리기준 영상을, 시간별 발 위치 목록으로 흉내 내서 확인한다.
"""

import json
import random
import tempfile
import unittest
from pathlib import Path

import numpy as np

from alarm.levels import foot_ratio_at, load_calibration, save_calibration
from runner.calibrate import (
    build_calibration,
    collect_samples,
    find_plateaus,
    parse_times,
    pick_spans,
    sanity_report,
)

H = 1080


def sample(t, foot_ratio, h=H):
    y2 = foot_ratio * h
    return {"t": t, "box": (800.0, y2 - 400, 900.0, y2, 0.9, 0), "frame_h": h}


def make_track(
    levels, hold_s=10.0, walk_s=3.0, fps_samples=5, noise=0.004, seed=1, gaps=()
):
    """levels 의 발 위치에 hold_s 초씩 서고, 사이를 walk_s 초 동안 걸어서 이동하는 샘플 목록."""
    rnd = random.Random(seed)
    out = []
    t = 0.0
    dt = 1.0 / fps_samples
    prev = levels[0]
    for lv in levels:
        if lv != levels[0] or out:
            steps = int(walk_s / dt)
            for k in range(1, steps + 1):  # 걸어서 이동: 발 위치가 계속 바뀐다
                out.append(
                    sample(t, prev + (lv - prev) * k / steps + rnd.gauss(0, noise))
                )
                t += dt
        for _ in range(int(hold_s / dt)):
            out.append(sample(t, lv + rnd.gauss(0, noise)))
            t += dt
        prev = lv
    return [s for s in out if not any(a <= s["t"] <= b for a, b in gaps)]


# 높이 70cm, 아래 15도, 화각 82도 카메라의 실제 발 위치
F55, F3, F2 = (foot_ratio_at(d, 0.7, 15.0, 82.0) for d in (5.5, 3.0, 2.0))


class PlateauTest(unittest.TestCase):
    def test_finds_four_standing_spans_and_skips_walking(self):
        track = make_track([F55, F3, F2, F2 + 0.001])
        plateaus = find_plateaus(track)
        # 서 있는 구간 4개(5.5m, 3m, 2m, 돌아서서 2m)가 시간순으로 나온다. 걷는 구간은 빠진다
        self.assertGreaterEqual(len(plateaus), 3)
        meds = [p["median"] for p in plateaus[:3]]
        self.assertAlmostEqual(meds[0], F55, delta=0.01)
        self.assertAlmostEqual(meds[1], F3, delta=0.01)
        self.assertAlmostEqual(meds[2], F2, delta=0.01)
        self.assertTrue(all(p["end"] - p["start"] >= 2.5 for p in plateaus))
        self.assertEqual(
            [p["start"] for p in plateaus], sorted(p["start"] for p in plateaus)
        )

    def test_survives_missing_detections(self):
        track = make_track(
            [F55, F3, F2], gaps=((3.0, 4.5), (17.0, 18.0))
        )  # 감지가 잠깐 끊긴 구간
        plateaus = find_plateaus(track)
        self.assertEqual(len(plateaus), 3)

    def test_too_short_or_empty(self):
        self.assertEqual(find_plateaus([]), [])
        short = make_track([F55], hold_s=1.0)
        self.assertEqual(find_plateaus(short), [])  # 1초만 선 것은 구간이 아니다

    def test_pick_spans_errors_clearly_when_not_enough(self):
        with self.assertRaises(ValueError) as cm:
            pick_spans(make_track([F55, F3], hold_s=10.0))  # 두 곳에만 섰다
        self.assertIn("--times", str(cm.exception))


class BuildTest(unittest.TestCase):
    def test_calibration_from_track_matches_each_distance(self):
        track = make_track([F55, F3, F2, F2])
        spans = pick_spans(track)
        cal, summary = build_calibration(track, spans, camera_height_cm=70)
        self.assertEqual([s["name"] for s in summary], ["5.5m", "3m", "2m"])
        # 대표값을 그대로 경계로 쓴다: 각 거리의 발 위치가 해당 단계를 가리킨다
        self.assertAlmostEqual(cal.foot_5_5, F55, delta=0.01)
        self.assertAlmostEqual(cal.foot_3, F3, delta=0.01)
        self.assertAlmostEqual(cal.foot_2, F2, delta=0.01)
        self.assertLess(cal.foot_5_5, cal.foot_3)
        self.assertLess(cal.foot_3, cal.foot_2)
        self.assertEqual(cal.camera_height_cm, 70)

    def test_explicit_times_override_auto_detection(self):
        track = make_track([F55, F3, F2])
        times = parse_times("0-9,13-22,26-35")
        cal, summary = build_calibration(track, pick_spans(track, times))
        self.assertAlmostEqual(summary[1]["foot"], F3, delta=0.01)

    def test_wrong_order_is_rejected(self):
        track = make_track([F2, F3, F55])  # 가까운 곳에서 먼 곳으로 섰다
        with self.assertRaises(ValueError):
            build_calibration(track, pick_spans(track))

    def test_empty_span_is_rejected(self):
        track = make_track([F55, F3, F2])
        with self.assertRaises(ValueError):
            build_calibration(track, [(0, 9), (13, 22), (500, 510)])

    def test_margin_moves_boundaries_up(self):
        track = make_track([F55, F3, F2])
        plain, _ = build_calibration(track, pick_spans(track))
        early, _ = build_calibration(track, pick_spans(track), margin=0.02)
        self.assertAlmostEqual(plain.foot_3 - early.foot_3, 0.02, places=6)

    def test_saved_file_loads_back(self):
        track = make_track([F55, F3, F2])
        cal, _ = build_calibration(track, pick_spans(track))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "cal.json"
            save_calibration(cal, p)
            self.assertEqual(load_calibration(p), cal)
            self.assertIn("foot_5_5", json.loads(p.read_text(encoding="utf-8")))


class HelpersTest(unittest.TestCase):
    def test_parse_times(self):
        self.assertEqual(
            parse_times("3-13,18-28.5,33-43"), [(3.0, 13.0), (18.0, 28.5), (33.0, 43.0)]
        )
        for bad in ("3-13,18-28", "5-2,1-9,3-4", "a-b,c-d,e-f", "1-2,3-4,5-6,7-8"):
            with self.assertRaises(ValueError, msg=bad):
                parse_times(bad)

    def test_sanity_report_flags_misplaced_mark(self):
        track = make_track([F55, F3, F2])
        _, summary = build_calibration(track, pick_spans(track))
        notes = sanity_report(summary, 0.7, 15.0)
        self.assertFalse(any("확인한다" in n for n in notes))  # 맞게 섰으면 경고가 없다
        # 3m 표시를 엉뚱한 곳에 놓은 영상
        bad = make_track([F55, F3 + 0.045, F2])
        _, summary2 = build_calibration(bad, pick_spans(bad))
        self.assertTrue(
            any("확인한다" in n for n in sanity_report(summary2, 0.7, 15.0))
        )


class CollectTest(unittest.TestCase):
    class Src:
        fps = 10.0

        def __init__(self, n):
            self.n, self.i = n, 0

        def read(self):
            if self.i >= self.n:
                return None
            self.i += 1
            return np.zeros((H, 1920, 3), np.uint8)

    class Det:
        def __init__(self, plan):
            self.plan, self.i = plan, 0

        def detect(self, frame):
            out = self.plan(self.i)
            self.i += 1
            return out

    def test_uses_largest_person_skips_cut_feet_and_stride(self):
        def plan(i):
            if i == 1:  # 프레임 3 에서는 사람이 없다
                return []
            if i == 2:  # 프레임 6 에서는 발이 잘렸다
                return [(100, 600, 200, H, 0.9, 0)]  # 발이 화면 아래에서 잘림 -> 뺀다
            return [
                (100, 300, 160, 700, 0.9, 0),  # 작은 사람
                (800, 200, 1000, 800, 0.8, 0),  # 가장 큰 사람
                (500, 500, 900, 900, 0.95, 2),  # 자동차는 무시
            ]

        samples = collect_samples(self.Src(12), self.Det(plan), stride=3, min_conf=0.3)
        # 감지는 stride=3 이라 프레임 0, 3, 6, 9 에서만 한다. 3번은 사람 없음, 6번은 발 잘림 -> 0, 9 만 남는다
        self.assertEqual(len(samples), 2)
        self.assertEqual(samples[0]["box"][3], 800)  # 큰 사람의 발
        self.assertAlmostEqual(samples[1]["t"], 0.9)
        self.assertEqual(samples[0]["frame_h"], H)

    def test_max_seconds_stops_early(self):
        samples = collect_samples(
            self.Src(100),
            self.Det(lambda i: [(1, 1, 50, 500, 0.9, 0)]),
            stride=1,
            max_seconds=1.0,
        )
        self.assertLessEqual(max(s["t"] for s in samples), 1.0)


if __name__ == "__main__":
    unittest.main()
