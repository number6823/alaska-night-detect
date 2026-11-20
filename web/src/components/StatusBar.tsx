import type { StoreInfo } from "../api.ts";

interface Props {
  live: boolean;
  lastAt?: string;
  /** 서버 DB(SQLite)에 저장된 기록 수와 오경보로 표시해 보호되는 수. 서버가 없으면 null */
  store?: StoreInfo | null;
  onToggleTheme: () => void;
  manualOpen: boolean;
  onToggleManual: () => void;
}

// 관리자 화면의 맨 위 줄. 화면 전환과 밝게/어둡게 버튼을 위쪽 오른쪽에 둔다.
export default function StatusBar({ live, lastAt, store, onToggleTheme, manualOpen, onToggleManual }: Props) {
  // /admin 이든 ?view=admin 이든, 운전자 화면은 같은 곳의 맨 위 주소(/)다.
  const root = window.location.pathname.replace(/admin\/?$/, "");
  return (
    <div className="topbar">
      <h1>후방 감지 · 관리자 화면</h1>
      <span className="live">
        <span className={live ? "dot" : "dot off"} />
        {live ? "Jetson 연결됨" : "Jetson 연결 안 됨 · 예시 기록"} · 마지막 수신 {lastAt || "—"}
      </span>
      {store && (
        <span
          className="store"
          title="경보 기록과 캡처는 이 기기 안의 SQLite 파일(data/server/detections.db)에 저장됩니다. 인터넷이 필요 없습니다. 오경보로 표시한 기록은 자동 삭제되지 않습니다."
        >
          기록 저장 <b>{store.count}</b>건 · 오경보 <b>{store.flagged}</b>건 보호
        </span>
      )}
      <div className="top-actions">
        <button type="button" className="top-btn" aria-pressed={manualOpen} onClick={onToggleManual}>매뉴얼</button>
        <a className="top-btn" href={root}>운전자 화면 보기</a>
        <button type="button" className="top-btn" onClick={onToggleTheme}>밝게 / 어둡게</button>
      </div>
    </div>
  );
}
