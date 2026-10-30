from __future__ import annotations

import datetime
from pathlib import Path

CLASS_NAMES = {0: "person", 1: "bicycle"}
# TIDE(Bolya et al. 2020)의 배경 기준: 모든 정답 박스와 IoU가 이 미만이면 배경 오류(Bkg).
BG_IOU = 0.1
ERROR_TYPES = ["Cls", "Loc", "Both", "Dupe", "Bkg", "Miss"]


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


def _match_scored(preds: list[tuple], gts: list[tuple], iou_threshold: float) -> tuple[list[str], int]:
    """conf 높은 순으로 아직 안 쓴 같은 클래스 정답과 짝짓고(COCO 방식) 틀린 박스를 TIDE 종류로 나눈다.

    preds는 (cls, cx, cy, w, h, conf). 반환: 박스별 "TP" 또는 오류 종류, 놓친 정답 수(Miss).
    """
    used = [False] * len(gts)
    covered = set()  # Cls·Loc 오류가 가리키는 정답은 Miss로 다시 세지 않는다.
    kinds = []
    for p in sorted(preds, key=lambda b: -b[5]):
        same = [(_iou(p, g), j) for j, g in enumerate(gts) if g[0] == p[0]]
        other = [(_iou(p, g), j) for j, g in enumerate(gts) if g[0] != p[0]]
        free = max(((v, j) for v, j in same if not used[j]), default=(0.0, -1))
        if free[0] >= iou_threshold:
            used[free[1]] = True
            kinds.append("TP")
            continue
        best_same = max(same, default=(0.0, -1))
        best_other = max(other, default=(0.0, -1))
        if best_same[0] >= iou_threshold:
            kinds.append("Dupe")  # 맞는 정답이 이미 다른 박스와 짝지어짐
        elif best_other[0] >= iou_threshold:
            kinds.append("Cls")
            covered.add(best_other[1])
        elif best_same[0] >= BG_IOU:
            kinds.append("Loc")
            covered.add(best_same[1])
        elif best_other[0] >= BG_IOU:
            kinds.append("Both")
        else:
            kinds.append("Bkg")
    miss = sum(not used[j] and j not in covered for j in range(len(gts)))
    return kinds, miss


def _ap(hits: list[tuple], n_gt: int) -> float:
    """(conf, TP 여부) 목록으로 VOC 방식 AP를 구한다. precision은 오른쪽 최대값으로 채운다."""
    if not n_gt:
        return 0.0
    points = []
    tp = 0
    for k, (_, hit) in enumerate(sorted(hits, key=lambda h: -h[0]), 1):
        tp += hit
        points.append((tp / n_gt, tp / k))
    ap, prev_recall, best = 0.0, 0.0, 0.0
    envelope = []
    for recall, precision in reversed(points):
        best = max(best, precision)
        envelope.append((recall, best))
    for recall, precision in reversed(envelope):
        ap += (recall - prev_recall) * precision
        prev_recall = recall
    return ap


