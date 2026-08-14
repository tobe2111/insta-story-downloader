/**
 * 트레이딩뷰 심볼 매핑을 **실행해서** 검사한다 (docs/assets/tradingview.js).
 *
 * ⚠️ 왜 이 하네스가 있나 (2026-08-14). 이 매핑은 today.html 안에만 있었고,
 *    사장님 요청("종목을 클릭하면 트레이딩뷰 차트가 보이게끔")으로 첫 화면에도
 *    붙이면서 파일 하나로 뺐다. 매핑이 틀리면 차트가 **조용히 안 뜬다** —
 *    문자열 검사로는 못 잡고, 화면에서도 '아직 로딩 중'과 구별되지 않는다.
 *
 *    운영 20종목이 전부 심볼을 만들 수 있는지 여기서 값으로 확인한다.
 *
 * 실행: node tests/tradingview_check.mjs   (실패 시 종료코드 1)
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
const src = readFileSync(join(root, "docs", "assets", "tradingview.js"), "utf8");
new Function(src)();
const Q = globalThis.QuantTV;

const fails = [];
const check = (name, cond, detail) => {
  if (!cond) fails.push(name + (detail ? " — " + detail : ""));
};
const eq = (name, got, want) => check(name, got === want, `${got} ≠ ${want}`);

/* ── 1. 시장별 매핑 ────────────────────────────────────────────── */
eq("코인은 슬래시를 뗀다", Q.symbol("crypto:SOL/USDT"), "BINANCE:SOLUSDT");
eq("코인 BTC", Q.symbol("crypto:BTC/USDT"), "BINANCE:BTCUSDT");
eq("코스피는 .KS를 뗀다", Q.symbol("kr_stock:000660.KS"), "KRX:000660");
// ⚠️ 코스닥(.KQ)도 떼야 한다. 옛 인라인 사본은 `.replace(".KS","")`뿐이라
//    코스닥 종목이 "KRX:247540.KQ"가 되어 차트가 안 떴다 — 파일로 빼면서
//    같이 고친 자리다.
eq("코스닥도 .KQ를 뗀다", Q.symbol("kr_stock:247540.KQ"), "KRX:247540");
eq("미국주식 기본은 나스닥", Q.symbol("us_stock:AAPL"), "NASDAQ:AAPL");
eq("SPY는 AMEX", Q.symbol("us_stock:SPY"), "AMEX:SPY");
eq("QQQ는 나스닥", Q.symbol("us_stock:QQQ"), "NASDAQ:QQQ");

/* ── 2. 모르면 모른다고 한다 ──────────────────────────────────── */
check("모르는 시장은 null", Q.symbol("fx:USDKRW") === null);
check("빈 키는 null", Q.symbol("") === null);
check("null 키도 안 터진다", Q.symbol(null) === null);
check("심볼이 없으면 null", Q.symbol("crypto:") === null);
// 코인 심볼에 콜론이 들어가는 거래소 표기(SOL/USDT:USDT)도 잘려선 안 된다.
eq("콜론이 더 있어도 심볼을 안 자른다",
   Q.symbol("crypto:SOL/USDT:USDT"), "BINANCE:SOLUSDT:USDT");

/* ── 3. 운영 종목 전부가 차트를 가진다 ────────────────────────────
   여기가 이 파일의 본론이다. 종목을 추가했는데 매핑이 없으면 그 종목만
   눌러도 아무 일이 없다 — 화면에서는 고장으로 보인다. */
{
  const py = readFileSync(join(root, "quant", "markets.py"), "utf8");
  // AUTO_TARGETS = [("crypto", "BTC/USDT"), ...] 형태를 그대로 읽는다.
  const block = py.slice(py.indexOf("AUTO_TARGETS"));
  const end = block.indexOf("\n]");
  const pairs = [...block.slice(0, end > 0 ? end : block.length)
    .matchAll(/\(\s*"([a-z_]+)"\s*,\s*"([^"]+)"/g)];
  check("운영 종목 목록을 읽었다", pairs.length >= 15, `${pairs.length}종목`);
  const missing = pairs
    .map(([, m, s]) => [`${m}:${s}`, Q.symbol(`${m}:${s}`)])
    .filter(([, tv]) => !tv)
    .map(([k]) => k);
  check("매핑 없는 운영 종목이 없다", missing.length === 0, missing.join(", "));
}

/* ── 4. 위젯 마운트 — 없는 자리·없는 심볼에 안 터진다 ───────────── */
check("자리가 없으면 false", Q.mount(null, "BINANCE:SOLUSDT") === false);
check("심볼이 없으면 false", Q.mount({}, null) === false);

if (fails.length) {
  console.error("트레이딩뷰 매핑 검사 실패:\n  - " + fails.join("\n  - "));
  process.exit(1);
}
console.log("트레이딩뷰 매핑 검사 통과");
