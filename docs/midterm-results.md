# 중간 발표 결과 정리

- 발표일: 2026-11-13
- 정리: 변성진 (labeler) · 기준 시각: 2026-11-12 15:30
- 이 문서의 모든 수치는 실제로 돌려서 잰 값입니다. 재현 방법은 맨 아래에 있습니다.

> **이 문서의 수치는 전부 2026-11-12 복구 후에 다시 잰 값입니다.**
> 11월 11일까지의 측정(242장 세트로 학습한 모델, gt100 v2 기준 평가 등)과는 **데이터도 정답 세트도 다르므로 같은 표에 놓고 비교하면 안 됩니다.** 이전 수치는 기획서를 따르고, 둘을 나란히 쓸 때는 어느 세트에서 잰 값인지 반드시 함께 적습니다. 차이는 아래 "복구 전후 비교"에 적었습니다.

---

## 한 줄 요약

수집부터 자동 라벨·검수·학습까지 파이프라인 전체가 돕니다. 다만 **웹에서 모은 일반 야간 사진으로 학습한 모델은, 자동 라벨 기준 val에서 학습 전 `yolo11n`과 비슷한 수준**입니다. 그래서 다음 단계는 COCO에 없는 분포인 **후방 카메라 영상**입니다.

---

## 1. 파이프라인

```
"야간 자전거 수집해줘"
  │
  ▼ agent      키워드 사전으로 검색어 생성 → y/n 승인
  ▼ collector  수집 → 품질 검사 → 중복 제거 → CLIP 관련성 필터
  ▼ labeler    YOLO 자동 라벨 → 자동 통과 / 검수 대기 / 폐기
  ▼ 사람        검수 대기분만 손으로 고침
  ▼ labeler.split  train / val 분할 + data.yaml
  ▼ training   YOLO 학습 → 평가
```

미니 프로젝트에서 만든 도구 2개(collector, labeler)와 에이전트를 그대로 쓰고, 최종 프로젝트에서 `split`과 `training`을 붙였습니다.

## 2. 데이터 현황 (복구 후 기준, 2026-11-12)

| 항목 | 값 |
|---|---|
| 사진 (`data/images`) | **164장** |
| 걸러낸 사진 (`data/removed`) | 25장 |
| 라벨 (`data/labels`) | 149개 |
| └ 사람이 검수한 라벨 | **134장** (박스 1,577개) |
| └ 자동 라벨만 된 것 | 15장 |
| 출처 기록 (`metadata.csv`) | 189줄 (사진 164 + 제거 25) |

출처는 **전부 Wikimedia Commons**입니다. 라이선스가 모두 확인 가능한 공개 라이선스입니다.

| 라이선스 | 장수 | | 라이선스 | 장수 |
|---|---|---|---|---|
| CC BY-SA 4.0 | 55 | | CC BY-SA 2.0 | 17 |
| CC0 | 26 | | Public domain | 8 |
| CC BY 2.0 | 23 | | CC BY 4.0 | 7 |
| CC BY-SA 3.0 | 22 | | CC BY 3.0 | 5 |
| | | | GODL-India | 1 |

### 필터가 걸러낸 것

| 사유 | 장수 | 기준 |
|---|---|---|
| `not_night` | 17 | CLIP 밤 점수 0.4 미만 |
| `near_duplicate` | 5 | pHash·dHash 거리 10 이하 |
| `not_photo` | 3 | CLIP 사진 아님 점수 0.8 초과 |

### 검수의 효과

| | 사진당 평균 박스 |
|---|---|
| 자동 라벨 (yolo11n) | 4.1개 |
| 사람이 검수한 라벨 | **11.8개** |

자동 라벨은 멀리 있거나 작은 사람을 많이 놓칩니다. 검수가 박스를 약 3배로 늘렸습니다. 라벨 기준은 [`labeler/LABEL_GUIDE.md`](../labeler/LABEL_GUIDE.md)를 따릅니다.