def _ap50(scored: dict, gts: dict, iou_threshold: float, min_conf: float) -> dict:
    """사진별 conf 있는 예측(scored)에서 min_conf 이상만 써서 클래스별 AP와 평균(mAP)을 구한다."""
    hits = {cls: [] for cls in CLASS_NAMES}
    n_gt = {cls: 0 for cls in CLASS_NAMES}
    for stem, g in gts.items():
        preds = sorted((b for b in scored.get(stem, []) if b[5] >= min_conf), key=lambda b: -b[5])
        kinds, _ = _match_scored(preds, g, iou_threshold)
        for b, kind in zip(preds, kinds):
            hits[b[0]].append((b[5], kind == "TP"))
        for b in g:
            n_gt[b[0]] += 1
    per_class = {CLASS_NAMES[c]: round(_ap(hits[c], n_gt[c]), 4) for c in CLASS_NAMES}
    return {**per_class, "mAP50": round(sum(per_class.values()) / len(per_class), 4)}


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
    scored: dict | None = None,
    discard_threshold: float = 0.25,
) -> dict:
    """자동 라벨(pred_dir)을 정답 라벨(gt_dir)과 비교해 정확도를 계산하고 리포트를 쓴다.

    정답 txt가 있는 사진만 평가한다. 예측 txt가 없으면(폐기된 사진) 정답 박스는 모두 놓친 것으로 센다.
    일치율 = 전체 F1 (잘못 그린 박스와 놓친 박스를 둘 다 반영).
    scored(사진별 (cls, cx, cy, w, h, conf), autolabel.predict_scored)를 주면 AP50과 오류 종류 개수도 낸다.
    오류 종류는 labeler가 실제로 내보내는 discard_threshold 이상 박스로 센다.
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

    ap50 = ap50_labeler = errors = None
    extra = []
    if scored is not None:
        gts = {p.stem: _read_boxes(p) for p in gt_files}
        ap50 = _ap50(scored, gts, iou_threshold, 0.0)
        ap50_labeler = _ap50(scored, gts, iou_threshold, discard_threshold)
        errors = dict.fromkeys(["TP", *ERROR_TYPES], 0)
        for stem, g in gts.items():
            kinds, miss = _match_scored([b for b in scored.get(stem, []) if b[5] >= discard_threshold], g, iou_threshold)
            for kind in kinds:
                errors[kind] += 1
            errors["Miss"] += miss
        extra = [
            "## AP50",
            "",
            "| 기준 | person | bicycle | mAP50 |",
            "|---|---|---|---|",
            "| 낮은 conf까지 예측 전부 (표준 방식, eval은 conf 0.001부터) "
            f"| {ap50['person']:.3f} | {ap50['bicycle']:.3f} | {ap50['mAP50']:.3f} |",
            f"| labeler 출력 (conf {discard_threshold} 이상) "
            f"| {ap50_labeler['person']:.3f} | {ap50_labeler['bicycle']:.3f} | {ap50_labeler['mAP50']:.3f} |",
            "",
            f"## 오류 종류 (TIDE 방식, labeler 출력 conf {discard_threshold} 이상, IoU {iou_threshold} / 배경 {BG_IOU})",
            "",
            "| TP | Cls | Loc | Both | Dupe | Bkg | Miss |",
            "|---|---|---|---|---|---|---|",
            "| " + " | ".join(str(errors[k]) for k in ["TP", *ERROR_TYPES]) + " |",
            "",
            "- Cls: 위치는 맞는데(IoU 기준 이상) 클래스가 틀림",
            f"- Loc: 클래스는 맞는데 위치가 어긋남 (IoU {BG_IOU} 이상 {iou_threshold} 미만)",
            "- Both: 클래스도 틀리고 위치도 어긋남",
            "- Dupe: 이미 다른 박스가 잡은 정답에 또 그림",
            f"- Bkg: 어떤 정답과도 거의 안 겹침 (IoU {BG_IOU} 미만). 정답에서 안 그린 작은 사람도 여기에 들어갈 수 있음",
            "- Miss: 놓친 정답 중 Cls·Loc 오류로 설명되지 않는 것",
            "- 짝짓는 순서가 위 F1 표(IoU 큰 순)와 달라(conf 높은 순) TP 수가 조금 다를 수 있음",
            "",
        ]

    lines = [
        "# 자동 라벨 정확도 리포트",
        "",
        f"- 날짜: {datetime.date.today().isoformat()}",
        f"- 비교: 자동 라벨 `{pred_dir}` vs 정답 `{gt_dir}`, IoU {iou_threshold} 이상이면 맞음",
        f"- 사진: {len(gt_files)}장",
        f"- **일치율(F1): {overall['f1']:.1%}** (보고용, 목표 아님)",
        "- 주의: labeler 기준값(NMS 0.5, 검수 conf 0.7)은 gt100에서 골랐다. gt100으로 잰 숫자는 낙관적일 수 있다",
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
        *extra,
    ]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")

    return {
        "images": len(gt_files),
        **overall,
        "per_class": per_class,
        "per_group": per_group,
        "ap50": ap50,
        "ap50_labeler": ap50_labeler,
        "errors": errors,
        "report_path": str(report_path),
    }
