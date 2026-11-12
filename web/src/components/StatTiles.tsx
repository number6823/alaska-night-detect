import type { Detection } from "../types.ts";

interface Props {
  rows: Detection[];
  flagged: Set<string>;
}

interface Tile {
  k: string;
  v: number;
  color?: string;
}

export default function StatTiles({ rows, flagged }: Props) {
  const live = rows.filter((r) => !flagged.has(r.id));
  const tiles: Tile[] = [
    { k: "감지된 장면", v: live.filter((r) => r.person + r.bicycle > 0).length },
    { k: "사람 박스", v: live.reduce((a, r) => a + r.person, 0), color: "var(--person)" },
    { k: "자전거 박스", v: live.reduce((a, r) => a + r.bicycle, 0), color: "var(--bicycle)" },
    { k: "오경보 표시", v: flagged.size, color: "var(--danger)" },
  ];
  return (
    <div className="stats">
      {tiles.map((t) => (
        <div className="stat" key={t.k}>
          <div className="k">{t.k}</div>
          <div className="v" style={t.color ? { color: t.color } : undefined}>{t.v}</div>
        </div>
      ))}
    </div>
  );
}
