# alaska-night-detect

한국어 요청 한 줄로 야간 보행자·자전거 사진을 모으고, 걸러내고, YOLO 라벨까지 만드는 학습 데이터 자동 준비 파이프라인입니다.

- **기간**: 2026-10-27 ~ 진행 중
- **팀**: 알래스카 알아서해스카

| 이름 | 역할 | 폴더 |
|------|------|------|
| 강민철 | 도구 1: 자동 수집·정리 | `collector/` |
| 변성진 | 도구 2: 자동 라벨링, 깃 관리 | `labeler/` |
| 최수창 | 팀장, 훅·에이전트, 도구 연결 | `agent/` |

## 해결하려는 문제

야간 학습 데이터는 라이선스를 확인할 수 있는 사진을 모으기 어렵고, 모은 뒤에도 사람이 거르고 라벨을 그리는 데 시간이 많이 듭니다. 이 프로젝트는 출처와 라이선스를 기록하며 사진을 모으고, 사람이 검수할 사진과 고칠 박스를 줄이는 것을 목표로 합니다.

## 결과

| 지표 | 값 | 기준 |
|------|-----|------|
| 자동 확정 박스 정답률 | **92.8%** (206/222) | conf 0.7 이상 박스 중 IoU 0.5로 정답과 맞은 비율 |
| 전체 박스 중 자동 확정 비율 | **40.6%** (222/547) | 이 박스들은 사람이 고칠 필요를 줄이는 대상 |

정답 세트 gt100(100장), `yolo11n`, 입력 크기 640 기준입니다. 기준값을 같은 gt100에서 골랐기 때문에 이 수치는 낙관적일 수 있습니다.

## 전체 흐름

```
"야간 자전거 수집해줘"
  │
  ▼ agent: 키워드 사전으로 검색어를 만들고 y/n 승인
  │         (night bicycle, night cyclist)
  ▼ collector: 수집 → 품질 검사 → 중복 제거 → CLIP 관련성 필터
  │         data/images, data/removed, data/metadata.csv
  ▼ labeler: YOLO 자동 라벨 → 자동 통과 / 검수 대기 / 폐기
  │         data/labels, data/review_queue.csv
  ▼ agent: 수집·라벨·폐기 장수 보고
```

## 기술 판단

시도해 보고 결과에 따라 정한 내용입니다.

| 도구 | 판단 | 근거 |
|------|------|------|
| labeler | 조각 추론(SAHI)을 쓰지 않음 | gt100에서 F1 0.610 → 0.397 |
| labeler | 야간 밝기 보정을 쓰지 않음 | 당시 기준(NMS 0.7) F1 0.602 대비 0.592~0.604, 효과 없음 |
| labeler | Sum 상위 40% 방식을 쓰지 않음 | 정답률 68.0%, 무작위 73.6%보다 낮음 |
| collector | CLIP 프롬프트를 "밤인가"에서 "사진인가"와 "밤인가"로 나눔 | 처음 프롬프트로는 낮·실내의 진짜 사진 15장이 걸러짐 |

## 빠른 실행

```bash
python -m agent.agent "야간 자전거 수집해줘"
```

검색어를 보여 주면 `y`로 승인합니다. 끝나면 수집·라벨·폐기 장수를 보고합니다. 처음이라면 아래 설치부터 진행하세요.

<details>
<summary><b>설치</b></summary>

모든 명령은 레포 맨 위 폴더에서 실행합니다.

**1. 레포 받기**

레포 경로가 너무 길면 설치가 실패할 수 있으니 짧은 경로에 받으세요.

```bash
git clone https://github.com/number6823/alaska-night-detect.git
```

```bash
cd alaska-night-detect
```

**2. 가상환경 만들기**

conda 기준입니다. 환경 이름은 자유롭게 정해도 됩니다.

```bash
conda create -n alaska python=3.11 -y
```

```bash
conda activate alaska
```

**3. 패키지 설치**

```bash
pip install -r collector/requirements.txt
```

```bash
pip install -r labeler/requirements.txt
```

| 파일 | 패키지 | 쓰는 곳 |
|------|--------|---------|
| `collector/requirements.txt` | `requests`, `opencv-python`, `imagehash`, `open-clip-torch` | 수집, 품질 검사, 중복 제거, CLIP 필터 |
| `labeler/requirements.txt` | `ultralytics` | YOLO 자동 라벨, 정확도 평가 |

에이전트는 따로 설치할 것이 없고, 위 두 도구를 함께 씁니다.

**4. 설치 확인**

```bash
python -c "import requests, cv2, imagehash, open_clip, ultralytics; print('설치 확인 완료')"
```

```bash
python -m labeler --help
```

**5. GPU 사용 (선택)**

