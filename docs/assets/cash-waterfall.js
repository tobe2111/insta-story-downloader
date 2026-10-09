/* 현금이 왜 이만큼 남았나 — 본 계좌의 비중이 줄어드는 단계를 한 표로.
 *
 * 사장님 질문(2026-10-01): "현금은 왜 계속 이 비율로 들고있는거야?"
 * → 답을 들은 뒤(2026-10-06): "둘 다 진행" — 단계 표 + 넘친 예산 재분배 그림자.
 *
 * 쓰는 법: <div data-cash-waterfall></div>
 * 숫자는 배치가 장부에 남긴 `cash_waterfall`(본 계좌 마지막 줄)과
 * status.json의 `budget_shadow`다 — 여기서 계산하지 않는다
 * (파이썬 짝: quant/live/daily.py cash_waterfall · quant/live/budget_shadow.py).
 *
 * ⚠️ 한국어 조각은 값과 다른 텍스트 노드에 둔다(번역기는 노드를 통째로 찾는다).
 */
(function (root) {
  "use strict";

  var CSS =
    ".cw{border:1px solid var(--line,#ddd);border-radius:10px;padding:14px 16px;" +
    "margin:14px 0;background:var(--bg2,transparent);color:var(--fg,inherit);" +
    "font-size:14px;line-height:1.6}" +
    ".cw h2{font-size:16px;margin:0 0 6px}.cw h3{font-size:14px;margin:14px 0 4px}" +
    ".cw .sub{color:var(--muted,#777);font-size:12.5px}" +
    ".cw .tw{overflow-x:auto;-webkit-overflow-scrolling:touch}" +
    ".cw table{border-collapse:collapse;width:100%;font-size:13px;margin-top:6px}" +
    ".cw th,.cw td{border-bottom:1px solid var(--line,#eee);padding:5px 6px;text-align:left}" +
    ".cw td.n,.cw th.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap;width:1%}" +
    ".cw .bar{display:block;height:4px;border-radius:2px;background:var(--accent,#3b82f6);" +
    "margin-top:3px;opacity:.6;max-width:100%}" +
    ".cw ul{margin:6px 0 0;padding-left:18px}";

  // 단계 이름은 배치가 적는 열쇠 순서 그대로다.
  var STAGES = [
    ["budget_raw", "종목별 배분 예산(상한 전)"],
    ["budget", "종목당 상한을 넘친 몫을 버린 뒤"],
    ["signal", "모델 신호 크기를 곱하면"],
    ["risk", "목표 변동성까지 키우면(브레이크·실적 가드 포함)"],
    ["gated", "검증 관문·켈리 상한을 지나면"],
    ["applied", "1주 단위·종목 상한을 맞춘 실제 투자"]
  ];
  var ARMS = [["discard", "버림(지금 규칙)"], ["redistribute", "다시 나눔"]];

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.appendChild(document.createTextNode(String(text)));
    return e;
  }
  function pct(v, d) {
    var n = Number(v);
    if (!isFinite(n)) return "—";
    return (n * 100).toFixed(d == null ? 1 : d) + "%";
  }
  function line(cls, parts) {
    var p = el("div", cls);
    parts.forEach(function (x) {
      if (x == null || x === "") return;
      if (typeof x === "object" && x.b != null) p.appendChild(el("b", null, x.b));
      else p.appendChild(el("span", null, x));
    });
    return p;
  }

  function lastRow(st) {
    var paper = (st && st.paper) || {};
    var key = Object.keys(paper).find(function (k) { return k.indexOf("portfolio:") === 0; });
    var h = key ? (paper[key].history || []) : [];
    for (var i = h.length - 1; i >= 0; i--) if (h[i] && h[i].cash_waterfall) return h[i];
    return null;
  }

  function render(box, st) {
    var row = lastRow(st);
    var bs = st && st.budget_shadow;
    if (!row && !bs) return;
    box.innerHTML = "";
    var card = el("div", "cw");
    card.appendChild(el("h2", null, "현금이 왜 이만큼 남았나 — 투자 비중이 줄어드는 단계"));
    if (row) {
      var w = row.cash_waterfall;
      card.appendChild(line("sub", ["기준일", " ", {b: row.date}, " · ",
        "각 줄은 그 단계까지 남은 투자 비중(자산 대비)입니다."]));
      if (row.engine) {
        // 엔진 전환(감사 335) — 이 표는 챔피언 체계의 계산이라 오늘 주문과 다르다.
        card.appendChild(line("sub", ["오늘 비중은 추세 코어가 정했습니다 — 아래 단계표는 이전 체계(챔피언)의 계산으로, 참고용입니다."]));
      }
      var tw = el("div", "tw");
      var t = el("table");
      var hr = el("tr");
      hr.appendChild(el("th", null, "단계"));
      hr.appendChild(el("th", "n", "투자 비중"));
      t.appendChild(hr);
      STAGES.forEach(function (s) {
        var v = w[s[0]];
        var tr = el("tr");
        tr.appendChild(el("td", null, s[1]));
        var td = el("td", "n", pct(v));
        tr.appendChild(td);
        // 막대는 이름 칸 아래에 — 숫자 칸을 넓히면 휴대폰에서 숫자가 밀려난다.
        var bar = el("span", "bar");
        bar.style.width = Math.max(0, Math.min(100, Number(v) * 100)) + "%";
        tr.firstChild.appendChild(bar);
        t.appendChild(tr);
      });
      var trc = el("tr");
      trc.appendChild(el("td", null, "현금으로 남은 몫"));
      trc.appendChild(el("td", "n", pct(w.cash)));
      t.appendChild(trc);
      tw.appendChild(t);
      card.appendChild(tw);
      var ul = el("ul", "sub");
      var g = w.gate_counts || {};
      var li = el("li");
      li.appendChild(el("span", null, "검증 관문"));
      li.appendChild(document.createTextNode(" — "));
      li.appendChild(el("span", null, "그대로"));
      li.appendChild(el("b", null, " " + (g.full || 0)));
      li.appendChild(document.createTextNode(" · "));
      li.appendChild(el("span", null, "비중 줄임"));
      li.appendChild(el("b", null, " " + (g.partial || 0)));
      li.appendChild(document.createTextNode(" · "));
      li.appendChild(el("span", null, "비중 0으로"));
      li.appendChild(el("b", null, " " + (g.zero || 0)));
      ul.appendChild(li);
      if (w.deferred_lots) {
        var li2 = el("li");
        li2.appendChild(el("span", null, "1주 값이 배정 예산보다 비싸 오늘 못 산 종목"));
        li2.appendChild(el("b", null, " " + w.deferred_lots));
        ul.appendChild(li2);
      }
      [
        "목표 변동성 단계가 100%를 넘을 수 있습니다 — 위험 예산은 남는데 다른 장치(검증 관문·종목 상한)가 막고 있다는 뜻이고, 계좌는 빚을 내지 않으므로 실제로는 100%를 넘지 않습니다.",
        "검증 관문은 과최적화 검사를 통과하지 못한 규칙에 작게 거는 안전장치입니다 — 실력이 입증되면 저절로 풀립니다."
      ].forEach(function (s) { ul.appendChild(el("li", null, s)); });
      card.appendChild(ul);
    }

    card.appendChild(el("h3", null, "넘친 예산을 버리지 않고 다시 나누면? — 가상 계좌 둘"));
    if (!bs) {
      card.appendChild(line("sub", ["이 비교는 등록일(2026-10-06) 밤 배치부터 기록됩니다."]));
    } else {
      var tw2 = el("div", "tw");
      var t2 = el("table");
      var h2 = el("tr");
      ["계좌", "수익률", "평균 배분 예산", "평균 투자 비중", "최대낙폭"].forEach(function (h) {
        h2.appendChild(el("th", null, h));
      });
      t2.appendChild(h2);
      ARMS.forEach(function (a) {
        var r = (bs.arms || {})[a[0]] || {};
        var tr = el("tr");
        tr.appendChild(el("td", null, a[1]));
        var rp = Number(r.return_pct);
        tr.appendChild(el("td", "n", isFinite(rp) ? (rp > 0 ? "+" : "") + rp.toFixed(2) + "%" : "—"));
        tr.appendChild(el("td", "n", pct(r.avg_budget)));
        tr.appendChild(el("td", "n", pct(r.avg_gross)));
        var md = Number(r.worst_mdd_pct);
        tr.appendChild(el("td", "n", isFinite(md) ? md.toFixed(2) + "%" : "—"));
        t2.appendChild(tr);
      });
      tw2.appendChild(t2);
      card.appendChild(tw2);
      var pr = bs.paired || {};
      card.appendChild(line("sub", [
        "다시 나눔 − 버림, 하루 평균", " ",
        {b: pr.mean_bp_per_day == null ? "—" : pr.mean_bp_per_day + "bp"}, " · ",
        "t", " ", {b: pr.t == null ? "—" : pr.t}, " · ",
        "관측", " ", {b: String(pr.n || 0)}, " · ",
        "판정일", " ", {b: bs.judge_on || "—"}]));
      if (bs.note) card.appendChild(line("sub", [bs.note]));
    }
    box.appendChild(card);
  }

  function boot() {
    var boxes = document.querySelectorAll("[data-cash-waterfall]");
    if (!boxes.length) return;
    if (!document.getElementById("cw-css")) {
      var s = document.createElement("style");
      s.id = "cw-css";
      s.textContent = CSS;
      document.head.appendChild(s);
    }
    fetch("status.json").then(function (r) { return r.ok ? r.json() : null; })
      .then(function (st) {
        Array.prototype.forEach.call(boxes, function (b) { if (st) render(b, st); });
      })
      .catch(function () {});
  }

  root.CashWaterfall = {render: render, lastRow: lastRow, STAGES: STAGES};
  if (typeof document === "undefined") return;   // node 검사에서 불러올 때
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})(typeof window !== "undefined" ? window : this);
