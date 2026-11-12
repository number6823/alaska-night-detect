# labeler — 도구 2 자동 라벨링

담당: 변성진 · 브랜치: `feat/labeler`

## 하는 일
이미지 폴더를 넣으면 YOLO 라벨과 정확도 리포트가 나온다.

1. YOLO 자동 라벨 (YOLO txt 형식)
2. 신뢰도 `conf_threshold` 미만 박스가 있는 사진은 검수 대기열로 분리
3. 정답 라벨 대비 정확도 측정 → 리포트
4. 검수를 마친 라벨을 train/val로 나누고 Ultralytics `data.yaml` 생성 (`training/`이 읽는다)

## 실행법
```
C:\Users\Woori\anaconda3\envs\alaska\python.exe -m labeler run [--images data/images] [--labels data/labels] [--review-queue data/review_queue.csv] [--conf-threshold 0.7] [--discard-threshold 0.25] [--model yolo11n.pt]
```

정확도 측정 (정답 사진을 자동 라벨링한 뒤 정답과 비교, 리포트 `data\accuracy_report.md`):
```
C:\Users\Woori\anaconda3\envs\alaska\python.exe -m labeler eval [--images data/gt100/images] [--gt data/gt100/labels] [--pred data/gt100/pred] [--iou 0.5] [--conf-threshold 0.7] [--discard-threshold 0.25] [--model yolo11n.pt]
```
- 정답은 `data\gt100\images\`(사진)와 `data\gt100\labels\`(같은 이름 YOLO txt). 클래스 순서 person=0, bicycle=1
- 일치율 = 전체 F1 (IoU 0.5 이상, 같은 클래스끼리 짝지음). F1은 보고만 하고 목표로 삼지 않는다. 목표는 검수할 사진 수와 고칠 박스 수 줄이기
- 파일 이름 첫 `_` 앞(`night`, `day`)으로 야간·낮을 따로 집계한다
- 리포트에 자동 확정 박스 정답률(conf 0.7 이상 박스 중 IoU 0.5로 맞은 비율)과 확정 박스 수·비율, AP50(표준 방식 conf 0.001부터 / labeler 출력 conf 0.25 이상)과 오류 종류 개수(TIDE: Cls, Loc, Both, Dupe, Bkg, Miss)를 함께 낸다. 라벨 txt에는 conf가 없어서 eval이 conf 0.001로 한 번 더 예측한다(`predict_scored`)

데이터셋 나누기 (검수를 마친 라벨을 train/val로 나눠 `data\dataset\`과 `data.yaml`을 만든다):
```
C:\Users\Woori\anaconda3\envs\alaska\python.exe -m labeler.split [--images data/images] [--labels data/labels] [--out data/dataset] [--val-ratio 0.2] [--seed 0]
```
- `run`·`eval`과 달리 하위 명령이 아니라 모듈을 바로 부른다(`-m labeler.split`)
- 라벨 txt가 있는 사진만 넣는다. 폐기된 사진(txt 없음)은 빠진다
- gt100과 gt100 v2는 평가 전용이라 넣지 않는다
- `--out` 폴더가 이미 있으면 `FileExistsError`로 멈춘다. 지난 결과와 섞이지 않게 하려는 것이니 다시 나누려면 폴더를 직접 지운다
- 사진과 라벨은 `out\images\{train,val}`, `out\labels\{train,val}`로 복사한다. `data\images\`의 원본은 그대로 둔다
- 여기서 나온 `data\dataset\data.yaml`을 `training\train.py`가 읽는다

## 함수 규약 (agent 호출, 최수창 합의)
`run_labeler(images_dir="data/images", labels_dir="data/labels", review_queue_csv="data/review_queue.csv", conf_threshold=0.7, discard_threshold=0.25, model="yolo11n.pt") -> dict`
- 반환: `labels_dir`, `review_queue_csv`, `images`, `labeled`(txt 만든 장수 = 자동 통과 + 검수), `review`(검수 대기 장수), `discarded`(폐기 장수), `review_ratio`(`review` / `labeled`, 소수 4자리), `boxes`(라벨이 만들어진 사진의 전체 박스 수), `confirmed_boxes`(`conf_threshold` 이상 박스 수, 검수 사진 안 박스 포함)
- 예측: `imgsz=640`, NMS `iou=0.5`, `conf=discard_threshold`
- 이미지 단위 분류: 박스가 모두 `conf_threshold` 이상이면 자동 통과, 미만 박스가 하나라도 있으면 검수 대기, `discard_threshold` 이상 박스가 없으면 폐기(txt 없음)
- `conf_threshold=0.7`은 gt100에서 자동 확정 박스 정답률 90% 이상인 가장 작은 값으로 골랐다(92.8%(206/222), 확정 비율 40.6%(222/547)). 같은 세트에서 골라 낙관적일 수 있다
- Sum 상위 X%는 시험했지만 무작위(73.6%)보다 낮은 68.0%여서 쓰지 않는다
- `review_queue.csv` 열: `filename,status,boxes,low_conf_boxes,min_conf` (status = `review` / `discard`, 자동 통과는 기록 안 함)

## 함수 규약 (split, training 호출)
`split_dataset(images_dir="data/images", labels_dir="data/labels", out_dir="data/dataset", val_ratio=0.2, seed=0) -> dict`
- 반환: `data_yaml`(만든 yaml 경로), `train`·`val`(각 장수), `boxes`(train/val 각각 person·bicycle 박스 수)
- `seed`로 섞는 순서를 고정한다. 같은 입력이면 같게 나뉜다
- agent가 아니라 `training/train.py`가 쓴다. 경로·반환을 바꿀 때는 training 쪽과 먼저 맞춘다

## 라이브러리
- 사용: `ultralytics`(YOLO)
- 안 쓰기로 한 것: 야간 밝기 보정, `sahi`(조각 추론). gt100 실험에서 밝기 보정 효과 없음(±0.01 이내), 조각 추론 0.610 → 0.397(yolo11n F1)

## 규칙
- `labeler/` 밖은 수정하지 않는다. 공용 파일(루트 `CLAUDE.md`, `.gitignore`)은 팀장(최수창)이 관리한다.
- 입력은 collector가 채운 `data\images\` 폴더다. labeler는 `data\metadata.csv`를 읽지 않는다. metadata.csv 열은 `collector/_metadata.py`를 따른다: `filename, source, source_url, author, license, license_url, query, brightness, blur, removed_reason` (`filename`은 확장자 포함, `data\images\` 안 이름과 동일)
- `data\images\`에는 최종 이미지만 둔다. labeler가 폴더를 통째로 읽는다.
- agent가 호출하는 CLI 인자·출력 경로를 바꿀 때는 최수창과 먼저 합의한다.
- 모델 가중치(`*.pt`)와 이미지는 커밋하지 않는다.
