import type { Detection } from "../types.ts";

interface Props {
  rows: Detection[];
  flagged: Set<string>;
}

interface Tile {
  k: string;
  v: number | string;
  color?: string;
  sub?: string;
}

export default function StatTiles({ rows, flagged }: Props) {
  const live = rows.filter((r) => !flagged.has(r.id));
  // 오경보율 = 오경보로 표시한 기록 ÷ 경보가 울린 기록(경고 단계 1 이상)
  const alarms = rows.filter((r) => r.level > 0);
  const marked = alarms.filter((r) => flagged.has(r.id)).length;
  const rate = alarms.length ? `${Math.round((100 * marked) / alarms.length)}%` : "—";
  const tiles: Tile[] = [
    { k: "감지된 장면", v: live.filter((r) => r.person + r.bicycle > 0).length },
    { k: "사람 박스", v: live.reduce((a, r) => a + r.person, 0), color: "var(--person)" },
    { k: "자전거 박스", v: live.reduce((a, r) => a + r.bicycle, 0), color: "var(--bicycle)" },
    { k: "오경보율", v: rate, color: "var(--danger)", sub: `표시 ${marked}건 / 경보 ${alarms.length}건` },
  ];
  return (
    <div className="stats">
      {tiles.map((t) => (
        <div className="stat" key={t.k}>
          <div className="k">{t.k}</div>
          <div className="v" style={t.color ? { color: t.color } : undefined}>{t.v}</div>
          {t.sub && <div className="sub-note">{t.sub}</div>}
        </div>
      ))}
    </div>
  );
}
