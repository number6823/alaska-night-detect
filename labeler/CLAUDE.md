# labeler — 도구 2 자동 라벨링

담당: 변성진 · 브랜치: `feat/labeler`

## 하는 일
이미지 폴더를 넣으면 YOLO 라벨과 정확도 리포트가 나온다.

1. YOLO 자동 라벨 (YOLO txt 형식)
2. 불확실한 사진(사진 점수 상위 `review_top` 비율)은 검수 대기열로 분리
3. 정답 라벨 대비 정확도 측정 → 리포트

## 실행법
```
C:\Users\Woori\anaconda3\envs\alaska\python.exe -m labeler run [--images data/images] [--labels data/labels] [--review-queue data/review_queue.csv] [--discard-threshold 0.25] [--model yolo11n.pt] [--review-top 0.4]
```

정확도 측정 (정답 사진을 자동 라벨링한 뒤 정답과 비교, 리포트 `data\accuracy_report.md`):
```
C:\Users\Woori\anaconda3\envs\alaska\python.exe -m labeler eval [--images data/gt100/images] [--gt data/gt100/labels] [--pred data/gt100/pred] [--iou 0.5] [--discard-threshold 0.25] [--model yolo11n.pt]
```
- 정답은 `data\gt100\images\`(사진)와 `data\gt100\labels\`(같은 이름 YOLO txt). 클래스 순서 person=0, bicycle=1
- 일치율 = 전체 F1 (IoU 0.5 이상, 같은 클래스끼리 짝지음). F1은 보고만 하고 목표로 삼지 않는다. 목표는 검수할 사진 수와 고칠 박스 수 줄이기
- 파일 이름 첫 `_` 앞(`night`, `day`)으로 야간·낮을 따로 집계한다

## 함수 규약 (agent 호출, 최수창 합의)
`run_labeler(images_dir="data/images", labels_dir="data/labels", review_queue_csv="data/review_queue.csv", discard_threshold=0.25, model="yolo11n.pt", review_top=0.4) -> dict`
- 반환: `labels_dir`, `review_queue_csv`, `images`, `labeled`(txt 만든 장수 = 자동 통과 + 검수), `review`(검수 대기 장수), `discarded`(폐기 장수), `review_ratio`(`review` / `labeled`, 소수 4자리)
- 예측: `imgsz=640`, NMS `iou=0.5`, `conf=discard_threshold`
- 이미지 단위 분류: `discard_threshold` 이상 박스가 없으면 폐기(txt 없음). 나머지는 사진 점수가 높은 순으로 `labeled × review_top`(내림)장을 검수 대기, 나머지는 자동 통과
- 박스 점수 = `(1 - |2·conf - 1|)²` (conf 0.5일 때 1, 0·1에 가까우면 0), 사진 점수 = 박스 점수의 합
- `review_queue.csv` 열: `filename,status,boxes,score,min_conf` (status = `review` / `discard`, 자동 통과는 기록 안 함). `review` 줄이 사진 점수 높은 순으로 먼저, `discard` 줄은 뒤에 (`score`·`min_conf` 빈칸)

## 라이브러리
- 사용: `ultralytics`(YOLO)
- 안 쓰기로 한 것: 야간 밝기 보정, `sahi`(조각 추론). gt100 실험에서 밝기 보정은 F1 변화가 없었고, 조각 추론은 F1이 떨어졌다(yolo11n 0.602 → 0.397)

## 규칙
- `labeler/` 밖은 수정하지 않는다. 공용 파일(루트 `CLAUDE.md`, `.gitignore`)은 팀장(최수창)이 관리한다.
- 입력은 collector가 채운 `data\images\` 폴더다. labeler는 `data\metadata.csv`를 읽지 않는다. metadata.csv 열은 `collector/_metadata.py`를 따른다: `filename, source, source_url, author, license, license_url, query, brightness, blur, removed_reason` (`filename`은 확장자 포함, `data\images\` 안 이름과 동일)
- `data\images\`에는 최종 이미지만 둔다. labeler가 폴더를 통째로 읽는다.
- agent가 호출하는 CLI 인자·출력 경로를 바꿀 때는 최수창과 먼저 합의한다.
- 모델 가중치(`*.pt`)와 이미지는 커밋하지 않는다.
