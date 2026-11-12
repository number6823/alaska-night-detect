"""후방 촬영 프레임에 모델을 돌려 시나리오별 감지 현황을 표와 그래프로 만든다. 라벨(정답)이 없어도 된다.

실행: python -m training.rear_report --frames <프레임 폴더> --model <pt 경로> [--out <결과 폴더>] [--conf 0.25]
      (프레임 폴더는 training.extract_frames가 만든 manifest.csv가 있어야 한다)
지표(라벨 없는 대용 지표, 참고용):
- 감지율: 사람·자전거가 나오는 시나리오에서 하나라도 잡은 프레임 비율. 영상 앞뒤에 대상이 없는 프레임도 있어 100%가 되지 않는다.
- 자전거 감지율: 자전거 시나리오에서 bicycle을 잡은 프레임 비율.
- 오탐: 빈 장면 클립에서 잡은 프레임 수(0이어야 한다).
- 놓친 프레임 사진: 대상이 있어야 하는데 못 잡은 프레임을 missed/ 폴더에 저장한다(원인을 눈으로 보기 위함).
정확한 F1·AP50은 라벨이 있는 평가셋에서 python -m labeler eval로 잰다.
"""

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

PERSON, BICYCLE = 0, 1
EMPTY_WORDS = ("빈", "empty")
BIKE_WORDS = ("자전거", "bike", "bicycle")


def scenario_kind(name: str) -> str:
    """시나리오 이름으로 기대를 정한다: empty(아무도 없음), bike(자전거), person(보행자 등)."""
    low = name.lower()
    if any(w in low for w in EMPTY_WORDS):
        return "empty"
    if any(w in low for w in BIKE_WORDS):
        return "bike"
    return "person"


def _read(path: Path):
    return cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)


def predict_frames(
    model_path: str,
    frame_dir: Path,
    rows: list,
    conf: float,
    imgsz: int,
    batch: int = 16,
) -> list:
    from ultralytics import YOLO

    model = YOLO(model_path)
    out = []
    for i in range(0, len(rows), batch):
        chunk = rows[i : i + batch]
        imgs = [_read(frame_dir / r["frame"]) for r in chunk]
        for r, res in zip(
            chunk,
            model.predict(
                imgs, conf=conf, imgsz=imgsz, classes=[PERSON, BICYCLE], verbose=False
            ),
        ):
            cls = res.boxes.cls.cpu().numpy().astype(int).tolist()
            confs = res.boxes.conf.cpu().numpy().tolist()
            out.append(
                {
                    **r,
                    "person": cls.count(PERSON),
                    "bicycle": cls.count(BICYCLE),
                    "max_conf": round(max(confs), 3) if confs else 0.0,
                }
            )
    return out


def summarize(results: list) -> dict:
    """(구분, 이름)별로 프레임 수, 감지율, 자전거 감지율, 오탐 프레임 수를 모은다."""
    groups = defaultdict(list)
    for r in results:
        groups[(r["round"] or "-", r["scenario"])].append(r)
    summary = {}
    for key, rs in sorted(groups.items()):
        kind = scenario_kind(key[1])
        any_det = sum(1 for r in rs if r["person"] + r["bicycle"] > 0)
        bike_det = sum(1 for r in rs if r["bicycle"] > 0)
        summary[key] = {
            "kind": kind,
            "frames": len(rs),
            "det_rate": any_det / len(rs),
            "bike_rate": bike_det / len(rs),
            "false_pos": any_det if kind == "empty" else 0,
        }
    return summary


def save_missed(results: list, frame_dir: Path, out_dir: Path, limit: int = 40) -> int:
    missed_dir = out_dir / "missed"
    missed_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for r in results:
        if (
            scenario_kind(r["scenario"]) != "empty"
            and r["person"] + r["bicycle"] == 0
            and n < limit
        ):
            img = _read(frame_dir / r["frame"])
            ok, buf = cv2.imencode(".jpg", img)
            if ok:
                buf.tofile(str(missed_dir / r["frame"]))
                n += 1
    return n


