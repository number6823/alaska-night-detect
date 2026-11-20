// 서버가 있으면 거기서 읽고, 없으면 예시 기록을 쓴다.
// Jetson이 POST /api/detections 로 보낸 것을 서버가 모아 두는 구조를 가정한다.
import { DEMO } from "./demoData.ts";
import type { Detection, RunnerStatus } from "./types.ts";

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

// 오경보 표시를 PATCH /api/detections/<id> 로 서버에 남긴다.
// 서버가 없으면 화면 안에서만 바뀐다.
export async function flagDetection(id: string, flagged: boolean): Promise<boolean> {
  try {
    const res = await fetch(`/api/detections/${encodeURIComponent(id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ false_alarm: flagged }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

// runner 상태(막대와 미리보기용). server 가 없거나 runner 가 꺼져 있으면 null.
export async function fetchStatus(): Promise<RunnerStatus | null> {
  try {
    const res = await fetch("/api/status", { headers: { Accept: "application/json" } });
    if (!res.ok) return null;
    return (await res.json()) as RunnerStatus;
  } catch {
    return null;
  }
}

// 서버 DB(SQLite)에 저장된 기록 수와, 오경보로 표시해 자동 삭제에서 보호되는 수. 서버가 없으면 null.
export interface StoreInfo {
  count: number;
  flagged: number;
}
export async function fetchHealth(): Promise<StoreInfo | null> {
  try {
    const res = await fetch("/api/health", { headers: { Accept: "application/json" } });
    if (!res.ok) return null;
    const d = (await res.json()) as { count?: number; flagged?: number };
    return { count: d.count ?? 0, flagged: d.flagged ?? 0 };
  } catch {
    return null;
  }
}
