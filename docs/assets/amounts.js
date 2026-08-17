/**
 * 장부의 **금액**이 계좌와 앞뒤가 맞는가 — 화면 두 곳이 공유한다.
 *
 * ⚠️ 왜 이 파일이 생겼나 (2026-08-17, 감사 265 · 사장님 지적
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

  /**
   * 그날 기록 전체를 훑어 계좌보다 큰 금액을 찾는다.
   * 반환: {fills:[{key,amount}], lot_priority:[{key,spent}], equity} — 없으면 {}.
   */
  function overEquity(record) {
    var rec = record || {};
    var eq = Number(rec.equity);
    if (!isFinite(eq) || !(eq > 0)) return {};
    var out = {};
    var f = (rec.fills || []).filter(function (x) {
      return impossible(eq, x && x.amount);
    }).map(function (x) { return { key: x.key, amount: _num(x.amount) }; });
    if (f.length) out.fills = f;
    var lp = rec.lot_priority || {};
    var l = Object.keys(lp).sort().filter(function (k) {
      return impossible(eq, (lp[k] || {}).spent);
    }).map(function (k) { return { key: k, spent: _num((lp[k] || {}).spent) }; });
    if (l.length) out.lot_priority = l;
    if (f.length || l.length) out.equity = eq;
    return out;
  }

  /** 이 종목이 그날 기록에서 '못 믿을 금액'으로 걸렸는가. */
  function flagged(record, key, where) {
    var bad = overEquity(record)[where] || [];
    return bad.some(function (x) { return x.key === key; });
  }

  root.QuantAmounts = {
    SANITY_RATIO: SANITY_RATIO,
    impossible: impossible, overEquity: overEquity, flagged: flagged,
  };
})(typeof globalThis !== "undefined" ? globalThis : this);
