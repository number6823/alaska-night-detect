# runner — 후방 감지 실행

담당: 최수창 · 브랜치: `feat/runner`

카메라나 영상이 들어오면 **감지 → 거리 단계 → 경고음 → 기록 전송**을 한 번에 돌립니다. 서버(`server/`)가 죽어도, 소리가 안 나도, 카메라가 끊겨도 이 프로그램은 멈추지 않습니다.

## 쓰는 법

```bash
python -m runner --source demo.mp4 --realtime               # 영상 파일을 원래 속도로 (시연)
python -m runner --source 0                                  # USB 카메라
python -m runner --source rtsp://192.168.0.5:8554/live       # 네트워크 카메라, 스마트폰 카메라 앱
python -m runner --source demo.mp4 --mute --max-frames 300   # 소리 없이 시험
python -m runner --config data/runner/config.json            # 설정 파일
```

기록을 보려면 다른 창에서 `python -m server` 를 켭니다. 서버가 꺼져 있으면 기록은 `data/runner/spool/` 에 쌓였다가 서버가 켜지면 자동으로 올라갑니다.

## 입력 (`--source` 하나로 고름)
영상 파일, 카메라 번호, `rtsp://`·`http://` 주소를 같은 방식(`cv2.VideoCapture`)으로 읽습니다. 감지 이후의 코드는 입력이 무엇인지 모릅니다. 카메라나 스트림이 끊기면 다시 연결을 시도하고, 파일은 끝나면 멈춥니다.

## 거리 기준값
- `--calibration cal.json`: 거리기준 영상(5.5m·3m·2m)으로 잰 값(`alarm.levels.save_calibration` 으로 만든 것).
- 없으면 `--height-m`(기본 0.7), `--tilt-deg`(15), `--vfov-deg`(60) 로 계산한 **추정치**를 씁니다. 렌즈 화각을 가정한 값이라 실제 영상으로 보정해야 정확합니다.
- 영상 높이에 맞춰 쓰므로 기준값 파일을 만든 해상도와 달라도 됩니다.

## 경고음
1단계 삐, 2단계 삐삐, 3단계 삐삐삐. 높은 단계일수록 빨리 반복하고, **단계가 올라가는 순간은 기다리지 않고 바로** 울립니다. Windows 는 `winsound`, Linux·Jetson 은 `aplay` 를 씁니다(없으면 터미널 벨). 표준 라이브러리만 씁니다.

## 기록 전송
- 경보 단계가 올라가면 박스를 그린 캡처와 함께 바로 올립니다. 같은 단계가 계속되면 `post_interval_s`(2초)에 한 번만 올립니다.
- 올리는 일은 별도 스레드라 영상 처리를 막지 않습니다. 서버가 죽어 있으면 디스크(spool, 최대 500개)에 쌓았다가 오래된 것부터 다시 올립니다.
- 캡처에는 원본 프레임의 사람이 그대로 찍힙니다. 기록과 캡처는 이 장치와 로컬 서버 안에만 두고 밖으로 내보내지 않습니다.

## 파일 (모두 `data/runner/` 아래, 레포에 올리지 않음)
- `status.json`: 상태(`running` / `camera_lost` / `finished`), FPS, 현재 단계, 마지막 감지, 쌓인 기록 수 (1초마다)
- `preview.jpg`: 박스와 5.5m·3m·2m 거리선을 그린 최신 화면 (약 5장/초)
- `spool/`: 아직 서버에 못 올린 기록

## 시험
```bash
python -m unittest runner.test_runner runner.test_calibrate -v     # 60개 (모델·카메라·서버·스피커는 가짜로)
```
Python 3.8 과 3.11 에서 확인했습니다(Jetson 계열은 3.8).

## 느린 장치(Jetson)에서 지연이 쌓이지 않게 — 항상 최신 프레임
감지가 카메라(30fps)보다 느리면(Jetson Nano 는 6~17fps) 밀린 프레임을 하나씩 처리하다가 경고가 점점 늦어진다. 그래서
- 카메라·네트워크 스트림은 별도 스레드가 계속 읽어 두고 **가장 최근 프레임만** 처리한다.
- `--realtime` 영상 파일은 처리가 늦어진 만큼 프레임을 건너뛰어 영상 시간에 맞춘다(21초 영상을 CPU 15fps 로 돌려도 약 20초에 끝난다).
- 건너뛴 프레임 수는 `status.json`·요약의 `dropped_frames` 에 나온다. `--realtime` 이 아니면 모든 프레임을 처리한다(평가용).

