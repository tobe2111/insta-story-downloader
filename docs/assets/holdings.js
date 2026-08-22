/* 종목별 손익 표 — 실험 세 페이지가 **같은 한 곳**을 쓴다.
 *
 * 사장님 지시(2026-08-22): "각 페이지들의 결과값들이 종목마다 각 얼마
 * 현재 손해 혹은 이익인지 알려줘야 해."
 *
 * 왜 파일 하나로 모으나: 그리는 규칙을 세 페이지에 복사하면 언젠가
 * 갈라진다(FROZEN_IDEAS ①). 그러면 같은 날 코인 페이지와 선물 페이지가
 * 서로 다른 모양으로 손익을 말하게 된다.
 *
 * ⚠️ 숫자는 여기서 **계산하지 않는다.** 장부(quant/live/holdings.py)가
 *    계산해 실어 보낸 값을 그리기만 한다 — 화면이 자기 계산을 시작하면
 *    장부와 갈라진다(감사 197).
 *
 * ⚠️ 못 잰 칸은 '—'다. 0으로 그리면 '본전'이라는 뜻이 되고, 그건 모르는
 *    것을 아는 척하는 것이다.
 */
(function (root) {
  "use strict";

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return {"&": "&amp;", "<": "&lt;", ">": "&gt;",
              '"': "&quot;", "'": "&#39;"}[c];
    });
  }

  function num(v, d) {
    var n = Number(v);
    if (!isFinite(n)) return null;
    return n.toLocaleString("ko-KR",
      {minimumFractionDigits: d, maximumFractionDigits: d});
  }

  /* 수량은 종목마다 자릿수가 천차만별이다(리플 502주 vs 비트코인 0.0022주).
     고정 소수점으로 찍으면 한쪽이 통째로 0이 된다. */
  function qty(q) {
    var n = Math.abs(Number(q) || 0);
    if (n >= 100) return num(Math.round(n), 0);
    if (n >= 1) return n.toFixed(3);
    return n.toPrecision(3);
  }

  function price(v) {
    var n = Number(v);
    if (!isFinite(n) || n <= 0) return null;
    return num(n, n >= 100 ? 2 : (n >= 1 ? 4 : 6));
  }

  /* 표를 그린다. rows는 장부가 준 그대로. */
  function render(tbody, rows, cur) {
    if (!tbody) return;
    rows = rows || [];
    cur = cur || "USDT";
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="sub">' +
        '지금은 아무것도 안 들고 있습니다</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(function (r) {
      var short = r.direction === "short";
      var p = r.pnl, pp = r.pnl_pct;
      var known = (p != null && isFinite(Number(p)));
      var win = known && Number(p) >= 0;
      var pnlCell = known
        ? '<b class="' + (win ? "up" : "down") + '">' +
          (win ? "+" : "−") + num(Math.abs(Number(p)), 2) + '</b>' +
          (pp == null ? "" : '<div class="cd ' + (win ? "up" : "down") + '">' +
            (Number(pp) >= 0 ? "+" : "") + Number(pp).toFixed(2) + '%</div>')
        /* 시세를 못 받았거나 살 때 값이 기록에 없는 줄 — 지어내지 않는다. */
        : '<span class="sub" title="시세를 못 받았거나 살 때 값이 기록에 ' +
          '없어 아직 잴 수 없습니다 — 0원이라는 뜻이 아닙니다">—</span>';
      return '<tr><td style="text-align:left">' + esc(r.symbol) + '</td>' +
        /* 이 사이트는 오름이 빨강·내림이 파랑이다. 오름에 거는 롱이 빨강,
           내림에 거는 숏이 파랑 — 거는 방향을 따른다. */
        '<td class="' + (short ? "down" : "up") + '">' +
          (short ? "숏" : "롱") + '</td>' +
        '<td class="num">' + qty(r.quantity) + '</td>' +
        '<td class="num">' + (price(r.avg_cost) || '<span class="sub">—</span>') +
          '</td>' +
        '<td class="num">' + (price(r.last_price) || '<span class="sub">—</span>') +
          '</td>' +
        '<td class="num">' + (r.value == null
          ? '<span class="sub">—</span>'
          : num(Math.abs(Number(r.value)), 2)) + '</td>' +
        '<td class="num">' + pnlCell + '</td></tr>';
    }).join("");
  }

  /* 표 아래 한 줄 — 합계와, **못 잰 줄이 몇 개인지.**
     못 잰 줄을 조용히 빼고 합계만 보여 주면 그 합계는 사실이 아니다. */
  function note(el, total, cur) {
    if (!el) return;
    total = total || {};
    cur = cur || "USDT";
    var p = Number(total.pnl);
    if (!isFinite(p) || !total.counted) {
      el.textContent = "아직 잴 수 있는 보유가 없습니다.";
      return;
    }
    var win = p >= 0;
    el.innerHTML = '들고 있는 것 전부 합치면 지금 <b class="' +
      (win ? "up" : "down") + '">' + (win ? "+" : "−") +
      num(Math.abs(p), 2) + " " + esc(cur) + (win ? " 이익" : " 손해") +
      '</b>입니다 (' + total.counted + '종목 기준' +
      (total.unknown
        ? ' · ' + total.unknown + '종목은 아직 잴 수 없어 뺐습니다'
        : '') + ').' +
      ' 이 값은 <b>아직 안 판</b> 평가 손익입니다 — 팔 때 비용이 한 번 더 듭니다.';
  }

  root.QuantHoldings = { render: render, note: note };
})(typeof globalThis !== "undefined" ? globalThis : this);
