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

  /**
   * 문장을 절(clause)로 끊는다 — **괄호 안은 건드리지 않는다.**
   *
   * 매일 새벽 배치가 만드는 판단 설명은 절을 ` · `와 ` — `로 이어 붙인
   * 것이다. 통째로는 매일 글자가 달라 사전이 영영 못 찾지만, **절 단위**로는
   * 틀이 몇 개 안 된다. 그래서 절마다 따로 찾아 다시 잇는다.
   *
   * ⚠️ 괄호 안에도 ` · `가 있다("(95% 신뢰구간 37%~62% · 보합 2일 포함 …)").
   *    거기서 끊으면 문장이 부서진다 — 괄호 깊이가 0인 자리에서만 끊는다.
   * ⚠️ 이음매를 **기억해서 그대로 다시 쓴다.** 전부 ` · `로 이어 붙이면
   *    "매수 +36% · 로지스틱회귀 …"가 되어 원문과 다른 문장이 된다.
   *
   * 돌려주는 것: [조각, 이음매, 조각, 이음매, …, 조각]
   */
  var SEPS = [" · ", " — "];

  function clauses(text) {
    var out = [], depth = 0, start = 0, i = 0;
    while (i < text.length) {
      var c = text.charAt(i);
      if (c === "(") { depth++; i++; continue; }
      if (c === ")") { depth = Math.max(0, depth - 1); i++; continue; }
      var hit = null;
      if (depth === 0) {
        for (var k = 0; k < SEPS.length; k++) {
          if (text.substr(i, SEPS[k].length) === SEPS[k]) { hit = SEPS[k]; break; }
        }
      }
      if (hit) {
        out.push(text.slice(start, i));
        out.push(hit);
        i += hit.length;
        start = i;
      } else {
        i++;
      }
    }
    out.push(text.slice(start));
    return out;
  }

  /** 사전에서 찾기. 앞뒤 공백은 유지한 채 알맹이만 바꾼다. */
  function look(raw) {
    var m = /^(\s*)([\s\S]*?)(\s*)$/.exec(raw);
    var core = m[2];
    if (!core) return null;
    // ⚠️ 찾는 방법은 **one_of 한 곳에만** 있다. 예전에는 같은 사전·규칙
    //    조회를 여기와 one_of 두 곳에 적어 뒀는데, 그러면 언젠가 갈라진다
    //    (FROZEN_IDEAS ①).
    var whole = one_of(core);
    var hit = (whole === null) ? undefined : whole;
    // 통째로 못 찾았으면 **절 단위**로 다시 시도한다. 아는 절만 바뀌고
    // 모르는 절은 한국어로 남는다 — 반쪽짜리 영어가 되지만, 통째로
    // 한국어인 것보다는 낫고 **지어낸 영어보다는 훨씬 낫다.**
    //
    // 통째로 찾았더라도 한 번 더 해 본다. 욕심 많은 규칙(`(.+)`)이 여러 절을
    // 한꺼번에 삼키면 가운데 절만 옮겨지고 앞뒤는 한국어로 남는데, 그런 문장은
    // 절 단위로 끊으면 대개 전부 옮겨진다. **한국어가 덜 남는 쪽**을 쓴다.
    var by = by_clause(core);
    if (by !== null && (hit === undefined || korean(by) < korean(hit))) {
      hit = by;
    }
    if (hit === undefined || hit === core) return null;
    return m[1] + hit + m[3];
  }

  var HANGUL = /[가-힣]/g;

  function korean(text) {
    var found = String(text).match(HANGUL);
    return found ? found.length : 0;
  }

  function by_clause(core) {
    var parts = clauses(core);
    if (parts.length < 2) return null;
    var any = false;
    var done = parts.map(function (part, idx) {
      if (idx % 2 === 1) return part;              // 홀수 자리는 이음매
      var one = one_of(part);
      if (one !== null) { any = true; return one; }
      return part;
    });
    return any ? done.join("") : null;
  }

  /** 절 하나만 찾는다(사전 → 규칙). 못 찾으면 null. */
  function one_of(core, depth) {
    var d = dict();
    var hit = d[core];
    if (hit === undefined) hit = d[core.replace(/\s+/g, " ")];
    if (hit === undefined) {
      var rs = rules();
      for (var i = 0; i < rs.length; i++) {
        var m = new RegExp(rs[i][0]).exec(core);
        if (m) { hit = fill(rs[i][1], m, depth || 0); break; }
      }
    }
    return (hit === undefined || hit === core) ? null : hit;
  }

  // 치환문의 `$*2`는 "잡아 둔 그 조각을 한 번 더 옮겨라"는 뜻이다.
  //
  // 판단 근거는 "20일선 이격 +4.0%(선 위)"처럼 괄호 안에 상태 이름을 달고
  // 나온다. 이름은 종목·날마다 달라지고(선 위/선 아래/밴드 중간/깊은
  // 콘탱고(안정)…) 값과 이름의 조합은 수백 가지라, 규칙 하나에 다 적을 수
  // 없다. 그래서 값은 그대로 흘려보내고(`$1`) 이름만 다시 사전으로 보낸다.
  // 옮길 말이 없으면 **한국어를 그대로 둔다** — 지어내지 않는다.
  var MAX_DEPTH = 4;                  // 규칙이 서로를 부르며 도는 것을 막는다

  function fill(tpl, m, depth) {
    return tpl.replace(/\$(\*?)(\d)/g, function (whole, star, n) {
      var at = Number(n);
      if (at >= m.length) return whole;        // 없는 자리는 글자 그대로
      var g = m[at] === undefined ? "" : m[at];  // 안 걸린 괄호는 빈칸
      if (!star || depth >= MAX_DEPTH) return g;
      var deeper = one_of(g, depth + 1);
      return deeper === null ? g : deeper;
    });
  }

  var SKIP = { SCRIPT: 1, STYLE: 1, TEXTAREA: 1, CODE: 1, PRE: 1 };

  /**
   * `data-qi18n="keep"`이 붙은 자리는 손대지 않는다.
   *
   * 개선 이력처럼 **커밋 제목을 그대로 옮겨 적는 자리**가 있다. 그 문장은
   * 매일 새로 생기고 끝이 없어서 사전에 담을 수 없는데, 일반 규칙이 문장의
   * 앞머리만 잡아 "90 days: 시계가 선언만 봤다"처럼 반쪽짜리로 만든다.
   * 반쪽 영어는 한국어보다 나쁘다 — 읽는 사람이 고장으로 읽는다.
   */
  function kept(node) {
    for (var n = node; n; n = n.parentNode) {
      if (n.nodeType === 1 && n.getAttribute
          && n.getAttribute("data-qi18n") === "keep") return true;
    }
    return false;
  }

  function walk(node) {
    if (!node) return;
    if (node.nodeType === 3) {                      // 글자
      var out = look(node.nodeValue);
      if (out !== null) node.nodeValue = out;
      return;
    }
    if (node.nodeType !== 1) return;                // 주석 등
    if (SKIP[node.tagName]) return;
    if (node.getAttribute && node.getAttribute("data-qi18n") === "keep") return;
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
        for (var j = 0; j < added.length; j++) {
          if (!kept(added[j])) walk(added[j]);     // 조상까지 보고 판단한다
        }
        if (recs[i].type === "characterData" && !kept(recs[i].target)) {
          walk(recs[i].target);
        }
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
