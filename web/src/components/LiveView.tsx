import type { RunnerStatus } from "../types.ts";

interface Props {
  status: RunnerStatus | null;
}

// runner 가 박스와 5.5m·3m·2m 거리선을 그려 둔 최신 화면(MJPEG)을 그대로 보여 준다.
export default function LiveView({ status }: Props) {
  const on = status?.online === true;
  return (
    <section className="panel">
      <header>
        <h2>실시간 화면</h2>
        <span className="sub">
          {on ? `${status?.fps ?? 0} fps${status?.device ? ` · ${status.device}` : ""}` : "runner 꺼짐"}
        </span>
      </header>
      <div className="capture">
        <div className="frame live">
          {on ? (
            <img src="/api/preview" alt="박스와 거리선이 그려진 실시간 화면" />
          ) : (
            <div className="empty">runner 가 꺼져 있습니다</div>
          )}
        </div>
      </div>
    </section>
  );
}
