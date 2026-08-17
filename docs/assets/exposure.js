/**
 * 종목별 실제 노출(장부의 `applied`)을 **부호까지 지켜서** 읽는 규칙 —
 * 화면 세 곳(첫 화면·오늘·SNS 카드)이 공유한다.
 *
 * ⚠️ 왜 이 파일이 생겼나 (2026-08-17, 감사 264).
 *    장부는 오랫동안 노출을 `abs()`로 적었다. 그래서 **숏 -30%와 롱 +30%가
 *    화면에 똑같이 `30%`로 남았다.** 지금은 숏이 링에 없어 값이 늘 양수라
 *    아무도 눈치채지 못한다 — 숏을 켜는 날, 화면은 "아마존 30% 보유"라고
 *    말하면서 실제로는 아마존을 **팔아 둔** 상태가 된다. 방송에 나가는
 *    숫자라 사이트보다 오히려 더 위험하다(감사 238과 같은 계열).
 *
 *    부호를 살리는 것만으로는 부족했다. 화면 네 곳이 각자
 *    `applied[k] > 0`을 "들고 있다"의 뜻으로 쓰고 있어서, 부호를 살리면
 *    **숏이 '보유 없음'으로 사라진다.** 판정을 한 곳에 모으는 이유다
 *    (FROZEN_IDEAS ①·㉞ — 같은 판정을 두 곳에서 쓰면 언젠가 갈라진다).
 *
 * 파이썬 짝은 quant/reporting/exposure.py이고,
 * tests/exposure_check.mjs가 이 파일을 그대로 실행해 값으로 확인한다.
 */
(function (root) {
  "use strict";

  /** 이 종목을 지금 **잡고 있는가** — 롱이든 숏이든. */
  function held(v) {
    var x = Number(v);
    return isFinite(x) && Math.abs(x) > 0;
  }

  /** 잡고 있는 종목 수 (롱 + 숏). */
  function count(applied) {
    if (!applied) return 0;
    var n = 0;
    Object.keys(applied).forEach(function (k) { if (held(applied[k])) n++; });
    return n;
  }

  /** 방향 — 롱이면 "", 숏이면 "숏 ". 문구 앞에 그대로 붙인다. */
  function side(v) {
    return Number(v) < 0 ? "숏 " : "";
  }

  /**
   * 화면에 찍을 노출 문자열. **크기는 절댓값, 방향은 말로** 적는다.
   * `-30%`라고만 쓰면 "손실 30%"로 읽힌다 — 방향은 부호가 아니라 글자로.
   */
  function text(v, digits) {
    if (!held(v)) return "0%";
    var x = Number(v);
    return side(x) + (Math.abs(x) * 100).toFixed(digits == null ? 2 : digits) + "%";
  }

  /**
   * 큰 것부터 n개 — **크기(절댓값) 기준**이다. 부호로 정렬하면 숏이
   * 아무리 커도 목록 맨 끝으로 밀려 "오늘 어디에 실었나"에 답하지 못한다.
   */
  function top(applied, n) {
    if (!applied) return [];
    return Object.keys(applied)
      .filter(function (k) { return held(applied[k]); })
      .map(function (k) { return [k, Number(applied[k])]; })
      .sort(function (a, b) { return Math.abs(b[1]) - Math.abs(a[1]); })
      .slice(0, n == null ? 5 : n);
  }

  /** 총노출 Σ|w| — "얼마가 시장에 나가 있나". */
  function gross(applied) {
    if (!applied) return 0;
    return Object.keys(applied).reduce(function (s, k) {
      var x = Number(applied[k]);
      return s + (isFinite(x) ? Math.abs(x) : 0);
    }, 0);
  }

  /**
   * 순노출 Σw — "시장이 오르면 이득인가". 롱숏이 반반이면 총노출은
   * 100%인데 순노출은 0%(시장 중립)다. 총노출만 적으면 그 구별이 사라진다.
   */
  function net(applied) {
    if (!applied) return 0;
    return Object.keys(applied).reduce(function (s, k) {
      var x = Number(applied[k]);
      return s + (isFinite(x) ? x : 0);
    }, 0);
  }

  root.QuantExposure = {
    held: held, count: count, side: side, text: text,
    top: top, gross: gross, net: net,
  };
})(typeof globalThis !== "undefined" ? globalThis : this);
