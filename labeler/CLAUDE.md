# labeler — 도구 2 자동 라벨링

담당: 변성진 · 브랜치: `feat/labeler`

## 하는 일
이미지 폴더를 넣으면 YOLO 라벨과 정확도 리포트가 나온다.

1. 야간 밝기 보정
2. YOLO 자동 라벨 (YOLO txt 형식)
3. 신뢰도 낮은 이미지는 검수 대기열로 분리
4. 정답 라벨 대비 정확도 측정 → 리포트

## 실행법
```
C:\Users\Woori\anaconda3\envs\alaska\python.exe -m labeler run [--images data/images] [--labels data/labels] [--review-queue data/review_queue.csv] [--conf-threshold 0.5] [--discard-threshold 0.25] [--model yolo11n.pt]
```

정확도 측정 (정답 사진을 자동 라벨링한 뒤 정답과 비교, 리포트 `data\accuracy_report.md`):
```
C:\Users\Woori\anaconda3\envs\alaska\python.exe -m labeler eval [--images data/gt100/images] [--gt data/gt100/labels] [--pred data/gt100/pred] [--iou 0.5]
```
- 정답은 `data\gt100\images\`(사진)와 `data\gt100\labels\`(같은 이름 YOLO txt). 클래스 순서 person=0, bicycle=1
- 일치율 = 전체 F1 (IoU 0.5 이상, 같은 클래스끼리 짝지음). 목표 85%
- 파일 이름 첫 `_` 앞(`night`, `day`)으로 야간·낮을 따로 집계한다

## 함수 규약 (agent 호출, 최수창 합의)
`run_labeler(images_dir="data/images", labels_dir="data/labels", review_queue_csv="data/review_queue.csv", conf_threshold=0.5, discard_threshold=0.25, model="yolo11n.pt") -> dict`
- 반환: `labels_dir`, `review_queue_csv`, `images`, `labeled`(txt 만든 장수 = 자동 통과 + 검수), `review`(검수 대기 장수), `discarded`(폐기 장수)
- 이미지 단위 분류: 박스가 모두 `conf_threshold` 이상이면 자동 통과, 미만 박스가 하나라도 있으면 검수 대기, `discard_threshold` 이상 박스가 없으면 폐기(txt 없음)
- `review_queue.csv` 열: `filename,status,boxes,low_conf_boxes,min_conf` (status = `review` / `discard`, 자동 통과는 기록 안 함)

## 라이브러리
- 사용: `ultralytics`(YOLO), `opencv-python`(밝기 보정)
- 안 쓰기로 한 것: 미정

## 규칙
- `labeler/` 밖은 수정하지 않는다. 공용 파일(루트 `CLAUDE.md`, `.gitignore`)은 팀장(최수창)이 관리한다.
- 입력은 collector의 `data\metadata.csv`. 필수 열은 `filename`(확장자 포함, `data\images\` 안 이름과 동일), 나머지는 강민철 제안서를 따른다: `filename, source, source_url, author, license, license_url, query, brightness, removed_reason`
- `data\images\`에는 최종 이미지만 둔다. labeler가 폴더를 통째로 읽는다.
- agent가 호출하는 CLI 인자·출력 경로를 바꿀 때는 최수창과 먼저 합의한다.
- 모델 가중치(`*.pt`)와 이미지는 커밋하지 않는다.
