/* 운용 계좌 카드 — 단타냐 그냥 보유냐를 기계가 고른 계좌 (감사 345).
 *
 * 사장님(2026-10-11): "그냥 결과적으로 수익을 최대한 만들면 되는거야."
 *
 * 쓰는 법: <div data-operated="intraday.json"></div>
 * 숫자는 장부가 실어 보낸 `operated` 칸만 읽는다 — 여기서 계산하지 않는다
 * (파이썬 짝: quant/live/intraday_mode.py).
 *
 * ⚠️ 실험 계좌(사전 등록 90일)와 **다른 계좌**다. 화면이 그 사실을 먼저 말한다.
 * ⚠️ 글자와 숫자를 다른 노드에 둔다 — 번역기가 문장을 통째로 찾게.
 */
(function () {
  "use strict";

  function el(tag, text, cls) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.appendChild(document.createTextNode(String(text)));
    return e;
  }
  function pct(v) {
    if (v == null || isNaN(Number(v))) return "—";
    var n = Number(v);
    return (n > 0 ? "+" : "") + n.toFixed(2) + "%";
  }
  function line(parent, label, value) {
    var d = el("div");
    d.appendChild(el("span", label));
    d.appendChild(document.createTextNode(" "));
    d.appendChild(el("b", value));
    parent.appendChild(d);
    return d;
  }
  var REASON = {
    switch: "최근 성적 차이가 문턱을 넘어 갈아탔습니다.",
    keep: "차이가 문턱 아래라 지금 방식을 유지합니다.",
    min_hold: "갈아탄 지 얼마 안 돼 그대로 둡니다(최소 유지 기간).",
    not_enough_days: "비교할 날이 아직 모자라 지금 방식을 유지합니다."
  };

  function render(box, op) {
    box.textContent = "";
    if (!op) {
      box.appendChild(el("span", "운용 계좌가 아직 첫 회차를 돌지 않았습니다.", "sub"));
      return;
    }
    box.appendChild(el("p", "실험 계좌와 별개인 계좌입니다. 같은 시드·같은 종목·같은 비용으로, 후보 방식 중 수수료 뺀 성적이 나은 쪽을 기계가 매일 고릅니다.", "sub"));
    line(box, "지금 방식", op.mode_label || op.mode || "—");
    line(box, "운용 계좌 수익률(수수료 뺀 뒤)", pct(op.return_pct));
    line(box, "최대 낙폭", pct(op.mdd_pct));
    line(box, "낸 비용", String(op.cost_paid == null ? "—" : op.cost_paid));
    if (op.as_of) line(box, "기준일(하루 한 번, 그날 종가로 갱신)", String(op.as_of));
    if (op.mode_since) line(box, "지금 방식으로 바꾼 날", String(op.mode_since));
    line(box, "시작", String(op.since || "—"));
    if (op.inherited_from_experiment) {
      line(box, "단타 실험 계좌에서 이어받은 날", String(op.inherited_from_experiment));
    }
    var dec = op.decision || {};
    var labels = (op.rule && op.rule.modes) || {};
    if (dec.date) {
      var tbl = dec.table || {};
      var names = Object.keys(tbl);
      if (names.length) {
        var wrap = el("div", null, "tw");
        var t = el("table");
        var hr = el("tr");
        ["후보 방식", "최근 비교 기간 수익", "지금 방식보다 앞선 정도(t)", "비교한 날 수"].forEach(function (h) {
          hr.appendChild(el("th", h));
        });
        t.appendChild(hr);
        names.forEach(function (m) {
          var r = tbl[m] || {};
          var tr = el("tr");
          var nm = el("td", labels[m] || m);
          if (m === dec.incumbent) {
            nm.appendChild(document.createTextNode(" "));
            nm.appendChild(el("b", "← 지금"));
          }
          tr.appendChild(nm);
          tr.appendChild(el("td", pct(r.pct)));
          tr.appendChild(el("td", r.t == null ? "—" : String(r.t)));
          tr.appendChild(el("td", r.n == null ? "—" : String(r.n)));
          t.appendChild(tr);
        });
        wrap.appendChild(t);
        box.appendChild(wrap);
      } else {
        line(box, "최근 비교 기간 · 단타", pct(dec.trade_pct));
        line(box, "최근 비교 기간 · 그냥 보유", pct(dec.hold_pct));
        line(box, "비교한 날 수", String(dec.n_days == null ? "—" : dec.n_days));
      }
      line(box, "갈아타는 문턱(t)", dec.t_needed == null ? "—" : String(dec.t_needed));
      if (REASON[dec.reason]) box.appendChild(el("div", REASON[dec.reason], "sub"));
    }
    box.appendChild(el("div", "과거에 나았던 쪽이 앞으로도 낫다는 보장은 없습니다. 그래서 문턱과 최소 유지 기간을 둡니다.", "sub"));
  }

  function boot() {
    var nodes = document.querySelectorAll("[data-operated]");
    Array.prototype.forEach.call(nodes, function (box) {
      fetch(box.getAttribute("data-operated"))
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) { render(box, d ? d.operated : null); })
        .catch(function () {
          box.textContent = "";
          box.appendChild(el("span", "운용 계좌를 불러오지 못했습니다.", "sub"));
        });
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
