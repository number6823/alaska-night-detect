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
import os

from .app import run
from .config import build_config, load_config_file


def make_logger(data_dir: str):
    """화면에 찍고, 파일(data_dir/runner.log, 1MB 씩 3개까지 돌려 씀)에도 남긴다. 콘솔 없는 장치에서 원인을 보려고."""
    import logging
    from logging.handlers import RotatingFileHandler

    os.makedirs(data_dir, exist_ok=True)
    logger = logging.getLogger("runner")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fh = RotatingFileHandler(
            os.path.join(data_dir, "runner.log"),
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        fh.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%m-%d %H:%M:%S"))
        logger.addHandler(fh)

    def log(message: str) -> None:
        print(message)
        logger.info(message)

    return log


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
    p.add_argument("--imgsz", type=int, help="감지 입력 크기(기본 480, 640...). TensorRT 엔진은 만든 크기 그대로")
    p.add_argument(
        "--min-conf-bicycle",
        type=float,
        dest="min_conf_bicycle",
        help="자전거만 따로 쓰는 신뢰도 기준(비우면 --min-conf 와 같다)",
    )
    p.add_argument("--device", help='감지 장치. 빈 값=GPU 가 되면 GPU 아니면 CPU, "0"=첫 GPU, "cpu"=CPU 강제')
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
    # 설정 파일: --config 로 준 것, 없으면 data_dir 의 config.json (server 설정 화면이 저장하는 곳)
    data_dir = cli.get("data_dir") or "data/runner"
    config_path = a.config
    if not config_path:
        default = os.path.join(data_dir, "config.json")
        config_path = default if os.path.isfile(default) else None
    file_values = load_config_file(config_path) if config_path else {}
    # server 가 config.json 을 고치면 실행 중에 반영한다. 명령줄로 직접 준 값은 파일보다 우선이라 그대로 둔다
    cli_keys = {k for k, v in cli.items() if v is not None}
    cfg = build_config(file_values, cli)
    if not config_path:
        config_path = os.path.join(data_dir, "config.json")  # 나중에 만들어져도 읽을 수 있게
    summary = run(
        cfg, config_path=config_path, cli_keys=cli_keys, log=make_logger(cfg.data_dir)
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
