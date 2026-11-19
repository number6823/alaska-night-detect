import type { StoreInfo } from "../api.ts";

interface Props {
  live: boolean;
  lastAt?: string;
  /** 서버 DB(SQLite)에 저장된 기록 수와 오경보로 표시해 보호되는 수. 서버가 없으면 null */
  store?: StoreInfo | null;
}

export default function StatusBar({ live, lastAt, store }: Props) {
  return (
    <div className="topbar">
      <h1>후방 감지 모니터</h1>
      <span className="live">
        <span className={live ? "dot" : "dot off"} />
        {live ? "Jetson 연결됨" : "서버 없음 · 예시 기록"} · 마지막 수신 {lastAt || "—"}
      </span>
      {store && (
        <span
          className="store"
          title="경보 기록과 캡처는 이 기기 안의 SQLite 파일(data/server/detections.db)에 저장됩니다. 인터넷이 필요 없습니다. 오경보로 표시한 기록은 자동 삭제되지 않습니다."
        >
          기록 저장(SQLite) <b>{store.count}</b>건 · 오경보 <b>{store.flagged}</b>건 보호
        </span>
      )}
      {!live && <span className="tag">임시 사진 · 실제 감지 결과</span>}
    </div>
  );
}
