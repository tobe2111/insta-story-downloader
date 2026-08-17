/**
 * 금액 검사 규칙을 **실행해서** 확인한다 (docs/assets/amounts.js).
 *
 * ⚠️ 왜 이 하네스가 있나 (2026-08-17, 감사 265 · 사장님 지적
 *    "홈페이지 내에서 지금 숫자들이 다 맞진 않은 것 같은데? 금액이 말이야.").
 *
 *    자산 997,198원짜리 계좌의 화면이 "아마존 매수 6,361,688원"과
 *    "비앤비 4,526,594원/배정 4,501,933원"을 사실처럼 보여주고 있었다.
 *
 * 실행: node tests/amounts_check.mjs   (실패 시 종료코드 1)
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(join(here, "..", "docs", "assets", "amounts.js"), "utf8");
new Function(src)();
const Q = globalThis.QuantAmounts;

const fails = [];
const check = (name, cond, detail) => {
  if (!cond) fails.push(name + (detail ? " — " + detail : ""));
};

/* ── 1. 한 건이 계좌보다 클 수 없다 ────────────────────────────── */
const EQ = 997197.56;
check("실측 그 체결이 걸린다", Q.impossible(EQ, 6361687.93) === true);
// 대조군 — 정상 체결은 조용해야 한다. 이게 없으면 "전부 의심"도 통과한다.
check("정상 체결은 조용하다", Q.impossible(EQ, 27929.95) === false);
check("계좌를 살짝 넘는 것도 걸린다", Q.impossible(EQ, 1086327.14) === true);
// ⚠️ 여유를 1.5배로 잡았다면 위 1.09배짜리를 놓친다. 그 줄도 화면에 나갔다.
check("여유는 자릿수가 아니라 반올림용", Q.SANITY_RATIO < 1.1, String(Q.SANITY_RATIO));
check("정확히 자산만큼은 통과", Q.impossible(EQ, EQ) === false);
check("매도(음수)도 크기로 본다", Q.impossible(EQ, -6361687.93) === true);

/* ── 2. 자산을 모르면 의심하지 않는다 ──────────────────────────── */
// 모르는 것과 아닌 것은 다르다 — 근거가 없으면 판정도 하지 않는다.
check("자산 미상은 판정 안 함", Q.impossible(null, 9e9) === false);
check("자산 0도 판정 안 함", Q.impossible(0, 9e9) === false);
check("자산이 숫자가 아니면", Q.impossible("백만원", 9e9) === false);

/* ── 3. 기록 하나를 통째로 훑기 ────────────────────────────────── */
{
  // 2026-08-15 실측 기록을 줄여 옮긴 것.
  const rec = {
    equity: EQ,
    fills: [{ key: "us_stock:AMZN", amount: 6361687.93 },
            { key: "crypto:BNB/USDT", amount: 27929.95 }],
    lot_priority: {
      "crypto:BTC/USDT": { spent: 1086327.14 },
      "crypto:ETH/USDT": { spent: 80581.96 },
      "crypto:BNB/USDT": { spent: 4526594.72 },
    },
  };
  const bad = Q.overEquity(rec);
  check("걸린 체결은 하나", (bad.fills || []).length === 1, JSON.stringify(bad.fills));
  check("그 하나가 아마존", (bad.fills || [])[0].key === "us_stock:AMZN");
  check("예산은 둘", (bad.lot_priority || []).length === 2,
        JSON.stringify(bad.lot_priority));
  // 정상인 이더리움은 남아야 한다 — 다 지우면 그날의 진짜 사실도 사라진다.
  check("정상 예산은 안 걸린다",
        !(bad.lot_priority || []).some(x => x.key === "crypto:ETH/USDT"));
  check("자산을 함께 돌려준다", bad.equity === EQ);
  check("종목 단위로 물어볼 수 있다",
        Q.flagged(rec, "us_stock:AMZN", "fills") === true &&
        Q.flagged(rec, "crypto:BNB/USDT", "fills") === false);
}

/* ── 4. 대조군 — 멀쩡한 날은 완전히 조용하다 ───────────────────── */
{
  const ok = { equity: 999847.15,
               fills: [{ key: "crypto:BNB/USDT", amount: 27929.95 }],
               lot_priority: { "crypto:BTC/USDT": { spent: 62776.39 } } };
  check("멀쩡한 날은 빈 결과", Object.keys(Q.overEquity(ok)).length === 0,
        JSON.stringify(Q.overEquity(ok)));
  check("빈 기록도 안 터진다", Object.keys(Q.overEquity({})).length === 0);
  check("null도 안 터진다", Object.keys(Q.overEquity(null)).length === 0);
}

if (fails.length) {
  console.error("금액 검사 규칙 실패:\n  - " + fails.join("\n  - "));
  process.exit(1);
}
console.log("금액 검사 규칙 통과");
