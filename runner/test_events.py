"""이벤트 평가 시험: 가짜 박스로 경보 시각, 선행 시간, 놓침, 빈 구간 오경보를 확인한다."""

import os
import tempfile
import unittest

from alarm.levels import Calibration
from runner import events as E

CAL = Calibration(foot_5_5=0.30, foot_3=0.43, foot_2=0.51, frame_height=1000)
FPS = 10.0


def box(foot_ratio, conf=0.9, cls=0):
    y2 = foot_ratio * 1000
    return [100.0, y2 - 200, 200.0, y2, conf, cls]


def make_dump(frames):
    """frames: 프레임마다의 박스 리스트."""
    return {"fps": FPS, "frame_height": 1000, "boxes": frames}


def person_walk():
    """0~2초 빈 화면, 2초에 5.5m 안으로 들어와 4초에 3m, 6초에 2m, 8초에 나감, 이후 빈 화면 (총 12초)."""
    frames = []
    for i in range(120):
        t = i / FPS
        if t < 2.0:
            frames.append([])
        elif t < 4.0:
            frames.append([box(0.35)])
        elif t < 6.0:
            frames.append([box(0.45)])
        elif t < 8.0:
            frames.append([box(0.60)])
        else:
            frames.append([])
    return frames


EVENTS_TEXT = (
    "take,who,event,t_sec\n"
    "1,person,start,1.5\n"
    "1,person,cross_5.5m,2.0\n"
    "1,person,cross_3m,4.0\n"
    "1,person,cross_2m,6.0\n"
    "1,person,exit,8.0\n"
)


def write_events(text):
    f = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8")
    f.write(text)
    f.close()
    return f.name


class ReplayTest(unittest.TestCase):
    def test_two_of_three_rule_delays_alarm_one_frame(self):
        tl = E.replay(make_dump(person_walk()), CAL, E.Settings())
        # 2.0초 프레임부터 박스가 있고, 3프레임 중 2번째 프레임(2.1초)에 1단계가 된다
        first = next(t for t, lvl in tl if lvl >= 1)
        self.assertAlmostEqual(first, 2.1, places=3)

    def test_changes_listed(self):
        tl = E.replay(make_dump(person_walk()), CAL, E.Settings())
        self.assertEqual(
            [(a, b) for _t, a, b in E.level_changes(tl)],
            [(0, 1), (1, 2), (2, 3), (3, 0)],
        )

    def test_process_fps_skips_frames(self):
        tl = E.replay(make_dump(person_walk()), CAL, E.Settings(process_fps=5))
        self.assertEqual(len(tl), 60)
        self.assertAlmostEqual(tl[1][0], 0.2, places=3)

    def test_bicycle_confidence_threshold_applies(self):
        frames = [[box(0.45, conf=0.3, cls=1)] for _ in range(20)]
        low = E.replay(make_dump(frames), CAL, E.Settings(min_conf=0.25))
        high = E.replay(
            make_dump(frames), CAL, E.Settings(min_conf=0.25, min_conf_bicycle=0.4)
        )
        self.assertEqual(max(l for _t, l in low), 2)
        self.assertEqual(max(l for _t, l in high), 0)


class ParseTest(unittest.TestCase):
    def test_parse_ok(self):
        takes = E.parse_events(write_events(EVENTS_TEXT + "1,setup,in_frame,0.0-0.8\n"))
        actor = takes[1].actors["person"]
        self.assertEqual((actor.start, actor.exit), (1.5, 8.0))
        self.assertEqual(actor.crosses, {1: 2.0, 2: 4.0, 3: 6.0})
        self.assertEqual(takes[1].setups, [(0.0, 0.8)])

    def test_bicycle_alias(self):
        takes = E.parse_events(
            write_events("take,who,event,t_sec\n1,bicycle,start,1\n1,bicycle,exit,5\n")
        )
        self.assertIn("bike", takes[1].actors)

    def test_missing_exit_rejected(self):
        with self.assertRaises(ValueError):
            E.parse_events(write_events("take,who,event,t_sec\n1,person,start,1\n"))

    def test_bad_event_names_line(self):
        with self.assertRaisesRegex(ValueError, "2번째 줄"):
            E.parse_events(write_events("take,who,event,t_sec\n1,person,cross_9m,1\n"))

    def test_bad_header(self):
        with self.assertRaises(ValueError):
            E.parse_events(write_events("a,b\n1,2\n"))


