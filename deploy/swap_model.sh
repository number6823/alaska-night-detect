#!/usr/bin/env bash
# Jetson 에서 감지 모델만 갈아끼운다: .pt → TensorRT 엔진 변환 → config.json 의 model 만 교체 → 컨테이너 다시 시작 → 준비 완료 확인.
# 준비가 안 되거나 변환이 실패하면 이전 설정으로 자동으로 되돌린다. 화면·소리·거리 기준값은 모델과 상관없이 그대로다.
#
# 사용 (Jetson 본체에서, 레포 맨 위 폴더가 아니어도 된다):
#   REPO=~/alaska-night-detect bash deploy/swap_model.sh best_v13.pt            # 새 모델로 교체(입력 크기 기본 480)
#   REPO=~/alaska-night-detect IMGSZ=640 bash deploy/swap_model.sh best_v13.pt  # 640 엔진으로(정확하지만 Jetson Nano 에서는 느리다. 평가·시험용)
#   REPO=~/alaska-night-detect bash deploy/swap_model.sh --rollback             # 직전 설정으로 되돌리기
#   DRY_RUN=1 ... bash deploy/swap_model.sh best_v13.pt                          # 아무것도 바꾸지 않고 할 일만 출력
#
# 환경변수(없으면 기본값):
#   REPO     이 레포를 받아 둔 폴더(컨테이너 안 /workspace 로 연결된 폴더). 필수
#   NAME     컨테이너 이름(기본 alaska_auto)
#   IMGSZ    엔진 입력 크기(기본 480). config.json 의 imgsz 도 같이 맞춘다. Jetson Nano 가 구형·소형이라 480 으로 맞춘다(2026-11-20). v12 는 640 평가보다 480 에서 자전거 놓침률이 0.29→0.50 으로 나빠진다
#   WAIT_S   준비 완료를 기다리는 최대 시간(초, 기본 240). 엔진 로딩에 수십 초가 걸린다
#   PORT     server 포트(기본 8000)
#   DRY_RUN  1 이면 실제로 하지 않고 단계만 보여 준다
#
# 순서와 이유:
#   ① 컨테이너를 멈춘다: Jetson Nano 는 메모리가 4GB 라서 runner 가 켜져 있으면 엔진 변환이 메모리가 모자랄 수 있다.
#   ② 같은 이미지로 변환 전용 컨테이너를 잠깐 띄워 클래스 순서(person=0, bicycle=1)를 확인하고 엔진을 만든다.
#   ③ config.json 을 백업(config.json.bak_<시각>)한 뒤 model 과 imgsz 만 바꾼다. 다른 설정은 건드리지 않는다.
#   ④ 컨테이너를 다시 켜고 /api/status 가 running 이 될 때까지 기다린다. 실패하면 백업으로 되돌린다.
set -u

REPO="${REPO:-}"
NAME="${NAME:-alaska_auto}"
IMGSZ="${IMGSZ:-480}"
WAIT_S="${WAIT_S:-240}"
PORT="${PORT:-8000}"
DRY_RUN="${DRY_RUN:-0}"
[ -n "$REPO" ] || { echo "REPO 에 레포 경로를 준다. 예: REPO=~/alaska-night-detect bash deploy/swap_model.sh best_v13.pt"; exit 2; }
CFG="$REPO/data/runner/config.json"
MODELS="$REPO/models"

say() { echo "[$(date +%T)] $*"; }
run() { if [ "$DRY_RUN" = "1" ]; then echo "  (DRY_RUN) $*"; else "$@"; fi; }

latest_backup() { ls -1t "$CFG".bak_* 2>/dev/null | head -n 1; }

wait_ready() {  # running 이 되고 runner 가 켜져 있다고 나올 때까지 기다린다
  local t0=$SECONDS
  while [ $(( SECONDS - t0 )) -lt "$WAIT_S" ]; do
    if curl -s -m 3 "http://127.0.0.1:$PORT/api/status" | grep -Eq '"state"[[:space:]]*:[[:space:]]*"running"'; then
      say "준비 완료 ($(( SECONDS - t0 ))초 걸림)"; return 0
    fi
    sleep 3
  done
  return 1
}

restore_and_restart() {
  local bak; bak="$(latest_backup)"
  [ -n "$bak" ] || { say "되돌릴 백업이 없다"; return 1; }
  say "되돌린다: $bak → $CFG"
  run cp "$bak" "$CFG"
  run docker restart "$NAME" >/dev/null
  if [ "$DRY_RUN" != "1" ] && wait_ready; then say "이전 모델로 돌아왔다"; else say "되돌린 뒤에도 준비되지 않았다. docker logs $NAME 확인"; fi
}

if [ "${1:-}" = "--rollback" ]; then
  restore_and_restart; exit $?
fi

