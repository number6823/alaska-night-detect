from __future__ import annotations

import datetime
from pathlib import Path

CLASS_NAMES = {0: "person", 1: "bicycle"}


def _read_boxes(path: Path) -> list[tuple]:
    """YOLO txt를 (cls, cx, cy, w, h) 목록으로 읽는다. 파일이 없으면 박스 0개."""
    if not path.exists():
        return []
    boxes = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        cls = int(parts[0])
        if cls not in CLASS_NAMES:
            raise ValueError(f"{path}: 클래스 {cls}는 없는 클래스입니다 (person=0, bicycle=1만 사용)")
        boxes.append((cls, *map(float, parts[1:5])))
    return boxes


def _iou(a: tuple, b: tuple) -> float:
    # 0~1 비율 좌표로 계산해도 가로·세로 배율이 분자·분모에 똑같이 곱해져 IoU는 같다.
    ax1, ay1, ax2, ay2 = a[1] - a[3] / 2, a[2] - a[4] / 2, a[1] + a[3] / 2, a[2] + a[4] / 2
    bx1, by1, bx2, by2 = b[1] - b[3] / 2, b[2] - b[4] / 2, b[1] + b[3] / 2, b[2] + b[4] / 2
    inter = max(0.0, min(ax2, bx2) - max(ax1, bx1)) * max(0.0, min(ay2, by2) - max(ay1, by1))
    union = a[3] * a[4] + b[3] * b[4] - inter
    return inter / union if union > 0 else 0.0


def _match(preds: list[tuple], gts: list[tuple], iou_threshold: float) -> dict:
    """같은 클래스끼리 IoU 큰 순으로 짝지어 클래스별 [TP, FP, FN]을 센다."""
    counts = {cls: [0, 0, 0] for cls in CLASS_NAMES}
    pairs = sorted(
        ((_iou(p, g), i, j) for i, p in enumerate(preds) for j, g in enumerate(gts) if p[0] == g[0]),
        reverse=True,
    )
    used_p, used_g = set(), set()
    for iou, i, j in pairs:
        if iou < iou_threshold:
            break
        if i in used_p or j in used_g:
            continue
        used_p.add(i)
        used_g.add(j)
        counts[preds[i][0]][0] += 1
    for i, p in enumerate(preds):
        if i not in used_p:
            counts[p[0]][1] += 1
    for j, g in enumerate(gts):
        if j not in used_g:
            counts[g[0]][2] += 1
    return counts


def _scores(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def _table(rows: dict) -> list[str]:
    lines = ["| 구분 | TP | FP(잘못 그림) | FN(놓침) | precision | recall | F1 |", "|---|---|---|---|---|---|---|"]
    for name, s in rows.items():
        lines.append(
            f"| {name} | {s['tp']} | {s['fp']} | {s['fn']} | {s['precision']:.3f} | {s['recall']:.3f} | {s['f1']:.3f} |"
        )
    return lines


def evaluate(
    pred_dir: str | Path = "data/gt100/pred",
    gt_dir: str | Path = "data/gt100/labels",
    report_path: str | Path = "data/accuracy_report.md",
    iou_threshold: float = 0.5,
) -> dict:
    """자동 라벨(pred_dir)을 정답 라벨(gt_dir)과 비교해 정확도를 계산하고 리포트를 쓴다.

    정답 txt가 있는 사진만 평가한다. 예측 txt가 없으면(폐기된 사진) 정답 박스는 모두 놓친 것으로 센다.
    일치율 = 전체 F1 (잘못 그린 박스와 놓친 박스를 둘 다 반영).
    """
    pred_dir = Path(pred_dir)
    gt_dir = Path(gt_dir)
    report_path = Path(report_path)

    # 라벨링 도구가 함께 내보내는 클래스 목록 파일은 정답이 아니므로 뺀다.
    gt_files = sorted(p for p in gt_dir.glob("*.txt") if p.name != "classes.txt")
    if not gt_files:
        raise FileNotFoundError(f"정답 라벨(.txt)이 없습니다: {gt_dir}")

    class_counts = {name: [0, 0, 0] for name in CLASS_NAMES.values()}
    group_counts: dict = {}
    per_image = []

    for gt_path in gt_files:
        counts = _match(_read_boxes(pred_dir / gt_path.name), _read_boxes(gt_path), iou_threshold)
        # 파일 이름 첫 "_" 앞(night, day)으로 야간·낮을 나눠 본다.
        group = group_counts.setdefault(gt_path.stem.split("_")[0], [0, 0, 0])
        for cls, values in counts.items():
            for k, v in enumerate(values):
                class_counts[CLASS_NAMES[cls]][k] += v
                group[k] += v
        per_image.append((sum(fp + fn for _, fp, fn in counts.values()), gt_path.stem))

    total = [sum(c[k] for c in class_counts.values()) for k in range(3)]
    overall = _scores(*total)
    per_class = {name: _scores(*c) for name, c in class_counts.items()}
    per_group = {name: _scores(*c) for name, c in sorted(group_counts.items())}
    worst = [(e, stem) for e, stem in sorted(per_image, reverse=True) if e > 0][:10]

    lines = [
        "# 자동 라벨 정확도 리포트",
        "",
        f"- 날짜: {datetime.date.today().isoformat()}",
        f"- 비교: 자동 라벨 `{pred_dir}` vs 정답 `{gt_dir}`, IoU {iou_threshold} 이상이면 맞음",
        f"- 사진: {len(gt_files)}장",
        f"- **일치율(F1): {overall['f1']:.1%}** (보고용, 목표 아님)",
        "",
        "## 클래스별",
        "",
        *_table({**per_class, "전체": overall}),
        "",
        "## 야간·낮별 (파일 이름 앞부분 기준)",
        "",
        *_table(per_group),
        "",
        "## 틀린 박스가 많은 사진 (검수 우선)",
        "",
        *([f"- {stem}: {e}개" for e, stem in worst] or ["- 없음"]),
        "",
    ]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")

    return {
        "images": len(gt_files),
        **overall,
        "per_class": per_class,
        "per_group": per_group,
        "report_path": str(report_path),
    }
