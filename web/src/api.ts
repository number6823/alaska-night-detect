// 서버가 있으면 거기서 읽고, 없으면 예시 기록을 쓴다.
// Jetson이 POST /api/detections 로 보낸 것을 서버가 모아 두는 구조를 가정한다.
import { DEMO } from "./demoData.ts";
import type { Detection } from "./types.ts";

export interface DetectionsResult {
  rows: Detection[];
  /** 서버에서 받은 것이면 true, 예시 기록이면 false */
  live: boolean;
}

export async function fetchDetections(): Promise<DetectionsResult> {
  try {
    const res = await fetch("/api/detections", { headers: { Accept: "application/json" } });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const rows = (await res.json()) as Detection[];
    if (!Array.isArray(rows) || rows.length === 0) throw new Error("빈 목록");
    return { rows, live: true };
  } catch {
    return { rows: DEMO, live: false };
  }
}

// 오경보 표시를 서버에 남기려면 PATCH /api/detections/<id> 가 필요하다.
// 지금은 화면 안에서만 바뀐다.
export async function flagDetection(id: string, flagged: boolean): Promise<boolean> {
  try {
    await fetch(`/api/detections/${encodeURIComponent(id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ false_alarm: flagged }),
    });
    return true;
  } catch {
    return false;
  }
}
