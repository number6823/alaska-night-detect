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
C:\Users\Woori\anaconda3\envs\alaska\python.exe -m labeler.split [--images data/images] [--labels data/labels] [--out data/dataset] [--val-ratio 0.2] [--seed 0] [--group-by video] [--exclude-rounds R5] [--all-train]
```
- `run`·`eval`과 달리 하위 명령이 아니라 모듈을 바로 부른다(`-m labeler.split`)
- 라벨 txt가 있는 사진만 넣는다. 폐기된 사진(txt 없음)은 빠진다
- gt100과 gt100 v2는 평가 전용이라 넣지 않는다
- `--group-by video|round`: 후방 영상 프레임은 같은 영상이 train과 val에 나뉘어 들어가면 val 점수가 실제보다 좋게 나온다. 이 옵션을 주면 사진 한 장씩이 아니라 묶음 단위로 나눈다. `video`는 영상 하나(`_R6_01_`), `round`는 라운드 전체(`_R6_`)를 한 묶음으로 본다. **한 라운드에 영상이 여러 개면 `video`를 쓴다.** `round`로 묶으면 그 라운드가 통째로 한쪽으로 가서 val에 영상 프레임이 한 장도 없을 수 있다(11/13 v4에서 실제로 R6 197장이 전부 train으로 갔다). 라운드 표시가 없는 사진(collector가 모은 사진)은 한 장이 한 묶음이라 전과 같게 나뉜다
- `--exclude-rounds`: 평가 전용 라운드를 아예 뺀다. 기본값 `R5`이며 `--group-by`와 상관없이 적용한다(학습에 섞이면 평가를 못 쓰게 되므로). 빼지 않으려면 값 없이 `--exclude-rounds`
- 라운드가 적어 val이 0묶음이 되면 1묶음은 val로 보낸다(val이 비면 학습이 안 돈다)
- `--max-background-ratio`(기본 **0.1**): 빈 txt 사진(배경)이 최종 세트에서 차지할 **상한**. 넘으면 `seed` 로 무작위로 덜어낸다. 배경이 너무 많으면 모델이 "아무것도 없다" 쪽으로 치우친다
- `--all-train`: val을 떼지 않고 **전부 train에 넣는다**. 최적 에포크를 이미 정한 뒤 마지막으로 한 번 더 학습할 때만 쓴다. Ultralytics가 `val` 키를 요구하므로 `data.yaml`의 `val`은 `images/train`을 가리킨다. **그래서 학습 중 나오는 val 점수는 학습에 쓴 사진으로 잰 것이라 성능이 아니다.** 조기 종료도 뜻이 없으니 `--epochs`를 정해 두고 돌린다. `--exclude-rounds`(기본 `R5`)는 그대로 적용돼서 평가 전용 라운드는 여기서도 빠진다
- `--portable`: `data.yaml`에 절대 경로(`path:`)를 넣지 않는다. Ultralytics는 `path`가 없으면 `data.yaml`이 있는 폴더를 기준으로 삼으므로, 폴더째 Colab이나 다른 PC로 옮겨도 그대로 돌아간다. 내 PC에서만 쓸 때는 필요 없다
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
`split_dataset(images_dir="data/images", labels_dir="data/labels", out_dir="data/dataset", val_ratio=0.2, seed=0, group_by=None, exclude_rounds=("R5",), portable=False, max_background_ratio=0.1, all_train=False) -> dict`
- 반환: `data_yaml`(만든 yaml 경로), `train`·`val`(각 장수), `boxes`(train/val 각각 person·bicycle 박스 수), `group_by`, `excluded_rounds`(뺀 라운드별 장수), `background`(넣은 배경 장수), `background_dropped`(상한 때문에 덜어낸 장수), `background_ratio`, `all_train`, `groups`(`group_by`를 줬을 때만, train/val에 들어간 묶음 이름)
- `seed`로 섞는 순서를 고정한다. 같은 입력이면 같게 나뉜다
- `group_by=None`(기본)은 사진 한 장 단위로 나눈다. 전과 같은 동작이다
- `group_by="video"`는 영상 단위, `"round"`는 라운드 단위로 나눈다. 영상 프레임을 넣을 때 쓴다
- `all_train=True`면 `parts`에 val이 없고 `val`은 0이다. `groups`도 나오지 않는다
- agent가 아니라 `training/train.py`가 쓴다. 경로·반환을 바꿀 때는 training 쪽과 먼저 맞춘다

Roboflow export 가져오기 (검수한 라벨을 우리 형식으로 되돌린다):
```
C:\Users\Woori\anaconda3\envs\alaska\python.exe -m labeler.from_roboflow <export 폴더> [--labels data/labels] [--images data/images] [--copy-images] [--out-reviewed data/labels_reviewed]
```
- **Roboflow는 클래스를 알파벳 순서로 내보낸다.** `bicycle` < `person` 이라 **항상** `bicycle=0, person=1` 로 나오고, 우리 규칙(`person=0, bicycle=1`)과 반대다. 그대로 쓰면 사람과 자전거가 통째로 뒤바뀌는데 **조용히 틀린다**
- `data.yaml` 의 `names` 순서를 읽어서 번호를 맞춘다. Roboflow가 순서를 바꾸더라도 맞게 들어간다
- 우리가 쓰지 않는 클래스가 있으면 멈춘다(모르는 채로 넘어가지 않게)
- 파일 이름의 `_jpg.rf.<해시>` 를 떼서 원래 이름으로 되돌린다
- `train/valid/test` 를 모두 합친다. 학습용 분할은 `labeler.split` 이 다시 한다
- 빈 라벨은 txt 를 만들지 않는다(폐기 규칙과 같게)
- `--copy-images`: 사진 폴더에 없는 사진을 export 에서 가져온다
- `--out-reviewed`: 이번에 들어온 라벨만 따로 한 벌 더 쓴다. `labeler.split --labels` 에 바로 넘기려는 용도
- `--keep-empty`: 빈 라벨을 **빈 txt** 로 남긴다. YOLO 는 빈 txt 를 "물체 없음"으로 읽어 그 사진을 **배경**으로 쓴다

### 빈 라벨을 배경으로 쓰는 규칙 (2026-11-13, 최수창 합의)
- **진짜 아무도 없는 프레임만** Roboflow 에서 빈 라벨(Mark Null)로 둔다
- **사람이 있는데 어두워서 안 보이는 프레임은 Dataset 에서 뺀다.** 애매하면 뺀다
- 그래서 빈 txt 는 전부 배경으로 취급해도 된다. 안 보이는 사람을 배경으로 넣으면 "여기 사람 없다"를 잘못 가르친다
- 배경이 필요한 이유: 촬영 계획의 `빈장면` 클립이 노리는 것이 오탐 줄이기다. `training/rear_report.py` 가 그 오탐 프레임 수를 센다

## 함수 규약 (from_roboflow)
`import_export(export_dir, labels_dir="data/labels", images_dir="data/images", copy_images=False, out_reviewed=None) -> dict`
- 반환: `export_names`(export의 클래스 순서), `flipped`(뒤집었는지), `labels`(쓴 장수), `boxes`, `person`, `bicycle`, `empty`(빈 라벨), `background_kept`(배경으로 남긴 장수), `images_copied`, `skipped_no_image`, `unnamed`(`.rf` 꼬리표가 없어 건너뛴 파일)
- `original_name(stem)`: `이름_jpg.rf.해시` → `("이름", "jpg")`. 꼬리표가 없으면 `None`
- `read_class_order(export_dir)`: `data.yaml` 의 클래스 이름을 번호 순서대로 읽는다(한 줄 `names: [...]` 와 여러 줄 `0: person` 둘 다 지원)

## 라이브러리
- 사용: `ultralytics`(YOLO)
- 안 쓰기로 한 것: 야간 밝기 보정, `sahi`(조각 추론). gt100 실험에서 밝기 보정 효과 없음(±0.01 이내), 조각 추론 0.610 → 0.397(yolo11n F1)

## 규칙
- `labeler/` 밖은 수정하지 않는다. 공용 파일(루트 `CLAUDE.md`, `.gitignore`)은 팀장(최수창)이 관리한다.
- 입력은 collector가 채운 `data\images\` 폴더다. labeler는 `data\metadata.csv`를 읽지 않는다. metadata.csv 열은 `collector/_metadata.py`를 따른다: `filename, source, source_url, author, license, license_url, query, brightness, blur, removed_reason` (`filename`은 확장자 포함, `data\images\` 안 이름과 동일)
- `data\images\`에는 최종 이미지만 둔다. labeler가 폴더를 통째로 읽는다.
- agent가 호출하는 CLI 인자·출력 경로를 바꿀 때는 최수창과 먼저 합의한다.
- 모델 가중치(`*.pt`)와 이미지는 커밋하지 않는다.
