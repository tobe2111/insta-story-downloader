/**
 * 장부의 **금액**이 계좌와 앞뒤가 맞는가 — 화면 두 곳이 공유한다.
 *
 * ⚠️ 왜 이 파일이 생겼나 (2026-08-17, 감사 273 · 사장님 지적
 *    "홈페이지 내에서 지금 숫자들이 다 맞진 않은 것 같은데? 금액이 말이야.").
 *
 *    자산 997,198원짜리 계좌의 2026-08-15 기록에 이런 숫자들이 남아 있었고,
 *    사이트가 그대로 보여주고 있었다.
 *
 *        체결   아마존 매수 24,017.24주 · 6,361,687.93원   ← 자산의 6.4배
 *        예산   비앤비 4,526,594원 · 리플 4,084,420원      ← 합계 9.8배
 *
 *    레버리지가 잠긴 계좌에서 **한 건·한 종목이 계좌 전체보다 클 수는 없다.**
 *    그런 숫자는 시장이 아니라 코드가 만든 것이고, 거의 언제나 통화 환산이
 *    어딘가에서 빠진 것이다(감사 212·254가 그랬다).
 *
 *    **비중만 보는 검사로는 못 잡았다.** 그날 체결 비중은 0.0878, 총노출은
 *    0.4215 — 비중은 전부 정상 범위였다. 비중과 금액이 다른 통화로 계산되면
 *    한쪽만 보는 검사는 통과한다.
 *
 * 기록은 **고치지 않는다**(과거 불변). 대신 화면이 그 숫자를 사실처럼 말하지
 * 않게 한다 — 모르는 것과 아닌 것은 다르다.
 *
 * 파이썬 짝은 quant/live/daily.py의 amounts_over_equity이고,
 * tests/amounts_check.mjs가 이 파일을 그대로 실행해 값으로 확인한다.
 */
(function (root) {
  "use strict";

  // 파이썬 짝(daily.py AMOUNT_SANITY_RATIO)과 **같은 값이어야 한다.**
  var SANITY_RATIO = 1.02;

  function _num(v) {
    var x = Number(v);
    return isFinite(x) ? x : 0;
  }

  /** 이 금액이 그날 계좌로는 설명되지 않는가. */
  function impossible(equity, amount) {
    var eq = Number(equity);
    if (!isFinite(eq) || !(eq > 0)) return false;   // 모르면 의심하지 않는다
    return Math.abs(_num(amount)) > eq * SANITY_RATIO;
  }

  /** 두 목록을 key로 합친다(중복 제거) — 순서는 먼저 온 쪽을 지킨다. */
  function _merge(a, b) {
    var seen = {}, out = [];
    (a || []).concat(b || []).forEach(function (x) {
      if (!x || x.key == null || seen[x.key]) return;
      seen[x.key] = 1;
      out.push(x);
    });
    return out;
  }

  /**
   * 그날 기록 전체를 훑어 계좌보다 큰 금액을 찾는다.
   * 반환: {fills:[{key,amount}], lot_priority:[{key,spent}], equity} — 없으면 {}.
   *
   * ⚠️ **장부가 이미 적어 둔 판정을 먼저 읽는다**(감사 286). 배치는 같은
   *    검사를 파이썬 쪽에서 돌려 그 결과를 기록에 `impossible_amounts`로
   *    남긴다. 화면이 그것을 안 읽고 매번 다시 계산하면, 같은 규칙이 두
   *    곳에 살아 언젠가 갈라진다(FROZEN_IDEAS ①). 잣대가 달라지는 날
   *    장부는 "못 믿을 금액"이라 적어 두었는데 화면은 아무 일 없다는 듯
   *    그 숫자를 그대로 말하게 된다 — 가장 잡기 어려운 종류의 거짓말이다.
   *
   *    다시 계산하는 쪽도 남긴다. 이 필드가 생기기 전(2026-08-15까지)의
   *    기록에는 값이 없고, 그 시절 사고가 바로 이 장치를 만든 계기였다.
   *    둘을 합집합으로 쓴다 — 한쪽만 잡아도 화면은 말한다.
   */
  function overEquity(record) {
    var rec = record || {};
    var eq = Number(rec.equity);
    if (!isFinite(eq) || !(eq > 0)) return {};
    var out = {};
    var rekt = rec.impossible_amounts || {};
    var f = (rec.fills || []).filter(function (x) {
      return impossible(eq, x && x.amount);
    }).map(function (x) { return { key: x.key, amount: _num(x.amount) }; });
    f = _merge(rekt.fills, f);
    if (f.length) out.fills = f;
    var lp = rec.lot_priority || {};
    var l = Object.keys(lp).sort().filter(function (k) {
      return impossible(eq, (lp[k] || {}).spent);
    }).map(function (k) { return { key: k, spent: _num((lp[k] || {}).spent) }; });
    l = _merge(rekt.lot_priority, l);
    if (l.length) out.lot_priority = l;
    if (f.length || l.length) out.equity = eq;
    return out;
  }

  /** 이 종목이 그날 기록에서 '못 믿을 금액'으로 걸렸는가. */
  function flagged(record, key, where) {
    var bad = overEquity(record)[where] || [];
    return bad.some(function (x) { return x.key === key; });
  }

  /**
   * 준실시간 합계가 **확정 자산과 같은 세상의 숫자인가.**
   *
   * ⚠️ 왜 필요한가 (감사 275). 준실시간 값은 확정값과 조금 다른 게 정상이다
   *    — 그래서 `impossible()`의 1.02배 잣대를 그대로 쓸 수 없다. 하지만
   *    **자릿수가 다르면** 그건 시장이 아니라 환율·단위가 빠진 것이다.
   *    실제로 시세 경로에 환율이 빠지면 코인 평가액이 1,400배로 튄다
   *    (감사 212가 그 사고였고, 그때는 확정값 쪽에서 터졌다).
   *
   *    라벨만 붙이고 내보내면 "지금 35,969,655원"이 화면에 남는다 —
   *    100만원 계좌에서. 라벨은 그 숫자를 참으로 만들지 못한다.
   */
  var LIVE_MAX_DRIFT = 1.5;      // 하루 안에 자산이 1.5배가 되지는 않는다

  function livePlausible(book, live) {
    var b = Number(book), l = Number(live);
    if (!isFinite(b) || !isFinite(l) || !(b > 0)) return false;
    if (!(l > 0)) return false;
    var r = l / b;
    return r <= LIVE_MAX_DRIFT && r >= 1 / LIVE_MAX_DRIFT;
  }

  root.QuantAmounts = {
    LIVE_MAX_DRIFT: LIVE_MAX_DRIFT, livePlausible: livePlausible,
    SANITY_RATIO: SANITY_RATIO,
    impossible: impossible, overEquity: overEquity, flagged: flagged,
  };
})(typeof globalThis !== "undefined" ? globalThis : this);
