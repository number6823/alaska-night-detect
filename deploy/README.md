# deploy — Jetson Nano 배포

담당: 최수창 · Jetson 실기기 확인: 강민철

**Jetson Nano 한 대 안에서** 감지, 거리 단계 경고음, 기록·캡처 저장, 웹 화면 제공이 모두 돌아간다. 인터넷·클라우드·외부 서버가 필요 없다. 전원을 켜면 Docker가 컨테이너를 다시 켜고, 컨테이너 안에서 server와 runner가 같이 시작된다.

```
[Jetson Nano]  카메라(또는 영상 파일) → runner: 감지(TensorRT) → 거리 단계 → 스피커 경고음
               └ server(:8000, SQLite): 기록·캡처 저장 + 웹 화면(web/dist) 제공
[노트북·휴대폰]  같은 와이파이·핫스팟에서  http://<Jetson IP>:8000   (보기 전용)
```

- 소리는 **Jetson의 runner가** 낸다. 웹은 보여 주기만 한다.
- server가 죽어도 runner의 경고음은 멈추지 않는다. runner나 server가 죽으면 3~30초 뒤 다시 켜진다(오래 돌다 죽으면 3초, 금방 계속 죽으면 간격이 늘어난다).

## 준비물

| 준비물 | 설명 |
|---|---|
| Jetson Nano (JetPack 4) + Docker | 5V 4A 배럴잭 전원 권장(아래 "속도와 전원") |
| 컨테이너 이미지 | ultralytics Jetson 이미지(Python 3.8, torch 1.11, TensorRT 8.2)에 `fastapi`·`uvicorn`·소리 플러그인이 들어간 것. 새 컨테이너에는 이것들이 없어서, 동작하는 컨테이너를 `docker commit`으로 이미지로 저장해 쓴다 |
| TensorRT 엔진(`.engine`) | Jetson에서 변환. **입력 크기(480/640)를 만든 것과 같게** 쓴다 |
| `calibration.json` | 거리 기준값(발 위치/화면 높이: 5.5m=0.308, 3m=0.428, 2m=0.512, 카메라 높이 70cm) |
| `web/dist` | 웹 화면 빌드 결과. Jetson에는 노드가 없으니 PC에서 `cd web && npm run build`로 만들어 복사한다 |
| 스피커 | 블루투스, USB, HDMI 중 하나(아래 "소리") |

## 폴더 배치 (`REPO` = 이 레포를 받아 둔 Jetson의 폴더)

```
REPO/
  deploy/                 run_container.sh, start_all.sh
  web/dist/index.html     웹 화면(PC에서 빌드해 복사)
  data/runner/config.json         runner 설정(선택, 아래 "config.json")
  data/runner/calibration.json    거리 기준값
  data/demo_cut.mp4       카메라가 없을 때 쓰는 영상(선택)
  models/xxx.engine       TensorRT 엔진
```

`REPO`는 컨테이너 안에서 `/workspace`로 보인다. `config.json`의 경로는 **컨테이너 안 경로**(`/workspace/...`)로 적는다. `data/`와 영상은 git에 올라가지 않으므로 직접 복사한다.

## 실행

```bash
git switch main && git pull
NAME=alaska_auto IMGSZ=480 ALASKA_AUDIO_DEVICE=pulse PULSE_SERVER=tcp:172.17.0.1:4713 \
  IMAGE=<이미지 이름> REPO=<레포 경로> bash deploy/run_container.sh
docker logs -f alaska_auto
```

로그에서 확인할 것: `거리 기준값: ...`, `모델을 올리는 중이다(...)`, 그 뒤 **"준비 완료" 소리**(올라가는 세 음). 이어서 노트북 브라우저에서 `http://<Jetson IP>:8000`을 연다. 녹화·시연용 화면은 `http://<Jetson IP>:8000/?view=demo`.

## 환경변수

`run_container.sh`가 받아서 컨테이너로 넘기고, 컨테이너 안에서 `start_all.sh`가 읽는다.

