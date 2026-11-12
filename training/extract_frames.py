"""촬영 영상에서 프레임을 뽑고 영상 단위 목록(manifest.csv)을 만든다.

실행: python -m training.extract_frames --videos <영상 폴더> --out <프레임 폴더> [--fps 2] [--eval-rounds R5]
파일명 규칙: 20261112_R1_01_보행접근.mp4 (날짜_라운드_번호_이름), 촬영_계획표.md 참고.
- manifest.csv: 프레임 경로, 영상, 라운드, 번호, 시나리오, 용도(train/eval), 영상 안 시각
- 용도는 라운드로 정한다(기본 R5는 eval). 같은 영상의 프레임은 한쪽에만 들어가므로 영상 단위 분할이 된다.
"""

import argparse
import csv
import re
import shutil
import tempfile
from pathlib import Path

import cv2

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".m4v"}
NAME_RE = re.compile(r"^(?P<date>\d{8})_(?P<round>R\d+)_(?P<no>\d+)_(?P<name>.+)$")


def parse_name(stem: str) -> dict:
    """파일 이름에서 라운드·번호·시나리오를 읽는다. 규칙에 안 맞으면 빈 값으로 둔다."""
    m = NAME_RE.match(stem)
    if not m:
        return {"round": "", "no": "", "scenario": stem}
    return {"round": m["round"], "no": m["no"], "scenario": m["name"]}


def _open(path: Path):
    """한글 경로를 못 여는 OpenCV 빌드를 위해 실패하면 영문 임시 이름으로 복사해 다시 연다."""
    cap = cv2.VideoCapture(str(path))
    if cap.isOpened():
        return cap, None
    tmp = Path(tempfile.mkdtemp()) / ("clip" + path.suffix.lower())
    shutil.copy(path, tmp)
    return cv2.VideoCapture(str(tmp)), tmp


def _save(path: Path, frame) -> None:
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
    if not ok:
        raise RuntimeError(f"프레임 인코딩 실패: {path}")
    buf.tofile(str(path))  # imwrite는 한글 경로에서 실패할 수 있어 tofile을 쓴다


def extract(videos: str, out: str, fps: float = 2.0, eval_rounds=("R5",)) -> Path:
    videos_dir, out_dir = Path(videos), Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    files = sorted(p for p in videos_dir.rglob("*") if p.suffix.lower() in VIDEO_EXTS)
    if not files:
        raise FileNotFoundError(f"영상이 없습니다: {videos_dir}")
    for vid in files:
        cap, tmp = _open(vid)
        if not cap.isOpened():
            print(f"[건너뜀] 영상을 열 수 없음: {vid.name}")
            continue
        src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        step = max(1, round(src_fps / fps))
        info = parse_name(vid.stem)
        split = "eval" if info["round"] in eval_rounds else "train"
        idx = kept = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % step == 0:
                name = f"{vid.stem}_f{idx:05d}.jpg"
                _save(out_dir / name, frame)
                rows.append(
                    {
                        "frame": name,
                        "video": vid.name,
                        **info,
                        "split": split,
                        "sec": round(idx / src_fps, 2),
                    }
                )
                kept += 1
            idx += 1
        cap.release()
        if tmp is not None:
            shutil.rmtree(tmp.parent, ignore_errors=True)
        print(f"{vid.name}: {kept}장 ({split})")
    manifest = out_dir / "manifest.csv"
    with open(manifest, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f, fieldnames=["frame", "video", "round", "no", "scenario", "split", "sec"]
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"프레임 {len(rows)}장 → {out_dir}  목록: {manifest}")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m training.extract_frames")
    parser.add_argument("--videos", required=True, help="영상 폴더")
    parser.add_argument(
        "--out",
        required=True,
        help="프레임을 저장할 폴더 (data/ 안을 권장, 레포에 올리지 않는다)",
    )
    parser.add_argument(
        "--fps", type=float, default=2.0, help="초당 뽑을 프레임 수 (평가용은 1 정도)"
    )
    parser.add_argument(
        "--eval-rounds", nargs="*", default=["R5"], help="평가 전용으로 쓸 라운드"
    )
    args = parser.parse_args()
    extract(args.videos, args.out, args.fps, tuple(args.eval_rounds))


if __name__ == "__main__":
    main()
