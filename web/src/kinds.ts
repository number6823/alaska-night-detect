import type { Detection, DetectionKind, Level } from "./types.ts";

export const BEEP: Record<Exclude<Level, 0>, string> = { 1: "삐", 2: "삐삐", 3: "삐삐삐" };

// 경고 단계별 거리 이름. 운전자 화면·관리자 화면·기록표가 같은 말을 쓰게 한곳에 둔다.
export const LEVEL_NAME: Record<Level, string> = { 0: "안전", 1: "약 5.5m", 2: "약 3m", 3: "약 2m" };

// 위험율은 가까울수록 초록 → 호박 → 빨강으로 바뀐다.
export function riskColor(v: number): string {
  if (v < 34) return "var(--person)";
  if (v < 67) return "var(--accent)";
  return "var(--danger)";
}

// 한 장면에 사람과 자전거가 같이 잡히면 둘 다 적는다.
export function kindOf(rec: Detection): DetectionKind {
  if (!rec.person && !rec.bicycle) return { key: "none", label: "없음", color: "var(--fg-dim)" };
  if (rec.person && rec.bicycle) return { key: "both", label: "사람+자전거", color: "var(--bicycle)" };
  if (rec.bicycle) return { key: "bicycle", label: "자전거", color: "var(--bicycle)" };
  return { key: "person", label: "사람", color: "var(--person)" };
}
