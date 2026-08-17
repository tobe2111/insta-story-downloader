/**
 * 우리 종목 키 → 트레이딩뷰 심볼 (순수 변환, 화면과 분리).
 *
 * ⚠️ 왜 파일을 나눴나: 이 저장소는 화면 안에 박힌 계산을 검사하지 못해
 *    여러 번 당했다(감사 229·231). 변환표는 실행해서 값으로 확인한다 —
 *    tests/tv_symbols_check.mjs.
 *
 * ⚠️ **모르는 종목은 만들어내지 않는다.** 매핑이 없으면 null을 주고, 화면은
 *    그 종목에 트레이딩뷰 버튼을 아예 띄우지 않는다. 추측한 심볼을 넣으면
 *    "삼성전자를 눌렀는데 엉뚱한 차트가 뜬다" — 가짜 데이터를 진짜처럼
 *    보여주는 것과 같은 종류의 사고다.
 *
 * ⚠️ 트레이딩뷰 차트는 **거래소 데이터**다. 우리 장부(체결가·진입가·보유)와
 *    출처가 다르므로 숫자가 미세하게 다를 수 있다. 그래서 우리 차트를
 *    대체하지 않고 나란히 놓으며, 화면에 "거래소 공개 차트 · 장부와 별개"
 *    라고 적는다.
 */
(function (root) {
  "use strict";

  // 코인은 전부 바이낸스 현물 — 우리 시세도 같은 곳에서 받는다.
  var CRYPTO_EXCHANGE = "BINANCE";

  // 미국주식은 상장 거래소를 명시한다. 생략하면 트레이딩뷰가 알아서
  // 고르는데, 같은 티커가 여러 거래소에 있으면 엉뚱한 것이 걸린다.
  var US_EXCHANGE = {
    SPY: "AMEX",       // NYSE Arca — 트레이딩뷰 표기가 AMEX다
    QQQ: "NASDAQ",
    NVDA: "NASDAQ",
    MSFT: "NASDAQ",
    AAPL: "NASDAQ",
    AMZN: "NASDAQ",
    META: "NASDAQ",
    TSLA: "NASDAQ",
  };

  /**
   * "crypto:BTC/USDT" → "BINANCE:BTCUSDT"
   * "us_stock:SPY"    → "AMEX:SPY"
   * "kr_stock:005930.KS" → "KRX:005930"
   * 모르면 null.
   */
  function tvSymbol(key) {
    if (typeof key !== "string") return null;
    var i = key.indexOf(":");
    if (i < 0) return null;
    var market = key.slice(0, i);
    var symbol = key.slice(i + 1);
    if (!symbol) return null;

    if (market === "crypto") {
      // BTC/USDT → BTCUSDT. 슬래시가 없으면 우리 표기가 아니다.
      if (symbol.indexOf("/") < 0) return null;
      return CRYPTO_EXCHANGE + ":" + symbol.replace("/", "");
    }
    if (market === "us_stock") {
      var ex = US_EXCHANGE[symbol];
      return ex ? ex + ":" + symbol : null;
    }
    if (market === "kr_stock") {
      // 005930.KS → KRX:005930. 코스닥(.KQ)도 트레이딩뷰에서는 KRX다.
      var m = /^(\d{6})\.(KS|KQ)$/.exec(symbol);
      return m ? "KRX:" + m[1] : null;
    }
    return null;      // upbit·synthetic 등 — 모르면 안 만든다
  }

  /** 트레이딩뷰 차트 페이지 주소(새 탭으로 열 때 쓴다). */
  function tvUrl(key) {
    var s = tvSymbol(key);
    return s ? "https://www.tradingview.com/chart/?symbol=" +
      encodeURIComponent(s) : null;
  }

  /**
   * 페이지 안에 끼워 넣을 차트 주소(iframe용).
   *
   * ⚠️ **외부 스크립트를 쓰지 않는다.** 트레이딩뷰가 권하는 방식은
   *    `<script src="s3.tradingview.com/...">`를 우리 페이지에 넣는 것인데,
   *    그러면 남의 자바스크립트가 우리 문서 안에서 실행된다 — 이 사이트는
   *    공개 장부이고, 숫자를 보여주는 화면에 제3자 코드를 들이지 않는다.
   *    iframe은 샌드박스 경계가 있고, 트레이딩뷰가 죽으면 그 칸만 비고
   *    나머지 화면은 멀쩡하다.
   *
   * interval: "D"(일봉) 기본. theme: "dark" | "light".
   */
  function tvEmbedUrl(key, opts) {
    var s = tvSymbol(key);
    if (!s) return null;
    var o = opts || {};
    var q = [
      "symbol=" + encodeURIComponent(s),
      "interval=" + encodeURIComponent(o.interval || "D"),
      "theme=" + (o.theme === "light" ? "light" : "dark"),
      "style=1",                 // 캔들
      "locale=kr",
      "hide_side_toolbar=1",
      "allow_symbol_change=0",   // 다른 종목으로 갈아타지 못하게 — 이 창은
                                 // '이 종목'을 보는 창이다
      "save_image=0",
      "withdateranges=1",
    ];
    return "https://s.tradingview.com/widgetembed/?" + q.join("&");
  }

  /**
   * 차트를 그 칸에 실제로 끼워 넣는다. 반환: 끼웠으면 true, 매핑이 없어
   * **안 끼웠으면 false**(그 칸은 비운다).
   *
   * ⚠️ 왜 이 함수가 여기 생겼나 (2026-08-17, 감사 264).
   *    첫 화면과 '오늘의 판단'이 둘 다 `QuantTV.mount(...)`를 부르고 있었는데
   *    **그런 함수가 없었다.** 그리고 '오늘의 판단'은 스크립트 이름까지
   *    틀려서(`tradingview.js` — 없는 파일) 2026-08-16부터 페이지가 통째로
   *    죽어 있었다. 두 페이지가 각자 위젯 iframe을 짓지 않고 여기 한 곳을
   *    부르게 두는 이유이기도 하다(FROZEN_IDEAS ①).
   *
   *    검사는 매일 초록이었다 — 브라우저로 띄워 보는 검사가 첫 화면에만
   *    있었고, 그마저도 이 칸을 열어 보지 않았다.
   */
  function mount(host, key, opts) {
    if (!host) return false;
    var o = opts || {};
    if (!o.theme && root.matchMedia) {
      o = {
        interval: o.interval,
        theme: root.matchMedia("(prefers-color-scheme: light)").matches
          ? "light" : "dark",
      };
    }
    var url = tvEmbedUrl(key, o);
    if (!url) { host.innerHTML = ""; return false; }
    var f = document.createElement("iframe");
    f.src = url;
    f.style.cssText = "width:100%;height:100%;border:0;display:block";
    f.setAttribute("loading", "lazy");
    // 남의 문서다 — 우리 페이지를 건드리지 못하게 최소 권한만 준다.
    f.setAttribute("sandbox", "allow-scripts allow-same-origin allow-popups");
    f.setAttribute("referrerpolicy", "no-referrer");
    host.innerHTML = "";
    host.appendChild(f);
    return true;
  }

  root.QuantTV = { tvSymbol: tvSymbol, tvUrl: tvUrl, tvEmbedUrl: tvEmbedUrl,
                   mount: mount };
})(typeof globalThis !== "undefined" ? globalThis : this);
