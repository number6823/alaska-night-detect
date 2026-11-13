"""alarm.levels 시험. 실행: python -m unittest alarm.test_levels -v"""

import unittest

from alarm.levels import (
    AlarmState,
    Calibration,
    box_level,
    calibrate_from_samples,
    estimate_calibration,
    frame_level,
)

H = 1080
CAL = Calibration(foot_5_5=0.55, foot_3=0.70, foot_2=0.85, frame_height=H)


def person(foot_ratio: float, conf: float = 0.9):
    """박스 아래 끝이 화면 높이의 foot_ratio 위치인 사람 박스."""
    y2 = foot_ratio * H
    return (400, y2 - 300, 500, y2, conf, 0)


class BoxLevelTest(unittest.TestCase):
    def test_levels_by_foot_position(self):
        self.assertEqual(box_level(person(0.40), CAL), 0)  # 멀다
        self.assertEqual(box_level(person(0.60), CAL), 1)  # 5.5m 이내
        self.assertEqual(box_level(person(0.75), CAL), 2)  # 3m 이내
        self.assertEqual(box_level(person(0.90), CAL), 3)  # 2m 이내

    def test_boundary_is_inclusive(self):
        self.assertEqual(box_level(person(0.55), CAL), 1)
        self.assertEqual(box_level(person(0.70), CAL), 2)
        self.assertEqual(box_level(person(0.85), CAL), 3)

    def test_foot_cut_at_bottom_is_closest(self):
        self.assertEqual(box_level((400, 500, 600, H, 0.9, 0), CAL), 3)
        self.assertEqual(box_level((400, 500, 600, H - 3, 0.9, 0), CAL), 3)

    def test_low_confidence_ignored(self):
        self.assertEqual(box_level(person(0.90, conf=0.1), CAL), 0)
        self.assertEqual(box_level(person(0.90, conf=0.1), CAL, min_conf=0.05), 3)

    def test_only_person_and_bicycle_count(self):
        car = (400, 500, 600, 0.9 * H, 0.95, 2)  # COCO 모델의 car
        bicycle = (400, 500, 600, 0.9 * H, 0.95, 1.0)  # 모델 출력은 실수로 나온다
        self.assertEqual(box_level(car, CAL), 0)
        self.assertEqual(box_level(bicycle, CAL), 3)
        self.assertEqual(
            frame_level([car, person(0.60)], CAL), 1
        )  # 가까운 자동차는 무시
        self.assertEqual(frame_level([car], CAL), 0)
        self.assertEqual(box_level(car, CAL, classes=None), 3)  # 거르기를 끄면 통과
        self.assertEqual(
            box_level((400, 500, 600, 0.9 * H, 0.95), CAL), 3
        )  # 클래스 값이 없으면 통과

    def test_frame_level_takes_closest_box(self):
        boxes = [person(0.40), person(0.75), person(0.60)]
        self.assertEqual(frame_level(boxes, CAL), 2)
        self.assertEqual(frame_level([], CAL), 0)


class CalibrationTest(unittest.TestCase):
    def test_bad_order_rejected(self):
        with self.assertRaises(ValueError):
            Calibration(0.8, 0.7, 0.9)

    def test_estimate_is_monotonic(self):
        cal = estimate_calibration()
        self.assertLess(cal.foot_5_5, cal.foot_3)
        self.assertLess(cal.foot_3, cal.foot_2)
        self.assertTrue(0.0 <= cal.foot_5_5 and cal.foot_2 <= 1.0)

    def test_estimate_lower_camera_sees_foot_higher_up(self):
        # 카메라가 낮으면 같은 거리의 발이 화면 위쪽(수평선 쪽)에 가깝다
        low = estimate_calibration(camera_height_m=0.6, tilt_deg=15)
        high = estimate_calibration(camera_height_m=0.9, tilt_deg=15)
        self.assertLess(low.foot_3, high.foot_3)

    def test_calibrate_from_samples_reproduces_levels(self):
        s55 = [person(0.55), person(0.56), person(0.54)]
        s3 = [person(0.70), person(0.71), person(0.69)]
        s2 = [person(0.85), person(0.86), person(0.84)]
        cal = calibrate_from_samples(s55, s3, s2, frame_height=H)
        self.assertEqual(frame_level(s55, cal), 1)
        self.assertEqual(frame_level(s3, cal), 2)
        self.assertEqual(frame_level(s2, cal), 3)
        self.assertEqual(frame_level([person(0.35)], cal), 0)  # 5.5m 보다 훨씬 멀다

    def test_calibrate_rejects_wrong_order(self):
        s55 = [person(0.80)]
        s3 = [person(0.70)]
        s2 = [person(0.85)]
        with self.assertRaises(ValueError):
            calibrate_from_samples(s55, s3, s2, frame_height=H)

    def test_calibrate_rejects_empty_group(self):
        with self.assertRaises(ValueError):
            calibrate_from_samples([], [person(0.7)], [person(0.85)], frame_height=H)


class AlarmStateTest(unittest.TestCase):
    def run_levels(self, levels, **kw):
        st = AlarmState(**kw)
        return [st.update(x) for x in levels]

    def test_two_of_three_needed(self):
        # 한 번만 잡힌 것은 울리지 않는다
        self.assertEqual(self.run_levels([3, 0, 0]), [0, 0, 0])
        # 3프레임 중 2번 잡히면 울린다
        self.assertEqual(self.run_levels([3, 0, 3]), [0, 0, 3])
        self.assertEqual(self.run_levels([3, 3, 0]), [0, 3, 3])

    def test_level_is_highest_reached_twice(self):
        # 3, 2, 2 -> 3은 한 번뿐, 2 이상은 세 번 -> 2단계
        self.assertEqual(self.run_levels([3, 2, 2])[-1], 2)
        self.assertEqual(self.run_levels([1, 1, 1])[-1], 1)

    def test_drops_when_object_leaves(self):
        out = self.run_levels([3, 3, 3, 0, 0, 0])
        self.assertEqual(out, [0, 3, 3, 3, 0, 0])

    def test_reset(self):
        st = AlarmState()
        st.update(3)
        st.reset()
        self.assertEqual(st.update(3), 0)

    def test_invalid_args(self):
        with self.assertRaises(ValueError):
            AlarmState(window=2, need=3)


if __name__ == "__main__":
    unittest.main()
