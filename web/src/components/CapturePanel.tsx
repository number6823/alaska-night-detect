import { BEEP } from "../kinds.ts";
import type { Detection } from "../types.ts";

interface Props {
  rec: Detection | null;
}

export default function CapturePanel({ rec }: Props) {
  if (!rec) {
    return (
      <section className="panel">
        <header><h2>감지 캡처</h2></header>
        <div className="capture"><div className="frame"><div className="empty">기록이 없습니다</div></div></div>
      </section>
    );
  }

  return (
    <section className="panel">
      <header>
        <h2>감지 캡처</h2>
        <span className="sub">{rec.id}</span>
      </header>
      <div className="capture">
        <div className="frame">
          {rec.shot ? (
            <img src={rec.shot} alt="감지 박스가 그려진 야간 캡처" />
          ) : (
            <div className="empty">캡처 없음</div>
          )}
          {rec.level > 0 && (
            <span className="beep" data-level={rec.level}>
              {BEEP[rec.level as 1 | 2 | 3]}&nbsp;&nbsp;단계 {rec.level}
            </span>
          )}
          <span className="stamp">{rec.at}</span>
        </div>

        <div className="meta">
          <span>사람 <b>{rec.person}</b></span>
          <span>자전거 <b>{rec.bicycle}</b></span>
          <span>최고 신뢰도 <b>{rec.top ? rec.top.toFixed(2) : "—"}</b></span>
          <span>추정 거리 <b>{rec.dist ? `약 ${rec.dist.toFixed(1)}m` : "—"}</b></span>
          <span>처리 <b>{rec.ms}ms</b></span>
        </div>

        {rec.credit && (
          <div className="credit">
            사진: <a href={rec.credit.url} target="_blank" rel="noopener noreferrer">Wikimedia Commons</a>
            {" · "}{rec.credit.author}{" · "}{rec.credit.license}
          </div>
        )}
      </div>
    </section>
  );
}
