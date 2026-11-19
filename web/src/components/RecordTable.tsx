import { useState } from "react";
import { BEEP, kindOf } from "../kinds.ts";
import Filters from "./Filters.tsx";
import type { Detection, Filter } from "../types.ts";

const PAGE_SIZE = 10;

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
}

export default function RecordTable({
  rows, filter, onFilter, selectedId, onSelect, flagged, onFlag,
}: Props) {
  const shown = rows.filter((r) => {
    if (filter === "all") return true;
    if (filter === "low") return r.top > 0 && r.top < 0.7;
    if (filter === "person") return r.person > 0;
    return r.bicycle > 0;
  });

  // 한 쪽에 10건씩. 새 기록이 계속 들어와 건수가 바뀌어도 쪽 번호가 범위를 벗어나지 않게 맞춘다.
  const [page, setPage] = useState(1);
  const pages = Math.max(1, Math.ceil(shown.length / PAGE_SIZE));
  const cur = Math.min(page, pages);
  const pageRows = shown.slice((cur - 1) * PAGE_SIZE, cur * PAGE_SIZE);

  return (
    <section className="panel">
      <header>
        <h2>감지 기록</h2>
        <Filters value={filter} onChange={(f) => { onFilter(f); setPage(1); }} />
      </header>
      <div className="hint">
        <p>
          경보가 잘못 울렸다면(사람·자전거가 <b>없는데</b> 울림) <b>오경보로 표시</b>하세요. 서버 DB(SQLite)에 저장되어
          오경보율 계산에 쓰이고, 자동 삭제되지 않습니다. 사람이 실제로 있는 기록은 표시하지 마세요.
        </p>
        <p>
          {flagged.size > 0 ? (
            <a className="export" href="/api/export/false-alarms" download>
              오경보 {flagged.size}건 내보내기 (zip)
            </a>
          ) : (
            <span className="export off">오경보 내보내기 (zip) — 표시한 기록이 없습니다</span>
          )}{" "}
          <span className="hint-sub">
            zip = 박스 없는 원본 사진 + 빈 라벨(사람·자전거 없음) + 목록. 재학습 때 “이건 사람이 아니다”를 가르치는 배경 자료로 추가합니다.
          </span>
        </p>
      </div>
      <div className="tablewrap">
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
                      {r.level ? `${BEEP[r.level as 1 | 2 | 3]} ${r.level}` : "—"}
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
                      {isFlagged ? "오경보" : "오경보로 표시"}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <nav className="pager" aria-label="기록 페이지">
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
        <span className="pg-total">총 {shown.length}건 · {cur}/{pages}쪽</span>
      </nav>
    </section>
  );
}
