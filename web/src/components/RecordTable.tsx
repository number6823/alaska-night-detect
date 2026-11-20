import { useLayoutEffect, useRef, useState } from "react";
import { BEEP, LEVEL_NAME, kindOf } from "../kinds.ts";
import Filters from "./Filters.tsx";
import JudgeTable, { JUDGE_TIP } from "./JudgeTable.tsx";
import type { Detection, Filter } from "../types.ts";

// 한 쪽에 몇 건을 보여 줄지는 표가 들어갈 칸의 높이로 정한다(화면을 스크롤하지 않고 한눈에 보이게).
const MIN_ROWS = 3;
const MAX_ROWS = 12;
const FALLBACK_ROW_PX = 40;
const FALLBACK_HEAD_PX = 36;

// 페이지 번호 줄: 처음과 끝, 현재 쪽 주변 두 쪽씩만 보이고 나머지는 "…"로 줄인다. 예) 1 … 4 5 6 7 8 … 20
function pageList(cur: number, pages: number): (number | "…")[] {
  const keep = new Set<number>([1, pages]);
  for (let p = cur - 2; p <= cur + 2; p++) if (p >= 1 && p <= pages) keep.add(p);
  const sorted = [...keep].sort((a, b) => a - b);
  const out: (number | "…")[] = [];
  sorted.forEach((p, i) => {
    if (i > 0 && p - sorted[i - 1] > 1) out.push("…");
    out.push(p);
  });
  return out;
}

interface Props {
  rows: Detection[];
  filter: Filter;
  onFilter: (f: Filter) => void;
  selectedId: string | null;
  onSelect: (id: string) => void;
  flagged: Set<string>;
  onFlag: (id: string) => void;
  /** 서버에 연결돼 있는데 오경보 표시를 저장하지 못했을 때 */
  saveError?: boolean;
  /** 서버가 없어 예시 기록을 보여 주는 중 */
  example?: boolean;
}

