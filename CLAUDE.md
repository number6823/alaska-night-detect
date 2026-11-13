# alaska-night-detect

팀 알래스카 알아서해스카(강민철, 변성진, 최수창)의 야간 보행자·자전거 감지 프로젝트.
미니 프로젝트(도구 2개 + 훅·에이전트)를 먼저 만들고, 같은 레포에서 최종 프로젝트(학습, 웹)로 이어 간다.

## 담당과 폴더
- A 강민철: collector/ (도구 1 자동 수집·정리)
- B 변성진: labeler/ (도구 2 자동 라벨링), 깃 관리자
- C 최수창: agent/ (훅·에이전트, 도구 연결), 팀장
- web/ (감지 화면, 서버 연결·배포): 변성진
- alarm/ (거리 단계 경고, 연속 프레임 경보 규칙): 최수창. 함수 단위로 만들어 web/·agent/·Jetson이 부른다
- 자기 폴더만 고친다. 다른 폴더를 고쳐야 하면 먼저 담당자에게 말한다.
- data/ 는 결과물 폴더이며 git에 올리지 않는다.

## 일정
- 미니 개발 마감 11/6, 정리 11/7, 리허설 11/8, 발표 11/9
- 최종 프로젝트 11/10 시작, 중간 발표 11/13, 최종 발표 11/27

## 브랜치와 커밋
- main에 직접 푸시하지 않는다. 브랜치(feat/collector, feat/labeler, feat/agent)에서 작업하고 PR로 올린다.
- 작업 전에 git switch main 다음 git pull
- 커밋 말머리: feat(기능), fix(버그), docs(문서), style(서식), refactor(구조)
- 커밋은 한 줄로, 무엇을 왜 바꿨는지 알 수 있게 쓴다.
- PR은 올린 사람이 아닌 다른 사람이 승인한다.

## 기술과 규칙
- 비용 0원: 오픈소스와 무료 API만 쓴다. 유료 API는 쓰지 않는다.
- 말 해석은 규칙 기반 키워드 사전으로 한다. (예: 야간→night, 자전거→bicycle)
- 사용 기술: Python, Ultralytics YOLO, OpenCV, imagehash, CLIP(open-clip), 사진 사이트 API
- 클래스는 person=0, bicycle=1 만 쓴다. 킥보드는 다루지 않는다.
- 수집은 라이선스를 확인할 수 있는 곳(Wikimedia Commons, Unsplash Lite)만 쓴다. Flickr(API 유료)와 Pexels(키 발급 중단)는 쓰지 않는다.
- Unsplash Lite 데이터셋의 사진과 metadata.csv의 Unsplash 줄(설명·작가 이름 포함)은 발표·웹·레포·카톡에 공개하지 않고 data\ 밖으로 내보내지 않는다. 파일로 주고받지도 않는다(각자 내려받는다). 발표와 웹 예시 사진은 Wikimedia 사진만 쓴다.
- 2026-11-02 Unsplash에서 교육용 허락을 받았다("Your use case is acceptable; we support all educational use cases."). Unsplash Lite 사진을 최종 프로젝트 학습에 쓸 수 있다. 위의 공개 금지 규칙은 그대로다. 이 허락은 메일에 적은 비상업 교육 용도 기준이다. 상업 이용 등 메일에 적지 않은 용도는 다시 문의한다.
- 도구는 최종 프로젝트의 웹 서버가 부를 수 있게 함수 단위로 만든다.

## 비밀값과 올리지 않을 것
- 레포가 공개다. API 키는 .env 에만 넣고 올리지 않는다. 키가 올라가면 기록에 남으므로 즉시 키를 폐기하고 새로 받는다.
- 영상, 이미지, 모델 파일(*.pt)은 올리지 않는다.

## 실행 방법
모든 명령은 레포 맨 위 폴더에서 실행한다. 레포 경로가 너무 길면 설치가 실패하니 짧은 경로에 둔다.

- 도구 1 (collector)
  - 설치: `pip install -r collector/requirements.txt`
  - 실행: `python -c "from collector import run_collector; print(run_collector(['night bicycle']))"`
  - 결과: `data/images`(남은 사진), `data/removed`(걸러진 사진), `data/metadata.csv`(출처·제거 사유)
  - 처음 실행 때 CLIP 가중치 약 578MB를 받으므로 인터넷이 필요하다.
  - Unsplash Lite는 약관을 읽고 각자 https://unsplash.com/data/lite/latest 에서 zip을 받아 `data/unsplash_lite`에 푼다. 없으면 Wikimedia만 쓰고 `[건너뜀]`이 나온다.
- 도구 2 (labeler)
  - 설치: `pip install -r labeler/requirements.txt`
  - 실행: `python -m labeler run` (`data/images`를 읽는다. 처음 실행 때 `yolo11n.pt`를 자동으로 받는다.)
  - 결과: 라벨은 `data/labels/*.txt`, 검수·폐기 목록은 `data/review_queue.csv`
- 에이전트 (agent): 위 두 도구를 설치한 뒤 `python -m agent.agent "야간 자전거 수집해줘"`. 검색어를 보여 주면 y/n으로 승인하고, 끝나면 수집·라벨·폐기 장수를 보고한다.
