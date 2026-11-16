#!/usr/bin/env bash
# Jetson 에서 컨테이너를 만들어 server 와 runner 를 자동으로 켠다. 전원을 켜면 Docker 가 이 컨테이너를 다시 켠다.
#
# 사용: IMAGE=<이미지 이름> REPO=<레포 경로> bash deploy/run_container.sh
#   IMAGE  민철님이 만든 컨테이너 이미지(ultralytics 와 GPU 가 되는 것)
#   REPO   이 레포를 받아 둔 폴더(컨테이너 안 /workspace 로 연결된다)
#   SOUND  스피커 장치를 컨테이너에 연결할지(기본 1). 소리가 안 나면 호스트의 `aplay -l` 로 장치를 확인한다
#
# 주의: 이 스크립트는 Jetson 에서 아직 시험하지 못했다. 이미지의 파이썬 버전, GPU 실행 옵션(--runtime nvidia),
#       오디오 장치 이름이 장치마다 다를 수 있어서 처음에는 한 줄씩 확인하면서 쓴다.
set -eu
: "${IMAGE:?IMAGE 에 컨테이너 이미지 이름을 준다}"
: "${REPO:?REPO 에 레포 경로를 준다}"
NAME="${NAME:-alaska}"
SOUND="${SOUND:-1}"

AUDIO_ARGS=()
if [ "$SOUND" = "1" ] && [ -d /dev/snd ]; then AUDIO_ARGS=(--device /dev/snd); fi

docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" \
  --restart unless-stopped \
  --runtime nvidia \
  --network host \
  "${AUDIO_ARGS[@]}" \
  --device /dev/video0 \
  -v "$REPO":/workspace \
  -w /workspace \
  -e PYTHON="${PYTHON:-python3}" -e SOURCE="${SOURCE:-0}" -e MODEL="${MODEL:-yolo11n.pt}" -e ALASKA_TOKEN="${ALASKA_TOKEN:-}" \
  "$IMAGE" \
  bash deploy/start_all.sh
echo "시작했다. 로그: docker logs -f $NAME   (runner 로그 파일: $REPO/data/runner/runner.log)"
echo "폰에서 접속: http://<장치 주소>:8000"
