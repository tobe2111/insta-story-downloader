/**
 * "이 체결은 정말 체결인가"를 **실행해서** 확인한다 (docs/assets/fills.js).
 *
 * ⚠️ 왜 이 하네스가 있나 (2026-08-18, 감사 281). 사장님 지적:
 *    "투자한 잔고는 지금 코인밖에 없고, 거래내역에는 주식이 있고..."
 *    2026-08-15 기록에는 아마존이 `fills`(샀다)와 `cash_short`(못 샀다)에
 *    동시에 있고 잔고에는 없다. 감사 273·274는 **금액만** 가렸다 —
 *    화면에는 여전히 "아마존 · 매수"라고 적혀 있었다.
 *
 * 실행: node tests/fills_check.mjs   (실패 시 종료코드 1)
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
new Function(readFileSync(join(here, "..", "docs", "assets", "fills.js"), "utf8"))();
const Q = globalThis.QuantFills;

const fails = [];
const check = (n, c, d) => { if (!c) fails.push(n + (d ? " — " + d : "")); };

/* ── 1. 실측 그 기록 (2026-08-15) ─────────────────────────────── */
const REAL = {
  date: "2026-08-15", equity: 997197.56,
  fills: [{ key: "us_stock:AMZN", side: "buy", quantity: 24017.2448278807,
            amount: 6361687.93, price: 264.880005, type: "시가" }],
  cash_short: [{ key: "us_stock:AMZN", need: 6365504.94, cash: 677061.47 }],
};
check("거부된 주문은 체결이 아니다", Q.settled(REAL, "us_stock:AMZN") === false);
check("이유를 말한다", Q.refusal(REAL, "us_stock:AMZN") === "현금 부족",
      String(Q.refusal(REAL, "us_stock:AMZN")));

/* ── 2. 대조군 — 멀쩡한 체결까지 지우면 장부가 아니다 ─────────── */
check("정상 체결은 체결이다", Q.settled(REAL, "crypto:BNB/USDT") === true);
check("정상 체결에는 사유가 없다", Q.refusal(REAL, "crypto:BNB/USDT") === null);
{
  const clean = { date: "2026-08-14", fills: [{ key: "crypto:BNB/USDT" }] };
  check("거부 칸이 아예 없는 날", Q.settled(clean, "crypto:BNB/USDT") === true);
}

/* ── 3. 원인이 다르면 다르게 말한다 ───────────────────────────── */
{
  const rec = { short_refused: [{ key: "us_stock:TSLA", need: 1, cash: 0 }] };
  check("증거금 부족", Q.refusal(rec, "us_stock:TSLA") === "증거금 부족",
        String(Q.refusal(rec, "us_stock:TSLA")));
}
{
  const rec = { rejected: [{ key: "kr_stock:005930.KS" }] };
  check("그 밖의 거부", Q.refusal(rec, "kr_stock:005930.KS") === "주문 거부");
}
/* 장부 판이 바뀌어 객체 형태로 와도 조용히 빈손이 되면 안 된다 */
{
  const rec = { cash_short: { "us_stock:AMZN": { need: 1, cash: 0 } } };
  check("객체 형태도 읽는다", Q.refusal(rec, "us_stock:AMZN") === "현금 부족");
}

/* ── 4. 모르면 지어내지 않는다 ────────────────────────────────── */
check("기록 없음", Q.refusal(null, "us_stock:AMZN") === null);
check("종목 없음", Q.refusal(REAL, null) === null);
check("빈 기록", Q.settled({}, "us_stock:AMZN") === true);

/* ── 5. 날짜 색인 ─────────────────────────────────────────────── */
{
  const m = Q.byDate([REAL, { date: "2026-08-14T00:00:00Z" }, null, {}]);
  check("날짜로 찾는다", m["2026-08-15"] === REAL);
  check("시각이 붙어 있어도 날짜만", "2026-08-14" in m, JSON.stringify(Object.keys(m)));
  check("날짜 없는 기록은 안 넣는다", Object.keys(m).length === 2);
}

if (fails.length) {
  console.error("체결 판정 검사 실패:\n  - " + fails.join("\n  - "));
  process.exit(1);
}
console.log("체결 판정 검사 통과");