class MultiPassTest(unittest.TestCase):
    """한 영상에 같은 사람이 두 번 지나가는 경우(person, person2 처럼 번호를 붙여 적는다)."""

    TEXT = (
        EVENTS_TEXT
        + "1,person2,start,11.5\n"
        + "1,person2,cross_5.5m,12.0\n"
        + "1,person2,cross_3m,14.0\n"
        + "1,person2,cross_2m,16.0\n"
        + "1,person2,exit,18.0\n"
    )

    def frames(self):
        return (
            person_walk()[:100] + person_walk()
        )  # 10초 + 12초 = 22초, 두 번째는 10초 뒤

    def test_parse_numbered_actors(self):
        takes = E.parse_events(write_events(self.TEXT.replace("person2", "bicycle2")))
        self.assertEqual(set(takes[1].actors), {"person", "bike2"})
        takes = E.parse_events(write_events(self.TEXT))
        self.assertEqual(takes[1].actors["person2"].start, 11.5)

    def test_bad_number_name_rejected(self):
        with self.assertRaises(ValueError):
            E.parse_events(
                write_events("take,who,event,t_sec\n1,dog2,start,1\n1,dog2,exit,2\n")
            )

    def test_two_passes_counted_without_false_alarm(self):
        data = make_dump(self.frames())
        tl = E.replay(data, CAL, E.Settings())
        ev = E.parse_events(write_events(self.TEXT))[1]
        r = E.evaluate_take(1, tl, ev, len(self.frames()) / FPS)
        self.assertEqual(len(r.actors), 2)
        self.assertEqual(sum(len(a.crosses) for a in r.actors), 6)
        self.assertTrue(all(c.t_alarm is not None for a in r.actors for c in a.crosses))
        self.assertEqual(r.false_s, 0.0)

    def test_summary_groups_numbered_by_kind(self):
        data = make_dump(self.frames())
        ev = E.parse_events(write_events(self.TEXT))
        results = E.run_eval([(1, "a.mp4", data)], ev, CAL, E.Settings())
        text = "\n".join(E.summarize(results))
        self.assertIn("보행자: 6/6", text)
        self.assertTrue(
            any("보행자 2" in l for l in E.format_take(results[0], "a.mp4"))
        )


