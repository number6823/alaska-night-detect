# server — 후방 감지 기록 서버

담당: 최수창 · 브랜치: `feat/server`

Jetson 이 올린 감지 캡처와 기록을 모아 두고, `web/` 화면이 읽어 가게 하는 서버입니다. 경고음은 Jetson 이 직접 울리고, 서버가 죽어도 경보는 멈추지 않습니다.

## 쓰는 법

```bash
pip install -r server/requirements.txt
python -m server                      # http://127.0.0.1:8000
python -m server --host 0.0.0.0       # 같은 네트워크의 Jetson 이 올릴 때
python -m server --runner-dir data/runner --max-records 1000   # runner 와 주고받는 폴더, 보관할 기록 수
```

- 기록은 `data/server/detections.db`, 캡처는 `data/server/shots/` 에 쌓입니다(레포에 올리지 않습니다).
- `web/dist` 가 있으면 같은 주소에서 화면도 열립니다. `/` 는 운전자 화면, `/admin` 은 관리자 화면입니다(같은 `index.html`을 주고 화면은 주소를 보고 정합니다. `/admin/` 은 `/admin` 으로 돌립니다). 개발 중에는 `web/` 에서 `npm run dev` 를 하면 `/api` 요청이 이 서버(8000)로 넘어갑니다.
- **로그인이 없습니다.** 시연 노트북이나 Jetson 안에서, 신뢰하는 네트워크에서만 엽니다. 인터넷에 열려면 먼저 인증을 붙입니다.

## API (`web/README.md` 의 약속과 같습니다)

| 요청 | 하는 일 |
|---|---|
| `GET /api/detections?limit=200` | 기록 목록, 최신이 먼저 |
| `POST /api/detections` | Jetson 이 올림. multipart: `image`(jpg·png, 5MB 이하)와 `person, bicycle, top, ms, level, dist, at` |
| `PATCH /api/detections/<id>` | `{"false_alarm": true}` 오경보 표시 |
| `GET /api/shots/<파일>` | 캡처 이미지 |
| `GET /api/health` | `{"ok": true, "count": n}` |

- 기록의 `shot` 은 `api/shots/CAP-1.jpg` 모양이라 개발 서버(프록시)에서도, 서버가 화면을 같이 줄 때도 그대로 보입니다.
- 파일 이름은 서버가 정합니다(올린 이름은 쓰지 않습니다). 잘못된 값은 422, 이미지가 아니면 415, 5MB 가 넘으면 413 이고 기록을 남기지 않습니다.

## Jetson 에서 올리기

```python
from server.client import post_detection   # 표준 라이브러리만 씁니다
try:
    post_detection("http://192.168.0.10:8000", jpeg_bytes, person=1, top=0.91, ms=24, level=2, dist=3.1)
except Exception:
    pass   # 서버가 죽어도 경고음은 계속 울려야 한다
```

`level` 은 `alarm.levels` 가 정한 단계(0~3)를 그대로 넣습니다.

## runner(감지 프로그램) 제어 API

server 와 runner 는 **별도 프로세스**이고 **파일로** 주고받습니다(`--runner-dir`, 기본 `data/runner`). 한쪽이 죽어도 다른 쪽은 계속 돕니다. runner 가 꺼져 있으면 `/api/status` 가 `off` 를 돌려줍니다.

| 요청 | 하는 일 |
|---|---|
| `GET /api/status` | runner 상태: `online`, `state`(`running` `camera_lost` `finished` `stale` `off`), FPS, 현재 경보 단계, 사용 장치(GPU/CPU), 거리선 위치, 마지막 명령 결과, 다시 시작이 필요한 설정 |
| `GET /api/config` | 현재 설정, 기본값, **실행 중에 바로 반영되는 설정**(`live_keys`)과 **다시 시작해야 하는 설정**(`restart_keys`) |
| `PUT /api/config` | `{"values": {...}}` 바꿀 설정만 보낸다. 값을 검사해서 틀리면 422 이고 파일은 그대로다. 통과하면 `config.json` 에 저장하고 runner 가 읽어서 반영한다 |
| `POST /api/test-sound` | `{"level": 1\|2\|3}` 경고음 시험. 매번 새 id 로 `control.json` 에 쓰고 runner 가 한 번만 실행한다 |
| `POST /api/calibration` | `{camera_height_m, tilt_deg, vfov_deg, frame_height, save}` 5.5m·3m·2m **거리선 위치**(화면 비율과 픽셀)를 계산한다. `save: true` 면 설정에 저장한다 |
| `POST /api/calibration/fit` | `{distance_m, foot_ratio, camera_height_m, tilt_deg, save}` 한 지점에서 잰 발 위치로 화각을 맞추고 거리선을 계산한다 |
| `GET /api/cameras` | 연결된 카메라 목록(번호, 해상도). runner 가 쓰고 있는 번호는 `in_use` 로 표시 |
| `GET /api/preview` | 박스와 거리선을 그린 최신 화면 스트림(MJPEG). `/api/preview.jpg` 는 한 장 |