## 신뢰도와 입력 크기
- `--min-conf`(기본 0.25): 사람과 자전거 공통 기준. `--min-conf-bicycle` 을 주면 **자전거만** 따로 높은 기준을 쓴다(실행 중에도 바꿀 수 있다). Jetson 시험에서 자전거 오검출이 낮은 신뢰도에 몰렸지만, 표본이 작아서(15장) 기본은 같은 기준으로 둔다.
- `--imgsz`(기본 640): TensorRT 엔진은 **만든 크기와 같게** 준다(480 엔진이면 `--imgsz 480`). Jetson Nano 5W 에서 n 엔진은 640 이 약 12fps, 480 이 약 17fps 였다.

## 거리 기준값 만들기 (거리기준 영상)
```bash
python -m runner.calibrate --video <거리기준 영상> --out data/runner/calibration.json
python -m runner.calibrate --video <영상> --out cal.json --times 3-13,18-28,33-43   # 구간을 직접 줄 때(5.5m,3m,2m, 초)
python -m runner --source <영상> --calibration data/runner/calibration.json
```
영상에서 사람의 발 위치를 시간순으로 모아 **서 있는 구간**(발 위치가 거의 안 움직이는 구간, 걷는 구간은 자동으로 빠짐)을 찾고, 앞의 세 구간을 5.5m·3m·2m 로 보고 기준값을 만든다. 순서가 안 맞거나(가까울수록 아래여야 함) 구간을 못 찾으면 이유를 보여 주고 멈춘다. 카메라 높이·기울기를 `--height-m`, `--tilt-deg` 로 알려 주면 찾은 값이 기하학적으로 말이 되는지(표시를 맞게 놓았는지) 같이 점검한다.

## 안정성
- 감지가 오류를 내도(메모리 부족 등) 루프는 죽지 않는다. 50번 연속 실패하면 이유와 함께 `error` 로 멈춘다(`status.json` 의 `errors`, `last_error`).
- 켜지고 첫 프레임을 읽으면 **"준비 완료"**(올라가는 세 음), 카메라가 끊기면 끊긴 순간 한 번 **"끊김"**(낮고 긴 두 음) 소리를 낸다. 경보음과 다르게 들리게 했다. `--mute` 면 내지 않는다.
- 화면 출력과 함께 `data/runner/runner.log` 에 기록한다(1MB 씩 3개까지 돌려 씀). 콘솔이 없는 장치에서 원인을 볼 때 쓴다.

## server 와 주고받기 (실행 중에 설정 바꾸기, 명령)
`data/runner/` 의 파일로 주고받는다. 서버가 죽어도 runner 는 계속 돈다.
- `config.json`(server 가 씀): 바뀌면 **실행 중에** 반영한다 — `min_conf`, `calibration`, `camera_height_m`, `tilt_deg`, `vfov_deg`, `window`, `need`, `post_interval_s`, `mute`. `source`·`model`·`device` 는 다시 시작해야 하고, 바뀌었다고 `status.json` 의 `restart_required` 로만 알린다.
  검사에 실패한 값은 통째로 무시하고 이전 설정을 유지한다. **명령줄로 직접 준 값은 파일보다 우선**이라 파일이 바꾸지 못한다.
- `control.json`(server 가 씀): `{"id", "cmd": "test_sound", "level"}` 새 id 만 한 번 실행한다. 시작하기 전에 남아 있던 명령은 실행하지 않는다. 결과는 `status.json` 의 `last_control`(`played` / `muted` / `bad_level`) 로 알린다.
- `python -m runner` 만 쳐도 `data/runner/config.json` 이 있으면 그 설정으로 시작한다.

## 아직 없는 것
부팅 자동 시작과 준비 완료 소리(3단계), 카메라 번호 자동 선택.
