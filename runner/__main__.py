"""python -m runner --source <영상 | 카메라 번호 | rtsp 주소> 로 감지를 시작한다.

예)
  python -m runner --source demo.mp4 --realtime                 영상 파일을 원래 속도로 재생하며 시연
  python -m runner --source 0                                    USB 카메라
  python -m runner --source rtsp://192.168.0.5:8554/live         네트워크 카메라나 스마트폰 카메라 앱
  python -m runner --source demo.mp4 --mute --max-frames 300     소리 없이 300프레임만(시험)
  python -m runner --config data/runner/config.json              설정 파일로

기록을 보려면 다른 창에서 python -m server 를 켜 둔다. 서버가 꺼져 있어도 감지와 경고음은 그대로 돌고,
기록은 data/runner/spool 에 쌓였다가 서버가 켜지면 올라간다.
"""

import argparse
import json

from .app import run
from .config import build_config, load_config_file


def main() -> None:
    p = argparse.ArgumentParser(
        prog="python -m runner",
        description="후방 감지 실행: 영상 → 감지 → 경고음 → 기록",
    )
    p.add_argument("--config", help="설정 파일(JSON). 명령줄 인자가 파일보다 우선한다")
    p.add_argument(
        "--source", help="영상 파일, 카메라 번호(0, 1...), 또는 rtsp:// http:// 주소"
    )
    p.add_argument("--model", help="YOLO 가중치(.pt) 또는 TensorRT 엔진(.engine)")
    p.add_argument(
        "--min-conf", type=float, dest="min_conf", help="이 신뢰도 미만 박스는 무시"
    )
    p.add_argument(
        "--calibration",
        help="거리 기준값 JSON(alarm.levels.save_calibration 으로 만든 것)",
    )
    p.add_argument(
        "--height-m",
        type=float,
        dest="camera_height_m",
        help="렌즈 높이(미터). 기준값 파일이 없을 때 거리 추정에 쓴다",
    )
    p.add_argument(
        "--tilt-deg", type=float, dest="tilt_deg", help="아래로 기울인 각도(도)"
    )
    p.add_argument("--vfov-deg", type=float, dest="vfov_deg", help="세로 화각(도)")
    p.add_argument(
        "--server",
        dest="server_url",
        help="기록 서버 주소 (기본 http://127.0.0.1:8000)",
    )
    p.add_argument(
        "--data-dir",
        dest="data_dir",
        help="상태·미리보기·spool 을 둘 폴더 (기본 data/runner)",
    )
    p.add_argument(
        "--max-frames",
        type=int,
        dest="max_frames",
        help="이 장수까지만 처리하고 끝낸다(시험용)",
    )
    p.add_argument(
        "--mute", action="store_true", default=None, help="경고음을 내지 않는다"
    )
    p.add_argument(
        "--realtime",
        action="store_true",
        default=None,
        help="영상 파일을 원래 속도로 재생한다",
    )
    p.add_argument(
        "--no-preview",
        action="store_true",
        default=None,
        dest="no_preview",
        help="미리보기 파일을 쓰지 않는다",
    )
    a = p.parse_args()

    cli = {k: v for k, v in vars(a).items() if k not in ("config", "no_preview")}
    if a.no_preview:
        cli["preview"] = False
    file_values = load_config_file(a.config) if a.config else {}
    cfg = build_config(file_values, cli)
    summary = run(cfg)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
