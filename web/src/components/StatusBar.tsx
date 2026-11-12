interface Props {
  live: boolean;
  lastAt?: string;
}

export default function StatusBar({ live, lastAt }: Props) {
  return (
    <div className="topbar">
      <h1>후방 감지 모니터</h1>
      <span className="live">
        <span className={live ? "dot" : "dot off"} />
        {live ? "Jetson 연결됨" : "서버 없음 · 예시 기록"} · 마지막 수신 {lastAt || "—"}
      </span>
      {!live && <span className="tag">임시 사진 · 실제 감지 결과</span>}
    </div>
  );
}
