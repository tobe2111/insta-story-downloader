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
  // ⚠️ **트랙 넷이 앞에, 나란히**(2026-08-22 사장님 지시). 계좌가 넷이면
  //    페이지도 넷이다 — 한 페이지에 두 계좌를 얹으면 읽는 사람이 매번
  //    어느 숫자가 어느 계좌 것인지 골라내야 한다.
  var LINKS = [
    ["index.html", "100만 챌린지"],
    ["intraday.html", "코인 단타"],
    ["us.html", "미국주식 단타"],
    ["futures.html", "코인 선물"],
    // paper.html은 100만 챌린지의 '자세히 보기'다 — 트랙 넷을 앞으로
    // 뽑으면서 뒤로 옮겼을 뿐, 감추지 않는다.
    ["paper.html", "실기록 (100만)"],
    ["today.html", "오늘의 판단"],
    ["trust.html", "기록 검증"],
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
    /* 삼단 바(모바일 메뉴 버튼, 2026-08-23 사장님: "모바일로 보면 다른
       페이지를 볼 수가 없어"). 그 전까지 820px 아래에서는 링크를 숨기기만
       했다 — 숨긴 자리에 대체 수단이 없으면 그건 정리가 아니라 차단이다. */
    "#qnav .qn-burger{display:none;background:none;border:0;cursor:pointer;",
    "  padding:9px;margin-left:6px;color:var(--fg,#f4f5f7);border-radius:8px}",
    "#qnav .qn-burger:hover{background:var(--bg2,#0e1013)}",
    "#qnav .qn-burger svg{width:22px;height:22px;display:block}",
    "#qnav .qn-menu{display:none;position:absolute;top:56px;left:0;right:0;",
    "  flex-direction:column;gap:2px;padding:8px 14px 14px;",
    "  background:var(--bg,#0a0b0e);border-bottom:1px solid var(--line,#1e2128)}",
    "#qnav.qn-open .qn-menu{display:flex}",
    "#qnav .qn-menu a{color:var(--muted,#8f96a3);font-size:15px;font-weight:500;",
    "  padding:11px 12px;border-radius:8px;text-decoration:none}",
    "#qnav .qn-menu a.qn-here{color:var(--fg,#f4f5f7);",
    "  background:var(--bg2,#0e1013)}",
    "@media(max-width:820px){#qnav .qn-lnk{display:none}",
    "  #qnav .qn-burger{display:inline-flex}}",
    "@media(min-width:821px){#qnav .qn-menu{display:none !important}}"
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
    // 삼단 바 버튼 + 세로 메뉴 — 링크 목록은 위 LINKS **그대로**다(같은
    // 사실은 한 곳에서만 산다). 데스크톱에서는 CSS가 버튼·메뉴를 숨긴다.
    html.push('<button class="qn-burger" type="button" aria-label="메뉴 열기" ' +
      'aria-expanded="false"><svg viewBox="0 0 24 24" fill="none" ' +
      'stroke="currentColor" stroke-width="2.2" stroke-linecap="round">' +
      '<path d="M4 6h16"/><path d="M4 12h16"/><path d="M4 18h16"/></svg>' +
      "</button>");
    html.push('<div class="qn-menu">');
    for (var k = 0; k < LINKS.length; k++) {
      var act = LINKS[k][0] === here ? " qn-here" : "";
      html.push('<a class="' + act.replace(" ", "") + '" href="' +
        esc(LINKS[k][0]) + '">' + esc(LINKS[k][1]) + "</a>");
    }
    html.push("</div>");
    html.push("</div>");

    var style = document.createElement("style");
    style.textContent = css;
    document.head.appendChild(style);

    var bar = document.createElement("header");
    bar.id = "qnav";
    bar.innerHTML = html.join("");
    document.body.insertBefore(bar, document.body.firstChild);

    // 삼단 바 열고 닫기 — 바깥 탭·ESC로 닫힌다(모바일 관례).
    var burger = bar.querySelector(".qn-burger");
    function setOpen(open) {
      bar.classList.toggle("qn-open", open);
      burger.setAttribute("aria-expanded", open ? "true" : "false");
      burger.setAttribute("aria-label", open ? "메뉴 닫기" : "메뉴 열기");
    }
    burger.addEventListener("click", function (e) {
      e.stopPropagation();
      setOpen(!bar.classList.contains("qn-open"));
    });
    document.addEventListener("click", function (e) {
      if (!bar.contains(e.target)) setOpen(false);
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") setOpen(false);
    });

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
