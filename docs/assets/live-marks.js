/**
 * 준실시간 평가의 **순수 계산** — 화면에서 떼어내 검사할 수 있게 한 자리.
 *
 * ⚠️ 왜 파일을 나눴나(2026-08-13): 이 저장소에서 여러 번 겪은 병이 있다 —
 *    "검사는 초록인데 기능은 죽어 있다"(감사 229가 그 표본이다: 라벨은
 *    '준실시간'인데 요청은 매번 거부당하고 있었다). 원인은 사이트 검사가
 *    전부 **소스 문자열**을 읽는 것뿐이라서다. 문자열은 코드가 거기 있다는
 *    것만 말하지, 그 코드가 옳은 답을 낸다고는 말하지 않는다.
 *
 *    같은 날 워커에 실행 하네스를 붙였더니 **그 자리에서 결함을 잡았다**
 *    (종목마다 KIS 토큰을 재발급하고 있었다). 그래서 돈이 걸린 계산은
 *    인라인 스크립트 안에 두지 않고 여기로 꺼낸다. `tests/live_marks_check.mjs`
 *    가 이 파일을 그대로 실행해 값으로 확인한다.
 *
 * 여기 있는 것은 전부 **부수효과 없는 함수**다 — DOM도 네트워크도 시계도
 * 건드리지 않는다(시각은 인자로 받는다). 그래야 검사가 진짜 계산을 본다.
 */
(function (root) {
  "use strict";

  /** 달러(USD/USDT)로 호가되는 시장 — 원화 장부에 담으려면 환산해야 한다. */
  var USD_MKT = /^(us_stock|crypto):/;

  /**
   * 이 종목을 지금 시세로 평가하면 **원화로** 얼마인가.
   *
   * 환율을 모르면 `null` — 1.0으로 때우지 않는다(감사 212의 규칙).
   * 그래야 호출부가 "일부만 더한 합계"를 만들지 않는다.
   */
  function liveValueOf(key, qty, live, fx) {
    var lv = live && live[key];
    if (!lv || !qty) return null;
    if (!USD_MKT.test(key)) return qty * lv.px;      // 한국주식·업비트 = 원화
    if (!fx) return null;
    return qty * lv.px * fx;
  }

  /**
   * 보유 전체의 준실시간 평가 — **전부 값이 있을 때만** 합계를 낸다.
   *
   * 일부만 더한 합계는 계좌를 실제보다 작게 보이게 한다. 그렇다고 조용히
   * 지우면 화면이 아무 말 없이 비는데, 그게 감사 213·220·226에서 고친
   * 바로 그 침묵이다. 그래서 못 받은 종목 목록(`missing`)을 함께 돌려주고
   * 화면이 이유를 말하게 한다.
   */
  function markHoldings(holdings, live, fx) {
    var rows = {}, missing = [], sumLive = 0, sumBook = 0, n = 0;
    (holdings || []).forEach(function (h) {
      if (!h || !h.key) return;
      var v = liveValueOf(h.key, Number(h.quantity) || 0, live, fx);
      if (v == null) {
        missing.push(String(h.key).split(":")[1] || h.key);
        return;
      }
      rows[h.key] = v;
      sumLive += v;
      sumBook += Number(h.value) || 0;
      n += 1;
    });
    var complete = n > 0 && missing.length === 0;
    return {
      rows: rows,
      missing: missing,
      marked: n,
      total: (holdings || []).length,
      // 합계는 **전부 받았을 때만** 존재한다 — 부분 합계는 내지 않는다
      sumLive: complete ? sumLive : null,
      sumBook: complete ? sumBook : null,
      complete: complete,
    };
  }

  /**
   * 신선도 문장 — "코인은 실시간, 주식은 지연"을 문장에 박지 않는다.
   *
   * 박아 두면 KIS 키를 붙여 한국주식이 실시간이 된 날에도 화면은 계속
   * 지연이라고 말한다. 받은 사실(`delayed`)을 세어서 만든다(감사 229).
   */
  function freshness(holdings, live) {
    var fresh = 0, late = 0;
    (holdings || []).forEach(function (h) {
      var lv = live && live[h.key];
      if (!lv) return;
      if (lv.delayed) late += 1; else fresh += 1;
    });
    if (!fresh && !late) return { fresh: 0, late: 0, text: "" };
    var text = late === 0
      ? "모든 보유 종목이 <b>실시간</b> 시세입니다"
      : (fresh === 0
        ? "보유 종목이 <b>지연 시세</b>로 평가돼 있습니다"
        : "실시간 " + fresh + "종목 · 지연 " + late + "종목");
    return { fresh: fresh, late: late, text: text };
  }

  /**
   * 지금 어느 장이든 열려 있는가 — 폴링 주기를 정하는 데만 쓴다.
   *
   * ⚠️ 시각을 **인자로** 받는다. `Date.now()`를 안에서 부르면 검사가 특정
   *    순간을 재현할 수 없고, 그러면 이 판정은 영영 검사되지 않는다.
   * 경계는 넉넉하게 — 조금 더 부르는 것이 장 초반을 놓치는 것보다 낫다.
   * (한국 09:00~15:40 / 미국 22:20~05:10, 전부 KST)
   */
  function marketOpenish(nowMs) {
    var kst = new Date(nowMs + 9 * 3600 * 1000);
    var d = kst.getUTCDay();
    var h = kst.getUTCHours() + kst.getUTCMinutes() / 60;
    if (d === 0) return false;                       // 일요일(KST) — 양쪽 휴장
    if (d >= 1 && d <= 5 && h >= 9 && h < 15.7) return true;          // 한국장
    if ((d >= 1 && d <= 5 && h >= 22.3) || (d >= 2 && d <= 6 && h < 5.2))
      return true;                                                    // 미국장
    return false;
  }

  root.QuantLive = {
    USD_MKT: USD_MKT,
    liveValueOf: liveValueOf,
    markHoldings: markHoldings,
    freshness: freshness,
    marketOpenish: marketOpenish,
  };
})(typeof globalThis !== "undefined" ? globalThis : this);
