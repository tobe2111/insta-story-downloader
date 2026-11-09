/* 닫힌 트랙 안내 — 단타 두 트랙과 선물 트랙 (2026-11-09 감사 357).
 *
 * 쓰는 법: <div data-closed="intraday.json"></div>
 * 숫자는 장부가 실어 보낸 `closed` 칸만 읽는다(파이썬 짝: quant/live/track_closure.py).
 * 닫히지 않은 트랙이면 아무것도 그리지 않는다.
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
  function num(v) {
    if (v == null || isNaN(Number(v))) return "—";
    return Number(v).toLocaleString("en-US", { maximumFractionDigits: 2 });
  }
  function line(parent, label, value) {
    var d = el("div");
    d.appendChild(el("span", label));
    d.appendChild(document.createTextNode(" "));
    d.appendChild(el("b", value));
    parent.appendChild(d);
  }

  function render(box, c) {
    box.textContent = "";
    if (!c) { box.style.display = "none"; return; }
    box.appendChild(el("h2", "이 트랙은 닫았습니다"));
    line(box, "닫은 날", String(c.on || "—"));
    line(box, "최종 수익률(정리 비용 뺀 뒤)", pct(c.return_pct));
    line(box, "최종 자산", num(c.final_equity) + " " + String(c.currency || ""));
    line(box, "시작 자산", num(c.start_cash));
    line(box, "마지막 시세로 다 판 것으로 보고 뺀 정리 비용", num(c.exit_cost));
    line(box, "마지막 회차", String(c.last_round || "—"));
    var op = c.operated;
    if (op) {
      line(box, "운용 계좌 최종 수익률", pct(op.return_pct));
    }
    box.appendChild(el("div", "수수료를 뺀 성적이 그냥 보유보다 못했거나, 이길 근거가 없어 사장님 결정으로 판정일 전에 닫았습니다. 사전 등록을 판정일 전에 어긴 것이라 신뢰 페이지의 수정 이력에 적었습니다. 아래 기록은 지우지 않고 그대로 둡니다.", "sub"));
  }

  function boot() {
    var nodes = document.querySelectorAll("[data-closed]");
    Array.prototype.forEach.call(nodes, function (box) {
      fetch(box.getAttribute("data-closed"))
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) { render(box, d ? d.closed : null); })
        .catch(function () { box.style.display = "none"; });
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