### 복구 전후 비교

11월 12일 PC 포맷으로 `data/labels`와 gt100 v2가 사라져, 데이터와 평가 기준이 **둘 다 바뀌었습니다.** 이전 수치와 이 문서의 수치는 서로 다른 세트에서 잰 값입니다.

| | 복구 전 (~11/11) | 복구 후 (11/12, 이 문서) |
|---|---|---|
| 학습 사진 | 242장 세트 | **134장** (검수 라벨만) |
| 평가 기준 | gt100 v2 (사람이 만든 정답 100장) | split이 떼어 둔 val 27장 (자동 라벨 + 검수) |
| 평가의 성격 | 학습과 독립된 정답 세트 | 학습 데이터와 같은 출처에서 나눈 것 |

**따라서 이전 AP50 수치와 이 문서의 mAP50을 직접 비교할 수 없습니다.** gt100 v2는 복구하지 못했고, 사람이 처음부터 만든 정답은 후방 영상 R5(`gt_rear`)로 다시 만들 예정입니다. 그때 다시 같은 기준으로 재야 비교가 성립합니다.

## 3. 학습 실험 (복구 후 데이터 기준)

검수 라벨 134장을 `labeler.split`으로 나눠(train 107 / val 27) `yolo11n`을 학습했습니다. freeze 10, imgsz 640, batch 8, seed 0 고정.

| 설정 | epoch | best | mAP50 | mAP50-95 | precision | recall |
|---|---|---|---|---|---|---|
| **학습 전 `yolo11n`** (기준) | — | — | 0.6680 | **0.5356** | **0.8601** | 0.5721 |
| optimizer auto (lr0 0.01) | 100 | 1 | 0.6014 | 0.3919 | 0.6748 | 0.6025 |
| optimizer auto (lr0 0.001) | 21 | 1 | 0.6014 | 0.3919 | 0.6748 | 0.6025 |
| SGD lr0 0.01 | 22 | 2 | 0.6173 | 0.3932 | 0.7836 | 0.5984 |
| **SGD lr0 0.001** | 21 | 1 | **0.6780** | 0.5353 | 0.8334 | **0.6139** |

### 놓침률 (1 − recall)

후방 경고에서는 **사람을 놓치는 것**이 가장 위험하므로 recall을 뒤집어 봅니다.

| | 놓침률 |
|---|---|
| 학습 전 `yolo11n` | 0.428 |
| **SGD lr0 0.001** | **0.386** |
| 목표 | 0.3 이하 (아직 미달) |

열 명 중 네 명을 놓치던 것이 네 명 조금 안 되게 줄었습니다. 목표 0.3에는 아직 못 미칩니다.

### 읽는 법

- 가장 좋은 설정(SGD lr0 0.001)은 mAP50에서 학습 전보다 **+0.010**, recall에서 **+0.042**(놓침률 −0.042) 높습니다. mAP50-95는 0.5353 대 0.5356으로 **사실상 같습니다**.
- 즉 **"자동 라벨 기준 val에서는 학습 전 모델과 비슷한 수준"**입니다. 좋아졌다고 말하기에는 차이가 작습니다.

### 이 수치를 믿으면 안 되는 이유 두 가지

1. **val이 27장뿐입니다.** mAP50 +0.010 정도의 차이는 사진 몇 장으로 뒤집힙니다.
2. **val 정답이 `yolo11n` 자동 라벨에서 출발해 사람이 고친 것**입니다. 출제자와 응시자가 같은 셈이라 학습 전 `yolo11n`에게 유리합니다.

**공정한 비교는 사람이 처음부터 만든 정답(`gt_rear`)으로 해야 합니다.** 후방 영상 R5를 평가 전용으로 찍어 거기에 쓸 예정입니다.

## 4. 오늘 확인한 것

### Ultralytics `optimizer=auto`는 `lr0`를 무시합니다

