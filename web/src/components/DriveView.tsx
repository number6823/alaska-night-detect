import { BEEP, LEVEL_NAME, riskColor } from "../kinds.ts";
import { Bar } from "./RiskBars.tsx";
import type { Level, RunnerStatus } from "../types.ts";

interface Props {
  /** undefined = 첫 응답을 기다리는 중, null = 상태를 못 받음 */
  status: RunnerStatus | null | undefined;
}

// 가까워질수록 한 칸씩 켜진다(주차 센서처럼).
const STEPS = [
  { level: 1, dist: "5.5m" },
  { level: 2, dist: "3m" },
  { level: 3, dist: "2m" },
] as const;

/**
 * 운전자 화면. 차의 내비 화면이나 휴대폰에서 보는 보조 화면이라 크고 단순하다.
 * 기록표·오경보 표시는 관리자 화면에 있다. 차의 후방주차 화면을 대신하지 않고 곁에서 돕는다.
 */
export default function DriveView({ status }: Props) {
  const loading = status === undefined;
  const on = status?.online === true;
  const level = (on ? status?.alarm_level ?? 0 : 0) as Level;
  const risk = on ? status?.risk ?? 0 : 0;
  return (
    <div className="drive">
      <header className="drive-top">
        <h1>후방 감지</h1>
        <span className="live">
          <span className={on ? "dot" : "dot off"} />
          {loading ? "연결 중…" : on ? `감지 중${status?.fps ? ` · ${status.fps} fps` : ""}` : "감지 장치 연결 안 됨"}
        </span>
      </header>
      {/* 후방주차 화면처럼 영상이 위, 경고 단계와 위험율이 아래에 온다 */}
      <main className="drive-stage">
        <div className="drive-frame">
          {on ? (
            <img src="/api/preview" alt="박스와 거리선이 그려진 후방 화면" />
          ) : (
            <div className="empty">{loading ? "연결 중…" : "감지 장치가 연결되지 않았습니다"}</div>
          )}
          <div className="drive-badge" data-level={level}>
            {level > 0 ? `${BEEP[level as 1 | 2 | 3]}  ${LEVEL_NAME[level]}` : LEVEL_NAME[0]}
          </div>
        </div>
        <div className="drive-strip">
          <ol className="steps" aria-label="경고 단계">
            {STEPS.map((s) => (
              <li key={s.level} className={level >= s.level ? "step on" : "step"} data-level={s.level}>
                <b>{BEEP[s.level]}</b>
                <span>약 {s.dist}</span>
              </li>
            ))}
          </ol>
          <Bar label="위험율" hint="가까울수록 올라갑니다" value={risk} color={riskColor(risk)} />
        </div>
      </main>
    </div>
  );
}