export default function RecordTable({
  rows, filter, onFilter, selectedId, onSelect, flagged, onFlag, saveError, example,
}: Props) {
  const shown = rows.filter((r) => {
    if (filter === "all") return true;
    if (filter === "low") return r.top > 0 && r.top < 0.7;
    if (filter === "person") return r.person > 0;
    return r.bicycle > 0;
  });

  // 표 칸의 높이에 맞춰 한 쪽 건수를 정한다. 칸이 커지거나 줄면 다시 계산한다.
  const wrapRef = useRef<HTMLDivElement>(null);
  const [pageSize, setPageSize] = useState(6);
  const hasRows = shown.length > 0; // 첫 기록이 들어와 실제 줄 높이를 잴 수 있게 되면 다시 계산한다
  useLayoutEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const calc = () => {
      // 좁거나 낮은 화면에서는 표가 칸에 갇히지 않고(페이지가 스크롤됨) 내용만큼 늘어나므로 고정 건수를 쓴다.
      if (getComputedStyle(el).flexGrow === "0") { setPageSize(6); return; }
      const head = el.querySelector("thead")?.getBoundingClientRect().height || FALLBACK_HEAD_PX;
      const row = el.querySelector("tbody tr.row")?.getBoundingClientRect().height || FALLBACK_ROW_PX;
      const n = Math.floor((el.clientHeight - head - 2) / row);
      setPageSize(Math.max(MIN_ROWS, Math.min(MAX_ROWS, n)));
    };
    calc();
    const ro = new ResizeObserver(calc);
    ro.observe(el);
    return () => ro.disconnect();
  }, [hasRows]);

  // 새 기록이 계속 들어와 건수가 바뀌어도 쪽 번호가 범위를 벗어나지 않게 맞춘다.
  const [page, setPage] = useState(1);
  const pages = Math.max(1, Math.ceil(shown.length / pageSize));
  const cur = Math.min(page, pages);
  const pageRows = shown.slice((cur - 1) * pageSize, cur * pageSize);

  return (
    <section className="panel">
      <header>
        <h2>감지 기록</h2>
        <Filters value={filter} onChange={(f) => { onFilter(f); setPage(1); }} />
      </header>
      <div className="hint">
        {example && (
          <p className="hint-warn">
            <b>예시 기록입니다.</b> Jetson에 연결되지 않아 Wikimedia Commons 야간 사진에 모델을 돌린 결과를 보여 줍니다(시각·거리·경고 단계는 만든 값).
          </p>
        )}
        {saveError && (
          <p className="hint-warn"><b>서버에 저장하지 못했습니다.</b> 표시가 이 화면에만 남습니다. 서버 상태를 확인하세요.</p>
        )}
        <p className="hint-row">
          <span>경보가 잘못 울렸다면 <b>오경보로 표시</b>하세요.</span>
          {flagged.size > 0 ? (
            <a className="export" href="/api/export/false-alarms" download>
              오경보 {flagged.size}건 내보내기 (zip)
            </a>
          ) : (
            <span className="export off">내보내기 (zip) · 표시한 기록 없음</span>
          )}
        </p>
      </div>
      <details className="guide">
        <summary>무엇을 오경보로 표시하나요?</summary>
        <JudgeTable />
        <p className="guide-note">{JUDGE_TIP}</p>
      </details>
      <div className="tablewrap" ref={wrapRef}>
        <table>
          <thead>
            <tr>
              <th>시각</th><th>종류</th><th>경고</th><th>최고 신뢰도</th><th>박스</th><th>오경보 표시</th>
            </tr>
          </thead>
          <tbody>
            {shown.length === 0 && (
              <tr><td className="empty-row" colSpan={6}>해당하는 기록이 없습니다</td></tr>
            )}
            {pageRows.map((r) => {
              const k = kindOf(r);
              const isFlagged = flagged.has(r.id);
              const low = r.top > 0 && r.top < 0.7;
              return (
                <tr
                  key={r.id}
                  className={isFlagged ? "row flagged" : "row"}
                  tabIndex={0}
                  aria-selected={r.id === selectedId}
                  onClick={() => onSelect(r.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(r.id); }
                  }}
                >
                  <td className="t">{r.at}</td>
                  <td>
                    <span className="kind">
                      <span className="swatch" style={{ background: k.color }} />
                      {k.label}
                    </span>
                  </td>
                  <td>
                    <span className="lv" data-level={r.level}>
                      {r.level ? `${BEEP[r.level as 1 | 2 | 3]} ${LEVEL_NAME[r.level].replace("약 ", "")}` : "—"}
                    </span>
                  </td>
                  <td className={low ? "conf low" : "conf"}>{r.top ? r.top.toFixed(2) : "—"}</td>
                  <td className="boxes">{r.person + r.bicycle}</td>
                  <td className="c-flag">
                    <button
                      type="button"
                      className="flag"
                      aria-pressed={isFlagged}
                      title={isFlagged ? "오경보 표시를 취소합니다" : "이 경보가 잘못 울렸다고 서버에 남깁니다"}
                      onClick={(e) => { e.stopPropagation(); onFlag(r.id); }}
                    >
                      {isFlagged ? "표시 취소" : "오경보로 표시"}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <nav className="pager" aria-label="기록 페이지">
        <span aria-hidden="true" />
        <div className="pg-nums">
          <button type="button" className="pg" disabled={cur <= 1} onClick={() => setPage(cur - 1)}>‹ 이전</button>
          {pageList(cur, pages).map((p, i) =>
            p === "…" ? (
              <span className="pg-gap" key={`gap${i}`}>…</span>
            ) : (
              <button
                type="button"
                className="pg"
                key={p}
                aria-current={p === cur ? "page" : undefined}
                onClick={() => setPage(p)}
              >
                {p}
              </button>
            )
          )}
          <button type="button" className="pg" disabled={cur >= pages} onClick={() => setPage(cur + 1)}>다음 ›</button>
        </div>
        <span className="pg-total">총 {shown.length}건 · {cur}/{pages}쪽</span>
      </nav>
    </section>
  );
}
