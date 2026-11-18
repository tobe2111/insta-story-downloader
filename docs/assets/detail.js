/* '자세히 보기' 버튼 — 머신러닝 · 기록 검증 페이지용 (2026-11-18).
 *
 * 사장님: "페이지들에 너무 문장들도 많고 필요이상의 TMI 같은 것들이 많달까?"
 *
 * 100만 챌린지와 트랙 페이지 셋은 이미 '간단히 / 자세히'로 접혀 있었다. 이 두
 * 페이지에도 같은 버튼을 단다 — 같은 열쇠(quant.detail)라 한 페이지에서 고른
 * 보기가 다른 페이지로 이어진다. 접히는 것은 `.adv`이고(규칙은 site.css 한 곳),
 * 지우는 것은 없다 — 누르면 전부 나온다.
 *
 * 쓰는 법: <div data-detail-toggle="접혀 있는 것의 이름들"></div> 자리에 버튼이
 * 들어간다. 무엇이 접혀 있는지 이름으로 말한다 — 안 그러면 아무도 안 누른다.
 */
(function () {
  "use strict";
  var KEY = "quant.detail";

  function mount(host) {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "dt-more";
    var what = host.getAttribute("data-detail-toggle") || "";
    function apply(on) {
      document.body.classList.toggle("detail", on);
      btn.setAttribute("aria-expanded", on ? "true" : "false");
      btn.textContent = "";
      btn.appendChild(document.createTextNode(on ? "간단히 보기 ▴" : "자세히 보기 ▾"));
      if (what) {
        btn.appendChild(document.createTextNode(" "));
        var s = document.createElement("span");
        s.className = "sub";
        s.textContent = what;
        btn.appendChild(s);
      }
    }
    var saved = null;
    try { saved = localStorage.getItem(KEY); } catch (e) { /* 저장소 없음 */ }
    apply(saved === "1");
    btn.onclick = function () {
      var on = !document.body.classList.contains("detail");
      apply(on);
      try { localStorage.setItem(KEY, on ? "1" : "0"); } catch (e) { /* 저장소 없음 */ }
    };
    host.appendChild(btn);
  }

  function init() {
    var hosts = document.querySelectorAll("[data-detail-toggle]");
    for (var i = 0; i < hosts.length; i++) mount(hosts[i]);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