PT_SRC="${1:-}"
[ -n "$PT_SRC" ] && [ -f "$PT_SRC" ] || { echo "첫 번째 인자로 .pt 파일 경로를 준다. 예: bash deploy/swap_model.sh best_v13.pt"; exit 2; }
[ -f "$CFG" ] || { echo "$CFG 가 없다. config.json 이 있어야 모델을 바꿀 수 있다(deploy/README.md 의 config.json 절)"; exit 2; }
command -v docker >/dev/null || { echo "docker 가 없다. Jetson 본체에서 실행한다"; exit 2; }

STEM="$(basename "$PT_SRC" .pt)"
TAG="${STEM}_${IMGSZ}"
IMAGE="$(docker inspect --format '{{.Config.Image}}' "$NAME" 2>/dev/null || true)"
[ -n "$IMAGE" ] || { echo "컨테이너 $NAME 의 이미지를 못 찾았다. 먼저 deploy/run_container.sh 로 컨테이너를 만든다"; exit 2; }

say "모델 교체 시작: $PT_SRC → models/$TAG.engine (imgsz $IMGSZ, 이미지 $IMAGE)"
run mkdir -p "$MODELS"
run cp "$PT_SRC" "$MODELS/$TAG.pt"

say "① 컨테이너 $NAME 멈춤(변환 메모리 확보)"
run docker stop "$NAME" >/dev/null

DOCKER_GPU=(docker run --rm --runtime nvidia -v "$REPO":/workspace -w /workspace "$IMAGE")

say "② 클래스 순서 확인 (person=0, bicycle=1 이어야 한다)"
if [ "$DRY_RUN" != "1" ]; then
  NAMES="$("${DOCKER_GPU[@]}" python3 -c "from ultralytics import YOLO; m=YOLO('models/$TAG.pt'); print(sorted(m.names.items()))" 2>/dev/null | tail -n 1)"
  echo "  클래스: $NAMES"
  case "$NAMES" in
    *"(0, 'person'), (1, 'bicycle')"*) ;;
    *) say "클래스 순서가 다르다. 교체를 중단하고 컨테이너를 다시 켠다"; docker start "$NAME" >/dev/null; exit 3 ;;
  esac
else echo "  (DRY_RUN) 클래스 순서 확인 생략"; fi

say "② 엔진 변환 (10~15분 걸릴 수 있다)"
T0=$SECONDS
run "${DOCKER_GPU[@]}" yolo export model="models/$TAG.pt" format=engine half=True imgsz="$IMGSZ" workspace=2 device=0
if [ "$DRY_RUN" != "1" ] && [ ! -f "$MODELS/$TAG.engine" ]; then
  say "엔진이 만들어지지 않았다. 설정은 바꾸지 않고 컨테이너를 다시 켠다"; docker start "$NAME" >/dev/null; exit 4
fi
say "엔진 변환 시간: $(( SECONDS - T0 ))초"

say "③ config.json 백업 후 model·imgsz 교체"
BAK="$CFG.bak_$(date +%Y%m%d_%H%M%S)"
run cp "$CFG" "$BAK"
# config.json 을 고칠 파이썬: python3 우선, 안 되면 python (Jetson 본체는 보통 python3)
PY=""
for c in python3 python; do
  if "$c" -c "import json" >/dev/null 2>&1; then PY="$c"; break; fi
done
[ -n "$PY" ] || { say "본체에 파이썬이 없어 config.json 을 고칠 수 없다. 컨테이너를 다시 켠다"; run docker start "$NAME" >/dev/null; exit 6; }
if [ "$DRY_RUN" != "1" ]; then
  "$PY" - "$CFG" "/workspace/models/$TAG.engine" "$IMGSZ" <<'PY'
import json, sys
path, model, imgsz = sys.argv[1], sys.argv[2], int(sys.argv[3])
cfg = json.load(open(path, encoding="utf-8"))
cfg["model"], cfg["imgsz"] = model, imgsz   # 다른 키는 그대로 둔다
json.dump(cfg, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("  model =", model, "| imgsz =", imgsz)
PY
else echo "  (DRY_RUN) model=/workspace/models/$TAG.engine imgsz=$IMGSZ"; fi

say "④ 컨테이너 다시 시작 후 준비 확인 (최대 ${WAIT_S}초)"
run docker start "$NAME" >/dev/null
if [ "$DRY_RUN" = "1" ]; then say "DRY_RUN 끝. 실제로는 바뀐 것이 없다"; exit 0; fi
if wait_ready; then
  say "교체 성공: models/$TAG.engine"
  echo "  확인: 노트북 브라우저에서 http://<Jetson 주소>:$PORT , 소리(\"준비 완료\"), 되돌리기: bash deploy/swap_model.sh --rollback"
  exit 0
fi
say "준비되지 않았다(모델 로딩 실패 또는 시간 초과). 이전 설정으로 되돌린다"
restore_and_restart
exit 5
