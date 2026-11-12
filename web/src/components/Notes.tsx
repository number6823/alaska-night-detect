interface Props {
  live: boolean;
  onToggleTheme: () => void;
}

export default function Notes({ live, onToggleTheme }: Props) {
  return (
    <div className="note">
      <strong>프로토타입입니다.</strong>{" "}
      {live
        ? "서버에서 받은 기록을 보여 주고 있습니다."
        : "서버가 없어 예시 기록을 보여 주고 있습니다. 사진과 박스는 진짜입니다 — Wikimedia Commons 야간 사진을 우리가 학습시킨 모델로 돌린 실제 결과이고, 신뢰도와 박스 수도 그 출력 그대로입니다. 시각·추정 거리·경고 단계는 화면을 보여 주려고 지어냈습니다."}
      <ul>
        <li>
          <strong>경고 단계</strong>는 주차 센서 방식입니다 — 1단계 약 5.5m(삐), 2단계 약 3m(삐삐),
          3단계 약 2m(삐삐삐). 거리는 사람 발 위치(박스 아래 끝)로 추정하며, 카메라 높이 1m 고정과
          평탄한 바닥을 가정한 근사치입니다. 기준값은 <code>거리기준</code> 클립에서 재서 정합니다.
        </li>
        <li>
          Jetson이 캡처 JPEG와 감지 정보를 <code>POST /api/detections</code>로 보내고,
          이 화면이 <code>GET /api/detections</code>로 읽습니다. 서버가 없으면 예시 기록으로 넘어갑니다.
        </li>
        <li>
          오경보 표시를 서버에 남기려면 <code>PATCH /api/detections/&lt;id&gt;</code>가 필요합니다.
        </li>
        <li>
          후방 카메라 영상은 아직 촬영 전이라 길거리 야간 사진으로 대신했습니다.
          화각이 다르니 R1·R2 프레임이 나오면 교체합니다.
        </li>
      </ul>
      <button type="button" className="theme" onClick={onToggleTheme}>밝게 / 어둡게</button>
    </div>
  );
}
