/**
 * 화면을 영어로도 읽게 한다 (2026-08-25 사장님 지시: "서비스 영어로도
 * 만들어줘 홈페이지나 프로그램이나").
 *
 * ■ 왜 이런 방식인가 — 한국어가 '원본'이다
 *
 * 이 사이트의 문구는 손으로 쓴 한국어 HTML 안에 살고 있다(약 20만 자).
 * 영어 페이지를 따로 만들면 같은 문장이 두 곳에 살게 되고, 앞으로 문구를
 * 고칠 때마다 한쪽이 조용히 낡는다 — 이 저장소가 가장 자주 당한 실패
 * 모양이다(FROZEN_IDEAS ①: 같은 규칙이 두 곳에 있으면 반드시 갈라진다).
 *
 * 그래서 **페이지는 하나**로 두고, 한국어 문장을 열쇠로 삼는 사전
 * (assets/i18n-en.js)에서 영어를 찾아 바꿔 끼운다. 문구를 고치면 그
 * 문장이 사전에서 빠지므로 **영어가 낡는 대신 한국어로 되돌아간다** —
 * 틀린 영어가 남는 것보다 낫다.
 *
 * ■ 모르는 문장은 지어내지 않는다
 *
 * 사전에 없는 문장은 **한국어 그대로 둔다.** 기계 번역으로 메우지 않는다.
 * 이 사이트는 돈 이야기를 하는 공개 장부다 — "대충 맞는 영어"는 숫자
 * 옆에서 사실이 아닌 주장이 된다. 대신 언어 바가 "일부는 아직 한국어"
 * 라고 밝힌다(아래 notice).
 *
 * ■ 전환은 새로고침이다
 *
 * 영어 → 한국어로 되돌릴 때 원본을 기억해 뒀다가 복구하는 방식은 표가
 * 다시 그려질 때마다 어긋난다. 한국어는 **HTML 안에 그대로 있으므로**
 * 새로고침 한 번이면 공짜로 완벽하다. 느려 보이지만 틀리지 않는다.
 *
 * ■ 표는 나중에 그려진다
 *
 * 잔고·거래내역·차트 설명은 JSON을 받은 뒤 자바스크립트가 만든다. 그래서
 * 처음 한 번 훑는 것으로는 부족하고, MutationObserver로 **새로 생긴
 * 글자도** 계속 바꾼다.
 */
