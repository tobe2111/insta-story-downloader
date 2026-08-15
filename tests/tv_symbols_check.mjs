/**
 * 트레이딩뷰 심볼 변환을 **실행해서** 검사한다 (docs/assets/tv-symbols.js).
 *
 * 종목을 눌렀는데 엉뚱한 차트가 뜨는 것은 이 제품에서 흔한 UI 버그가 아니다 —
 * "삼성전자 차트"라고 써 놓고 다른 회사를 보여주는 것이라, 가짜 데이터를
 * 진짜처럼 보여주는 것과 같은 계열의 사고다. 그래서 20종목 전부를 값으로
 * 못박는다.
 *
 * 실행: node tests/tv_symbols_check.mjs   (실패 시 종료코드 1)
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(join(here, "..", "docs", "assets", "tv-symbols.js"),
                         "utf8");
new Function(src)();
const Q = globalThis.QuantTV;

const fails = [];
const check = (name, cond, detail) => {
  if (!cond) fails.push(name + (detail ? " — " + detail : ""));
};

// ① 운영 20종목 전부 (quant/markets.py AUTO_TARGETS와 같은 목록)
const EXPECT = {
  "crypto:BTC/USDT": "BINANCE:BTCUSDT",
  "crypto:ETH/USDT": "BINANCE:ETHUSDT",
  "crypto:SOL/USDT": "BINANCE:SOLUSDT",
  "crypto:BNB/USDT": "BINANCE:BNBUSDT",
  "crypto:XRP/USDT": "BINANCE:XRPUSDT",
  "us_stock:SPY": "AMEX:SPY",
  "us_stock:QQQ": "NASDAQ:QQQ",
  "us_stock:NVDA": "NASDAQ:NVDA",
  "us_stock:MSFT": "NASDAQ:MSFT",
  "us_stock:AAPL": "NASDAQ:AAPL",
  "us_stock:AMZN": "NASDAQ:AMZN",
  "us_stock:META": "NASDAQ:META",
  "us_stock:TSLA": "NASDAQ:TSLA",
  "kr_stock:069500.KS": "KRX:069500",
  "kr_stock:005930.KS": "KRX:005930",
  "kr_stock:000660.KS": "KRX:000660",
  "kr_stock:035420.KS": "KRX:035420",
  "kr_stock:005380.KS": "KRX:005380",
  "kr_stock:051910.KS": "KRX:051910",
  "kr_stock:105560.KS": "KRX:105560",
};
for (const [key, want] of Object.entries(EXPECT)) {
  const got = Q.tvSymbol(key);
  check("매핑 " + key, got === want, "받은 값 " + got);
}
check("운영 종목 20개를 전부 덮는다", Object.keys(EXPECT).length === 20,
      String(Object.keys(EXPECT).length));

// ② 코스닥도 KRX로 간다
check("코스닥(.KQ)", Q.tvSymbol("kr_stock:247540.KQ") === "KRX:247540");

// ③ **모르면 만들어내지 않는다** — 이게 이 파일의 핵심 계약이다
const UNKNOWN = [
  "us_stock:ZZZZ",          // 표에 없는 미국 티커
  "kr_stock:005930",        // 접미사 없는 국내 코드
  "kr_stock:12345.KS",      // 여섯 자리가 아니다
  "crypto:BTCUSDT",         // 슬래시 없는 우리 표기 아님
  "upbit:BTC/KRW",          // 다루지 않는 시장
  "synthetic:DEMO",
  "crypto:",
  "BTC/USDT",               // 시장 접두어 없음
  "",
];
for (const k of UNKNOWN) {
  check("모르는 종목은 null: " + JSON.stringify(k),
        Q.tvSymbol(k) === null, "받은 값 " + Q.tvSymbol(k));
}
for (const bad of [null, undefined, 42, {}, []]) {
  check("이상한 입력도 null: " + String(bad), Q.tvSymbol(bad) === null);
}

// ④ 주소 만들기
check("차트 주소", Q.tvUrl("kr_stock:005930.KS") ===
      "https://www.tradingview.com/chart/?symbol=KRX%3A005930",
      String(Q.tvUrl("kr_stock:005930.KS")));
check("모르는 종목은 주소도 없다", Q.tvUrl("upbit:BTC/KRW") === null);

// ⑤ 끼워 넣을 주소 — **외부 스크립트가 아니라 iframe**
{
  const u = Q.tvEmbedUrl("crypto:BTC/USDT");
  check("임베드 주소가 나온다", typeof u === "string", String(u));
  check("심볼이 들어간다", u.includes("symbol=BINANCE%3ABTCUSDT"), u);
  check("기본은 일봉", u.includes("interval=D"), u);
  check("기본은 다크", u.includes("theme=dark"), u);
  check("종목 갈아타기 금지 — 이 창은 '이 종목'을 보는 창이다",
        u.includes("allow_symbol_change=0"), u);
  check("밝은 테마도 된다",
        Q.tvEmbedUrl("crypto:BTC/USDT", { theme: "light" })
          .includes("theme=light"));
  check("이상한 테마는 다크로 떨어진다",
        Q.tvEmbedUrl("crypto:BTC/USDT", { theme: "<script>" })
          .includes("theme=dark"));
  check("봉 주기를 바꿀 수 있다",
        Q.tvEmbedUrl("crypto:BTC/USDT", { interval: "60" })
          .includes("interval=60"));
  check("모르는 종목은 임베드도 없다",
        Q.tvEmbedUrl("upbit:BTC/KRW") === null);
  // 주입 방어 — 심볼은 표에서만 오지만, 인자는 화면에서 온다
  check("인터벌이 그대로 주소에 박히지 않는다",
        !Q.tvEmbedUrl("crypto:BTC/USDT", { interval: '"><script>' })
          .includes("<script>"));
}

if (fails.length) {
  console.error("실패 " + fails.length + "건:");
  fails.forEach((f) => console.error("  ✗ " + f));
  process.exit(1);
}
console.log("트레이딩뷰 심볼 변환 실행 검사 통과");