| 변수 | 기본값 | 설명 |
|---|---|---|
| `IMAGE` | (필수) | 컨테이너 이미지 이름 |
| `REPO` | (필수) | 레포 폴더. 컨테이너 안 `/workspace`로 연결 |
| `NAME` | `alaska_auto` | 컨테이너 이름. **같은 이름이 있으면 지우고 새로 만든다.** 작업용 컨테이너 이름과 겹치지 않게 한다 |
| `SOUND` | `1` | `1`이고 `/dev/snd`가 있으면 소리 장치를 컨테이너에 연결 |
| `ALASKA_AUDIO_DEVICE` | (비움) | 소리를 낼 ALSA 장치. 블루투스를 PulseAudio로 보낼 때는 `pulse`. 비우면 기본 장치 |
| `PULSE_SERVER` | (비움) | 본체 PulseAudio 주소(예: `tcp:172.17.0.1:4713`). 컨테이너 소리를 본체로 보낼 때 |
| `IMGSZ` | (비움 = 640) | 감지 입력 크기. TensorRT 엔진을 만든 크기와 같게(480/640) |
| `CAMERA` | `/dev/video0` | 카메라 장치. **없으면 연결하지 않는다**(없는 장치를 주면 컨테이너가 안 만들어진다) |
| `SOURCE` | `0` | runner 입력(카메라 번호, 영상 파일, `rtsp://` 주소). `config.json`이 있으면 그 값이 우선 |
| `MODEL` | `yolo11n.pt` | 감지 모델(`.pt` 또는 `.engine`). `config.json`이 있으면 그 값이 우선 |
| `PYTHON` | `python3` | 파이썬 실행 파일 |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | server가 열리는 주소. 로그인이 없으니 신뢰하는 네트워크에서만 |
| `RUNNER_DIR` | `data/runner` | runner와 server가 파일로 주고받는 폴더 |
| `CALIBRATION` | `<RUNNER_DIR>/calibration.json` | 거리 기준값 파일. 있으면 runner에 `--calibration`으로 넘긴다 |
| `ALASKA_TOKEN` | (비움) | 정하면 설정을 바꾸는 요청에 `X-Token` 헤더가 필요하다 |

## config.json (`data/runner/config.json`)

이 파일이 있으면 `start_all.sh`는 입력·모델·설정을 **파일에서** 읽는다(`SOURCE`, `MODEL`은 무시). `IMGSZ`는 그대로 `--imgsz`로 덧붙는다. 거리 기준값은 파일에 `calibration` 문자열이 없으면 `calibration.json`을 자동으로 넘긴다.

```json
{
  "source": "/workspace/data/demo_cut.mp4",
  "model": "/workspace/models/check_n_480.engine",
  "imgsz": 480,
  "min_conf": 0.35,
  "device": "0",
  "calibration": "data/runner/calibration.json",
  "realtime": true
}
```

- `min_conf 0.35`: 사람 신뢰도 기준. 학습 없이 오경보가 크게 준다(기존 n 모델 기준 빈 구간 오경보 13.3초 → 4.1초, 경보 놓침 그대로 0). 정답용 영상 하나에서 고른 값이다.
- 모든 키와 의미는 `runner/README.md`, `runner/config.py`를 본다. 모르는 키는 시작할 때 거절한다.

## 카메라가 없을 때, 영상으로 돌리기

- 카메라 장치(`/dev/video0`)가 없으면 컨테이너에 연결하지 않는다. `config.json`의 `source`(또는 `SOURCE`)에 영상 파일을 준다.
- `realtime: true`는 영상 시간에 맞춰 프레임을 건너뛰며 재생한다(시연용). `false`면 모든 프레임을 처리해서 영상이 더 느리게 돈다(평가용).
- **엔진 로딩**: Ultralytics는 `.engine`을 만들 때가 아니라 **첫 감지 때** 불러와서 Jetson에서 수십 초 걸린다. runner는 영상 시계가 시작되기 전에 더미 프레임으로 한 번 감지(워밍업)해 두므로, 시작 직후 "모델을 올리는 중이다" 로그가 나오고 한참 뒤 "준비 완료" 소리가 난다. (이전 버전은 이 순서가 틀려 `frames 1, dropped 1000+`로 끝났다.)
- 영상 파일은 끝나면 runner가 종료되고, 3~30초 뒤 `start_all.sh`가 자동으로 다시 켜서 처음부터 재생된다(다시 켤 때마다 모델을 다시 올린다). 바로 처음부터 재생하려면 `docker restart alaska_auto`.

## 소리

경고음은 runner가 `aplay`로 낸다(1단계 삐, 2단계 삐삐, 3단계 삐삐삐).

**블루투스 스피커(시험 완료)**: 스피커는 본체 PulseAudio에 연결하고, 컨테이너가 본체 PulseAudio(TCP)로 소리를 보낸다.
- 본체: Jetson 블루투스가 오디오(A2DP)를 끄고 있으면 켠다. PulseAudio가 TCP로 컨테이너를 받게 설정한다.
- 컨테이너: `PULSE_SERVER=tcp:<본체 주소>:4713`, `ALASKA_AUDIO_DEVICE=pulse`.
- 먼저 본체에서 확인한다: `aplay -l`, `aplay -D <장치> /usr/share/sounds/alsa/Front_Center.wav`.

