import type { Detection, DetectionKind, Level } from "./types.ts";

export const BEEP: Record<Exclude<Level, 0>, string> = { 1: "삐", 2: "삐삐", 3: "삐삐삐" };

// 한 장면에 사람과 자전거가 같이 잡히면 둘 다 적는다.
export function kindOf(rec: Detection): DetectionKind {
  if (!rec.person && !rec.bicycle) return { key: "none", label: "없음", color: "var(--fg-dim)" };
  if (rec.person && rec.bicycle) return { key: "both", label: "사람+자전거", color: "var(--bicycle)" };
  if (rec.bicycle) return { key: "bicycle", label: "자전거", color: "var(--bicycle)" };
  return { key: "person", label: "사람", color: "var(--person)" };
}
