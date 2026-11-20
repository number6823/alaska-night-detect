import { BEEP, LEVEL_NAME, riskColor } from "../kinds.ts";
import type { Level, RunnerStatus } from "../types.ts";

interface Props {
  /** undefined = 첫 응답을 기다리는 중, null = 상태를 못 받음 */
  status: RunnerStatus | null | undefined;
}

export function Bar({ label, hint, value, color }: { label: string; hint: string; value: number; color: string }) {
  const v = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div className="bar">
      <div className="bar-head">
        <span className="bar-label">{label}</span>
        <span className="bar-hint">{hint}</span>
        <span className="bar-val">{v}<small>%</small></span>
      </div>
      <div
        className="bar-track"
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={v}
      >
        <div className="bar-fill" style={{ width: `${v}%`, background: color }} />
      </div>
    </div>
  );
}

export default function RiskBars({ status }: Props) {
  const loading = status === undefined;
  const on = status?.online === true;
  const risk = on ? status?.risk ?? 0 : 0;
  const conf = on ? status?.conf ?? 0 : 0;
  const level = (on ? status?.alarm_level ?? 0 : 0) as Level;
  return (
    <section className="panel">
      <header>
        <h2>위험율·감지율</h2>
        <span className="sub">{loading ? "연결 중…" : on ? "실시간" : "감지 장치 꺼짐"}</span>
      </header>
      <div className="bars-body">
        <Bar label="위험율" hint="가까울수록 올라갑니다" value={risk} color={riskColor(risk)} />
        <Bar label="감지율" hint="모델 신뢰도(확신 정도)" value={conf} color="var(--level1)" />
        <div className="level-row">
          <span className="level-name">경고 단계</span>
          <span className="beep-chip" data-level={level}>
            {level > 0 ? `${BEEP[level as 1 | 2 | 3]}  ${LEVEL_NAME[level]}` : LEVEL_NAME[0]}
          </span>
        </div>
        <p className="legend">경고음: 삐 약 5.5m · 삐삐 약 3m · 삐삐삐 약 2m</p>
      </div>
    </section>
  );
}