(function (root) {
  "use strict";

  var KEY = "quant.lang";
  var LANGS = ["ko", "en"];

  function stored() {
    try {
      var v = root.localStorage && root.localStorage.getItem(KEY);
      return LANGS.indexOf(v) >= 0 ? v : null;
    } catch (e) {
      return null;          // 사생활 보호 모드 등 — 한국어로 간다
    }
  }

  /** 지금 언어. 주소의 ?lang=en 이 저장값보다 세다(링크로 공유 가능). */
  function current() {
    var q = /[?&]lang=(ko|en)/.exec(root.location.search || "");
    if (q) return q[1];
    return stored() || "ko";
  }

  function set(lang) {
    if (LANGS.indexOf(lang) < 0) return;
    try {
      root.localStorage.setItem(KEY, lang);
    } catch (e) { /* 저장 못 해도 이번 방문에는 적용된다(아래 주소로) */ }
    // ⚠️ 저장이 막힌 브라우저에서도 전환이 되게 주소에 남긴다.
    var u = root.location.pathname + "?lang=" + lang + root.location.hash;
    root.location.href = u;
  }

  var DICT = null;
  function dict() {
    if (DICT === null) DICT = (root.QUANT_EN && root.QUANT_EN.strings) || {};
    return DICT;
  }

  /**
   * 숫자가 든 문장을 위한 규칙 — 사전은 **정확히 같은 글자**만 찾으므로
   * "−19.35 USD 손해"처럼 매일 바뀌는 문장은 영영 못 찾는다. 그렇다고
   * 기계 번역으로 메우지 않는다: 규칙도 **사람이 하나씩 적은 것**이고,
   * 안 맞으면 한국어가 남는다.
   */
  function rules() {
    return (root.QUANT_EN && root.QUANT_EN.rules) || [];
  }

  /** 사전에서 찾기. 앞뒤 공백은 유지한 채 알맹이만 바꾼다. */
  function look(raw) {
    var d = dict();
    var m = /^(\s*)([\s\S]*?)(\s*)$/.exec(raw);
    var core = m[2];
    if (!core) return null;
    // 표에서 온 글자는 공백이 여러 칸일 수 있다 — 한 칸으로 눌러서도 찾는다.
    var hit = d[core];
    if (hit === undefined) hit = d[core.replace(/\s+/g, " ")];
    if (hit === undefined) {
      var rs = rules();
      for (var i = 0; i < rs.length; i++) {
        var re = new RegExp(rs[i][0]);
        if (re.test(core)) { hit = core.replace(re, rs[i][1]); break; }
      }
    }
    if (hit === undefined || hit === core) return null;
    return m[1] + hit + m[3];
  }

  var SKIP = { SCRIPT: 1, STYLE: 1, TEXTAREA: 1, CODE: 1, PRE: 1 };

  function walk(node) {
    if (!node) return;
    if (node.nodeType === 3) {                      // 글자
      var out = look(node.nodeValue);
      if (out !== null) node.nodeValue = out;
      return;
    }
    if (node.nodeType !== 1) return;                // 주석 등
    if (SKIP[node.tagName]) return;
    // 눈에 안 보이지만 읽히는 것들
    ["title", "placeholder", "aria-label", "alt"].forEach(function (a) {
      var v = node.getAttribute && node.getAttribute(a);
      if (!v) return;
      var t = look(v);
      if (t !== null) node.setAttribute(a, t);
    });
    for (var c = node.firstChild; c; c = c.nextSibling) walk(c);
  }

  function apply() {
    walk(document.body);
    document.documentElement.setAttribute("lang", "en");
  }

  function watch() {
    if (!root.MutationObserver) return;
    var mo = new root.MutationObserver(function (recs) {
      for (var i = 0; i < recs.length; i++) {
        var added = recs[i].addedNodes || [];
        for (var j = 0; j < added.length; j++) walk(added[j]);
        if (recs[i].type === "characterData") walk(recs[i].target);
      }
    });
    mo.observe(document.body, {
      childList: true, subtree: true, characterData: true});
  }

  /**
   * 아직 영어가 덜 채워진 페이지에는 **그렇다고 적는다.**
   *
   * 이 저장소의 규칙("모르면 비운다")을 화면에도 적용한 것이다. 한국어가
   * 남아 있는데 아무 말도 없으면 읽는 사람은 그것을 **고장**으로 읽는다.
   */
  function notice() {
    var here = (location.pathname.split("/").pop() || "index.html");
    var partial = (root.QUANT_EN && root.QUANT_EN.partial) || [];
    if (partial.indexOf(here) < 0) return;
    var bar = document.createElement("div");
    bar.id = "qi18n-note";
    bar.setAttribute("role", "note");
    bar.style.cssText = [
      "padding:9px 16px", "font-size:13px", "line-height:1.5",
      "color:var(--muted,#8f96a3)",
      "background:var(--bg2,#0e1013)",
      "border-bottom:1px solid var(--line,#1e2128)"].join(";");
    bar.textContent = "This page is only partly translated — untranslated "
      + "sentences are left in Korean rather than machine-translated. "
      + "Numbers, dates and amounts are never translated.";
    document.body.insertBefore(bar, document.body.firstChild);
  }

  function start() {
    if (current() !== "en") {
      document.documentElement.setAttribute("lang", "ko");
      return;                       // 한국어는 HTML 원본 그대로 — 할 일 없음
    }
    apply();
    notice();
    watch();
  }

  root.QuantI18N = {
    current: current, set: set, apply: apply, look: look, LANGS: LANGS,
    /** 이 페이지에서 아직 한국어로 남은 글자가 있는가 — 화면이 밝힌다. */
    hasUntranslated: function () {
      var left = false;
      var w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      var n;
      while ((n = w.nextNode())) {
        if (n.parentNode && SKIP[n.parentNode.tagName]) continue;
        if (/[가-힣]/.test(n.nodeValue)) { left = true; break; }
      }
      return left;
    },
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})(window);
