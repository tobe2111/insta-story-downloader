/**
 * 트레이딩뷰 심볼 매핑 + 위젯 마운트 — 화면 여러 곳이 공유한다.
 *
 * ⚠️ 왜 파일로 뺐나 (2026-08-14). 이 매핑은 today.html 안에만 있었고,
 *    첫 화면에서 종목을 눌러도 차트를 볼 수 없었다(사장님 요청). 같은
 *    매핑을 index.html에 복사하면 두 곳이 갈라진다 — 상장 시장이 바뀌거나
 *    종목이 추가될 때 한쪽만 고쳐지고, 그러면 어느 쪽이 맞는지 아무도
 *    모르게 된다(FROZEN_IDEAS ①: 같은 규칙을 두 곳에 적으면 반드시 어긋난다).
 *
 * ⚠️ 이 차트는 **표시 전용**이다. 매매 판단은 새벽에 받은 데이터로만 하고,
 *    여기 보이는 실시간 가격은 판단에 관여하지 않는다. 화면의 실시간 값을
 *    판단 근거처럼 읽으면 안 된다.
 *
 * tests/hitrate_check.mjs와 같은 방식으로 tests/tradingview_check.mjs가
 * 이 파일을 그대로 실행해 매핑을 값으로 확인한다.
 */
(function (root) {
  "use strict";

  // 미국 상장 시장 — 기본은 나스닥이고, ETF 등 예외만 적는다.
  // (SPY·DIA는 NYSE Arca, QQQ는 나스닥)
  var US_EXCHANGE = { SPY: "AMEX", DIA: "AMEX", IWM: "AMEX", VOO: "AMEX" };

  /** 'market:symbol' 장부 키 → 트레이딩뷰 심볼. 모르면 null. */
  function symbol(key) {
    var parts = String(key || "").split(":");
    var m = parts[0], s = parts.slice(1).join(":");
    if (!s) return null;
    if (m === "crypto") return "BINANCE:" + s.replace("/", "");
    if (m === "kr_stock") return "KRX:" + s.replace(/\.(KS|KQ)$/, "");
    if (m === "us_stock") return (US_EXCHANGE[s] || "NASDAQ") + ":" + s;
    return null;
  }

  /** 위젯을 el 안에 새로 만든다(기존 내용은 지운다). */
  function mount(el, tvSymbol, opts) {
    if (!el || !tvSymbol) return false;
    opts = opts || {};
    el.innerHTML = "";
    var wrap = document.createElement("div");
    wrap.className = "tradingview-widget-container";
    wrap.style.height = "100%";
    var s = document.createElement("script");
    s.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    s.async = true;
    s.textContent = JSON.stringify({
      autosize: true, symbol: tvSymbol, interval: opts.interval || "D",
      timezone: "Asia/Seoul",
      theme: (root.matchMedia && root.matchMedia("(prefers-color-scheme: light)").matches)
        ? "light" : "dark",
      style: "1", locale: "kr", hide_top_toolbar: false,
      allow_symbol_change: false, save_image: false
    });
    wrap.appendChild(s);
    el.appendChild(wrap);
    return true;
  }

  root.QuantTV = { symbol: symbol, mount: mount, US_EXCHANGE: US_EXCHANGE };
})(typeof globalThis !== "undefined" ? globalThis : this);

if (typeof module !== "undefined" && module.exports) {
  module.exports = (typeof globalThis !== "undefined" ? globalThis : this).QuantTV;
}
