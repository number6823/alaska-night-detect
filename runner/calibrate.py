"""거리기준 영상에서 거리 기준값(calibration.json)을 만든다.

실행: python -m runner.calibrate --video <거리기준 영상> --out data/runner/calibration.json
        [--times 3-13,18-28,33-43] [--height-m 0.7] [--tilt-deg 15] [--model yolo11n.pt]

거리기준 영상(촬영 계획표 9번): 카메라를 고정하고, 바닥의 5.5m → 3m → 2m 표시 위에 차례로 서서 각 10초 정도
카메라를 본다(마지막에 돌아서서 2m 에서 한 번 더). 이 도구가 하는 일:
  1. 영상에서 사람 박스를 찾아 박스 아래 끝(발)의 화면 높이 비율을 시간순으로 모은다.
  2. 발 위치가 거의 움직이지 않는 구간(서 있는 구간)을 찾는다. 걸어서 이동하는 구간은 자동으로 빠진다.
  3. 시간순으로 앞의 세 구간을 5.5m, 3m, 2m 로 보고 alarm.levels.calibrate_from_samples 로 기준값을 만든다.
  4. 구간이 잘못 잡혔거나 순서가 안 맞으면(가까울수록 아래여야 한다) 이유를 보여 주고 멈춘다.

구간을 자동으로 못 찾거나 틀리면 --times 로 초 단위 구간 세 개를 직접 준다(5.5m, 3m, 2m 순서).
카메라 높이·기울기를 알려 주면(--height-m, --tilt-deg) 찾은 값이 기하학적으로 말이 되는지(표시를 맞게 놓았는지)
같이 점검해서 보여 준다. 이 점검은 참고이고, 기준값은 영상에서 잰 값 그대로 만든다.
"""

from __future__ import annotations

import argparse
import statistics
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from alarm.levels import (
    calibrate_from_samples,
    foot_ratio_at,
    save_calibration,
)

DIST_NAMES = ("5.5m", "3m", "2m")
STEP_S = 0.2  # 시간 눈금 간격(초). 발 위치를 이 간격으로 다시 모은다
WINDOW_S = 2.0  # 서 있는지 판단하는 창 길이(초)
STILL_STD = (
    0.012  # 창 안에서 발 위치(화면 높이 비율)의 표준편차가 이 이하면 서 있다고 본다
)
MERGE_GAP = 0.02  # 서 있는 구간 둘의 대표값 차이가 이 이하면 같은 구간으로 합친다
MIN_PLATEAU_S = 2.5  # 이보다 짧게 서 있던 구간은 버린다


