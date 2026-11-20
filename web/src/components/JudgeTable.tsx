// 오경보 판단 기준 한 장. 기록표 옆 "무엇을 오경보로 표시하나요?"에 쓰고, 관리자 매뉴얼은 이 표를 참고하라고 안내만 한다(근거: docs/false-alarm-retraining.md).
const ROWS = [
  { mark: true, label: "오경보로 표시", text: "사람·자전거가 없는데 박스가 있음 (나무, 가로등, 차 불빛, 기둥)" },
  { mark: false, label: "표시 안 함", text: "사람이 있고 박스가 맞음 (신뢰도가 낮아도 정상 경보)" },
  { mark: false, label: "표시 안 함", text: "사람은 있는데 엉뚱한 곳에 박스가 하나 더 (빈 라벨이 사람을 “없다”고 가르침)" },
  { mark: false, label: "표시 안 함", text: "자전거 탄 사람인데 사람만 잡힘 (오경보가 아니라 미탐)" },
];

export const JUDGE_TIP = "박스는 모델의 예측입니다. 신뢰도 숫자가 아니라 사진을 보고 판단하고, 애매하면 표시하지 마세요.";

export default function JudgeTable() {
  return (
    <table className="guide-table">
      <tbody>
        {ROWS.map((r) => (
          <tr key={r.text}>
            <td className={r.mark ? "judge-yes" : undefined}><b>{r.label}</b></td>
            <td>{r.text}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
