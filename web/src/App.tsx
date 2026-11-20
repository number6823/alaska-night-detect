import { useEffect, useMemo, useState } from "react";
import type { Detection, Filter, RunnerStatus } from "./types.ts";
import { fetchDetections, fetchHealth, fetchStatus, flagDetection } from "./api.ts";
import type { StoreInfo } from "./api.ts";
import StatusBar from "./components/StatusBar.tsx";
import StatTiles from "./components/StatTiles.tsx";
import CapturePanel from "./components/CapturePanel.tsx";
import RecordTable from "./components/RecordTable.tsx";
import LiveView from "./components/LiveView.tsx";
import RiskBars from "./components/RiskBars.tsx";
import DriveView from "./components/DriveView.tsx";
import ManualDrawer from "./components/ManualDrawer.tsx";

const STATUS_POLL_MS = 250; // runner 가 상태를 쓰는 간격과 같다
const RECORDS_POLL_MS = 1000;
const THEME_KEY = "alaska-theme";

function applyTheme(theme: "light" | "dark" | null) {
  const root = document.documentElement;
  if (theme) root.setAttribute("data-theme", theme);
  else root.removeAttribute("data-theme");
}

function isDarkNow(): boolean {
  const root = document.documentElement;
  const set = root.getAttribute("data-theme");
  if (set) return set === "dark";
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

export default function App() {
  const [rows, setRows] = useState<Detection[]>([]);
  const [live, setLive] = useState(false);
  // undefined = 첫 응답을 기다리는 중, null = 상태를 못 받음
  const [status, setStatus] = useState<RunnerStatus | null | undefined>(undefined);
  const [store, setStore] = useState<StoreInfo | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [flagged, setFlagged] = useState<Set<string>>(() => new Set());
  const [flagError, setFlagError] = useState(false);
  // 주소로 화면을 나눈다. / 는 운전자 화면, /admin 은 관리자 화면이다.
  // (정적 서버처럼 /admin 을 못 여는 곳에서는 ?view=admin, 옛 주소 ?view=drive·?view=demo 도 된다)
  const view = new URLSearchParams(window.location.search).get("view");
  const adminPath = /\/admin\/?$/.test(window.location.pathname);
  const drive = view === "drive" || view === "demo" ? true : view === "admin" ? false : !adminPath;

  // 관리자 매뉴얼은 다른 페이지로 가지 않고 관리자 화면 오른쪽에 겹쳐 열린다.
  const [manualOpen, setManualOpen] = useState(false);

  useEffect(() => {
    document.title = drive ? "후방 감지" : "후방 감지 · 관리자";
  }, [drive]);

  // 테마: 운전자 화면은 야간 운전을 가정해 어둡게 고정하고, 관리자 화면은 마지막에 고른 것을 기억한다.
  useEffect(() => {
    if (drive) { applyTheme("dark"); return; }
    let saved: string | null = null;
    try { saved = window.localStorage.getItem(THEME_KEY); } catch { /* 저장소를 못 쓰면 기본값 */ }
    applyTheme(saved === "light" || saved === "dark" ? saved : null);
  }, [drive]);

  useEffect(() => {
    if (drive) return;
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
  }, [drive]);

  // runner 상태(막대·실시간 화면)는 0.25초마다, 기록(최신 캡처)은 1초마다 새로 읽는다.
  useEffect(() => {
    let alive = true;
    const pollStatus = () => fetchStatus().then((s) => { if (alive) setStatus(s); });
    const pollRecords = () =>
      fetchDetections().then(({ rows, live }) => {
        if (!alive) return;
        setRows(rows);
        setLive(live);
        fetchHealth().then((h) => { if (alive) setStore(h); });
      });
    pollStatus();
    const a = window.setInterval(pollStatus, STATUS_POLL_MS);
    const b = drive ? undefined : window.setInterval(pollRecords, RECORDS_POLL_MS);
    return () => {
      alive = false;
      window.clearInterval(a);
      if (b !== undefined) window.clearInterval(b);
    };
  }, [drive]);

  // 서버가 상태를 주면 runner 가 실제로 돌고 있는지로, 못 받으면 기록이 있는지로 "연결됨"을 정한다.
  const connected = status ? status.online : live;

  const selected = useMemo(
    () => rows.find((r) => r.id === selectedId) ?? rows[0] ?? null,
    [rows, selectedId]
  );

  function toggleFlag(id: string) {
    const on = !flagged.has(id);
    setFlagged((prev) => {
      const next = new Set(prev);
      if (on) next.add(id); else next.delete(id);
      return next;
    });
    // 서버가 있으면 같이 남긴다. 서버에 연결돼 있는데 저장이 안 되면 알려 준다.
    flagDetection(id, on).then((ok) => setFlagError(live && !ok));
  }

  function toggleTheme() {
    const next = isDarkNow() ? "light" : "dark";
    applyTheme(next);
    try { window.localStorage.setItem(THEME_KEY, next); } catch { /* 저장 못 해도 이번 화면에는 적용됨 */ }
  }

  if (drive) return <DriveView status={status} />;

  return (
    // 관리자 화면은 스크롤 없이 한 화면에 들어오게: 위 줄(작은 실시간 화면·막대·통계)과,
    // 검수하는 아래 줄(감지 캡처와 감지 기록을 같은 크기·같은 높이로 나란히)
    <div className="wrap admin">
      <StatusBar
        live={connected}
        lastAt={rows[0]?.at}
        store={store}
        onToggleTheme={toggleTheme}
        manualOpen={manualOpen}
        onToggleManual={() => setManualOpen((v) => !v)}
      />
      <div className="admin-top">
        <LiveView status={status} />
        <RiskBars status={status} />
        <StatTiles rows={rows} flagged={flagged} />
      </div>
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
          saveError={flagError}
          example={!live}
        />
      </div>
      {manualOpen && <ManualDrawer onClose={() => setManualOpen(false)} />}
    </div>
  );
}
