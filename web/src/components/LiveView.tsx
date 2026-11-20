import type { RunnerStatus } from "../types.ts";

interface Props {
  /** undefined = 첫 응답을 기다리는 중, null = 상태를 못 받음 */
  status: RunnerStatus | null | undefined;
}

// 감지 장치가 박스와 5.5m·3m·2m 거리선을 그려 둔 최신 화면(MJPEG)을 그대로 보여 준다.
export default function LiveView({ status }: Props) {
  const loading = status === undefined;
  const on = status?.online === true;
  return (
    <section className="panel">
      <header>
        <h2>실시간 화면</h2>
        <span className="sub">
          {loading ? "연결 중…" : on ? `${status?.fps ?? 0} fps${status?.device ? ` · ${status.device}` : ""}` : "감지 장치 꺼짐"}
        </span>
      </header>
      <div className="capture">
        <div className="frame live">
          {on ? (
            <img src="/api/preview" alt="박스와 거리선이 그려진 실시간 화면" />
          ) : (
            <div className="empty">{loading ? "연결 중…" : "감지 장치가 꺼져 있습니다"}</div>
          )}
        </div>
      </div>
    </section>
  );
}
