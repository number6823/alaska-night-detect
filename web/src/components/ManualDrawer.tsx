import { useEffect, useRef } from "react";

interface Props {
  onClose: () => void;
}

// 신입 관리자 매뉴얼. 다른 페이지로 가지 않고 관리자 화면 오른쪽에 겹쳐 열리는 짧은 요약이다.
// 명령어와 자세한 근거는 docs/false-alarm-retraining.md 에 있다.
export default function ManualDrawer({ onClose }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <aside className="drawer" role="dialog" aria-label="신입 관리자 매뉴얼">
      <header>
        <h2>신입 관리자 매뉴얼</h2>
        <button type="button" className="top-btn" ref={closeRef} onClick={onClose}>닫기 ✕</button>
      </header>
      <div className="drawer-body">
        <h3>하는 일</h3>
        <ol>
          <li><b>확인</b> — 감지 기록 줄을 누르면 왼쪽 감지 캡처가 바뀝니다.</li>
          <li><b>표시</b> — 잘못 울린 것만 “오경보로 표시”를 누릅니다.</li>
          <li><b>내보내기</b> — 표시한 기록을 zip으로 받아 재학습 담당에게 넘깁니다.</li>
        </ol>

        <p className="drawer-tip">오경보 판단 기준은 감지 기록의 <b>“무엇을 오경보로 표시하나요?”</b>를 참고하세요.</p>

        <h3>매일 점검</h3>
        <ol>
          <li>맨 위가 “Jetson 연결됨”인지 봅니다. “예시 기록”이면 연결부터 확인합니다.</li>
          <li>필터 <b>신뢰도 0.7 미만</b>으로 의심 후보부터 봅니다(낮아도 사람이면 정상).</li>
          <li>줄 클릭 → 사진 확인 → 오경보만 표시. 잘못 눌렀으면 “표시 취소”.</li>
          <li>필터 <b>전체</b>에서 삐삐삐(2m) 기록도 확인합니다.</li>
          <li>표시가 20~50장 모이면 <b>내보내기 (zip)</b>.</li>
          <li>받은 <b>zip 파일은 그대로 재학습 담당자에게 넘깁니다.</b> 사진에 얼굴이 찍혀 있으니 직접 외부에 올리지 않습니다.</li>
        </ol>
        <p className="drawer-warn">표시하지 않은 기록은 1000건을 넘으면 오래된 것부터 자동 삭제됩니다.</p>

        <h3>재학습 (담당자)</h3>
        <p className="drawer-tip">관리자가 넘긴 zip 파일을 받아서 아래 순서로 합니다.</p>
        <ol>
          <li><b>얼굴 모자이크</b>(필수) — 원본은 외부에 올리지 않습니다.</li>
          <li>Roboflow에 <b>이미지만</b> 업로드(라벨 txt는 올리지 않음).</li>
          <li><b>Mark Null</b>(빈 프레임)로 처리해 Dataset에 넣기.</li>
          <li>새 Version은 이전과 같게(클래스 정리, Auto-Orient만, 증강 없음).</li>
          <li>같은 설정으로 학습(yolo11n, 480, 100 epochs).</li>
          <li>효과 확인 — 빈 구간 오경보 시간이 줄었는지, 경보 놓침이 0인지.</li>
        </ol>
        <p className="drawer-tip">명령과 자세한 순서: <code>docs/false-alarm-retraining.md</code></p>

        <h3>하지 말 것</h3>
        <ul>
          <li>사람이 있는 기록에 표시하지 않기</li>
          <li>모자이크 없이 외부에 올리지 않기</li>
          <li>시연·평가 영상의 오경보를 학습에 넣고 같은 영상으로 평가하지 않기(점수가 거짓으로 좋아짐)</li>
          <li>사진·영상을 GitHub에 올리지 않기</li>
        </ul>
        <p className="drawer-tip">반자동 절차이고, 아직 한 바퀴를 끝까지 돌려 보지는 않았습니다.</p>
      </div>
    </aside>
  );
}
