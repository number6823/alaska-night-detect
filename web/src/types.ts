/** 경고 단계. 0 = 경고 없음, 1 = 약 5.5m(삐), 2 = 약 3m(삐삐), 3 = 약 2m(삐삐삐) */
export type Level = 0 | 1 | 2 | 3;

/** 기록표 필터 */
export type Filter = "all" | "person" | "bicycle" | "low";

/** 사진 출처. Wikimedia 사진을 임시로 쓸 때만 있다. 실제 캡처에는 없다. */
export interface Credit {
  author: string;
  license: string;
  url: string;
}

/**
 * 감지 한 건. Jetson이 POST /api/detections 로 보내는 것과 같은 모양이다.
 * shot 은 캡처 이미지 경로, dist 는 발 위치로 추정한 거리(m).
 */
export interface Detection {
  id: string;
  shot: string;
  at: string;
  person: number;
  bicycle: number;
  /** 한 장면에서 가장 높은 신뢰도. 0 이면 감지 없음 */
  top: number;
  /** 추론에 걸린 시간(ms) */
  ms: number;
  level: Level;
  /** 추정 거리(m). 0 이면 추정값 없음 */
  dist: number;
  credit?: Credit;
}

export interface DetectionKind {
  key: "person" | "bicycle" | "both" | "none";
  label: string;
  color: string;
}