GPU가 없어도 돌아가지만 CLIP 필터와 YOLO 라벨링이 느려집니다. 코드는 쓸 수 있는 GPU를 자동으로 사용합니다. 아래 명령이 `False`를 출력하는데 NVIDIA GPU가 있다면, [PyTorch 설치 안내](https://pytorch.org/get-started/locally/)에서 자기 CUDA 버전에 맞는 명령으로 `torch`를 다시 설치하세요.

```bash
python -c "import torch; print(torch.cuda.is_available())"
```

**6. Unsplash Lite 데이터셋 (선택)**

없으면 Wikimedia Commons만 쓰고 `[건너뜀]`을 출력합니다. 쓰려면 약관을 읽은 뒤 각자 [데이터셋 zip](https://unsplash.com/data/lite/latest)을 받아 `data/unsplash_lite`에 풉니다. 파일로 주고받지 마세요. `keywords.tsv000`과 `photos.tsv000`이 이 폴더 바로 아래에 있어야 합니다.

**7. 처음 실행할 때 받는 파일**

아래 파일은 처음 실행할 때 자동으로 받으므로 인터넷이 필요합니다.

| 파일 | 받는 때 |
|------|---------|
| CLIP 가중치 ViT-B-32 (약 578MB) | 도구 1 첫 실행 |
| `yolo11n.pt` | 도구 2 첫 실행 |

**API 키**

지금 코드는 API 키 없이 돌아가므로 `.env`를 만들지 않아도 됩니다. 나중에 키를 쓰게 되면 `.env`에만 넣고 레포에 올리지 마세요.

</details>

## 도구별 사용법

### 도구 1: 수집 (collector)

```bash
python -c "from collector import run_collector; print(run_collector(['night bicycle']))"
```

검색어마다 최대 10장을 출처별로 나눠 받습니다(`count_per_query`로 변경). 한 출처가 실패하면 `[건너뜀]`을 출력하고 나머지 출처로 계속합니다. 걸러진 사진은 `data/removed`로 옮기고, 사유를 `data/metadata.csv`의 `removed_reason`에 적습니다.

| 단계 | 사유 | 기준 |
|------|------|------|
| 품질 (OpenCV) | `too_dark`, `blurry`, `unreadable` | 평균 밝기 5 미만, 라플라시안 분산 20 미만, 읽기 실패 |
| 중복 (MD5, imagehash) | `duplicate`, `near_duplicate` | 파일 동일, pHash·dHash 거리 모두 10 이하 |
| 관련성 (CLIP ViT-B-32) | `not_photo`, `not_night` | 사진 아님 점수 0.8 초과, 밤 점수 0.4 미만 |

### 도구 2: 라벨링 (labeler)

```bash
python -m labeler run
```

`data/images`의 사진을 `yolo11n.pt`로 라벨링합니다. 클래스는 `person=0`, `bicycle=1`만 씁니다.

| 분류 | 조건 | 결과 |
|------|------|------|
| 자동 통과 | 모든 박스가 conf 0.7 이상 | 라벨 txt 저장 |
| 검수 대기 | conf 0.7 미만 박스가 하나라도 있음 | 라벨 txt 저장, `review_queue.csv`에 기록 |
| 폐기 | conf 0.25 이상 박스가 없음 | 라벨 없음, `review_queue.csv`에 기록 |

### 정확도 평가

```bash
python -m labeler eval
```

정답 세트(`data/gt100/images`, `data/gt100/labels`)와 비교해 `data/accuracy_report.md`를 만듭니다. 정답 세트는 레포에 없습니다.

gt100 측정값입니다. 설정은 `yolo11n`, 입력 크기 640, NMS 0.5, 확정 conf 0.7, 폐기 conf 0.25, IoU 0.5입니다. F1은 보고용이며 목표로 삼지 않습니다. 모두 기준값을 고른 gt100으로 잰 값이라 낙관적일 수 있습니다.

| 항목 | 값 |
|------|-----|
| F1 | 0.610 (TP 403, FP 144, FN 371, precision 0.737, recall 0.521) |
| 클래스별 F1 | person 0.605, bicycle 0.634 |
| 야간·낮 F1 | 밤 0.612, 낮 0.597 |
| AP50 | 0.584 (person 0.557, bicycle 0.612) |
| 오류 종류 (TIDE) | Cls 1, Loc 85, Both 5, Dupe 0, Bkg 53, Miss 304 |
| 사진 분류 | 라벨 92장 중 검수 73장(79.3%), 폐기 8장 |

### 에이전트와 보조 도구 (agent)

에이전트는 규칙 기반 키워드 사전으로 요청을 해석합니다. 사전에 있는 말은 `야간`, `자전거`, `사람`이며, 대상(`자전거`, `사람`)이 없으면 "해석 불가"로 끝납니다.

| 파일 | 하는 일 | 실행 |
|------|---------|------|
| `agent/hook.py` | Claude Code `UserPromptSubmit` 훅용 스크립트. 수집 요청이면 검색어 후보를 한 줄 출력. 레포에 등록 설정은 없음 | `python agent/hook.py "야간 자전거 수집해줘"` |
| `agent/preview.py` | 박스를 conf 기준으로 초록(확정)·빨강(확인 필요)으로 그린 미리보기 생성 | `python -m agent.preview` |
| `agent/flir.py` | FLIR 정답(COCO JSON)을 YOLO txt로 변환. `bike` 클래스 이름은 실제 데이터로 아직 확인하지 않음 | `python -m agent.flir <coco_json> <out_dir>` |

### 함수로 부르기

최종 프로젝트의 웹 서버가 부를 수 있도록 함수 단위로 만들었습니다.

```python
from collector import run_collector
from labeler import run_labeler

collected = run_collector(["night bicycle"])
labeled = run_labeler(collected["images_dir"])
```

## 데이터와 라이선스

- 수집은 라이선스를 확인할 수 있는 Wikimedia Commons와 Unsplash Lite만 씁니다.
- Unsplash Lite 사진과 `metadata.csv`의 Unsplash 줄(설명·작가 이름 포함)은 공개하지 않고 `data/` 밖으로 내보내지 않습니다.
- 영상, 이미지, 모델 파일(`*.pt`)과 `.env`는 레포에 올리지 않습니다.

## 앞으로의 계획

- 모은 데이터로 야간 감지 모델 학습 (예정)
- 도구를 부르는 웹 서버 (예정)

팀 작업 규칙은 [CLAUDE.md](CLAUDE.md), labeler 세부 사항은 [labeler/CLAUDE.md](labeler/CLAUDE.md)를 참고하세요.
