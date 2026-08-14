/**
 * 준실시간 평가 계산을 **실행해서** 검사한다 (docs/assets/live-marks.js).
 *
 * ⚠️ 왜 이 하네스가 있나: 이 저장소의 사이트 검사는 오랫동안 소스 문자열만
 *    읽었다. 문자열은 코드가 거기 있다는 것만 말하고, 그 코드가 옳은 답을
 *    낸다고는 말하지 않는다. 감사 229가 그 표본이다 — 라벨은 '준실시간'인데
 *    요청은 매번 거부당하고 있었고, 검사는 전부 초록이었다.
 *
 *    같은 날 워커에 붙인 실행 하네스는 그 자리에서 결함을 잡았다(종목마다
 *    토큰 재발급). 그래서 돈이 걸린 계산은 전부 이렇게 값으로 확인한다.
 *
 * 실행: node tests/live_marks_check.mjs   (실패 시 종료코드 1)
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(join(here, "..", "docs", "assets", "live-marks.js"),
                         "utf8");
new Function(src)();                       // 페이지가 하는 것과 같은 방식으로 적재
const Q = globalThis.QuantLive;

const fails = [];
const check = (name, cond, detail) => {
  if (!cond) fails.push(name + (detail ? " — " + detail : ""));
};
const near = (a, b) => Math.abs(a - b) < 1e-6;

const FX = 1412.5;
const LIVE = {
  "us_stock:SPY": { px: 772.49, delayed: false },
  "kr_stock:105560.KS": { px: 167500, delayed: true },
  "crypto:SOL/USDT": { px: 75.89, delayed: false },
};
const HOLD = [
  { key: "us_stock:SPY", quantity: 1.0, value: 1_090_000 },
  { key: "kr_stock:105560.KS", quantity: 1.0, value: 166_000 },
  { key: "crypto:SOL/USDT", quantity: 2.0, value: 214_000 },
];

// ① 환산 — 달러 종목은 환율을 곱하고, 원화 종목은 그대로
check("달러 종목 환산",
      near(Q.liveValueOf("us_stock:SPY", 1, LIVE, FX), 772.49 * FX),
      String(Q.liveValueOf("us_stock:SPY", 1, LIVE, FX)));
check("코인 환산",
      near(Q.liveValueOf("crypto:SOL/USDT", 2, LIVE, FX), 2 * 75.89 * FX));
check("원화 종목은 그대로(대조군)",
      near(Q.liveValueOf("kr_stock:105560.KS", 1, LIVE, FX), 167500));

// ② 환율이 없으면 해외는 값을 만들지 않는다 — 1.0으로 때우지 않는다
check("환율 없음: 달러 종목은 null",
      Q.liveValueOf("us_stock:SPY", 1, LIVE, null) === null);
check("환율 없음: 원화 종목은 살아 있다",
      near(Q.liveValueOf("kr_stock:105560.KS", 1, LIVE, null), 167500));
check("수량 0이면 값 없음", Q.liveValueOf("us_stock:SPY", 0, LIVE, FX) === null);
check("시세 없으면 값 없음", Q.liveValueOf("없는:종목", 1, LIVE, FX) === null);

// ③ 합계는 **전부 받았을 때만** — 부분 합계는 계좌를 작게 보이게 한다
{
  const m = Q.markHoldings(HOLD, LIVE, FX);
  check("전부 수신: 합계가 나온다", m.complete === true);
  check("합계 값", near(m.sumLive, 772.49 * FX + 167500 + 2 * 75.89 * FX),
        String(m.sumLive));
  check("장부 합계도 같이", near(m.sumBook, 1_090_000 + 166_000 + 214_000));
  check("빠진 것 없음", m.missing.length === 0);
}
{
  const partial = { "kr_stock:105560.KS": LIVE["kr_stock:105560.KS"] };
  const m = Q.markHoldings(HOLD, partial, FX);
  check("일부 수신: 합계를 내지 않는다", m.sumLive === null,
        "sumLive=" + m.sumLive);
  check("일부 수신: 받은 것은 칠한다", near(m.rows["kr_stock:105560.KS"], 167500));
  check("일부 수신: 빠진 종목을 이름으로 알려준다",
        m.missing.includes("SPY") && m.missing.includes("SOL/USDT"),
        JSON.stringify(m.missing));
  check("일부 수신: 몇 개 받았는지 센다", m.marked === 1 && m.total === 3);
}
{
  const m = Q.markHoldings(HOLD, {}, FX);
  check("한 건도 못 받음: 합계 없음", m.sumLive === null);
  check("한 건도 못 받음: marked 0", m.marked === 0);
}
{
  // 환율만 빠진 경우 — 국내 한 종목만 살아남는다(같은 침묵을 만들면 안 된다)
  const m = Q.markHoldings(HOLD, LIVE, null);
  check("환율 없음: 합계를 내지 않는다", m.sumLive === null);
  check("환율 없음: 국내는 칠한다", near(m.rows["kr_stock:105560.KS"], 167500));
}

// ④ 신선도 문장은 **세어서** 만든다 — 문장에 박으면 KIS를 붙여도 안 바뀐다
{
  const f = Q.freshness(HOLD, LIVE);
  check("혼합: 실시간 2 · 지연 1", f.fresh === 2 && f.late === 1,
        JSON.stringify(f));
  check("혼합 문구", f.text.includes("실시간 2종목") && f.text.includes("지연 1종목"),
        f.text);
}
{
  const allLive = {};
  for (const k of Object.keys(LIVE)) allLive[k] = { ...LIVE[k], delayed: false };
  const f = Q.freshness(HOLD, allLive);
  check("전부 실시간이면 그렇게 말한다", f.late === 0 && f.text.includes("실시간"),
        f.text);
  check("전부 실시간이면 '지연'을 말하지 않는다", !f.text.includes("지연"), f.text);
}
{
  const allLate = {};
  for (const k of Object.keys(LIVE)) allLate[k] = { ...LIVE[k], delayed: true };
  const f = Q.freshness(HOLD, allLate);
  check("전부 지연이면 그렇게 말한다", f.fresh === 0 && f.text.includes("지연"),
        f.text);
}
check("아무것도 없으면 문장도 없다", Q.freshness(HOLD, {}).text === "");

// ⑤ 장중 판정 — 시각을 인자로 받으므로 특정 순간을 재현할 수 있다
{
  // 기준: 2026-08-13(목) 그 주. UTC로 만들어 KST를 정확히 겨눈다.
  const kst = (y, mo, d, h, mi) => Date.UTC(y, mo, d, h - 9, mi || 0);
  check("목요일 10:00 KST — 한국장",
        Q.marketOpenish(kst(2026, 7, 13, 10)) === true);
  check("목요일 16:00 KST — 한국장 마감 후",
        Q.marketOpenish(kst(2026, 7, 13, 16)) === false);
  check("목요일 23:00 KST — 미국장",
        Q.marketOpenish(kst(2026, 7, 13, 23)) === true);
  check("금요일 03:00 KST — 미국장(전날 이어짐)",
        Q.marketOpenish(kst(2026, 7, 14, 3)) === true);
  check("토요일 03:00 KST — 금요일 미국장 마무리",
        Q.marketOpenish(kst(2026, 7, 15, 3)) === true);
  check("토요일 12:00 KST — 전부 휴장",
        Q.marketOpenish(kst(2026, 7, 15, 12)) === false);
  check("일요일 12:00 KST — 전부 휴장",
        Q.marketOpenish(kst(2026, 7, 16, 12)) === false);
  check("일요일 23:00 KST — 미국장 아직 안 열림",
        Q.marketOpenish(kst(2026, 7, 16, 23)) === false);
  check("월요일 10:00 KST — 한국장",
        Q.marketOpenish(kst(2026, 7, 17, 10)) === true);
}

if (fails.length) {
  console.error("실패 " + fails.length + "건:");
  fails.forEach((f) => console.error("  ✗ " + f));
  process.exit(1);
}
console.log("준실시간 평가 계산 실행 검사 통과");
