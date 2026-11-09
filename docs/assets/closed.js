/* 닫힌 트랙 안내 — 단타 두 트랙과 선물 트랙 (2026-11-09 감사 357).
 *
 * 쓰는 법: <div data-closed="intraday.json"></div>
 * 숫자는 장부가 실어 보낸 `closed` 칸만 읽는다(파이썬 짝: quant/live/track_closure.py).
 * 닫히지 않은 트랙이면 아무것도 그리지 않는다. 다시 연 트랙(`season`, 감사 366)이면
 * 지금 몇 기인지와 지난 기의 최종 성적을 그린다.
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

  // 2기(감사 366) — 닫았다 다시 연 트랙은 지금 몇 기인지와 지난 기의 최종 성적을 싣는다.
  function renderSeason(box, s) {
    box.textContent = "";
    box.style.display = "";
    box.appendChild(el("h2", "닫았던 트랙을 다시 열었습니다"));
    line(box, "지금", String(s.n) + "기");
    line(box, "시작한 날", String(s.since || "—"));
    line(box, "이어받은 현금", num(s.start_equity));
    line(box, "이번 기 수익률", pct(s.return_pct));
    if (s.operated_return_pct != null) line(box, "이번 기 운용 계좌 수익률", pct(s.operated_return_pct));
    (s.previous || []).forEach(function (p) {
      var d = el("div", null, "sub");
      d.appendChild(el("span", String(p.n) + "기"));
      d.appendChild(document.createTextNode(" "));
      d.appendChild(el("span", "최종 수익률(정리 비용 뺀 뒤)"));
      d.appendChild(document.createTextNode(" "));
      d.appendChild(el("b", pct(p.return_pct)));
      d.appendChild(document.createTextNode(" · "));
      d.appendChild(el("span", "닫은 날"));
      d.appendChild(document.createTextNode(" "));
      d.appendChild(el("b", String(p.on || "—")));
      if (p.operated_return_pct != null) {
        d.appendChild(document.createTextNode(" · "));
        d.appendChild(el("span", "운용 계좌 최종 수익률"));
        d.appendChild(document.createTextNode(" "));
        d.appendChild(el("b", pct(p.operated_return_pct)));
      }
      box.appendChild(d);
    });
    box.appendChild(el("div", "지난 기의 최종 자산(정리 비용 뺀 값)을 현금으로 이어받았습니다. 누적 수익률은 처음 시작 자산에서 끊김 없이 이어집니다. 이번 기는 운용 계좌가 첫날부터 단타와 그냥 보유(선물은 현금까지) 중에서 고르는 새 실험이고, 판정 기준은 신뢰 페이지에 새로 등록했습니다.", "sub"));
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
        .then(function (d) {
          if (d && d.season && !d.closed) renderSeason(box, d.season);
          else render(box, d ? d.closed : null);
        })
        .catch(function () { box.style.display = "none"; });
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
