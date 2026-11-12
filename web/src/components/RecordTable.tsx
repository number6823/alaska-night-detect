import { BEEP, kindOf } from "../kinds.ts";
import Filters from "./Filters.tsx";
import type { Detection, Filter } from "../types.ts";

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

  return (
    <section className="panel">
      <header>
        <h2>감지 기록</h2>
        <Filters value={filter} onChange={onFilter} />
      </header>
      <div className="tablewrap">
        <table>
          <thead>
            <tr>
              <th>시각</th><th>종류</th><th>경고</th><th>최고 신뢰도</th><th>박스</th><th>오경보</th>
            </tr>
          </thead>
          <tbody>
            {shown.length === 0 && (
              <tr><td className="empty-row" colSpan={6}>해당하는 기록이 없습니다</td></tr>
            )}
            {shown.map((r) => {
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
                      onClick={(e) => { e.stopPropagation(); onFlag(r.id); }}
                    >
                      {isFlagged ? "오경보" : "표시"}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
