import { useEffect, useMemo, useState } from "react";
import type { Detection, Filter, RunnerStatus } from "./types.ts";
import { fetchDetections, fetchStatus, flagDetection } from "./api.ts";
import StatusBar from "./components/StatusBar.tsx";
import StatTiles from "./components/StatTiles.tsx";
import CapturePanel from "./components/CapturePanel.tsx";
import RecordTable from "./components/RecordTable.tsx";
import Notes from "./components/Notes.tsx";
import LiveView from "./components/LiveView.tsx";
import RiskBars from "./components/RiskBars.tsx";

const STATUS_POLL_MS = 250; // runner 가 상태를 쓰는 간격과 같다
const RECORDS_POLL_MS = 1000;

export default function App() {
  const [rows, setRows] = useState<Detection[]>([]);
  const [live, setLive] = useState(false);
  const [status, setStatus] = useState<RunnerStatus | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [flagged, setFlagged] = useState<Set<string>>(() => new Set());
  // 주소 뒤에 ?view=demo 를 붙이면 녹화용으로 실시간 화면·막대·최신 캡처만 크게 보여 준다.
  const demo = new URLSearchParams(window.location.search).get("view") === "demo";

  useEffect(() => {
    let alive = true;
    fetchDetections().then(({ rows, live }) => {
      if (!alive) return;
      setRows(rows);
      // 서버에 저장된 오경보 표시를 불러와, 새로고침해도 표시가 남게 한다.
      setFlagged(new Set(rows.filter((r) => r.false_alarm).map((r) => r.id)));
      setLive(live);
      setSelectedId((cur) => cur ?? rows[0]?.id ?? null);
    });
    return () => { alive = false; };
  }, []);

  // runner 상태(막대·실시간 화면)는 0.25초마다, 기록(최신 캡처)은 1초마다 새로 읽는다.
  useEffect(() => {
    let alive = true;
    const pollStatus = () => fetchStatus().then((s) => { if (alive) setStatus(s); });
    const pollRecords = () =>
      fetchDetections().then(({ rows, live }) => {
        if (!alive) return;
        setRows(rows);
        setLive(live);
      });
    pollStatus();
    const a = window.setInterval(pollStatus, STATUS_POLL_MS);
    const b = window.setInterval(pollRecords, RECORDS_POLL_MS);
    return () => { alive = false; window.clearInterval(a); window.clearInterval(b); };
  }, []);

  // 서버가 상태를 주면 runner 가 실제로 돌고 있는지로, 못 받으면 기록이 있는지로 "연결됨"을 정한다.
  const connected = status ? status.online : live;

  const selected = useMemo(
    () => (demo ? rows[0] : rows.find((r) => r.id === selectedId) ?? rows[0]) ?? null,
    [rows, selectedId, demo]
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
    <div className={demo ? "wrap demo" : "wrap"}>
      <StatusBar live={connected} lastAt={rows[0]?.at} />
      <div className="livegrid">
        <LiveView status={status} />
        <RiskBars status={status} />
      </div>
      {demo ? (
        <CapturePanel rec={selected} />
      ) : (
        <>
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
        </>
      )}
    </div>
  );
}