**삐삐삐 중 한 음이 가끔 빠질 때**: 스피커가 쉬다 깨는 순간의 현상으로 보인다. 시도할 것: ① `/etc/pulse/default.pa`의 `module-suspend-on-idle`을 주석 처리하고 PulseAudio 재시작, ② 무음 스트림을 계속 열어 두기(`pacat --playback < /dev/zero`), ③ USB 스피커.

**HDMI·보드 오디오**: 기본 장치가 스피커가 아닐 수 있다. `ALASKA_AUDIO_DEVICE=plughw:<카드>,<장치>`로 고른다(`aplay -l`로 확인).

**알려진 한계**: 본체의 PulseAudio TCP 설정은 **재부팅하면 풀린다**. 전원을 켜고 자동 시작했을 때 소리까지 나게 하려면 본체 설정을 영구로 해야 한다(아래 "확인 상태").

## 모델 교체

**한 줄로 교체** (Jetson 본체에서, 새 `.pt`는 어디에 있어도 된다):
```bash
REPO=~/alaska-night-detect bash deploy/swap_model.sh ~/best_v13.pt            # 입력 크기 기본 640
REPO=~/alaska-night-detect IMGSZ=480 bash deploy/swap_model.sh ~/best_v13.pt  # 480 엔진으로(fps는 오르지만 자전거 정확도가 떨어진다)
REPO=~/alaska-night-detect bash deploy/swap_model.sh --rollback               # 직전 설정으로 되돌리기
DRY_RUN=1 REPO=~/alaska-night-detect bash deploy/swap_model.sh ~/best_v13.pt  # 아무것도 바꾸지 않고 할 일만 출력
```
스크립트가 하는 일: ① 컨테이너를 멈춘다(Jetson Nano는 메모리가 모자라 runner가 켜져 있으면 변환이 실패할 수 있다) → ② 클래스 순서(`person=0`, `bicycle=1`)를 확인하고 엔진을 변환한다(**10~15분**, 걸린 시간을 출력) → ③ `config.json`을 `config.json.bak_<시각>`으로 백업하고 `model`과 `imgsz`만 바꾼다 → ④ 컨테이너를 다시 켜고 `/api/status`가 `running`이 될 때까지 기다린다(최대 240초, `WAIT_S`로 바꾼다). **준비가 안 되거나 변환이 실패하면 이전 설정으로 자동으로 되돌린다.** 클래스 순서가 다르면 아무것도 바꾸지 않고 중단한다. 화면, 소리, 거리 기준값은 모델과 상관없이 그대로다.

- 새 `.pt`는 `models/<이름>_<imgsz>.pt`로 복사되고 엔진은 `models/<이름>_<imgsz>.engine`으로 생긴다. 이전 엔진 파일은 지우지 않으므로 `--rollback`이 된다.
- 교체한 뒤 확인: 소리("준비 완료"), 노트북 브라우저에서 `http://<Jetson 주소>:8000`, 위험율 막대가 움직이는지.
- **이 스크립트는 PC에서 가짜 docker로 흐름(정상·자동 되돌리기·클래스 순서 오류·엔진 없음)만 시험했다. Jetson 실기기에서는 아직 실행해 보지 않았다.** 처음에는 `DRY_RUN=1`로 단계를 확인한다.

**손으로 하려면**
1. `.pt`를 Jetson에서 TensorRT로 변환한다(입력 크기는 쓸 크기와 같게).
   ```bash
   yolo export model=models/final.pt format=engine half=True imgsz=480 workspace=2 device=0
   ```
2. `config.json`의 `"model"`을 새 엔진 경로(`/workspace/models/final.engine`)로 바꾼다. `imgsz`는 엔진을 만든 크기와 같아야 한다.
3. `docker restart alaska_auto`.
4. 이상하면 `model`을 이전 엔진 경로로 되돌리고 다시 `docker restart alaska_auto`.

클래스 순서는 `person=0`, `bicycle=1`이어야 한다. 학습한 모델이 이 순서인지 변환 전에 확인한다.

> **입력 크기는 640으로 정했다(2026-11-20).** v12를 같은 정답용 103장으로 평가했더니 480은 자전거 놓침률 0.29→0.50, 자전거 F1 64.9%→49.3%, mAP50 0.812→0.714로 나빠졌다(경보 이벤트 19/19와 빈 구간 오경보는 비슷). 발표 숫자는 모두 640 기준이다. `config.json`의 `imgsz`와 엔진 변환 크기를 둘 다 640으로 맞춘다.

