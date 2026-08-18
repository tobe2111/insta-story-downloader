/* 공용 상단 바 — index.html(홈)의 바와 같은 모습을 모든 공개 페이지에 얹는다.
 *
 * 왜 이렇게 하나: 페이지마다 손으로 만든 미니 nav가 제각각이었다(홈으로 가는
 * 링크만 있는 페이지, 링크 순서가 다른 페이지). 바를 한 파일로 모으면 "같은
 * 사실은 한 곳에서만 산다"는 이 저장소의 규칙이 화면에도 적용된다.
 * 링크 구성이 index.html의 <nav>와 어긋나면 계약 테스트가 잡는다
 * (tests/test_the_site_wears_one_navbar.py).
 *
 * 색은 페이지의 CSS 변수(--bg·--fg·--muted·--line·--accent)를 그대로 쓰므로
 * 밝은 페이지에서는 밝은 바, 어두운 페이지에서는 어두운 바가 된다 — 홈과
 * 같은 동작이다. 변수가 없는 페이지를 위해 홈의 어두운 팔레트를 기본값으로
 * 깔아 둔다.
 */
(function () {
  "use strict";

  // index.html의 nav 링크와 1:1 — 순서까지 같아야 한다(계약 테스트 대상).
  var LINKS = [
    ["paper.html", "실시간 현황"],
    ["today.html", "오늘의 판단"],
    ["trust.html", "기록 검증"],
    ["intraday.html", "장중 실험"],
    ["weekly.html", "주간 아카이브"]
  ];
  var DL = "https://github.com/tobe2111/insta-story-downloader/releases/latest";

  var css = [
    "#qnav{position:sticky;top:0;z-index:60;height:56px;",
    "  border-bottom:1px solid var(--line,#1e2128);",
    "  background:color-mix(in srgb,var(--bg,#0a0b0e) 88%,transparent);",
    "  backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px)}",
    "@supports not (background:color-mix(in srgb,red 50%,blue)){",
    "  #qnav{background:var(--bg,#0a0b0e)}}",
    "#qnav .qn-in{height:100%;display:flex;align-items:center;gap:4px;",
    "  padding:0 22px}",
    "#qnav .qn-logo{font-weight:800;font-size:15px;letter-spacing:.14em;",
    "  color:var(--fg,#f4f5f7);margin-right:18px;text-decoration:none}",
    "#qnav .qn-logo em{font-style:normal;color:var(--accent,#4c7dff)}",
    "#qnav .qn-lnk{color:var(--muted,#8f96a3);font-size:13.5px;font-weight:500;",
    "  padding:6px 12px;border-radius:7px;white-space:nowrap;text-decoration:none}",
    "#qnav .qn-lnk:hover{color:var(--fg,#f4f5f7);",
    "  background:var(--bg2,#0e1013);text-decoration:none}",
    "#qnav .qn-lnk.qn-here{color:var(--fg,#f4f5f7);background:var(--bg2,#0e1013)}",
    "#qnav .qn-sp{margin-left:auto}",
    "#qnav .qn-cta{display:inline-flex;align-items:center;gap:7px;font-size:13px;",
    "  font-weight:700;color:#fff;background:var(--accent,#4c7dff);",
    "  padding:8px 16px;border-radius:9px;white-space:nowrap;text-decoration:none}",
    "#qnav .qn-cta:hover{text-decoration:none;filter:brightness(1.08)}",
    /* 페이지 전역 svg 규칙(예: intraday의 차트용 svg{width:100%})에
       아이콘이 끌려가지 않게 크기를 바 쪽에서 못박는다. */
    "#qnav .qn-cta svg{width:15px;height:15px;display:inline-block;margin:0}",
    "#qnav .qn-ver{font-size:11px;color:var(--muted,#8f96a3);margin-left:9px;",
    "  white-space:nowrap}",
    "@media(max-width:820px){#qnav .qn-lnk{display:none}}"
  ].join("\n");

  function esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function build() {
    if (document.getElementById("qnav")) return;   // 두 번 실행돼도 바는 하나

    var here = (location.pathname.split("/").pop() || "index.html");
    var html = ['<div class="qn-in">',
      '<a class="qn-logo" href="index.html">QUANT<em>.</em></a>'];
    for (var i = 0; i < LINKS.length; i++) {
      var active = LINKS[i][0] === here ? " qn-here" : "";
      html.push('<a class="qn-lnk' + active + '" href="' + esc(LINKS[i][0]) +
        '">' + esc(LINKS[i][1]) + "</a>");
    }
    html.push('<span class="qn-sp"></span>');
    html.push('<a class="qn-cta" href="' + DL + '">' +
      '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" ' +
      'stroke="currentColor" stroke-width="2.2" stroke-linecap="round" ' +
      'stroke-linejoin="round"><path d="M12 3v12"/><path d="m7 10 5 5 5-5"/>' +
      '<path d="M5 21h14"/></svg>무료 다운로드</a>');
    html.push('<span class="qn-ver" id="qnav-ver"></span>');
    html.push("</div>");

    var style = document.createElement("style");
    style.textContent = css;
    document.head.appendChild(style);

    var bar = document.createElement("header");
    bar.id = "qnav";
    bar.innerHTML = html.join("");
    document.body.insertBefore(bar, document.body.firstChild);

    // 페이지 고유 요소(예: paper.html의 '라이브 보는 중' 버튼)를 바 안으로.
    var extras = document.querySelectorAll("[data-qnav-extra]");
    var sp = bar.querySelector(".qn-sp");
    for (var j = 0; j < extras.length; j++) {
      sp.parentNode.insertBefore(extras[j], sp.nextSibling);
    }

    // 최신 릴리스 버전 — 실패해도 무해(빈 칸으로 남는다).
    fetch("https://api.github.com/repos/tobe2111/insta-story-downloader/releases/latest")
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) {
        if (j && j.tag_name) {
          document.getElementById("qnav-ver").textContent = j.tag_name;
        }
      }).catch(function () {});
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", build);
  } else {
    build();
  }
})();
