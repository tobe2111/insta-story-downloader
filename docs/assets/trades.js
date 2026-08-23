/* 최근 체결 표 — 실험 세 페이지가 **같은 한 곳**을 쓴다.
 *
 * 사장님 지적(2026-08-23): *"미국 주식은 투자를 하는 모습을 못봤네?"*
 *
 * 맞는 지적이었다. 미국주식 페이지에는 **체결 표가 아예 없었다.** 나흘
 * 동안 48번 사고팔았는데 화면에는 "체결 48건 / 21회"라는 숫자 하나뿐이라,
 * 무엇을 언제 얼마에 샀는지 읽는 사람이 알 방법이 없었다. 코인·선물
 * 페이지에는 있는 표가 미국 페이지에만 빠져 있었던 것이다.
 *
 * 고친 결함은 형제를 찾기 전까지 고친 게 아니다(FROZEN_IDEAS ⑭). 그래서
 * 미국 페이지에 표를 하나 더 베껴 넣지 않고, 세 페이지가 쓰던 그리기
 * 규칙을 여기 한 곳으로 모았다 — 베껴 넣으면 넷째 페이지가 또 빠진다.
 *
 * ⚠️ 실현 손익은 **매도(덮는 주문)에만** 있다. 새로 여는 주문에는 아직
 *    확정된 것이 없으므로 '—'다. 0으로 적으면 '본전'이라는 뜻이 된다.
 * ⚠️ 옛 기록에는 이 값이 아예 없다(그때 평균매입가를 안 세었다). 과거는
 *    고치지 않고 화면이 비워 둔다.
 */
(function (root) {
  "use strict";

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return {"&": "&amp;", "<": "&lt;", ">": "&gt;",
              '"': "&quot;", "'": "&#39;"}[c];
    });
  }

  function money(v, cur) {
    var n = Number(v);
    if (!isFinite(n)) return "—";
    return n.toLocaleString("ko-KR", {maximumFractionDigits: 2}) + " " + cur;
  }

  /* 시각 키가 트랙마다 다르다(코인·미국은 time, 선물은 at). 한쪽만 읽으면
     다른 트랙의 표가 통째로 '—'가 된다 — 둘 다 받는다. */
  function when(t) {
    return t.time || t.at || null;
  }

  /* 표를 그린다.
   *   rows  : 장부가 준 체결 목록(오래된 것이 앞). 최신이 위로 오게 뒤집는다.
   *   opts  : {currency, direction, verbs, kst}
   *           direction=true면 롱/숏 칸을 하나 더 그린다(선물).
   *           kst는 페이지의 한국시간 변환 함수 — 페이지마다 이미 있다.
   */
  function render(tbody, rows, opts) {
    if (!tbody) return;
    opts = opts || {};
    var cur = opts.currency || "USDT";
    var verbs = opts.verbs || ["매수", "매도"];
    var kst = opts.kst || function (s) { return s || "—"; };
    var cols = opts.direction ? 8 : 7;
    var trs = (rows || []).slice().reverse();
    if (!trs.length) {
      tbody.innerHTML = '<tr><td colspan="' + cols + '" class="sub">' +
        '아직 체결이 없습니다</td></tr>';
      return;
    }
    tbody.innerHTML = trs.map(function (t) {
      var r = t.realized_pnl;
      var known = (r != null && isFinite(Number(r)));
      var pnl = known
        ? '<b class="' + (Number(r) >= 0 ? "up" : "down") + '">' +
          (Number(r) >= 0 ? "+" : "−") + money(Math.abs(Number(r)), cur) + '</b>'
        : '<span class="sub" title="새로 여는 주문이거나, 평균매입가를 세기 ' +
          '전의 옛 기록입니다 — 0이라는 뜻이 아닙니다">—</span>';
      var sell = t.side === "sell";
      return '<tr><td>' + esc(kst(when(t))) + '</td>' +
        '<td>' + esc(t.symbol || "") + '</td>' +
        '<td class="' + (sell ? "down" : "up") + '">' +
          esc(sell ? verbs[1] : verbs[0]) + '</td>' +
        (opts.direction ? '<td>' + esc(t.direction || "") + '</td>' : '') +
        '<td>' + money(Math.abs(Number(t.notional) || 0), cur) + '</td>' +
        '<td>' + pnl + '</td>' +
        '<td>' + money(Number(t.cost) || 0, cur) + '</td>' +
        '<td>' + Number(t.signal || 0).toFixed(2) + '</td></tr>';
    }).join("");
  }

  /* "지금 자산의 몇 %를 굴리고 있나" 한 줄.
   *
   * 이 줄이 없으면 수익률만 남는다. 그러면 읽는 사람은 시드 전부를 굴린
   * 결과로 읽는다 — 실제로 자산의 3%만 들고 있었다면 전혀 다른 이야기다. */
  function deployed(el, d, cur) {
    if (!el) return;
    cur = cur || "USDT";
    if (!d || d.pct == null || !isFinite(Number(d.pct))) {
      el.textContent = "";
      return;
    }
    var pct = Number(d.pct);
    var idle = pct < 1.0;
    el.innerHTML = '지금 자산의 <b>' + pct.toFixed(1) + '%</b>' +
      '(' + money(d.gross, cur) + ')를 굴리고 있고, 나머지 <b>' +
      money(d.cash, cur) + '</b>은 현금입니다.' +
      (idle ? ' <span class="sub">— 신호가 약하면 조금만 사거나 아예 ' +
              '안 삽니다. 전량 현금은 고장이 아니라 "지금은 살 이유가 ' +
              '없다"는 판단입니다.</span>' : '') +
      (d.unknown ? ' <span class="sub">(' + d.unknown +
        '종목은 시세를 못 받아 이 계산에서 빠졌습니다 — 실제 비중은 이보다 ' +
        '클 수 있습니다.)</span>' : '');
  }

  /* "규칙이 바뀐 날" 목록.
   *
   * 실험 도중에 규칙을 바꾸면 곡선의 한 지점부터 성격이 달라진다. 그걸
   * 안 적으면 보는 사람은 이유를 모른 채 앞뒤를 같은 것으로 읽는다 —
   * 조용한 골대 이동이고, 이 저장소가 판정 시계에서 가장 엄격하게 막는
   * 것이다. 셋이 같은 모양으로 적게 여기 둔다(세 페이지가 이 파일을
   * 이미 부른다).
   *
   * 돌려주는 것은 <li> 문자열이다 — 페이지마다 '정직한 한계' 목록이
   * 놓이는 자리가 달라서, 그리는 자리는 페이지가 정한다.
   */
  function ruleChangeItems(changes) {
    return (changes || []).map(function (c) {
      return '<li><b class="up">' + esc(c.on) +
        ' — 규칙이 바뀌었습니다.</b> ' + esc(c.what) + ' ' + esc(c.why) +
        '</li>';
    }).join("");
  }

  root.QuantTrades = { render: render, deployed: deployed,
                       ruleChangeItems: ruleChangeItems };
})(typeof globalThis !== "undefined" ? globalThis : this);