## 속도와 전원 (Jetson Nano 5W, micro-USB, 측정 보고)

| 입력 크기 | 추론 | fps | 메모리 |
|---|---|---|---|
| 640 | 88.0ms | 11.4 | 3739MB |
| 480 | 60.8ms | 16.5 | 3717MB |

- 측정 중 **over-current(과전류) 알림**이 있었다. micro-USB 5V로는 모자랄 수 있어서, 가능하면 **DC 배럴잭 5V 4A**(J48 점퍼)를 쓴다. 시연 중 갑자기 느려지거나 꺼질 수 있다.

## 문제 해결

| 증상 | 확인 |
|---|---|
| 로그가 `frames 1`(또는 3), `dropped`가 수백~천 개 | 영상 시계가 엔진 로딩 중에 흘러간 것. 워밍업이 들어간 최신 `main`인지 확인(`git pull`). 임시 방편은 `"realtime": false` |
| "준비 완료" 소리가 안 남 | 모델 로딩이 끝나야 난다(수십 초). 그래도 없으면 소리 장치와 `ALASKA_AUDIO_DEVICE`, `PULSE_SERVER` 확인, 소리 시험 API(`curl -X POST http://127.0.0.1:8000/api/test-sound -H "Content-Type: application/json" -d '{"level": 3}'`, 토큰을 정했다면 `-H "X-Token: <값>"`) |
| 삐삐삐 중 한 음이 빠짐 | 위 "소리"의 스피커 절전 대처 |
| 컨테이너가 안 만들어짐 | `/dev/video0`가 없는데 연결하면 실패한다(이제는 자동으로 뺀다). `docker logs`, `docker ps -a` 확인 |
| 웹이 안 열림 | `docker ps`, `curl http://127.0.0.1:8000/api/health`, 노트북과 Jetson이 같은 네트워크인지, `web/dist/index.html`이 있는지 |
| 웹은 뜨는데 "runner 꺼짐" | `curl http://127.0.0.1:8000/api/status`, `data/runner/runner.log` 확인 |
| 거리가 틀림 | 시작 로그에 `거리 기준값: ...`이 있는지. 없으면 높이 70cm·기울기 15° 추정치를 쓰고 있다. `calibration.json` 위치 확인 |
| 설정을 바꿨는데 반영 안 됨 | `config.json` 경로와 키 이름 확인. `model`, `source`, `imgsz`, `device`는 **다시 시작해야** 반영된다(`docker restart`). `min_conf` 등은 실행 중에도 반영 |
| 기록이 안 쌓임 | server 로그, `/api/health`의 `count`, runner가 `data/runner/spool/`에 쌓고 있는지 |

## 보안과 개인정보

- server에는 **로그인이 없다.** 시연 노트북이나 Jetson 안, 신뢰하는 네트워크에서만 연다(`HOST=0.0.0.0`로 열기 전에 확인). 설정을 바꾸는 요청을 막으려면 `ALASKA_TOKEN`을 정한다.
- 캡처와 원본 프레임에는 사람 얼굴이 찍힐 수 있다. `data/`는 git에 올리지 않고, 외부 사이트에 올리기 전에는 모자이크한다(`docs/false-alarm-retraining.md`).

## 확인 상태

| 항목 | 상태 |
|---|---|
| TensorRT 엔진 변환(640·480), fps 측정 | **Jetson에서 확인** |
| 블루투스 스피커 소리(컨테이너 → 본체 PulseAudio) | **Jetson에서 확인** (한 음 누락 현상 있음) |
| runner + server 동시 실행, 기록 전송 | **Jetson에서 확인** (영상 입력, 기록 53건 전송, 오류 0) |
| 카메라 없이 영상으로 실행 | Jetson에서 확인(영상 입력) |
| 노트북 브라우저에서 Jetson 웹 화면 접속 | PC에서 확인, **Jetson 확인 전** |
| 엔진 워밍업(영상 시계) 수정 | PC에서 단위 시험, **Jetson 실기기 확인 전** |
| 전원을 껐다 켰을 때 자동 시작 | **아직 확인 안 함** |
| 재부팅 후에도 소리 설정 유지 | **아직 안 됨**(본체 설정을 영구로 해야 함) |
| 실제 카메라 입력 | Jetson에 카메라가 없어 **확인 못 함** |
