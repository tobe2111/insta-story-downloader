/* 엔진 자동 선택 카드 — "지금 엔진은 누가, 왜 골랐나"에 답한다 (감사 341).
 *
 * 사장님(2026-10-10): "어떤 엔진을 선택할 지는 수익률에 따라서 머신러닝이
 * 결정하는거지 그걸 내가 결정하는건 아닌 것 같아."
 *
 * 쓰는 법: <div data-engine-select></div>
 * 숫자는 주간 선택기가 status.json의 `engine_select`에 실어 보낸 값이다 —
 * 여기서 계산하지 않는다(파이썬 짝: quant/portfolio/engine_select.py).
 *
 * ⚠️ 후보 표는 **낙폭을 수익 옆에** 둔다. 목표가 수익률이라 더 크게 흔들리는
 *    엔진이 뽑힐 수 있고, 그 대가를 같은 줄에서 읽을 수 있어야 한다.
 */
(function (root) {
  "use strict";

  var CSS =
    ".es{border:1px solid var(--line,#ddd);border-radius:10px;padding:14px 16px;" +
    "margin:14px 0;background:var(--bg2,transparent);color:var(--fg,inherit);" +
    "font-size:14px;line-height:1.6}" +
    ".es h2{font-size:16px;margin:0 0 6px}" +
    ".es h3{font-size:14px;margin:12px 0 4px}" +
    ".es .sub{color:var(--muted,#777);font-size:12.5px}" +
    ".es .tw{overflow-x:auto;-webkit-overflow-scrolling:touch}" +
    ".es table{border-collapse:collapse;width:100%;font-size:13px;margin-top:8px}" +
    ".es th,.es td{border-bottom:1px solid var(--line,#eee);padding:5px 6px;" +
    "text-align:left;white-space:nowrap}" +
    ".es td.n{text-align:right;font-variant-numeric:tabular-nums}" +
    ".es tr.on td{font-weight:600}" +
    ".es ul{margin:6px 0 0;padding-left:18px}";

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.appendChild(document.createTextNode(String(text)));
    return e;
  }

  function pct(v) {
    var n = Number(v);
    if (v == null || !isFinite(n)) return "—";
    return (n < 0 ? "−" : "") + Math.abs(n).toFixed(1) + "%";
  }

  /* 왜 이 엔진인가 — 선택기가 남긴 이유 코드를 말로. */
  var REASONS = {
    "switch": "최근 3년 수익률이 지금 엔진보다 우연이라 보기 어려울 만큼 높아 갈아탔습니다.",
    "incumbent_best": "최근 3년 수익률이 후보 중 가장 높아 그대로 둡니다.",
    "not_significant": "더 높은 후보가 있지만 차이가 우연과 구별되지 않아 그대로 둡니다.",
    "min_hold": "더 나은 후보가 있지만 갈아탄 지 3개월이 안 돼 그대로 둡니다.",
    "gate_failed": "고르는 규칙을 2016년부터 돌려 보니 기준 엔진을 그대로 둔 것보다 못해서, 기준 엔진을 씁니다.",
    "no_full_window": "3년치 자료가 있는 후보가 없어 그대로 둡니다.",
    "incumbent_unmeasured": "지금 엔진의 3년치 자료가 없어 그대로 둡니다.",
    "not_robust": "40종목에서는 더 나은 후보가 있지만, 규칙으로 고른 넓은 ETF 목록에서는 앞서지 못해 그대로 둡니다."
  };

  function render(box, es) {
    box.innerHTML = "";
    var card = el("div", "es");
    card.appendChild(el("h2", null, "지금 엔진은 누가 골랐나 — 수익률로 기계가 고릅니다"));
    var head = el("div");
    head.appendChild(el("span", null, "지금 엔진"));
    head.appendChild(document.createTextNode(" "));
    head.appendChild(el("b", null, es.active_label || es.active || "—"));
    head.appendChild(document.createTextNode(" · "));
    head.appendChild(el("span", null, "고른 날"));
    head.appendChild(document.createTextNode(" "));
    head.appendChild(el("b", null, es.asof || "—"));
    card.appendChild(head);
    var why = REASONS[es.reason];
    if (why) card.appendChild(el("div", "sub", why));

    var tw = el("div", "tw");
    var t = el("table");
    var hr = el("tr");
    ["후보", "최근 3년 연수익", "최근 3년 최대낙폭", "2016년 이후 연수익", "2016년 이후 최대낙폭"].forEach(function (h) {
      hr.appendChild(el("th", null, h));
    });
    t.appendChild(hr);
    var cands = es.candidates || {};
    Object.keys(cands).forEach(function (k) {
      var c = cands[k], w = c.window || {}, j = c.judge || {};
      var tr = el("tr", k === es.active ? "on" : null);
      tr.appendChild(el("td", null, c.label || k));
      tr.appendChild(el("td", "n", pct(w.cagr)));
      tr.appendChild(el("td", "n", pct(w.mdd)));
      tr.appendChild(el("td", "n", pct(j.cagr)));
      tr.appendChild(el("td", "n", pct(j.mdd)));
      t.appendChild(tr);
    });
    tw.appendChild(t);
    card.appendChild(tw);

    var g = es.gate || {}, s = g.selector || {}, b = g.baseline || {};
    var gl = el("div", "sub");
    gl.appendChild(el("span", null, "고르는 규칙 자체의 검증(2016년 이후)"));
    gl.appendChild(document.createTextNode(" — "));
    gl.appendChild(el("span", null, "규칙대로 갈아탔다면 연수익"));
    gl.appendChild(document.createTextNode(" "));
    gl.appendChild(el("b", null, pct(s.cagr)));
    gl.appendChild(document.createTextNode(" · "));
    gl.appendChild(el("span", null, "최대낙폭"));
    gl.appendChild(document.createTextNode(" "));
    gl.appendChild(el("b", null, pct(s.mdd)));
    gl.appendChild(document.createTextNode(" · "));
    gl.appendChild(el("span", null, "기준 엔진 그대로"));
    gl.appendChild(document.createTextNode(" "));
    gl.appendChild(el("b", null, pct(b.cagr)));
    gl.appendChild(document.createTextNode(" · "));
    gl.appendChild(el("b", null, g.pass ? "통과 — 규칙이 엔진을 정합니다" : "미달 — 기준 엔진을 씁니다"));
    card.appendChild(gl);

    // 생존 편향 점검(감사 342) — 같은 규칙을 규칙으로 고른 넓은 ETF 목록에서.
    var wd = g.wide;
    var wl = el("div", "sub");
    if (wd) {
      var ws = wd.selector || {}, wb = wd.baseline || {};
      wl.appendChild(el("span", null, "같은 규칙을 규칙으로 고른 넓은 ETF 목록에서"));
      wl.appendChild(document.createTextNode(" — "));
      wl.appendChild(el("span", null, "연수익"));
      wl.appendChild(document.createTextNode(" "));
      wl.appendChild(el("b", null, pct(ws.cagr)));
      wl.appendChild(document.createTextNode(" · "));
      wl.appendChild(el("span", null, "기준 엔진 그대로"));
      wl.appendChild(document.createTextNode(" "));
      wl.appendChild(el("b", null, pct(wb.cagr)));
      wl.appendChild(document.createTextNode(" · "));
      wl.appendChild(el("b", null, wd.pass ? "넓은 목록에서도 이김" : "넓은 목록에서는 못 이김"));
    } else {
      wl.appendChild(el("span", null, "넓은 ETF 목록 점검은 아직 못 쟀습니다 — 사람이 고른 40종목에서만 잰 결과입니다."));
    }
    card.appendChild(wl);

    // 후보 그림자 계좌(감사 342) — 같은 후보를 실제 배치 시세로 굴린 장부.
    var sh = root.__engineShadow;
    if (sh && sh.arms && Object.keys(sh.arms).length) {
      card.appendChild(el("h3", null, "후보마다 실제 시세로 굴린 가상 계좌"));
      var sl = el("div", "sub");
      sl.appendChild(el("span", null, "시작"));
      sl.appendChild(document.createTextNode(" "));
      sl.appendChild(el("b", null, sh.since || "—"));
      sl.appendChild(document.createTextNode(" · "));
      sl.appendChild(el("span", null, "기록한 날"));
      sl.appendChild(document.createTextNode(" "));
      sl.appendChild(el("b", null, String(sh.days == null ? "—" : sh.days)));
      card.appendChild(sl);
      var tw2 = el("div", "tw");
      var t2 = el("table");
      var h2 = el("tr");
      ["후보", "누적 수익", "최대낙폭", "낸 비용", "평균 투자 비중"].forEach(function (h) {
        h2.appendChild(el("th", null, h));
      });
      t2.appendChild(h2);
      Object.keys(sh.arms).forEach(function (k) {
        var a = sh.arms[k];
        var tr = el("tr", k === es.active ? "on" : null);
        tr.appendChild(el("td", null, a.label || k));
        tr.appendChild(el("td", "n", pct(a.return_pct)));
        tr.appendChild(el("td", "n", pct(a.worst_mdd_pct)));
        tr.appendChild(el("td", "n", pct(a.cost_pct)));
        tr.appendChild(el("td", "n", pct(a.avg_gross == null ? null : a.avg_gross * 100)));
        t2.appendChild(tr);
      });
      tw2.appendChild(t2);
      card.appendChild(tw2);
      card.appendChild(el("div", "sub", "고르는 데는 쓰지 않습니다 — 과거 시뮬레이션이 지금 실제와 맞는지 보는 계측기입니다. 정수 주는 맞추지 않아 본 계좌보다 약간 매끄럽습니다."));
    }

    var ul = el("ul", "sub");
    [
      "매주 금요일 종가로, 후보마다 최근 3년의 수수료·환전 뺀 연수익을 잽니다. 가장 높은 후보가 지금 엔진보다 우연이라 보기 어려울 만큼 앞설 때만 갈아타고, 갈아탄 뒤 3개월은 그대로 둡니다.",
      "최근 3년 최대낙폭이 −40%보다 나쁜 후보는 고르지 않습니다.",
      "숫자는 같은 코드·같은 비용으로 돌린 과거 시뮬레이션입니다. 앞으로의 수익을 약속하지 않습니다."
    ].forEach(function (x) { ul.appendChild(el("li", null, x)); });
    card.appendChild(ul);
    box.appendChild(card);
  }

  function boot() {
    var boxes = document.querySelectorAll("[data-engine-select]");
    if (!boxes.length) return;
    if (!document.getElementById("es-css")) {
      var st = document.createElement("style");
      st.id = "es-css";
      st.textContent = CSS;
      document.head.appendChild(st);
    }
    fetch("status.json").then(function (r) { return r.ok ? r.json() : null; })
      .then(function (s) {
        var es = s && s.engine_select;
        root.__engineShadow = s && s.engine_shadow;
        Array.prototype.forEach.call(boxes, function (b) { if (es) render(b, es); });
      })
      .catch(function () {});
  }

  root.EngineSelect = {render: render, REASONS: REASONS};
  if (typeof document === "undefined") return;
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})(typeof window !== "undefined" ? window : this);
