"""이벤트 평가: 박스 라벨 없이 "경보가 제때 울렸나"를 숫자로 낸다.

영상에서 사람이 읽어 적은 시각(발이 5.5m·3m·2m 선을 넘은 순간, 화면에 들어오고 나간 순간)을 정답으로 삼고,
runner 와 같은 파이프라인(거리 단계 + 3프레임 중 2번 규칙)이 낸 경보 시각과 견준다.

두 단계로 나눈다. 감지는 느려서 영상마다 한 번만 하고, 경보 설정을 바꿔 보는 것은 저장한 박스로 몇 초 만에 다시 한다.
  1) dump      영상 → 프레임별 박스(JSON). 모델이 필요하다.
  2) eval      박스 JSON + 이벤트 CSV + 보정 파일 → 이벤트별 경보 선행 시간, 놓침, 빈 구간 오경보.
  (timeline    박스 JSON → 경보 단계가 바뀐 시각 목록. CSV 를 적을 때 영상과 맞춰 보는 용도)

이벤트 CSV (영상 한 개에 take 번호 하나)
  take,who,event,t_sec
  1,person,start,10.0           보행자가 시작점에서 출발한 시각(초)
  1,person,cross_5.5m,13.5      발이 5.5m 선을 넘은 시각
  1,person,cross_3m,16.0
  1,person,cross_2m,18.2
  1,person,exit,26.0            화면 밖으로 나가 보이지 않게 된 시각
  1,bike,start,33.0             who 는 person 또는 bike (한 영상에 여러 번 지나가면 person2, bike2 처럼 번호를 붙인다)
  1,setup,in_frame,0.0-3.0      촬영 시작한 사람이 화면에 찍힌 구간(빈 구간 계산에서 뺀다)
cross_* 는 있는 것만 적어도 된다. start 와 exit 는 필수다.

선행 시간 = (발이 선을 넘은 시각) - (그 단계 경보가 처음 울린 시각). 양수면 선을 넘기 전에 울린 것, 음수면 늦은 것.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from alarm.levels import LEVEL_NAMES, Calibration, load_calibration
from runner.pipeline import Pipeline

DUMP_FLOOR_CONF = 0.15  # 저장할 박스의 가장 낮은 신뢰도. 설정을 이보다 낮출 수는 없다
CROSS_LEVELS = {"cross_5.5m": 1, "cross_3m": 2, "cross_2m": 3}
WHO_NAMES = {"person": "보행자", "bike": "자전거"}
WHO_RE = re.compile(
    r"^(person|bike|bicycle)(\d*)$"
)  # person2, bike2 처럼 번호를 붙여 한 영상에 여러 번 지나가는 것을 적는다


def norm_who(who: str) -> Optional[str]:
    """'bicycle2' -> 'bike2', 'person' -> 'person'. 모르는 이름이면 None."""
    m = WHO_RE.match(who)
    if not m:
        return None
    base = "bike" if m.group(1) == "bicycle" else m.group(1)
    return base + m.group(2)


def who_base(who: str) -> str:
    return who.rstrip("0123456789")


def who_label(who: str) -> str:
    num = who[len(who_base(who)) :]
    return WHO_NAMES[who_base(who)] + (f" {num}" if num else "")


PRE_MARGIN_S = 0.5  # 출발 전 이만큼은 빈 구간에서 뺀다(출발 동작이 화면에 걸칠 수 있다)
CLEAR_MARGIN_S = 2.0  # 나간 뒤 이만큼은 빈 구간에서 뺀다(경보가 꺼지는 데 걸리는 시간)

Timeline = List[Tuple[float, int]]  # (시각 초, 경보 단계 0~3)


# ---------------------------------------------------------------- 1) 감지 결과 저장
def dump_boxes(source: str, detector, progress_every: int = 300) -> dict:
    """영상 모든 프레임의 박스를 모은다. detector 는 detect(frame) -> [(x1,y1,x2,y2,conf,cls)...] 를 가진 것."""
    from runner.sources import VideoSource

    src = VideoSource(source)
    if not src.opened:
        raise RuntimeError(f"영상을 열 수 없다: {source}")
    boxes: List[list] = []
    height = 0
    while True:
        frame = src.read()
        if frame is None:
            break
        height = int(frame.shape[0])
        boxes.append(
            [
                [
                    round(b[0], 1),
                    round(b[1], 1),
                    round(b[2], 1),
                    round(b[3], 1),
                    round(b[4], 3),
                    int(round(b[5])),
                ]
                for b in detector.detect(frame)
            ]
        )
        if progress_every and len(boxes) % progress_every == 0:
            print(f"  {len(boxes)} 프레임...", flush=True)
    fps = float(src.fps)
    src.release()
    return {
        "source": str(source),
        "fps": fps,
        "frame_height": height,
        "frames": len(boxes),
        "floor_conf": getattr(detector, "min_conf", DUMP_FLOOR_CONF),
        "boxes": boxes,
    }


def save_dump(data: dict, path: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def load_dump(path: str) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for key in ("fps", "boxes"):
        if key not in data:
            raise ValueError(f"감지 결과 파일이 아니다({key} 없음): {path}")
    return data


# ---------------------------------------------------------------- 2) 경보 다시 계산
@dataclass
class Settings:
    min_conf: float = 0.25
    min_conf_bicycle: Optional[float] = None
    window: int = 3
    need: int = 2
    process_fps: Optional[float] = (
        None  # 이 장치가 처리하는 초당 프레임(Jetson 흉내). 비우면 영상 fps 그대로
    )

    def label(self) -> str:
        bike = "같음" if self.min_conf_bicycle is None else f"{self.min_conf_bicycle:g}"
        fps = "전부" if not self.process_fps else f"{self.process_fps:g}fps"
        return f"신뢰도 {self.min_conf:g}/자전거 {bike}, {self.need}/{self.window}프레임, 처리 {fps}"


def replay(data: dict, cal: Calibration, st: Settings) -> Timeline:
    """저장한 박스를 runner 와 같은 Pipeline 에 넣어, 프레임마다의 경보 단계를 돌려준다."""
    fps = float(data["fps"])
    step = 1
    if st.process_fps and st.process_fps < fps:
        step = max(1, int(round(fps / st.process_fps)))
    pipe = Pipeline(cal, st.min_conf, st.window, st.need)
    pipe.min_conf_bicycle = st.min_conf_bicycle
    out: Timeline = []
    boxes = data["boxes"]
    for i in range(0, len(boxes), step):
        out.append((i / fps, pipe.process(boxes[i]).alarm_level))
    return out


def level_changes(timeline: Timeline) -> List[Tuple[float, int, int]]:
    """경보 단계가 바뀐 지점 (시각, 전 단계, 새 단계)."""
    out = []
    prev = 0
    for t, lvl in timeline:
        if lvl != prev:
            out.append((t, prev, lvl))
            prev = lvl
    return out


# ---------------------------------------------------------------- 이벤트 CSV
@dataclass
class Actor:
    who: str
    start: Optional[float] = None
    exit: Optional[float] = None
    crosses: Dict[int, float] = field(default_factory=dict)  # 단계(1~3) -> 넘은 시각


@dataclass
class TakeEvents:
    actors: Dict[str, Actor] = field(default_factory=dict)
    setups: List[Tuple[float, float]] = field(default_factory=list)


def parse_events(path: str) -> Dict[int, TakeEvents]:
    takes: Dict[int, TakeEvents] = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        need = {"take", "who", "event", "t_sec"}
        if not reader.fieldnames or not need <= {h.strip() for h in reader.fieldnames}:
            raise ValueError(
                f"이벤트 CSV 의 첫 줄은 take,who,event,t_sec 여야 한다: {path}"
            )
        for n, row in enumerate(reader, start=2):
            row = {k.strip(): (v or "").strip() for k, v in row.items() if k}
            if not any(row.values()):
                continue
            try:
                take = int(row["take"])
            except ValueError:
                raise ValueError(f"{n}번째 줄: take 는 정수여야 한다({row['take']!r})")
            who, event, raw = row["who"], row["event"], row["t_sec"]
            ev = takes.setdefault(take, TakeEvents())
            try:
                if who == "setup":
                    if event != "in_frame" or "-" not in raw:
                        raise ValueError(
                            "setup 줄은 setup,in_frame,시작-끝 모양이어야 한다"
                        )
                    a, b = raw.split("-", 1)
                    ev.setups.append((float(a), float(b)))
                    continue
                nw = norm_who(who)
                if nw is None:
                    raise ValueError(
                        f"who 는 person, bike, setup (또는 person2, bike2 처럼 번호 붙인 것) 중 하나여야 한다({who!r})"
                    )
                who = nw
                t = float(raw)
                actor = ev.actors.setdefault(who, Actor(who))
                if event == "start":
                    actor.start = t
                elif event == "exit":
                    actor.exit = t
                elif event in CROSS_LEVELS:
                    actor.crosses[CROSS_LEVELS[event]] = t
                else:
                    raise ValueError(
                        f"event 는 start, exit, cross_5.5m, cross_3m, cross_2m 중 하나여야 한다({event!r})"
                    )
            except ValueError as e:
                raise ValueError(f"{n}번째 줄: {e}") from None
    for take, ev in takes.items():
        for actor in ev.actors.values():
            if actor.start is None or actor.exit is None:
                raise ValueError(
                    f"take {take} {actor.who}: start 와 exit 가 둘 다 있어야 한다"
                )
            if actor.exit <= actor.start:
                raise ValueError(
                    f"take {take} {actor.who}: exit 가 start 보다 뒤여야 한다"
                )
    return takes


# ---------------------------------------------------------------- 평가
@dataclass
class CrossResult:
    who: str
    level: int
    t_cross: float
    t_alarm: Optional[float]  # None = 놓침

    @property
    def lead(self) -> Optional[float]:
        return None if self.t_alarm is None else self.t_cross - self.t_alarm


@dataclass
class ActorResult:
    who: str
    crosses: List[CrossResult]
    drops: int  # 접근 중 경보 단계가 내려간 횟수(깜빡임)
    clear_delay: Optional[float]  # 나간 뒤 경보가 꺼지기까지(초). None = 안 꺼짐
    cleared: bool = True


@dataclass
class TakeResult:
    take: int
    duration: float
    actors: List[ActorResult]
    empty_s: float
    false_s: float
    false_runs: int


def _first_at_or_above(tl: Timeline, level: int, a: float, b: float) -> Optional[float]:
    for t, lvl in tl:
        if t < a:
            continue
        if t > b:
            break
        if lvl >= level:
            return t
    return None


def _merge(intervals: Sequence[Tuple[float, float]]) -> List[Tuple[float, float]]:
    out: List[Tuple[float, float]] = []
    for a, b in sorted(intervals):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def evaluate_take(
    take: int, tl: Timeline, ev: TakeEvents, duration: float
) -> TakeResult:
    starts = sorted(a.start for a in ev.actors.values())
    actors: List[ActorResult] = []
    busy: List[Tuple[float, float]] = list(ev.setups)
    for actor in ev.actors.values():
        busy.append((max(0.0, actor.start - PRE_MARGIN_S), actor.exit + CLEAR_MARGIN_S))
        crosses = [
            CrossResult(
                actor.who, lvl, t, _first_at_or_above(tl, lvl, actor.start, actor.exit)
            )
            for lvl, t in sorted(actor.crosses.items())
        ]
        drops = 0
        prev = 0
        for t, lvl in tl:
            if t < actor.start:
                continue
            if t > actor.exit:
                break
            if lvl < prev:
                drops += 1
            prev = lvl
        later = [s for s in starts if s > actor.exit]
        bound = min(later) if later else duration
        clear = None
        for t, lvl in tl:
            if t < actor.exit:
                continue
            if t >= bound:
                break
            if lvl == 0:
                clear = t - actor.exit
                break
        actors.append(ActorResult(actor.who, crosses, drops, clear, clear is not None))
    empty = _merge([(a, b) for a, b in busy if b > a])
    # 빈 구간 = 전체에서 바쁜 구간을 뺀 것
    free: List[Tuple[float, float]] = []
    cur = 0.0
    for a, b in empty:
        if a > cur:
            free.append((cur, min(a, duration)))
        cur = max(cur, b)
    if cur < duration:
        free.append((cur, duration))
    empty_s = sum(b - a for a, b in free if b > a)
    false_s = 0.0
    runs = 0
    in_run = False
    for i, (t, lvl) in enumerate(tl):
        t_next = tl[i + 1][0] if i + 1 < len(tl) else duration
        overlap = sum(max(0.0, min(t_next, b) - max(t, a)) for a, b in free)
        if lvl > 0 and overlap > 0:
            false_s += overlap
            if not in_run:
                runs += 1
            in_run = True
        else:
            in_run = False
    return TakeResult(take, duration, actors, empty_s, false_s, runs)


# ---------------------------------------------------------------- 보고
def _lead_text(c: CrossResult) -> str:
    if c.t_alarm is None:
        return "놓침(경보가 안 울림)"
    lead = c.lead
    when = f"(울린 {c.t_alarm:.1f}초, 선 넘음 {c.t_cross:.1f}초)"
    if abs(lead) < 0.05:
        return f"정확히 맞음 {when}"
    return f"{lead:.1f}초 빨리 {when}" if lead > 0 else f"{-lead:.1f}초 늦게 {when}"


def format_take(r: TakeResult, name: str = "") -> List[str]:
    lines = [f"[{r.take}번째 영상] {name} ({r.duration:.1f}초)"]
    for a in r.actors:
        lines.append(f"  {who_label(a.who)}")
        for c in a.crosses:
            lines.append(f"    {LEVEL_NAMES[c.level]}({c.level}단계): {_lead_text(c)}")
        lines.append(f"    접근 중 단계가 내려간 횟수: {a.drops}번")
        lines.append(
            "    나간 뒤 경보 꺼짐: "
            + (
                f"{a.clear_delay:.1f}초 뒤"
                if a.clear_delay is not None
                else "다음 사건까지 안 꺼짐"
            )
        )
    lines.append(
        f"  빈 구간 오경보: {r.false_s:.1f}초 / 빈 구간 {r.empty_s:.1f}초 ({r.false_runs}번 울림)"
    )
    return lines


def summarize(results: Sequence[TakeResult]) -> List[str]:
    crosses = [c for r in results for a in r.actors for c in a.crosses]
    lines = ["[전체 요약]"]
    for lvl in (1, 2, 3):
        cs = [c for c in crosses if c.level == lvl]
        if not cs:
            continue
        got = [c for c in cs if c.t_alarm is not None]
        leads = [c.lead for c in got]
        txt = f"  {LEVEL_NAMES[lvl]}({lvl}단계): {len(got)}/{len(cs)} 울림"
        if leads:
            txt += f", 선행 시간 중앙값 {statistics.median(leads):.1f}초 (가장 늦은 {min(leads):.1f}초, 가장 빠른 {max(leads):.1f}초)"
            txt += f", 선을 넘은 뒤에 울린 것 {sum(1 for x in leads if x < 0)}개"
        lines.append(txt)
    if crosses:
        got_all = sum(1 for c in crosses if c.t_alarm is not None)
        lines.append(
            f"  이벤트 전체: {got_all}/{len(crosses)} 울림, 놓침 {len(crosses) - got_all}개"
        )
    for who in WHO_NAMES:
        cs = [c for c in crosses if who_base(c.who) == who]
        if cs:
            got = sum(1 for c in cs if c.t_alarm is not None)
            lines.append(f"  {WHO_NAMES[who]}: {got}/{len(cs)} 울림")
    empty = sum(r.empty_s for r in results)
    false = sum(r.false_s for r in results)
    runs = sum(r.false_runs for r in results)
    lines.append(
        f"  빈 구간 오경보: {false:.1f}초 / 빈 구간 {empty:.1f}초 ({runs}번 울림)"
    )
    stuck = sum(1 for r in results for a in r.actors if not a.cleared)
    if stuck:
        lines.append(f"  경보가 안 꺼진 경우: {stuck}번")
    return lines


def summary_row(results: Sequence[TakeResult]) -> Tuple[int, int, str, float, int]:
    crosses = [c for r in results for a in r.actors for c in a.crosses]
    got = [c for c in crosses if c.t_alarm is not None]
    med = f"{statistics.median([c.lead for c in got]):.1f}" if got else "-"
    return (
        len(got),
        len(crosses),
        med,
        sum(r.false_s for r in results),
        sum(r.false_runs for r in results),
    )


SWEEP_GRID = [
    Settings(0.25, None, 3, 2),
    Settings(0.35, None, 3, 2),
    Settings(0.50, None, 3, 2),
    Settings(0.25, 0.40, 3, 2),
    Settings(0.25, 0.20, 3, 2),
    Settings(0.25, None, 2, 1),
    Settings(0.25, None, 4, 3),
    Settings(0.35, 0.25, 3, 2),
]


def run_eval(
    dumps: Sequence[Tuple[int, str, dict]],
    events: Dict[int, TakeEvents],
    cal: Calibration,
    st: Settings,
) -> List[TakeResult]:
    results = []
    for take, _name, data in dumps:
        if take not in events:
            raise ValueError(f"이벤트 CSV 에 take {take} 가 없다")
        tl = replay(data, cal, st)
        duration = len(data["boxes"]) / float(data["fps"])
        results.append(evaluate_take(take, tl, events[take], duration))
    return results


# ---------------------------------------------------------------- 명령줄
def _parse_boxes_args(items: Sequence[str]) -> List[Tuple[int, str, dict]]:
    """'파일' 또는 '번호=파일'. 번호를 안 주면 준 순서대로 1, 2, 3..."""
    out = []
    for i, item in enumerate(items, start=1):
        take = i
        path = item
        if "=" in item and item.split("=", 1)[0].isdigit():
            take, path = int(item.split("=", 1)[0]), item.split("=", 1)[1]
        data = load_dump(path)
        out.append((take, Path(data.get("source", path)).name, data))
    return out


def _settings_from(args) -> Settings:
    return Settings(
        args.min_conf, args.min_conf_bicycle, args.window, args.need, args.process_fps
    )


def _add_setting_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--calibration", default="data/runner/calibration.json", help="거리 기준 파일"
    )
    p.add_argument(
        "--min-conf",
        type=float,
        default=0.25,
        dest="min_conf",
        help="경보에 쓸 신뢰도 기준",
    )
    p.add_argument(
        "--min-conf-bicycle",
        type=float,
        default=None,
        dest="min_conf_bicycle",
        help="자전거만 따로 정한 기준",
    )
    p.add_argument("--window", type=int, default=3, help="연속 프레임 창 크기")
    p.add_argument("--need", type=int, default=2, help="창 안에서 이만큼 나와야 경보")
    p.add_argument(
        "--process-fps",
        type=float,
        default=None,
        dest="process_fps",
        help="장치가 처리하는 초당 프레임(Jetson 흉내, 예 12)",
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m runner.events", description=__doc__.split("\n")[0]
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("dump", help="영상 → 프레임별 박스 JSON")
    d.add_argument("--source", required=True, help="영상 파일")
    d.add_argument("--model", required=True, help="YOLO 가중치(.pt)나 .engine")
    d.add_argument("--imgsz", type=int, default=None)
    d.add_argument("--device", default=None)
    d.add_argument(
        "--out",
        default=None,
        help="저장 파일(기본 data/events/<영상>.<모델>.boxes.json)",
    )

    t = sub.add_parser("timeline", help="경보 단계가 바뀐 시각 목록")
    t.add_argument("boxes")
    _add_setting_args(t)

    e = sub.add_parser("eval", help="이벤트 CSV 와 견줘 수치를 낸다")
    e.add_argument(
        "--boxes",
        nargs="+",
        required=True,
        help="박스 JSON. '번호=파일'로 take 번호를 지정, 없으면 순서대로 1,2,3",
    )
    e.add_argument("--events", required=True, help="이벤트 CSV")
    e.add_argument("--sweep", action="store_true", help="여러 설정을 한 표로 비교")
    e.add_argument("--report", default=None, help="결과를 저장할 텍스트 파일")
    _add_setting_args(e)

    args = ap.parse_args(argv)

    if args.cmd == "dump":
        from runner.detector import Detector

        detector = Detector(args.model, DUMP_FLOOR_CONF, args.device, args.imgsz)
        print(f"감지 장치: {detector.describe()}")
        data = dump_boxes(args.source, detector)
        out = args.out or str(
            Path("data/events")
            / f"{Path(args.source).stem}.{Path(args.model).stem}.boxes.json"
        )
        data["model"] = str(args.model)
        save_dump(data, out)
        print(f"{data['frames']} 프레임, {data['fps']:.1f}fps → {out}")
        return 0

    cal = load_calibration(args.calibration)
    st = _settings_from(args)

    if args.cmd == "timeline":
        data = load_dump(args.boxes)
        if data.get("frame_height") and data["frame_height"] != cal.frame_height:
            print(
                f"[주의] 영상 높이 {data['frame_height']} 와 보정 파일 {cal.frame_height} 가 다르다"
            )
        print(f"설정: {st.label()}")
        for tt, a, b in level_changes(replay(data, cal, st)):
            print(f"  {tt:6.2f}초  {a}단계 → {b}단계")
        return 0

    dumps = _parse_boxes_args(args.boxes)
    events = parse_events(args.events)
    for take, name, data in dumps:
        if data.get("frame_height") and data["frame_height"] != cal.frame_height:
            print(
                f"[주의] take {take}: 영상 높이 {data['frame_height']} 와 보정 파일 {cal.frame_height} 가 다르다"
            )
    lines: List[str] = []
    if args.sweep:
        lines.append(
            f"{'설정':<44}{'울림':>9}{'선행중앙(초)':>14}{'오경보(초)':>12}{'울린 횟수':>10}"
        )
        for s in SWEEP_GRID:
            s.process_fps = st.process_fps
            got, total, med, fs, runs = summary_row(run_eval(dumps, events, cal, s))
            lines.append(
                f"{s.label():<44}{f'{got}/{total}':>9}{med:>14}{fs:>12.1f}{runs:>10}"
            )
    else:
        lines.append(f"설정: {st.label()}")
        results = run_eval(dumps, events, cal, st)
        for r, (_t, name, _d) in zip(results, dumps):
            lines.extend(format_take(r, name))
            lines.append("")
        lines.extend(summarize(results))
    text = "\n".join(lines)
    print(text)
    if args.report:
        Path(args.report).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
