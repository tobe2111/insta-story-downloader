/**
 * 트랙 페이지 실시간 평가 계산을 **실행해서** 검사한다
 * (docs/assets/track-live.js의 markLive — 순수 계산부).
 *
 * 문자열 검사는 코드가 있다는 것만 말한다 — 돈이 걸린 식은 값으로 확인한다
 * (live_marks_check.mjs와 같은 이유, 감사 229).
 *
 * 실행: node tests/track_live_check.mjs   (실패 시 종료코드 1)
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(join(here, "..", "docs", "assets", "track-live.js"),
                         "utf8");
// IIFE가 globalThis에 TrackLive를 단다 — 브라우저와 같은 방식으로 싣는다.
new Function(src)();
const { markLive, signedQty, equityFromCash } = globalThis.TrackLive;

let failed = 0;
function check(name, cond, got) {
  if (cond) return;
  failed += 1;
  console.error("✗ " + name + " — got: " + JSON.stringify(got));
}
function close(a, b) { return Math.abs(a - b) < 1e-9; }

// ① 롱 — 오르면 번다. 자산 = 확정 + 수량×(지금−확정가).
{
  const m = markLive(100, [{ symbol: "A/USDT", quantity: 2, last_price: 10,
                             avg_cost: 8 }], { "A/USDT": 12 });
  check("롱 자산 재평가", close(m.equityLive, 104), m);
  check("롱 델타", close(m.delta, 4), m);
  check("롱 줄 평가액", close(m.rows["A/USDT"].value, 24), m);
  check("롱 줄 손익(평단 대비)", close(m.rows["A/USDT"].pnl, 8), m);
}

// ② 숏 — 오르면 잃는다. 부호가 방향을 담아야 선물 페이지가 안 틀린다.
{
  const m = markLive(100, [{ symbol: "B/USDT", direction: "short",
                             quantity: 3, last_price: 10, avg_cost: 10 }],
                     { "B/USDT": 12 });
  check("숏은 오르면 잃는다", close(m.equityLive, 94), m);
  check("숏 줄 손익 음수", close(m.rows["B/USDT"].pnl, -6), m);
  const d = markLive(100, [{ symbol: "B/USDT", direction: "short",
                             quantity: 3, last_price: 10 }], { "B/USDT": 7 });
  check("숏은 내리면 번다", close(d.equityLive, 109), d);
}

// ③ 일부만 받았으면 합계를 지어내지 않는다 — 이름을 말한다.
{
  const m = markLive(100,
    [{ symbol: "A/USDT", quantity: 1, last_price: 10 },
     { symbol: "C/USDT", quantity: 1, last_price: 10 }],
    { "A/USDT": 11 });
  check("부분 수신이면 합계 null", m.equityLive === null, m);
  check("못 받은 종목 이름", m.missing.length === 1
        && m.missing[0] === "C/USDT", m);
}

// ④ 확정가가 없거나 0이면 그 줄은 '잴 수 없음'이다 — 0으로 때우지 않는다.
{
  const m = markLive(100, [{ symbol: "A/USDT", quantity: 1, last_price: 0 }],
                     { "A/USDT": 11 });
  check("확정가 0은 잴 수 없음", m.equityLive === null
        && m.missing[0] === "A/USDT", m);
}

// ⑤ 평단이 없으면 줄 손익은 null — 자산 델타는 그대로 성립한다.
{
  const m = markLive(100, [{ symbol: "A/USDT", quantity: 2, last_price: 10 }],
                     { "A/USDT": 12 });
  check("평단 없음 → 손익 null", m.rows["A/USDT"].pnl === null, m);
  check("평단 없어도 자산은 잰다", close(m.equityLive, 104), m);
}

// ⑥ 부호 수량 자체.
check("signedQty 롱", signedQty({ quantity: 2 }) === 2, null);
check("signedQty 숏", signedQty({ direction: "short", quantity: 2 }) === -2,
      null);
check("signedQty 숏 음수 입력도 음수로",
      signedQty({ direction: "short", quantity: -2 }) === -2, null);

// ⑦ 조종석(프로그램)용 — 현금 + Σ수량×지금가.
{
  const m = equityFromCash(50, [{ symbol: "BTC/USDT", quantity: 0.5,
                                  avg_price: 100 }], { "BTC/USDT": 120 });
  check("현금+보유 절대값", close(m.equityLive, 110), m);
  check("줄 손익(평단 대비)", close(m.rows["BTC/USDT"].pnl, 10), m);
}

// ⑧ 현금을 모르면 null + 사유 — Number(null)===0이라 가드를 지우면
//    '모름'이 '빈 지갑'으로 둔갑한다.
{
  const m = equityFromCash(null, [{ symbol: "A/USDT", quantity: 1 }],
                           { "A/USDT": 10 });
  check("현금 모름 → null", m.equityLive === null && m.reason === "현금 미기록",
        m);
}

// ⑨ 시세를 못 받은 종목이 있으면 합계를 지어내지 않는다.
{
  const m = equityFromCash(50, [{ symbol: "A/USDT", quantity: 1 },
                                { symbol: "B/USDT", quantity: 1 }],
                           { "A/USDT": 10 });
  check("부분 수신 → null + 이름", m.equityLive === null
        && m.missing[0] === "B/USDT", m);
}

// ⑩ 보유가 없으면 현금이 곧 자산이다(빈 배열이 실패가 아니다).
{
  const m = equityFromCash(77, [], {});
  check("현금만 → 자산 77", close(m.equityLive, 77) && m.complete, m);
}

if (failed) { console.error(failed + "건 실패"); process.exit(1); }
console.log("track-live 계산 전부 통과");
