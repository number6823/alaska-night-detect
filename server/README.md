# server — 후방 감지 기록 서버

담당: 최수창 · 브랜치: `feat/server`

Jetson 이 올린 감지 캡처와 기록을 모아 두고, `web/` 화면이 읽어 가게 하는 서버입니다. 경고음은 Jetson 이 직접 울리고, 서버가 죽어도 경보는 멈추지 않습니다.

## 쓰는 법

```bash
pip install -r server/requirements.txt
python -m server                      # http://127.0.0.1:8000
python -m server --host 0.0.0.0       # 같은 네트워크의 Jetson 이 올릴 때
```

- 기록은 `data/server/detections.db`, 캡처는 `data/server/shots/` 에 쌓입니다(레포에 올리지 않습니다).
- `web/dist` 가 있으면 같은 주소에서 화면도 열립니다. 개발 중에는 `web/` 에서 `npm run dev` 를 하면 `/api` 요청이 이 서버(8000)로 넘어갑니다.
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

## 시험

```bash
pip install httpx
python -m unittest server.test_app -v      # 14개
```
