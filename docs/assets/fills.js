/**
 * "이 체결은 정말 체결인가" — 한 곳에서만 판정한다.
 *
 * ⚠️ 왜 이 파일이 생겼나 (2026-08-18, 감사 281). 사장님 지적:
 *    *"투자한 잔고는 지금 코인밖에 없고, 거래내역에는 주식이 있고..."*
 *    맞는 지적이고, 화면이 거짓말을 하고 있었다.
 *
 *    2026-08-15 기록에는 **같은 종목이 두 줄로** 들어 있다.
 *
 *        fills:      아마존 매수 24,017.24주 · 6,361,687.93원
 *        cash_short: 아마존 need 6,365,504.94 / cash 677,061.47
 *
 *    "샀다"와 "돈이 모자라 못 샀다"가 같은 날 같은 종목에 동시에 적혀
 *    있다. 잔고에 아마존은 **없다.** 그러니 진실은 "못 샀다"이고,
 *    체결 줄이 거짓이다(감사 273에서 원인은 고쳤지만 그날 기록은 남는다).
 *
 *    감사 273·274는 **금액만** 가렸다("확인 필요"). 그래서 화면에는
 *    여전히 "아마존 · 매수"라고 적혀 있었다 — 숫자를 가려도 **주장은
 *    그대로 남았다.** 절반만 고친 것이다. 한 주도 안 샀으면 그 줄은
 *    매수가 아니다.
 *
 * **기록은 고치지 않는다.** 대신 화면이 같은 기록의 다른 칸(`cash_short`
 * 등)을 읽어 무엇이 사실인지 고른다.
 *
 * 파이썬 짝은 없다 — 이 판정은 화면 표시 전용이다. 장부를 쓰는 쪽은
 * 2026-08-17부터 거부된 주문을 애초에 체결로 적지 않는다.
 */
(function (g) {
  "use strict";

  /* 거부 사유가 담기는 칸들. 이름이 다른 이유는 원인이 다르기 때문이다 —
     현금이 없어서(cash_short)와 증거금이 없어서(short_refused)는 사용자에게
     다른 이야기이므로 뭉치지 않는다. */
  var KINDS = [
    { field: "cash_short", why: "현금 부족" },
    { field: "short_refused", why: "증거금 부족" },
    { field: "rejected", why: "주문 거부" }
  ];

  function rowsOf(rec, field) {
    var v = rec && rec[field];
    if (!v) return [];
    if (Array.isArray(v)) return v;
    /* 객체 형태({key: {...}})도 받는다 — 장부 판이 바뀌어도 조용히
       빈손으로 돌아가지 않게 한다. */
    return Object.keys(v).map(function (k) { return { key: k }; });
  }

  /** 그날 **거부된** 주문의 사유. 없으면 null. */
  function refusal(rec, key) {
    if (!rec || !key) return null;
    for (var i = 0; i < KINDS.length; i++) {
      var rows = rowsOf(rec, KINDS[i].field);
      for (var j = 0; j < rows.length; j++) {
        if (rows[j] && rows[j].key === key) return KINDS[i].why;
      }
    }
    return null;
  }

  /**
   * 그 줄을 '체결'로 보여도 되는가.
   *
   * ⚠️ 같은 날 같은 종목에 체결과 거부가 **함께** 있으면 거부가 이긴다.
   *    한 주도 안 샀는데 "매수"라고 적는 것이 이 사이트에서 가장 하면
   *    안 되는 일이다.
   */
  function settled(rec, key) { return refusal(rec, key) === null; }

  /** 날짜 → 기록. 거래내역 줄에서 그날 기록을 찾을 때 쓴다. */
  function byDate(history) {
    var out = {};
    (history || []).forEach(function (r) {
      if (r && r.date) out[String(r.date).slice(0, 10)] = r;
    });
    return out;
  }

  g.QuantFills = { refusal: refusal, settled: settled, byDate: byDate };
})(typeof globalThis !== "undefined" ? globalThis : this);
