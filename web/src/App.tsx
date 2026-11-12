import { useEffect, useMemo, useState } from "react";
import type { Detection, Filter } from "./types.ts";
import { fetchDetections, flagDetection } from "./api.ts";
import StatusBar from "./components/StatusBar.tsx";
import StatTiles from "./components/StatTiles.tsx";
import CapturePanel from "./components/CapturePanel.tsx";
import RecordTable from "./components/RecordTable.tsx";
import Notes from "./components/Notes.tsx";

export default function App() {
  const [rows, setRows] = useState<Detection[]>([]);
  const [live, setLive] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [flagged, setFlagged] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    let alive = true;
    fetchDetections().then(({ rows, live }) => {
      if (!alive) return;
      setRows(rows);
      setLive(live);
      setSelectedId((cur) => cur ?? rows[0]?.id ?? null);
    });
    return () => { alive = false; };
  }, []);

  const selected = useMemo(
    () => rows.find((r) => r.id === selectedId) ?? rows[0] ?? null,
    [rows, selectedId]
  );

  function toggleFlag(id: string) {
    setFlagged((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      // 서버가 있으면 같이 남긴다. 없으면 화면 안에서만 바뀐다.
      flagDetection(id, next.has(id));
      return next;
    });
  }

  function toggleTheme() {
    const root = document.documentElement;
    const isDark =
      root.getAttribute("data-theme") === "dark" ||
      (!root.hasAttribute("data-theme") &&
        window.matchMedia("(prefers-color-scheme: dark)").matches);
    root.setAttribute("data-theme", isDark ? "light" : "dark");
  }

  return (
    <div className="wrap">
      <StatusBar live={live} lastAt={rows[0]?.at} />
      <StatTiles rows={rows} flagged={flagged} />
      <div className="cols">
        <CapturePanel rec={selected} />
        <RecordTable
          rows={rows}
          filter={filter}
          onFilter={setFilter}
          selectedId={selected?.id ?? null}
          onSelect={setSelectedId}
          flagged={flagged}
          onFlag={toggleFlag}
        />
      </div>
      <Notes live={live} onToggleTheme={toggleTheme} />
    </div>
  );
}