def write_report(
    summary: dict, results: list, out_dir: Path, model: str, conf: float, missed: int
) -> None:
    total = len(results)
    lines = [
        "# 후방 촬영 감지 현황 (라벨 없는 대용 지표, 참고용)",
        "",
        f"- 모델: `{model}`, conf {conf}, 프레임 {total}장",
        f"- 놓친 프레임 사진 {missed}장을 `missed/`에 저장했다.",
        "",
        "| 라운드 | 시나리오 | 구분 | 프레임 | 감지율 | 자전거 감지율 | 오탐 프레임 |",
        "|---|---|---|---|---|---|---|",
    ]
    for (rnd, name), s in summary.items():
        bike = f"{s['bike_rate']:.0%}" if s["kind"] == "bike" else "-"
        det = "-" if s["kind"] == "empty" else f"{s['det_rate']:.0%}"
        fp = s["false_pos"] if s["kind"] == "empty" else "-"
        lines.append(
            f"| {rnd} | {name} | {s['kind']} | {s['frames']} | {det} | {bike} | {fp} |"
        )
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with open(out_dir / "frames.csv", "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)


def plot(summary: dict, out_dir: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.family"] = [
        "Malgun Gothic",
        "AppleGothic",
        "NanumGothic",
        "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False
    items = [(k, s) for k, s in summary.items() if s["kind"] != "empty"]
    if not items:
        return
    labels = [f"{k[0]} {k[1]}" for k, _ in items]
    rates = [s["det_rate"] * 100 for _, s in items]
    fig, ax = plt.subplots(figsize=(max(6, len(items) * 0.9), 4))
    colors = ["#c0312b" if r < 80 else "#2f6db5" for r in rates]
    ax.bar(range(len(items)), rates, color=colors)
    ax.set_xticks(range(len(items)))
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_ylim(0, 100)
    ax.set_ylabel("감지율 (%)")
    ax.set_title("시나리오별 감지율 (빨강 = 80% 미만, 보강 촬영 후보)")
    fig.tight_layout()
    fig.savefig(out_dir / "detect_rate.png", dpi=150)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m training.rear_report")
    parser.add_argument(
        "--frames",
        required=True,
        help="training.extract_frames가 만든 폴더(manifest.csv 포함)",
    )
    parser.add_argument("--model", required=True, help="학습한 가중치(.pt)")
    parser.add_argument("--out", default=None, help="결과 폴더 (기본: <frames>/report)")
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument(
        "--split",
        choices=["all", "train", "eval"],
        default="all",
        help="manifest의 용도로 거름",
    )
    args = parser.parse_args()

    frame_dir = Path(args.frames)
    out_dir = Path(args.out) if args.out else frame_dir / "report"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(frame_dir / "manifest.csv", encoding="utf-8-sig") as f:
        rows = [
            r
            for r in csv.DictReader(f)
            if args.split == "all" or r["split"] == args.split
        ]
    if not rows:
        raise SystemExit("대상 프레임이 없습니다. manifest.csv와 --split을 확인하세요.")

    results = predict_frames(args.model, frame_dir, rows, args.conf, args.imgsz)
    summary = summarize(results)
    missed = save_missed(results, frame_dir, out_dir)
    write_report(summary, results, out_dir, args.model, args.conf, missed)
    try:
        plot(summary, out_dir)
    except (
        ImportError,
        ValueError,
        OSError,
        RuntimeError,
    ) as e:  # matplotlib 설치가 깨진 PC에서도 표(report.md)는 남기려고 그래프 실패만 넘긴다
        print(f"[그래프 건너뜀] {type(e).__name__}: {e}")
    print(
        f"리포트: {out_dir / 'report.md'}\n놓친 프레임: {missed}장 ({out_dir / 'missed'})"
    )


if __name__ == "__main__":
    main()
