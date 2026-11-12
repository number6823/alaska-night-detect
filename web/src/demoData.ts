// 서버가 없을 때 쓰는 예시 기록.
// 사진·박스·신뢰도는 학습한 모델(best.pt)을 Wikimedia 야간 사진에 돌린 실제 출력이고,
// 시각·추정 거리·경고 단계는 화면을 보여 주려고 지어낸 값이다.
import type { Detection } from "./types.ts";

export const DEMO: Detection[] = [
  {
    id: "CAP-118", shot: "shots/shot1.jpg", at: "21:48:12",
    person: 4, bicycle: 1, top: 0.93, ms: 24, level: 2, dist: 3.1,
    credit: { author: "sookie from Vancouver, Canada", license: "CC BY 2.0",
      url: "https://commons.wikimedia.org/wiki/File:College_street_cyclist_(2042294662).jpg" },
  },
  {
    id: "CAP-117", shot: "shots/shot4.jpg", at: "21:46:50",
    person: 2, bicycle: 1, top: 0.97, ms: 23, level: 3, dist: 1.9,
    credit: { author: "Matt Harrop", license: "CC BY-SA 2.0",
      url: "https://commons.wikimedia.org/wiki/File:Delivery_cyclist,_Liverpool_-_geograph.org.uk_-_5599517.jpg" },
  },
  {
    id: "CAP-116", shot: "shots/shot5.jpg", at: "21:41:08",
    person: 11, bicycle: 15, top: 0.98, ms: 27, level: 1, dist: 5.3,
    credit: { author: "David Lally", license: "CC BY-SA 2.0",
      url: "https://commons.wikimedia.org/wiki/File:Cyclists_gather_-_geograph.org.uk_-_4236069.jpg" },
  },
  {
    id: "CAP-115", shot: "shots/shot2.jpg", at: "21:38:31",
    person: 5, bicycle: 13, top: 0.92, ms: 26, level: 1, dist: 5.6,
    credit: { author: "Stephen Craven", license: "CC BY-SA 2.0",
      url: "https://commons.wikimedia.org/wiki/File:Night_Riders_in_Greenwich_-_geograph.org.uk_-_1928526.jpg" },
  },
  {
    id: "CAP-114", shot: "shots/shot3.jpg", at: "21:35:02",
    person: 1, bicycle: 1, top: 0.98, ms: 22, level: 2, dist: 2.8,
    credit: { author: "Melic", license: "CC BY-SA 3.0",
      url: "https://commons.wikimedia.org/wiki/File:Night_Biking-7_Arshak_Ulubabyan.jpg" },
  },
  {
    id: "CAP-113", shot: "shots/shot6.jpg", at: "21:30:44",
    person: 2, bicycle: 0, top: 0.41, ms: 25, level: 1, dist: 5.9,
    credit: { author: "*angys*", license: "CC BY-SA 4.0",
      url: "https://commons.wikimedia.org/wiki/File:Sunway_Lagoon_Pedestrian_Walkway_at_night_(220711).jpg" },
  },
  {
    id: "CAP-112", shot: "shots/shot7.jpg", at: "21:22:55",
    person: 0, bicycle: 0, top: 0, ms: 21, level: 0, dist: 0,
    credit: { author: "KartikMistry", license: "CC BY-SA 4.0",
      url: "https://commons.wikimedia.org/wiki/File:Atal_Pedestrian_Bridge_at_Night.jpg" },
  },
];
