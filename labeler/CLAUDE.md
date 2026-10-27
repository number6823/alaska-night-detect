# labeler — 도구 2 자동 라벨링

담당: 변성진 · 브랜치: `feat/labeler`

## 하는 일
이미지 폴더를 넣으면 YOLO 라벨과 정확도 리포트가 나온다.

1. 야간 밝기 보정
2. YOLO 자동 라벨 (YOLO txt 형식)
3. 신뢰도 낮은 이미지는 검수 대기열로 분리
4. 정답 라벨 대비 정확도 측정 → 리포트

## 실행법
미정 — 구현 후 갱신. 예정: `python -m labeler run <이미지폴더>`

## 라이브러리
- 사용: `ultralytics`(YOLO), `opencv-python`(밝기 보정)
- 안 쓰기로 한 것: 미정

## 규칙
- `labeler/` 밖은 수정하지 않는다. 공용 파일(루트 `CLAUDE.md`, `.gitignore`)은 팀장(최수창)이 관리한다.
- 입력은 collector의 `metadata.csv` 형식을 따른다. 형식은 강민철과 합의 후 여기 적는다.
- agent가 호출하는 CLI 인자·출력 경로를 바꿀 때는 최수창과 먼저 합의한다.
- 모델 가중치(`*.pt`)와 이미지는 커밋하지 않는다.