처음에 lr0를 0.01 → 0.001로 낮춰 돌렸는데 결과가 소수점까지 같았습니다. 원인은 기본값 `optimizer=auto`였습니다.

```
ultralytics/engine/trainer.py:1224
  "'optimizer=auto' found, ignoring 'lr0=...' and determining best 'optimizer' and 'lr0' automatically"
```

클래스 수가 2이면 `lr_fit = 0.002 * 5 / (4 + 2) = 0.001667`로 정하고 optimizer를 **AdamW**로 덮어씁니다. `--optimizer SGD`를 직접 주고 나서야 lr0가 적용됐고, 그제야 위 표의 네 번째 줄이 나왔습니다.

이걸 모르고 두 실험이 같다는 이유로 "데이터가 문제"라고 결론지을 뻔했습니다.

### 라벨은 사진보다 비쌉니다

PC 포맷으로 `data/labels`와 gt100 v2가 날아갔습니다. 사진은 Wikimedia pageid가 파일 이름에 들어 있어 API로 다시 받을 수 있었지만(출처·작가·라이선스까지 121장 전부 복구), **손으로 그린 라벨은 Roboflow에 올려 둔 덕분에 겨우 살렸습니다.**

| 잃은 것 | 복구 | 방법 |
|---|---|---|
| 사진 | O | 이름의 Wikimedia pageid로 재다운로드 |
| `metadata.csv` 출처·라이선스 | O | Wikimedia API 조회 (121줄) |
| 검수 라벨 134장 | O | Roboflow 프로젝트에 남아 있던 것 |
| gt100 v2 정답 세트 | **X** | 복구 못 함 |
| 학습 기록 (`results.csv`) | **X** | 복구 못 함 |

교훈: **라벨은 레포 밖 어딘가에 반드시 복제본을 둔다.**

## 5. 다음 단계

| 할 일 | 담당 | 비고 |
|---|---|---|
| R1·R5 후방 영상 촬영 → 프레임 추출 | 최수창 | `training/extract_frames.py` |
| R5 `gt_rear` 정답 라벨 | 변성진 | 평가 전용, 학습에 안 씀 |
| R1 프레임으로 학습 | 공통 | 라운드 단위 분할(`--group-by round`) |
| Colab 학습 환경 | 최수창 | `--portable` data.yaml 사용 |
| 자동 라벨 15장 검수 | 변성진 | 끝나면 164장 전부 검수본 |

후방 영상은 승용차 뒤 번호판 높이(약 1m)에서 찍습니다. COCO 사진과 화각·높이·조명이 달라, 여기서는 학습 효과가 나올 것으로 봅니다. 그 가설을 검증하는 게 다음 목표입니다.

---

## 부록: 재현 방법

```bash
# 1. 수집
python -c "from collector import run_collector; print(run_collector(['night bicycle','night cyclist','night person','night pedestrian'], count_per_query=20))"

# 2. 자동 라벨
python -m labeler run

# 3. 검수한 라벨만 모아 분할 (Colab으로 옮기려면 --portable)
python -m labeler.split --labels data/labels_reviewed --out data/dataset_rf134

# 4. 학습 (gt100 v2가 없으면 --skip-eval)
python -m training.train --data data/dataset_rf134/data.yaml --name sgd_lr0001 \
    --skip-eval --optimizer SGD --lr0 0.001 --patience 20

# 5. 학습 전 모델과 비교
python -c "from ultralytics import YOLO; print(YOLO('yolo11n.pt').val(data='data/dataset_rf134/data.yaml', imgsz=640, classes=[0,1]).box.map50)"
```

환경: Python 3.11, ultralytics 8.4.211, torch 2.14.1+cu126, GTX 1060 3GB.
`--optimizer`, `--lr0`, `--patience`, `--skip-eval`은 PR #53, `--group-by round`와 `--portable`은 PR #54에 있습니다.