class EvaluateTest(unittest.TestCase):
    def run_take(self, frames, text=EVENTS_TEXT):
        data = make_dump(frames)
        tl = E.replay(data, CAL, E.Settings())
        ev = E.parse_events(write_events(text))[1]
        return E.evaluate_take(1, tl, ev, len(frames) / FPS)

    def test_perfect_take(self):
        r = self.run_take(person_walk())
        leads = {c.level: c.lead for c in r.actors[0].crosses}
        # 선을 넘은 직후 2번째 프레임에서 울린다 → 0.1초 늦다
        for lvl in (1, 2, 3):
            self.assertAlmostEqual(leads[lvl], -0.1, places=3)
        self.assertEqual(r.actors[0].drops, 0)
        self.assertEqual(r.false_s, 0.0)
        self.assertEqual(r.false_runs, 0)
        self.assertTrue(r.actors[0].cleared)
        self.assertGreater(r.actors[0].clear_delay, 0)

    def test_missed_level(self):
        frames = person_walk()
        for i in range(
            60, 80
        ):  # 6~8초 구간(2m 안쪽)을 3m 구간 모습으로 바꿔 3단계를 놓치게 한다
            frames[i] = [box(0.45)]
        r = self.run_take(frames)
        crosses = {c.level: c for c in r.actors[0].crosses}
        self.assertIsNone(crosses[3].t_alarm)
        self.assertIsNotNone(crosses[2].t_alarm)

    def test_false_alarm_in_empty_section(self):
        frames = person_walk()
        for i in range(100, 105):  # 10초부터 0.5초 동안 아무도 없는데 박스가 나온다
            frames[i] = [box(0.45)]
        r = self.run_take(frames)
        self.assertEqual(r.false_runs, 1)
        self.assertGreater(r.false_s, 0.3)
        self.assertLess(r.false_s, 0.8)

    def test_alarm_right_after_exit_is_not_false_alarm(self):
        frames = person_walk()
        for i in range(
            80, 90
        ):  # 나간 직후 1초(8~9초) 박스가 남아 있다 → 꺼지는 데 걸리는 시간으로 본다
            frames[i] = [box(0.60)]
        r = self.run_take(frames)
        self.assertEqual(r.false_s, 0.0)
        self.assertGreaterEqual(r.actors[0].clear_delay, 1.0)

    def test_setup_range_excluded(self):
        frames = person_walk()
        for i in range(0, 5):  # 시작한 사람이 0~0.5초 화면에 찍혀 3m 구간에서 감지됨
            frames[i] = [box(0.45)]
        r = self.run_take(frames, EVENTS_TEXT + "1,setup,in_frame,0.0-1.0\n")
        self.assertEqual(r.false_s, 0.0)
        r2 = self.run_take(frames)
        self.assertGreater(r2.false_s, 0.0)

    def test_dropping_counted(self):
        frames = person_walk()
        for i in range(40, 44):  # 4~4.4초 사이 박스가 사라졌다 돌아온다
            frames[i] = []
        r = self.run_take(frames)
        self.assertGreaterEqual(r.actors[0].drops, 1)

    def test_two_actors_stuck_alarm(self):
        frames = person_walk()[:80] + [
            [box(0.60)] for _ in range(40)
        ]  # 나간 뒤에도 계속 감지(안 꺼짐)
        r = self.run_take(frames)
        self.assertFalse(r.actors[0].cleared)
        self.assertIsNone(r.actors[0].clear_delay)


class ReportTest(unittest.TestCase):
    def test_summary_and_sweep_row(self):
        data = make_dump(person_walk())
        ev = E.parse_events(write_events(EVENTS_TEXT))
        results = E.run_eval([(1, "a.mp4", data)], ev, CAL, E.Settings())
        text = "\n".join(E.summarize(results))
        self.assertIn("3/3", text)
        got, total, _med, false_s, runs = E.summary_row(results)
        self.assertEqual((got, total, false_s, runs), (3, 3, 0.0, 0))
        self.assertTrue(any("늦게" in l for l in E.format_take(results[0], "a.mp4")))

    def test_missing_take_in_csv(self):
        ev = E.parse_events(write_events(EVENTS_TEXT))
        with self.assertRaises(ValueError):
            E.run_eval([(2, "a.mp4", make_dump(person_walk()))], ev, CAL, E.Settings())

    def test_sweep_cli(self):
        import json

        d = tempfile.mkdtemp()
        bpath = os.path.join(d, "a.boxes.json")
        with open(bpath, "w", encoding="utf-8") as f:
            json.dump(make_dump(person_walk()), f)
        cpath = os.path.join(d, "cal.json")
        with open(cpath, "w", encoding="utf-8") as f:
            json.dump(CAL.to_dict(), f)
        epath = write_events(EVENTS_TEXT)
        rpath = os.path.join(d, "r.txt")
        code = E.main(
            [
                "eval",
                "--boxes",
                bpath,
                "--events",
                epath,
                "--calibration",
                cpath,
                "--sweep",
                "--report",
                rpath,
            ]
        )
        self.assertEqual(code, 0)
        with open(rpath, encoding="utf-8") as f:
            self.assertIn("3/3", f.read())


if __name__ == "__main__":
    unittest.main()