def collect_samples(
    source,
    detector,
    stride: int = 3,
    min_conf: float = 0.3,
    max_seconds: Optional[float] = None,
) -> List[dict]:
    """영상을 stride 프레임마다 감지해서 {t, box, frame_h} 목록을 만든다. 사람은 가장 큰 박스 하나만 쓴다.

    박스 아래가 화면 아래 끝에 닿은 것(발이 잘림)은 발 위치를 못 믿어서 뺀다.
    """
    out = []
    idx = 0
    fps = source.fps
    while True:
        frame = source.read()
        if frame is None:
            break
        t = idx / fps
        if max_seconds is not None and t > max_seconds:
            break
        if idx % stride == 0:
            h = frame.shape[0]
            people = [
                b
                for b in detector.detect(frame)
                if round(b[5]) == 0 and b[4] >= min_conf
            ]
            if people:
                box = max(people, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
                if box[3] < h * 0.995:
                    out.append({"t": t, "box": tuple(box), "frame_h": h})
        idx += 1
    return out


def _resample(samples: Sequence[dict]) -> Tuple[List[Optional[float]], float]:
    """STEP_S 간격 눈금마다 가장 가까운 샘플의 발 위치를 넣는다(눈금에서 STEP_S 안에 샘플이 없으면 None)."""
    if not samples:
        return [], 0.0
    t0 = samples[0]["t"]
    n = int((samples[-1]["t"] - t0) / STEP_S) + 1
    grid: List[Optional[float]] = [None] * n
    for s in samples:
        k = int(round((s["t"] - t0) / STEP_S))
        if 0 <= k < n:
            y = s["box"][3] / s["frame_h"]
            grid[k] = y if grid[k] is None else (grid[k] + y) / 2
    return grid, t0


def find_plateaus(samples: Sequence[dict]) -> List[dict]:
    """발 위치가 거의 움직이지 않는 구간들을 시간순으로 돌려준다.

    각 구간: {start, end, median, std, n}. 걸어서 이동하는 동안은 발 위치가 계속 바뀌어서 빠진다.
    """
    grid, t0 = _resample(samples)
    w = max(3, int(round(WINDOW_S / STEP_S)))
    still = [False] * len(grid)
    centers = [None] * len(grid)
    for i in range(0, len(grid) - w + 1):
        win = [v for v in grid[i : i + w] if v is not None]
        if len(win) >= 0.6 * w and statistics.pstdev(win) <= STILL_STD:
            for j in range(i, i + w):
                still[j] = True
            centers[i] = statistics.median(win)
    # 서 있는 눈금을 이어 붙이되, 대표값이 크게 달라지면 구간을 끊는다
    plateaus: List[dict] = []
    i = 0
    while i < len(grid):
        if not still[i]:
            i += 1
            continue
        j = i
        vals: List[float] = []
        while j < len(grid) and still[j]:
            if grid[j] is not None:
                if vals and abs(grid[j] - statistics.median(vals)) > MERGE_GAP:
                    break
                vals.append(grid[j])
            j += 1
        if vals and (j - i) * STEP_S >= MIN_PLATEAU_S:
            plateaus.append(
                {
                    "start": round(t0 + i * STEP_S, 2),
                    "end": round(t0 + j * STEP_S, 2),
                    "median": statistics.median(vals),
                    "std": statistics.pstdev(vals),
                    "n": len(vals),
                }
            )
        i = max(j, i + 1)
    return plateaus


def parse_times(text: str) -> List[Tuple[float, float]]:
    spans = []
    for part in text.split(","):
        a, _, b = part.partition("-")
        start, end = float(a), float(b)
        if end <= start:
            raise ValueError(f"구간 {part!r} 의 끝이 시작보다 늦어야 한다")
        spans.append((start, end))
    if len(spans) != 3:
        raise ValueError(f"--times 는 구간 세 개(5.5m, 3m, 2m 순서)여야 한다: {text!r}")
    return spans


def pick_spans(
    samples: Sequence[dict], times: Optional[Sequence[Tuple[float, float]]] = None
) -> List[Tuple[float, float]]:
    """5.5m, 3m, 2m 에 해당하는 시간 구간 세 개를 정한다. times 를 주면 그대로, 아니면 자동으로 찾는다."""
    if times:
        return list(times)
    plateaus = find_plateaus(samples)
    if len(plateaus) < 3:
        raise ValueError(
            f"서 있는 구간을 {len(plateaus)}개만 찾았다(3개 이상 필요). "
            f"찾은 구간: {[(p['start'], p['end'], round(p['median'], 3)) for p in plateaus]}. "
            "사람이 가려지거나 너무 어두워 감지가 끊겼을 수 있다. --times 로 구간을 직접 주거나 --min-conf 를 낮춘다"
        )
    return [(p["start"], p["end"]) for p in plateaus[:3]]


def build_calibration(
    samples: Sequence[dict],
    spans: Sequence[Tuple[float, float]],
    camera_height_cm: int = 70,
    margin: float = 0.0,
):
    """구간 세 개의 박스로 기준값을 만든다. 돌려주는 값: (Calibration, 구간별 요약 목록)."""
    groups = []
    summary = []
    frame_h = samples[0]["frame_h"] if samples else 1080
    for name, (a, b) in zip(DIST_NAMES, spans):
        boxes = [s["box"] for s in samples if a <= s["t"] <= b]
        if not boxes:
            raise ValueError(f"{name} 구간({a}~{b}초)에서 사람 박스를 못 찾았다")
        groups.append(boxes)
        ys = [bx[3] / frame_h for bx in boxes]
        summary.append(
            {
                "name": name,
                "start": a,
                "end": b,
                "n": len(boxes),
                "foot": statistics.median(ys),
                "std": statistics.pstdev(ys) if len(ys) > 1 else 0.0,
            }
        )
    cal = calibrate_from_samples(
        groups[0], groups[1], groups[2], frame_h, camera_height_cm, margin
    )
    return cal, summary


SANITY_TOL = (
    0.02  # 세 점을 맞춘 뒤에도 이보다 어긋나면 표시 위치나 높이 입력을 의심한다
)
SANITY_VFOV = (20.0, 150.0)  # 맞춘 세로 화각이 이 범위 밖이면 말이 안 된다
SANITY_TILT = (-10.0, 60.0)  # 맞춘 기울기(아래로 +)가 이 범위 밖이면 말이 안 된다
DISTANCES = (5.5, 3.0, 2.0)


def fit_geometry(
    foots: Sequence[float], camera_height_m: float
) -> Tuple[float, float, float]:
    """세 거리(5.5m·3m·2m)에서 잰 발 위치에 기울기와 세로 화각을 함께 맞춘다. (기울기, 화각, 가장 큰 오차).

    한 점만으로 화각을 구하면 측정 오차에 크게 흔들리므로(특히 화면 한가운데 근처 지점) 세 점을 다 쓴다.
    표준 라이브러리만 쓰는 격자 탐색이다(굵게 찾은 뒤 근처를 촘촘하게).
    """

    def loss(tilt: float, vfov: float) -> float:
        return sum(
            (foot_ratio_at(d, camera_height_m, tilt, vfov) - f) ** 2
            for d, f in zip(DISTANCES, foots)
        )

    best = None
    tilt = SANITY_TILT[0]
    while tilt <= SANITY_TILT[1]:
        vfov = SANITY_VFOV[0]
        while vfov <= SANITY_VFOV[1]:
            err = loss(tilt, vfov)
            if best is None or err < best[0]:
                best = (err, tilt, vfov)
            vfov += 2.0
        tilt += 1.0
    _, t0, v0 = best
    tilt = t0 - 1.5  # 굵게 찾은 값 근처를 촘촘하게 다시 본다
    while tilt <= t0 + 1.5:
        vfov = max(1.0, v0 - 2.5)
        while vfov <= v0 + 2.5:
            err = loss(tilt, vfov)
            if err < best[0]:
                best = (err, tilt, vfov)
            vfov += 0.2
        tilt += 0.1
    _, tilt, vfov = best
    worst = max(
        abs(foot_ratio_at(d, camera_height_m, tilt, vfov) - f)
        for d, f in zip(DISTANCES, foots)
    )
    return tilt, vfov, worst


def sanity_report(
    summary: Sequence[dict], camera_height_m: float, tilt_deg: float
) -> List[str]:
    """찾은 발 위치가 기하학적으로 말이 되는지 본다.

    렌즈 높이는 알고 있으니 기울기와 세로 화각을 세 점에 함께 맞춰 보고, 맞춘 뒤에도 어긋나거나
    맞춘 값이 상식 밖이면 표시 위치(5.5m·3m·2m)나 높이 입력을 확인하라고 알린다.
    """
    by = {s["name"]: s for s in summary}
    foots = [by[n]["foot"] for n in DIST_NAMES]
    tilt, vfov, worst = fit_geometry(foots, camera_height_m)
    notes = [
        f"세 점에 맞춘 값: 기울기 {tilt:.0f}도, 세로 화각 {vfov:.0f}도 (높이 {camera_height_m}m 가정, 입력한 기울기 {tilt_deg:.0f}도)"
    ]
    problems = []
    if worst > SANITY_TOL:
        problems.append(f"맞춘 뒤에도 가장 어긋난 곳이 {worst:.3f}")
    if not SANITY_VFOV[0] < vfov < SANITY_VFOV[1] or not (
        SANITY_TILT[0] < tilt < SANITY_TILT[1]
    ):
        problems.append("맞춘 화각이나 기울기가 상식 범위 밖")
    if problems:
        notes.append(
            "  <- "
            + ", ".join(problems)
            + ": 표시 위치나 높이 입력을 확인한다 (기준값은 영상에서 잰 값 그대로 저장한다)"
        )
    else:
        notes.append(f"잰 값이 이 값에 맞는다 (가장 큰 오차 {worst:.3f})")
    return notes


def main() -> None:
    p = argparse.ArgumentParser(
        prog="python -m runner.calibrate",
        description="거리기준 영상으로 거리 기준값을 만든다",
    )
    p.add_argument(
        "--video",
        required=True,
        help="거리기준 영상(5.5m → 3m → 2m 에 차례로 서 있는 영상)",
    )
    p.add_argument(
        "--out", default="data/runner/calibration.json", help="기준값을 저장할 JSON"
    )
    p.add_argument(
        "--times",
        help="구간을 직접 준다: 5.5m 구간,3m 구간,2m 구간 (예: 3-13,18-28,33-43, 단위 초)",
    )
    p.add_argument("--model", default="yolo11n.pt")
    p.add_argument("--device", default="")
    p.add_argument("--min-conf", type=float, default=0.3)
    p.add_argument("--stride", type=int, default=3, help="몇 프레임마다 감지할지")
    p.add_argument(
        "--height-m",
        type=float,
        default=0.7,
        help="렌즈 높이(미터). 점검과 기록에만 쓴다",
    )
    p.add_argument(
        "--tilt-deg", type=float, default=15.0, help="아래로 기울인 각도. 점검에만 쓴다"
    )
    p.add_argument(
        "--margin",
        type=float,
        default=0.0,
        help="경계를 이만큼 위로 당겨 일찍 울리게 한다(화면 높이 비율)",
    )
    a = p.parse_args()

    from .detector import Detector
    from .sources import VideoSource

    src = VideoSource(a.video)
    if not src.opened:
        raise SystemExit(f"영상을 못 열었다: {a.video}")
    det = Detector(a.model, a.min_conf, a.device or None)
    print(f"감지 장치: {det.describe()}")
    samples = collect_samples(src, det, a.stride, a.min_conf)
    src.release()
    print(f"사람 박스를 찾은 시점 {len(samples)}개")
    if not samples:
        raise SystemExit(
            "사람 박스를 못 찾았다. 영상에 사람이 서 있는지, --min-conf 를 낮춰 본다"
        )
    times = parse_times(a.times) if a.times else None
    try:
        spans = pick_spans(samples, times)
        cal, summary = build_calibration(
            samples, spans, round(a.height_m * 100), a.margin
        )
    except ValueError as exc:
        raise SystemExit(f"실패: {exc}")
    for s in summary:
        print(
            f"  {s['name']:>4}: {s['start']:.1f}~{s['end']:.1f}초, 박스 {s['n']}개, 발 위치 {s['foot']:.3f} (흔들림 {s['std']:.3f})"
        )
    for line in sanity_report(summary, a.height_m, a.tilt_deg):
        print("  " + line)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    save_calibration(cal, a.out)
    print(f"기준값 저장: {a.out}")
    print(
        f"  5.5m 이내 {cal.foot_5_5:.3f} / 3m 이내 {cal.foot_3:.3f} / 2m 이내 {cal.foot_2:.3f} (화면 높이 {cal.frame_height}px 기준 비율)"
    )
    print("사용: python -m runner --source <영상> --calibration " + a.out)


if __name__ == "__main__":
    main()
