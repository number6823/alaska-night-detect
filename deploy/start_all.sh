#!/usr/bin/env bash
# 컨테이너(또는 장치) 안에서 server 와 runner 를 같이 켜고, 하나가 죽으면 그것만 다시 켠다.
# 전원이 들어오면 Docker 가 컨테이너를 자동으로 켜고(--restart unless-stopped), 이 스크립트가 두 프로그램을 켠다.
#
# 사용: cd <레포 맨 위 폴더> && bash deploy/start_all.sh
#   환경변수(없으면 기본값):
#     PYTHON=python3                  파이썬 실행 파일
#     SOURCE=0                        runner 의 입력(카메라 번호, 영상 파일, rtsp 주소). 설정 화면이 저장한 값이 있으면 그것이 우선
#     MODEL=yolo11n.pt                감지 모델(.pt 또는 TensorRT .engine)
#     IMGSZ=                          입력 크기(480, 640 등). 엔진을 만든 크기와 같게. 비우면 640
#     HOST=0.0.0.0                    server 가 열리는 주소. 같은 와이파이의 폰이 보려면 0.0.0.0 (로그인이 없으니 신뢰하는 네트워크에서만)
#     PORT=8000
#     RUNNER_DIR=data/runner          runner 와 server 가 주고받는 폴더
#     CALIBRATION=<RUNNER_DIR>/calibration.json   실측 거리 기준값 파일(있으면 runner 에 --calibration 으로 넘긴다)
#     ALASKA_AUDIO_DEVICE=            소리 낼 ALSA 장치(예: plughw:1,0). 비우면 기본 장치
#     ALASKA_TOKEN=                   정하면 설정을 바꾸는 요청에 X-Token 이 필요하다
set -u

PYTHON="${PYTHON:-python3}"
SOURCE="${SOURCE:-0}"
MODEL="${MODEL:-yolo11n.pt}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
RUNNER_DIR="${RUNNER_DIR:-data/runner}"
mkdir -p "$RUNNER_DIR" data/server

# 설정 화면이 저장한 설정(config.json)이 있으면 입력과 모델은 그 값을 쓴다(명령줄로 주면 파일보다 우선이라 주지 않는다).
if [ -f "$RUNNER_DIR/config.json" ]; then
  RUNNER_ARGS=(--data-dir "$RUNNER_DIR")
else
  RUNNER_ARGS=(--data-dir "$RUNNER_DIR" --source "$SOURCE" --model "$MODEL")
fi

# 입력 크기: TensorRT 엔진은 만든 크기와 같게 준다(480 엔진이면 IMGSZ=480). 비워 두면 runner 기본값(640)을 쓴다.
if [ -n "${IMGSZ:-}" ]; then RUNNER_ARGS+=(--imgsz "$IMGSZ"); fi

# 실측 거리 기준값(calibration.json)이 있으면 runner 에 넘긴다. 안 넘기면 높이 70cm·기울기 15° 로 계산한 추정치를 쓴다.
# 설정 화면이 저장한 config.json 에 calibration 파일이 이미 적혀 있으면 그 값을 따른다.
CAL="${CALIBRATION:-$RUNNER_DIR/calibration.json}"
if [ -f "$CAL" ] && ! { [ -f "$RUNNER_DIR/config.json" ] && grep -Eq '"calibration"[[:space:]]*:[[:space:]]*"' "$RUNNER_DIR/config.json"; }; then
  RUNNER_ARGS+=(--calibration "$CAL")
  echo "거리 기준값: $CAL"
else
  echo "거리 기준값 파일이 없거나 설정 파일에 이미 있다 → 설정/추정치를 쓴다"
fi

supervise() {  # 이름, 명령... : 죽으면 3초 뒤에 다시 켠다. 너무 빨리 계속 죽으면 간격을 늘린다(헛돌지 않게)
  local name="$1"; shift
  local wait=3
  while true; do
    local t0; t0=$(date +%s)
    echo "[$(date +%T)] $name 시작"
    "$@"
    local code=$?
    local ran=$(( $(date +%s) - t0 ))
    if [ "$ran" -ge 60 ]; then wait=3; elif [ "$wait" -lt 30 ]; then wait=$(( wait * 2 )); fi
    echo "[$(date +%T)] $name 종료(코드 $code, ${ran}초 실행). ${wait}초 뒤 다시 시작"
    sleep "$wait"
  done
}

cleanup() { kill 0 2>/dev/null; }
trap cleanup EXIT INT TERM

supervise server "$PYTHON" -m server --host "$HOST" --port "$PORT" --runner-dir "$RUNNER_DIR" &
supervise runner "$PYTHON" -m runner "${RUNNER_ARGS[@]}" --server "http://127.0.0.1:$PORT" &
wait
