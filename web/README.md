# web — 후방 감지 모니터

담당: 변성진 · 브랜치: `feat/web`

Jetson이 보낸 감지 캡처와 기록을 보여 주는 웹 화면입니다. 화면은 하나이고, 경고음은 Jetson이 울립니다. 이 화면은 **나중에 들여다보는 용도**입니다 — 무엇이 언제 잡혔는지, 어느 것이 오경보였는지.

## 환경

| | 버전 |
|---|---|
| Node | **20 이상** (개발·빌드는 v26.13.1에서 확인) |
| npm | 11.20.0 |
| React | 18.3.1 |
| Vite | 5.4.11 |
| TypeScript | 5.6.3 |

버전은 `package.json`에 범위 없이 고정했고, `package-lock.json`을 레포에 올립니다. **시연하는 PC에는 Node가 필요 없습니다** — 빌드한 `dist/`만 있으면 됩니다.

## 쓰는 법

```bash
cd web
npm ci            # package-lock.json 그대로 설치 (npm install 아님)
npm run dev       # 개발 서버 http://localhost:5173
npm run build     # 타입 검사 후 dist/ 생성
npm run typecheck # 타입만 검사
```

`npm run build`는 `tsc --noEmit`을 먼저 돌리므로 **타입 오류가 있으면 빌드가 실패합니다.**

### 발표용 시연

```bash
npm run build
```

나온 `dist/` 폴더를 통째로 옮겨 아무 정적 서버로 엽니다.

```bash
cd dist && python -m http.server 8123   # http://localhost:8123
```

`dist/index.html`을 파일로 바로 여는 것은 **안 됩니다.** 브라우저가 `file://`에서 ES 모듈을 막습니다. 반드시 서버로 여세요.

> 발표 전날 `dist/`를 압축해 드라이브에 백업해 둡니다. 빌드가 깨져도 그걸로 바로 시연합니다.

## 구조

```
web/
  index.html
  vite.config.ts          /api 요청을 개발 중 localhost:8000 으로 넘김
  tsconfig.json           strict 켜짐
  src/
    main.tsx
    App.tsx               상태(선택·필터·오경보)를 들고 있음
    types.ts              Detection, Level, Filter 등 공용 타입
    api.ts                GET/PATCH /api/detections, 실패하면 예시 기록
    demoData.ts           서버가 없을 때 쓰는 예시 기록
    kinds.ts              경고음 이름, 종류 판정
    styles.css            색 토큰과 레이아웃
    components/
      StatusBar.tsx       연결 상태, 마지막 수신
      StatTiles.tsx       지표 4칸
      CapturePanel.tsx    캡처 사진, 경고 단계, 추정 거리, 출처
      RecordTable.tsx     감지 기록표
      Filters.tsx         전체 / 사람 / 자전거 / 신뢰도 0.7 미만
      Notes.tsx           화면 아래 설명
  public/shots/           예시 캡처 (레포에 올리지 않음)
```

## 서버와 주고받는 것

아직 서버가 없습니다. 화면은 `GET /api/detections`를 먼저 시도하고, 실패하면 `demoData.ts`로 넘어갑니다. 상단에 **"Jetson 연결됨"** / **"서버 없음 · 예시 기록"** 으로 구분해 표시합니다.

```jsonc
// GET /api/detections  →  Detection[]
{
  "id": "CAP-118",
  "shot": "shots/shot1.jpg",   // 캡처 이미지 경로
  "at": "21:48:12",
  "person": 4,                  // 사람 박스 수
  "bicycle": 1,                 // 자전거 박스 수
  "top": 0.93,                  // 가장 높은 신뢰도
  "ms": 24,                     // 추론 시간
  "level": 2,                   // 경고 단계 0~3
  "dist": 3.1                   // 추정 거리(m)
}
```

- `POST /api/detections` — Jetson이 캡처와 감지 정보를 올립니다.
- `PATCH /api/detections/<id>` — 오경보 표시를 남깁니다. **아직 없어서 지금은 화면 안에서만 바뀝니다.**

### 경고 단계

주차 센서 방식입니다. 거리는 사람 발 위치(박스 아래 끝)로 추정하며, 카메라 높이 1m 고정과 평탄한 바닥을 가정한 근사치입니다.

| 단계 | 거리 | 소리 |
|---|---|---|
| 1 | 약 5.5m | 삐 |
| 2 | 약 3m | 삐삐 |
| 3 | 약 2m | 삐삐삐 |

기준값은 코드에 박지 않고 **`거리기준` 클립에서 2m 발 위치를 재서 정합니다.**

발끝이 화면 아래로 잘리면 박스 아래 끝이 화면 끝이 되어 거리값이 실제보다 가깝게 나옵니다. 그 경우 숫자 대신 **"2m 이내, 3단계"**로 처리할 예정입니다.

## 예시 캡처 사진

`public/shots/`의 사진은 **레포에 올리지 않습니다**(영상·이미지는 올리지 않는 규칙, `.gitignore`의 `*.jpg`). 받아서 처음 실행하면 캡처 자리가 비어 보입니다.

사진은 Wikimedia Commons의 야간 사진에 학습한 모델(`data/train_full/runs/.../best.pt`)을 돌려 박스를 그린 것입니다. 신뢰도와 박스 수도 모델 출력 그대로이고, 시각·거리·경고 단계만 화면을 보여 주려고 지어낸 값입니다. 각 캡처 아래에 작가와 라이선스를 표시합니다.

후방 영상 프레임(R1·R2)이 나오면 그것으로 교체합니다.