- 실행 중에 바로 반영되는 설정: `min_conf`, `calibration`, `camera_height_m`, `tilt_deg`, `vfov_deg`, `window`, `need`, `post_interval_s`, `mute`. `source`, `model`, `device` 등은 다시 시작해야 반영된다.
- **한 지점 보정**: 높이와 기울기를 알면 카메라에서 가까운 한 곳(약 1.5~2m)에 서서 발이 화면 몇 %에 찍혔는지만 재면 된다. **먼 곳(3m 이상)에서 재면 오차가 크다**: 3m 에서 발 위치를 화면 높이의 1%만 잘못 재도 화각이 59~124도로 흔들리고, 2m 는 70~97도, 1.5m 는 77~88도다(참값 82도 가정). 정확하게 하려면 5.5m·3m·2m 거리기준 영상으로 `alarm.levels.calibrate_from_samples` 를 쓴다.
- 설정을 바꾸는 요청(`PUT /api/config`, `POST /api/test-sound`, 저장하는 `calibration`)은 환경변수 `ALASKA_TOKEN` 을 정하면 `X-Token` 헤더가 같아야 한다. 정하지 않으면 같은 네트워크의 누구나 바꿀 수 있다(로그인이 없는 시연용).
- 기록이 `--max-records`(기본 1000)를 넘으면 오래된 기록과 캡처 파일을 자동으로 지운다.

시험: `python -m unittest server.test_app server.test_runner_api -v` (httpx 필요, 37개)

## 시험

```bash
pip install httpx
python -m unittest server.test_app -v      # 14개
```

## Jetson 에서 자동으로 켜기 (`deploy/`)
- `deploy/start_all.sh`: server 와 runner 를 같이 켜고, 하나가 죽으면 그것만 다시 켠다(너무 빨리 계속 죽으면 간격을 늘린다). PC 에서 두 프로그램이 같이 도는 것은 확인했다.
- `deploy/run_container.sh`: Jetson 에서 컨테이너를 `--restart unless-stopped` 로 만들어 `start_all.sh` 를 실행한다. 전원을 켜면 Docker 가 컨테이너를 다시 켠다. **Jetson 에서는 아직 시험하지 못했다**(이미지, GPU 옵션, 오디오·카메라 장치 이름은 장치마다 다르다).
- 설정 화면이 저장한 `data/runner/config.json` 이 있으면 입력과 모델은 그 값으로 시작한다.

## 오경보 기록 → 재학습 자료 (DB·내보내기)
- **DB**: 기록은 이 기기 안의 SQLite 파일(`data/server/detections.db`, `detections` 표)에 저장된다. 별도 DB 서버도 인터넷도 필요 없다. 오경보 표시는 `false_alarm` 열이다.
- **원본 프레임**: runner가 기록을 올릴 때 박스·거리선을 그린 캡처(`image`)와 함께 박스 없는 원본(`raw`)도 올린다. 원본은 `data/server/shots/RAW-<번호>.jpg`로 저장되고 열람 API는 없다(내보내기에만 쓴다). 원본 없이 올리는 예전 방식도 그대로 받는다.
- **자동 삭제**: 표시 안 한 기록이 `--max-records`(기본 1000)를 넘으면 오래된 것부터 캡처·원본 파일과 함께 지운다. **오경보로 표시한 기록은 지우지 않는다**(표시를 취소하면 다시 대상이 된다).
- **내보내기**: `GET /api/export/false-alarms` → `false_alarms.zip`
  - `images/CAP-<번호>.jpg` 박스 없는 원본 프레임(원본이 없으면 박스가 그려진 캡처)
  - `labels/CAP-<번호>.txt` **빈 파일** = YOLO에서 "이 사진에는 사람도 자전거도 없다"(배경 사진). 따로 라벨링할 필요가 없다.
  - `manifest.csv` id, 시각, 경고 단계, 박스 수, 신뢰도, 거리, 사진 종류(`raw` 원본 / `shot` 캡처 / `none`)
  - 표시한 기록이 없으면 404. 학습(재학습)은 사람이 직접 돌린다(자동 재학습이 아니다).
- **주의**: 사람이 실제로 있는데 박스만 틀린 기록을 오경보로 표시하면 빈 라벨이 틀린 정답이 된다. "사람·자전거가 없는데 울린" 기록만 표시한다.
- **개인정보**: 원본 프레임에는 얼굴이 찍힐 수 있다. 팀 안에서만 쓰고, Roboflow 같은 외부 사이트에 올리기 전에는 `python -m training.blur_for_upload`로 모자이크한다. `data/`는 git에 올리지 않는다.
- `GET /api/health`는 `{"ok", "count"(저장된 기록 수), "flagged"(오경보로 표시해 보호되는 수)}`를 돌려준다.

- 오경보 표시 → 재학습까지의 전체 절차와 판단 기준은 `docs/false-alarm-retraining.md`를 본다.
