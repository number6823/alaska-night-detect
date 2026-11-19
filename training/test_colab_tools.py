"""repeat_riders · fix_class_order · deploy_eval 의 순수 부분 시험. 실행: python -m unittest training.test_colab_tools"""
import tempfile
import unittest
from pathlib import Path

from training.deploy_eval import counts_from_matrix, model_size
from training.fix_class_order import fix_class_order
from training.repeat_riders import repeat_riders


def _make(root: Path, split: str, stem: str, label: str | None) -> None:
    (root / split / "images").mkdir(parents=True, exist_ok=True)
    (root / split / "labels").mkdir(parents=True, exist_ok=True)
    (root / split / "images" / f"{stem}.jpg").write_bytes(b"x")
    if label is not None:
        (root / split / "labels" / f"{stem}.txt").write_text(label, encoding="utf-8")


class RepeatRidersTest(unittest.TestCase):
    def test_repeats_only_bicycle_images_in_train(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _make(root, "train", "bike", "1 0.5 0.5 0.1 0.1\n0 0.2 0.2 0.1 0.1\n")
            _make(root, "train", "person", "0 0.5 0.5 0.1 0.1\n")
            _make(root, "train", "empty", "")
            _make(root, "valid", "vbike", "1 0.5 0.5 0.1 0.1\n")
            res = repeat_riders(root, repeat=3)
            self.assertEqual((res["riders"], res["copies"]), (1, 2))
            imgs = sorted(p.name for p in (root / "train" / "images").iterdir())
            self.assertEqual(imgs, ["bike.jpg", "bike_dup1.jpg", "bike_dup2.jpg", "empty.jpg", "person.jpg"])
            self.assertTrue((root / "train" / "labels" / "bike_dup2.txt").is_file())
            self.assertEqual(len(list((root / "valid" / "images").iterdir())), 1)  # valid 는 그대로

    def test_rerun_does_not_grow(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _make(root, "train", "bike", "1 0.5 0.5 0.1 0.1\n")
            repeat_riders(root, repeat=3)
            (root / "train" / "labels.cache").write_bytes(b"old")
            res = repeat_riders(root, repeat=3)
            self.assertEqual(res["train_images"], 3)
            self.assertEqual(res["removed_old_copies"], 4)  # 사진 2 + 라벨 2
            self.assertFalse((root / "train" / "labels.cache").exists())

    def test_keys_select_by_name(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _make(root, "train", "rider_01_jpg.rf.abc", "0 0.5 0.5 0.1 0.1\n")
            _make(root, "train", "bike_only", "1 0.5 0.5 0.1 0.1\n")
            res = repeat_riders(root, repeat=2, keys=["rider_"])
            self.assertEqual(res["riders"], 1)
            self.assertTrue((root / "train" / "images" / "rider_01_jpg.rf.abc_dup1.jpg").is_file())
            self.assertFalse((root / "train" / "images" / "bike_only_dup1.jpg").exists())

    def test_missing_train_folder_stops(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):
                repeat_riders(d)


class FixClassOrderTest(unittest.TestCase):
    def _export(self, root: Path, names: str) -> None:
        (root / "data.yaml").write_text(
            f"train: ../train/images\nval: ../valid/images\nnc: 2\nnames: {names}\n", encoding="utf-8")
        _make(root, "train", "a", "0 0.5 0.5 0.1 0.1\n1 0.3 0.3 0.1 0.1 0.2 0.2\n")
        _make(root, "valid", "b", "1 0.5 0.5 0.1 0.1\n")
        (root / "train" / "labels.cache").write_bytes(b"old")

    def test_swaps_alphabetical_order(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._export(root, "['bicycle', 'person']")
            res = fix_class_order(root)
            self.assertFalse(res["이미 맞음"])
            self.assertEqual((root / "train" / "labels" / "a.txt").read_text(encoding="utf-8"),
                             "1 0.5 0.5 0.1 0.1\n0 0.3 0.3 0.1 0.1 0.2 0.2\n")
            self.assertEqual((root / "valid" / "labels" / "b.txt").read_text(encoding="utf-8"),
                             "0 0.5 0.5 0.1 0.1\n")
            self.assertFalse((root / "train" / "labels.cache").exists())
            yaml_text = (root / "data.yaml").read_text(encoding="utf-8")
            self.assertIn("names: ['person', 'bicycle']", yaml_text)
            self.assertIn("train: train/images", yaml_text)
            self.assertIn("val: valid/images", yaml_text)
            self.assertNotIn("../", yaml_text)

    def test_rerun_is_safe(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._export(root, "['bicycle', 'person']")
            fix_class_order(root)
            before = (root / "train" / "labels" / "a.txt").read_text(encoding="utf-8")
            res = fix_class_order(root)
            self.assertTrue(res["이미 맞음"])
            self.assertEqual((root / "train" / "labels" / "a.txt").read_text(encoding="utf-8"), before)

    def test_unknown_class_stops(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._export(root, "['bicycle', 'car']")
            with self.assertRaises(ValueError):
                fix_class_order(root)
            self.assertEqual((root / "valid" / "labels" / "b.txt").read_text(encoding="utf-8"),
                             "1 0.5 0.5 0.1 0.1\n")  # 멈추면 라벨을 건드리지 않는다


class DeployEvalTest(unittest.TestCase):
    def test_model_size(self):
        self.assertEqual(model_size("yolo11n.pt"), "n")
        self.assertEqual(model_size("runs/yolo11s.pt"), "s")
        self.assertEqual(model_size(""), "")

    def test_counts_from_matrix(self):
        # 행=예측, 열=실제, 마지막=배경. 열0=person 실제, 열1=bicycle 실제
        mat = [[8, 1, 3],   # person 으로 예측: 실제 person 8, 실제 bicycle 1, 배경 3
               [2, 5, 4],   # bicycle 로 예측
               [6, 2, 0]]   # 예측 없음(놓침)
        try:
            import numpy as np
            mat = np.array(mat)
        except ImportError:
            self.skipTest("numpy 없음")
        c = counts_from_matrix(mat)
        self.assertEqual(c["person 총"], 16)
        self.assertEqual(c["person 놓침"], 6)
        self.assertEqual(c["놓침 비율"], round(6 / 16, 3))
        self.assertEqual((c["person→bicycle"], c["bicycle→person"]), (2, 1))
        self.assertEqual((c["bicycle 놓침"], c["오탐 person"], c["오탐 bicycle"]), (2, 3, 4))


if __name__ == "__main__":
    unittest.main()
