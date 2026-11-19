import { BEEP } from "../kinds.ts";
import type { Level, RunnerStatus } from "../types.ts";

interface Props {
  status: RunnerStatus | null;
}

const LEVEL_NAME: Record<Level, string> = { 0: "안전", 1: "약 5.5m", 2: "약 3m", 3: "약 2m" };

// 위험율은 가까울수록 초록 → 호박 → 빨강으로 바뀐다.
function riskColor(v: number): string {
  if (v < 34) return "var(--person)";
  if (v < 67) return "var(--accent)";
  return "var(--danger)";
}

function Bar({ label, hint, value, color }: { label: string; hint: string; value: number; color: string }) {
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
  const on = status?.online === true;
  const risk = on ? status?.risk ?? 0 : 0;
  const conf = on ? status?.conf ?? 0 : 0;
  const level = (on ? status?.alarm_level ?? 0 : 0) as Level;
  return (
    <section className="panel">
      <header>
        <h2>위험도</h2>
        <span className="sub">{on ? "실시간" : "runner 꺼짐"}</span>
      </header>
      <div className="bars-body">
        <Bar label="위험율" hint="가까울수록 올라갑니다" value={risk} color={riskColor(risk)} />
        <Bar label="감지율" hint="모델이 얼마나 확신하는지" value={conf} color="var(--level1)" />
        <div className="level-row">
          <span className="level-name">경고 단계</span>
          <span className="beep-chip" data-level={level}>
            {level > 0 ? `${BEEP[level as 1 | 2 | 3]}  ${LEVEL_NAME[level]}` : LEVEL_NAME[0]}
          </span>
        </div>
      </div>
    </section>
  );
}
