"""runner 본체. 영상 → 감지 → 경보 단계 → 경고음 → 기록 전송을 한 번에 돌린다.

모델·소리·서버는 밖에서 바꿔 끼울 수 있게 인자로 받는다(시험할 때 가짜를 넣는다).
서버가 죽어도, 소리가 안 나도, 카메라가 끊겨도 이 루프는 죽지 않는다.
"""

from __future__ import annotations

import dataclasses
import os
import time
from typing import Callable, Optional

from alarm.levels import Calibration, estimate_calibration, load_calibration

from .config import RunnerConfig
from .pipeline import LEVEL_DISTANCE_M, Pipeline
from .sound import Beeper
from .sources import VideoSource
from .spool import Reporter, Spool
from .status import StatusWriter, draw_overlay, encode_jpeg


def make_calibration(cfg: RunnerConfig, frame_height: int) -> Calibration:
    """파일이 있으면 그 기준값, 없으면 높이·기울기·화각으로 계산한 추정치. frame_height 는 실제 영상에 맞춘다."""
    if cfg.calibration:
        return dataclasses.replace(
            load_calibration(cfg.calibration), frame_height=frame_height
        )
    return estimate_calibration(
        cfg.camera_height_m, cfg.tilt_deg, cfg.vfov_deg, frame_height
    )


def run(
    cfg: RunnerConfig,
    detector=None,
    post_fn: Optional[Callable[..., dict]] = None,
    beeper: Optional[Beeper] = None,
    source: Optional[VideoSource] = None,
    log: Callable[[str], None] = print,
) -> dict:
    cfg.validate()
    src = source or VideoSource(cfg.source, realtime=cfg.realtime)
    if not src.opened:
        raise RuntimeError(f"입력을 열지 못했다: {cfg.source}")
    first = src.read()
    if first is None:
        raise RuntimeError(f"입력에서 프레임을 읽지 못했다: {cfg.source}")
    cal = make_calibration(cfg, first.shape[0])
    if detector is None:
        from .detector import Detector

        detector = Detector(cfg.model, cfg.min_conf)
    pipe = Pipeline(cal, cfg.min_conf, cfg.window, cfg.need, cfg.post_interval_s)
    own_beeper = beeper is None
    beeper = beeper or Beeper(mute=cfg.mute)
    spool = Spool(os.path.join(cfg.data_dir, "spool"))
    reporter = Reporter(cfg.server_url, spool, post_fn=post_fn)
    writer = StatusWriter(cfg.data_dir)

    frames = 0
    max_level = 0
    posts = 0
    last_detect_at = ""
    started = time.monotonic()
    state = "running"
    frame = first
    log(
        f"시작: 입력={cfg.source}, 모델={cfg.model}, 화면 높이={first.shape[0]}, 서버={cfg.server_url}"
    )
    try:
        while True:
            if frame is None:
                if src.is_file:
                    state = "finished"
                    break
                state = "camera_lost"
                writer.write_status(
                    _status(
                        state, cfg, frames, started, 0, last_detect_at, reporter, spool
                    ),
                    force=True,
                )
                time.sleep(1.0)
                if src.reopen():
                    log("카메라를 다시 연결했다")
                    state = "running"
                frame = src.read() if src.opened else None
                continue

            t0 = time.monotonic()
            boxes = detector.detect(frame)
            ms = int((time.monotonic() - t0) * 1000)
            res = pipe.process(boxes)
            beeper.update(res.alarm_level)
            frames += 1
            max_level = max(max_level, res.alarm_level)

            shown = None
            if res.should_post:
                shown = draw_overlay(frame, boxes, cal, res.alarm_level, cfg.min_conf)
                last_detect_at = time.strftime("%H:%M:%S")
                meta = {
                    "person": res.person,
                    "bicycle": res.bicycle,
                    "top": round(min(1.0, res.top), 3),
                    "ms": ms,
                    "level": res.alarm_level,
                    "dist": LEVEL_DISTANCE_M[res.alarm_level],
                    "at": last_detect_at,
                }
                reporter.submit(encode_jpeg(shown), meta)
                posts += 1
            if cfg.preview and writer.preview_due():
                shown = (
                    shown
                    if shown is not None
                    else draw_overlay(frame, boxes, cal, res.alarm_level, cfg.min_conf)
                )
                writer.write_preview(encode_jpeg(shown, 75))
            if writer.status_due():
                fps = frames / max(1e-6, time.monotonic() - started)
                writer.write_status(
                    _status(
                        state,
                        cfg,
                        frames,
                        started,
                        res.alarm_level,
                        last_detect_at,
                        reporter,
                        spool,
                        fps,
                    )
                )

            if cfg.max_frames and frames >= cfg.max_frames:
                state = "finished"
                break
            frame = src.read()
            if frame is None and src.is_file:
                state = "finished"
                break
    except KeyboardInterrupt:
        state = "stopped"
        log("사용자가 멈췄다")
    finally:
        elapsed = time.monotonic() - started
        writer.write_status(
            _status(
                state,
                cfg,
                frames,
                started,
                0,
                last_detect_at,
                reporter,
                spool,
                frames / max(1e-6, elapsed),
            ),
            force=True,
        )
        reporter.close()
        if own_beeper:
            beeper.close()
        src.release()
    summary = {
        "state": state,
        "frames": frames,
        "seconds": round(elapsed, 2),
        "fps": round(frames / max(1e-6, elapsed), 2),
        "max_alarm_level": max_level,
        "posts_submitted": posts,
        "posted_ok": reporter.sent,
        "post_failed": reporter.failed,
        "spooled_left": spool.count(),
        "beeps": len(beeper.played),
    }
    log(f"끝: {summary}")
    return summary


def _status(
    state, cfg, frames, started, level, last_detect_at, reporter, spool, fps=0.0
) -> dict:
    return {
        "state": state,  # running / camera_lost / finished / stopped
        "source": cfg.source,
        "frames": frames,
        "fps": round(fps, 1),
        "alarm_level": level,
        "last_detection_at": last_detect_at,
        "posted_ok": reporter.sent,
        "spooled": spool.count(),
        "pid": os.getpid(),
        "uptime_s": round(time.monotonic() - started, 1),
    }
