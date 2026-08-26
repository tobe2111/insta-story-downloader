"""사이트를 영어로도 읽을 수 있는가 (2026-08-25 감사 320).

사장님 지시: *"서비스 영어로도 만들어줘 홈페이지나 프로그램이나."*

■ 이 검사가 지키는 것

  ① **버튼이 있는가** — 넓은 화면과 **휴대폰 양쪽**에서. 영어권 방문자가
     첫 화면에서 언어 버튼을 못 찾으면, 그 사람에게 이 사이트는 한국어
     전용이다.
  ② **정말 영어로 보이는가** — 진짜 브라우저로 띄워서 확인한다. 사전에
     글자가 있는 것과 화면이 영어인 것은 다른 일이다(감사 229의 교훈).
  ③ **숫자를 건드리지 않았는가** — 이게 가장 중요하다. 이 사이트는 돈
     이야기를 하는 공개 장부다. 번역이 금액을 한 자라도 바꾸면 그건
     번역이 아니라 **장부 조작**이다. 한국어 화면과 영어 화면에서 자산
     금액이 **글자 그대로 같은지** 본다.
  ④ **모르는 문장을 지어내지 않는가** — 사전에 없으면 한국어로 남아야
     한다. 기계 번역으로 메우면 "대충 맞는 영어"가 숫자 옆에서 사실이
     아닌 주장이 된다.
  ⑤ **한계를 부드럽게 바꾸지 않았는가** — "수익을 보장하지 않습니다"가
     영어에서 사라지면 그건 번역 실수가 아니라 다른 제품이다.
"""

from __future__ import annotations

import functools
import html
import http.server
import json
import re
import shutil
import socketserver
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _browser import block_external, chromium_or_skip  # noqa: E402

DOCS = ROOT / "docs"
ENGINE = (DOCS / "assets" / "i18n.js").read_text("utf-8")
DICT = (DOCS / "assets" / "i18n-en.js").read_text("utf-8")
IDX = (DOCS / "index.html").read_text("utf-8")
NAV = (DOCS / "assets" / "nav.js").read_text("utf-8")

# 지금 영어가 **끝까지** 채워진 페이지. 여기 있는 페이지는 브라우저로 띄워
# 한국어가 남지 않았는지 본다 — 목록에 없는 페이지는 아직 차례가 아니다.
DONE = ["us.html", "intraday.html", "futures.html", "weekly.html",
        "ml.html", "today.html", "trust.html", "admin.html"]

# 공개 페이지 전부 — 하나라도 사전을 안 실으면 그 페이지만 한국어로 남는다.
PAGES = ["index.html", "paper.html", "today.html", "trust.html",
         "intraday.html", "us.html", "futures.html", "ml.html",
         "weekly.html", "admin.html"]


# ── ① 배선 ────────────────────────────────────────────────────

@pytest.mark.parametrize("name", PAGES)
def test_every_public_page_loads_the_dictionary(name):
    """사전 → 엔진 **순서**로 실어야 한다.

    엔진이 먼저 돌면 사전이 비어 있어 아무것도 안 바뀐다. 둘 다 defer라
    문서에 적힌 순서대로 실행된다.
    """
    src = (DOCS / name).read_text("utf-8")
    i = src.find("assets/i18n-en.js")
    j = src.find("assets/i18n.js")
    assert i >= 0, f"{name}이 영어 사전을 싣지 않는다"
    assert j >= 0, f"{name}이 번역 엔진을 싣지 않는다"
    assert i < j, f"{name}: 사전이 엔진보다 뒤에 있다 — 아무것도 안 바뀐다"


def test_the_bar_has_a_language_button():
    """언어 버튼은 **바 한 벌**에만 있으면 모든 페이지에 생긴다.

    ⚠️ 예전 판은 홈의 손수 만든 바(`class="navlang"`)와 공용 바를 따로
       확인했다. 2026-08-26에 홈도 공용 바를 쓰게 되면서(사장님: "상단바도
       페이지마다 구성이 다르고 일치시켜줘") 확인할 바가 하나가 됐다 —
       버튼이 한 곳에만 있으면 되는 것이 통일의 이점이다.
    """
    assert "qn-lang" in NAV, "공용 바에 언어 버튼이 없다"
    assert 'src="assets/nav.js"' in IDX, "홈이 공용 바를 안 싣는다"


def test_the_language_button_survives_a_narrow_screen():
    """대시보드 버튼과 달리 **좁은 화면에서 숨기지 않는다.**

    글자 두 개라 자리를 거의 안 먹는다. 숨기면 영어권 방문자에게 이
    사이트는 한국어 전용이 된다.
    """
    assert "#qnav .qn-lang{display:none}" not in NAV, (
        "공용 바: 좁은 화면에서 언어 버튼이 사라진다")
    assert "@media(max-width:820px){#qnav .qn-lang" not in NAV, (
        "공용 바: 좁은 화면 규칙이 언어 버튼을 건드린다")


# ── ② 사전 자체의 계약 ────────────────────────────────────────

# 화면이 **실행 중에 날짜를 끼워 넣는** 자리들. 이 문구 뒤에 오는 날짜는
# 장부에서 오므로 매일(혹은 갱신될 때마다) 바뀐다.
_LIVE_DATE_SLOTS = [
    ("마지막 갱신: ", "주간 아카이브의 갱신일(status.updated)"),
    ("수정 공지 (", "판정 시계 수정 공지(amended.on) — 괄호 있는 쪽"),
    ("수정 공지 ", "판정 시계 수정 공지(amended.on) — 괄호 없는 쪽"),
    ("마지막 확정일(", "단타 비교문의 확정일(장부 최신일)"),
]


def test_no_live_date_slot_is_pinned_in_a_dictionary_key():
    """**바뀌는 날짜를 사전 열쇠에 박지 않는다** (2026-08-26에 값비싸게 배운 것).

    사전은 한국어 문장 **전체**를 열쇠로 쓴다. 그런데 위 자리들에는 화면이
    실행 중에 장부의 날짜를 끼워 넣는다. 그 문장을 통째로 사전에 넣으면
    열쇠에 그날의 날짜가 박히고, **다음 밤 배치가 새 날짜를 쓰는 순간
    열쇠가 어긋난다** — 영어 화면에 한국어가 남고 이 파일의 검사가 빨개진다.

    실제로 그렇게 됐다: 사전을 쓴 08-25 아침에는 장부가 2026-08-24였고
    검사가 초록이었다. 그날 밤 배치가 08-25를 쓰자 세 페이지가 빨개졌다.
    **하루짜리 초록불**이었던 셈이고, 오늘 날짜를 다시 넣어 봐야 내일 또
    빨개진다 — 매일 헛울리는 관문은 곧 무시당한다.

    ⚠️ 왜 "열쇠에 날짜가 있으면 무조건 빨강"으로 하지 않았나. 사전에는
       **과거 기록**의 날짜가 잔뜩 들어 있다(오답 노트·개선 이력 —
       "2026-08-11, 기록 배열 순서 오류를 발견했습니다"). 그건 한번 적히면
       영원히 안 바뀌므로 낡지 않는다. 둘을 글자만 보고 가를 방법은 없어서,
       **바뀌는 자리를 이름으로 적어** 둔다. 새로 그런 자리가 생기면 위
       목록에 한 줄 추가하는 것이 이 검사를 유지하는 방법이다.

    바뀌는 자리는 사전이 아니라 **rules(정규식)** 가 잡는다 — 엔진에 그
    장치가 이미 있었는데(i18n.js의 rules) 안 쓴 것이 문제였다.
    """
    import re as _re
    keys = _re.findall(r'^\s+"((?:[^"\\]|\\.)*)":', DICT, _re.M)
    assert len(keys) > 50, f"사전 열쇠를 못 읽었다({len(keys)}개) — 검사가 헛돈다"
    bad = []
    for slot, what in _LIVE_DATE_SLOTS:
        pat = _re.escape(slot) + r"\d{4}-\d{2}-\d{2}"
        for k in keys:
            if _re.search(pat, k):
                bad.append(f"{what}: {k[:70]}")
    assert not bad, (
        "바뀌는 날짜가 사전 열쇠에 박혀 있다 — 그 항목은 장부 날짜가 바뀌는 "
        f"다음 밤에 스스로 만료된다. rules(정규식)로 옮길 것: {bad}")


def test_both_halves_of_a_two_way_label_are_translated():
    """짝으로 쓰이는 라벨은 **양쪽 다** 사전에 있어야 한다.

    실제로 당했다(2026-08-26 CI). 선물 화면은 포지션에 따라
    `q<0 ? "숏(내림에 걺)" : "롱(오름에 걺)"` 중 하나를 찍는다. 사전을 쓴 날
    계좌가 롱이어서 **롱 쪽만** 들어갔고, 계좌가 숏으로 돌아선 순간 영어
    화면에 한국어가 남았다.

    이건 날짜 문제(위 검사)와 다른 축의 같은 병이다 — **사전이 "그때 화면에
    있던 것"만 덮는다.** 화면에 지금 안 보이는 가지도 언젠가 보인다. 그래서
    소스에서 삼항 연산자로 갈리는 한국어 라벨 짝을 훑어, 한쪽만 번역돼 있으면
    빨간불을 켠다 — 데이터가 바뀌기를 기다렸다가 CI에서 아는 것보다 낫다.

    ⚠️ 양쪽 다 없는 짝은 잡지 않는다. 그건 "아직 이 페이지는 영어가 덜
       채워졌다"는 정직한 상태이고(partial 목록이 화면에 그렇게 적는다),
       이 검사가 다루는 사고는 **반쪽만 채운 것**이다.
    """
    import re as _re
    keys = set(_re.findall(r'^\s+"((?:[^"\\]|\\.)*)":', DICT, _re.M))
    ko = _re.compile(r"[가-힣]")
    pair = _re.compile(r'\?\s*"([^"]{2,60})"\s*:\s*"([^"]{2,60})"')
    half = []
    for page in sorted(DOCS.glob("*.html")):
        for a, b in pair.findall(page.read_text("utf-8")):
            if not (ko.search(a) and ko.search(b)):
                continue
            if (a in keys) != (b in keys):
                missing, have = (b, a) if a in keys else (a, b)
                half.append(f"{page.name}: {have!r}는 있고 {missing!r}가 없다")
    assert not half, (
        "짝의 한쪽만 번역돼 있다 — 데이터가 그쪽으로 가는 날 영어 화면에 "
        f"한국어가 남는다: {half}")


def test_the_rules_catch_those_dates_instead():
    """대조군 — 사전에서 뺐는데 규칙에도 없으면 그냥 번역을 지운 것이다."""
    for needle, what in (("^마지막 갱신: ", "주간 갱신일"),
                         ("^수정 공지 ", "수정 공지 날짜"),
                         ("마지막 확정일", "단타 확정일")):
        assert needle in DICT, f"{what} 규칙이 없다 — 영어가 사라진다"


def test_unknown_sentences_are_left_in_korean():
    """엔진이 **모르면 그대로 둔다**는 것이 코드에 있는가.

    실제 동작은 아래 브라우저 검사가 값으로 확인한다.
    """
    assert "if (hit === undefined || hit === core) return null;" in ENGINE, (
        "사전에 없을 때 null을 돌려주는 자리가 사라졌다 — 지어내기 시작한다")


def test_the_english_does_not_promise_returns():
    """'수익 보장'류 표현은 한국어에도 영어에도 없다(사기죄 소지).

    ⚠️ 영어는 한국어보다 이 실수를 하기 쉽다 — "guaranteed" 한 단어가
       마케팅 관용구로 흘러들기 때문이다.
    """
    low = DICT.lower()
    for bad in ("guaranteed return", "guaranteed profit", "risk-free",
                "guarantees a return", "guaranteed income"):
        assert bad not in low, f"영어 사전이 수익을 보장한다: {bad!r}"


def test_the_honest_limits_survive_translation():
    """한계 문장은 **한계 그대로** 옮겨야 한다.

    "가상 자금 실험입니다 … 수익을 보장하지 않습니다"가 영어에서 사라지면
    그건 번역 실수가 아니라 다른 제품이다.
    """
    assert "no return is guaranteed" in DICT, (
        "'수익을 보장하지 않습니다'의 영어가 사전에 없다")
    assert "not investment advice" in DICT, (
        "'투자 권유가 아닙니다'의 영어가 사전에 없다")
    assert "play money" in DICT, "'가상 자금'의 영어가 사전에 없다"


def test_the_dictionary_says_which_pages_are_only_half_done():
    """아직 덜 된 페이지는 **덜 됐다고 적는다.**

    한국어가 남아 있는데 아무 말도 없으면 읽는 사람은 그것을 고장으로
    읽는다. 이 저장소의 "모르면 비운다"를 화면에 적용한 것이다.
    """
    m = re.search(r"partial:\s*\[(.*?)\]", DICT, re.S)
    assert m, "덜 된 페이지 목록(partial)이 없다"
    listed = set(re.findall(r'"([\w.\-]+)"', m.group(1)))
    assert listed, "덜 된 페이지 목록이 비어 있다"
    # 다 끝난 페이지가 '덜 됐다'고 말하면 안 된다(반대 방향의 거짓말).
    assert not (listed & set(DONE)), (
        f"영어가 끝난 페이지가 '덜 됐다'고 적혀 있다: {sorted(listed & set(DONE))}")


# ── ③ 진짜 브라우저 ───────────────────────────────────────────

@pytest.fixture(scope="module")
def site(tmp_path_factory):
    pytest.importorskip("playwright.sync_api",
                        reason="playwright 없음 — 영어 화면 검사 생략")
    root = tmp_path_factory.mktemp("ensite")
    shutil.copytree(DOCS, root, dirs_exist_ok=True)

    class _Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    srv = socketserver.TCPServer(
        ("127.0.0.1", 0), functools.partial(_Quiet, directory=str(root)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()


@pytest.fixture(scope="module")
def browser(site):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=chromium_or_skip())
        try:
            yield b
        finally:
            b.close()


_LEFTOVER_JS = """() => {
  const SKIP = {SCRIPT:1, STYLE:1, TEXTAREA:1, CODE:1, PRE:1};
  const left = [];
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = w.nextNode())) {
    if (n.parentNode && SKIP[n.parentNode.tagName]) continue;
    // 언어 버튼 자신은 한국어여야 한다 — 되돌아갈 길이니까.
    if (n.parentNode && /qn-lang|navlang|mlang|qi18n-back/.test(
        n.parentNode.className + " " + (n.parentNode.id || ""))) continue;
    const t = n.nodeValue.trim().replace(/\\s+/g, ' ');
    if (t && /[가-힣]/.test(t)) left.push(t);
  }
  return left;
}"""


def _open(browser, site, path, wait=2500, lang="ko-KR"):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    block_external(page, lang=lang)
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"{site}/{path}")
    page.wait_for_timeout(wait)
    return page, errors


@pytest.mark.parametrize("name", DONE)
def test_a_finished_page_really_reads_in_english(browser, site, name):
    """사전에 글자가 있는 것과 **화면이 영어인 것**은 다른 일이다."""
    page, errors = _open(browser, site, f"{name}?lang=en")
    try:
        assert not errors, f"{name}: 영어로 띄우니 스크립트가 던졌다 — {errors}"
        left = page.evaluate(_LEFTOVER_JS)
        assert not left, (
            f"{name}: 영어인데 한국어가 남았다({len(left)}건) — "
            f"{left[:4]}")
    finally:
        page.close()


@pytest.mark.parametrize("name", DONE)
def test_the_korean_page_is_untouched(browser, site, name):
    """대조군 — 언어를 안 고르면 한국어 그대로여야 한다.

    이게 없으면 위 검사는 "빈 페이지도 통과"한다.
    """
    page, errors = _open(browser, site, name)
    try:
        assert not errors, f"{name}: 한국어에서 스크립트가 던졌다 — {errors}"
        left = page.evaluate(_LEFTOVER_JS)
        assert len(left) > 20, (
            f"{name}: 언어를 안 골랐는데 한국어가 {len(left)}건뿐이다 — "
            "엔진이 멋대로 번역했거나 페이지가 비었다")
    finally:
        page.close()


def test_the_money_is_identical_in_both_languages(browser, site):
    """**이 파일에서 가장 중요한 검사.**

    번역이 금액을 한 자라도 바꾸면 그건 번역이 아니라 장부 조작이다.
    같은 페이지를 두 언어로 띄워 자산 금액이 글자 그대로 같은지 본다.
    """
    grab = """() => Array.from(document.querySelectorAll('.kpi .v, .big, td'))
        .map(e => (e.innerText || '').match(/[\\d][\\d,]*\\.?\\d*/g) || [])
        .flat().slice(0, 60)"""
    ko, ko_err = _open(browser, site, "intraday.html")
    try:
        assert not ko_err, ko_err
        a = ko.evaluate(grab)
    finally:
        ko.close()
    en, en_err = _open(browser, site, "intraday.html?lang=en")
    try:
        assert not en_err, en_err
        b = en.evaluate(grab)
    finally:
        en.close()
    assert a, "한국어 화면에서 숫자를 하나도 못 찾았다 — 검사가 헛돈다"
    assert a == b, (
        "언어를 바꿨더니 숫자가 달라졌다 — 번역이 장부를 건드렸다\n"
        f"ko={a[:12]}\nen={b[:12]}")


def test_an_unknown_sentence_stays_korean(browser, site):
    """사전에 없는 문장은 **한국어로 남는다** — 지어내지 않는다."""
    page, _ = _open(browser, site, "us.html?lang=en", wait=1500)
    try:
        got = page.evaluate(
            "() => QuantI18N.look('이 문장은 사전에 없습니다 정말로')")
        assert got is None, f"없는 문장을 지어냈다: {got!r}"
    finally:
        page.close()


def test_a_half_done_page_says_so(browser, site):
    """아직 덜 된 페이지는 화면이 그 사실을 밝힌다(대조군 포함)."""
    page, _ = _open(browser, site, "paper.html?lang=en")
    try:
        assert page.locator("#qi18n-note").count() == 1, (
            "덜 된 페이지인데 아무 말도 없다 — 읽는 사람은 고장으로 읽는다")
    finally:
        page.close()
    done, _ = _open(browser, site, "us.html?lang=en", wait=1500)
    try:
        assert done.locator("#qi18n-note").count() == 0, (
            "다 된 페이지가 '덜 됐다'고 말한다")
    finally:
        done.close()


def test_the_choice_survives_a_click_and_a_page_move(browser, site):
    """버튼을 누르면 실제로 영어가 되고, 다른 페이지로 가도 유지된다."""
    page, _ = _open(browser, site, "us.html", wait=1500)
    try:
        page.click(".qn-lang")
        page.wait_for_timeout(1800)
        assert "lang=en" in page.url, "버튼을 눌렀는데 영어로 안 갔다"
        assert page.locator("html").get_attribute("lang") == "en"
        # 링크를 타고 다른 페이지로 가도 선택이 남아야 한다(저장값).
        page.goto(f"{site}/futures.html")
        page.wait_for_timeout(2000)
        assert page.locator("html").get_attribute("lang") == "en", (
            "페이지를 옮기니 한국어로 되돌아갔다 — 매번 다시 눌러야 한다")
    finally:
        page.close()

# ── ④ 덜 된 페이지도 **얼마나** 됐는지 잰다 ────────────────────
#
# "덜 됐다"만 적어 두면 90%든 5%든 같은 말이 된다. 바닥값을 재 두면
# 다음 사람이 문구를 고치다 사전을 깨뜨렸을 때 그 사실이 드러난다.
#
# ⚠️ 첫 화면에 남는 한국어의 대부분은 **깃 커밋 제목**(개선 이력)이다.
#    커밋 제목은 합쳐지는 순간 정해지는 글자라 사전으로 옮길 수 없다 —
#    그리고 옮겨서도 안 된다(저장소 이력의 사본이라는 것이 그 목록의 뜻이다).
#
#    매일 새벽 배치가 만드는 판단 설명은 **절 단위**로 옮긴다(엔진의
#    clauses()). 통째로는 매일 글자가 달라 못 찾지만 절로 끊으면 틀이 몇 개
#    안 되고, 모르는 절만 한국어로 남는다.
COVERAGE_FLOOR = {"index.html": 0.85, "paper.html": 0.92}

_COVERAGE_JS = """() => {
  const SKIP = {SCRIPT:1, STYLE:1, TEXTAREA:1, CODE:1, PRE:1};
  let ko = 0, tot = 0;
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = w.nextNode())) {
    if (n.parentNode && SKIP[n.parentNode.tagName]) continue;
    const t = n.nodeValue.trim().replace(/\\s+/g, ' ');
    if (!t) continue;
    tot += t.length;
    if (/[가-힣]/.test(t)) ko += t.length;
  }
  return {ko: ko, tot: tot};
}"""


@pytest.mark.parametrize("name,floor", sorted(COVERAGE_FLOOR.items()))
def test_a_half_done_page_is_at_least_this_far_along(browser, site, name, floor):
    page, errors = _open(browser, site, f"{name}?lang=en", wait=3000)
    try:
        assert not errors, f"{name}: {errors}"
        r = page.evaluate(_COVERAGE_JS)
        assert r["tot"] > 1000, f"{name}: 글자가 너무 적다 — 검사가 헛돈다"
        share = 1.0 - r["ko"] / r["tot"]
        assert share >= floor, (
            f"{name}: 영어가 {share:.1%}뿐이다(바닥 {floor:.0%}) — "
            "사전이 깨졌거나 문구가 바뀌었다")
    finally:
        page.close()


def test_the_floor_is_not_set_so_low_it_means_nothing():
    """대조군 — 바닥값이 0에 가까우면 위 검사는 아무것도 안 지킨다."""
    assert COVERAGE_FLOOR, "바닥값 목록이 비었다"
    for name, floor in COVERAGE_FLOOR.items():
        assert floor >= 0.5, f"{name}의 바닥값 {floor}은 너무 낮다"

# ── ⑤ 날짜가 박힌 열쇠는 언젠가 반드시 낡는다 ──────────────────
#
# 사전은 **정확히 같은 글자**만 찾는다. 그래서 열쇠 안에 날짜가 들어가면
# 그 날짜가 바뀌는 순간 영어가 조용히 사라지고 한국어가 돌아온다.
#
# 실제로 당했다(2026-08-25): "마지막 갱신: 2026-08-24"를 열쇠로 넣었더니
# 다음 날 배치가 날짜를 바꿔 주간 아카이브가 다시 한국어가 됐다. 규칙
# (정규식)으로 옮겨 날짜를 **잡아서 그대로 흘려보내야** 한다.
#
# 다만 위험한 것은 날짜 자체가 아니라 **그 글자를 누가 쓰느냐**이다.
# 기록 검증 페이지의 정정 이력("2026-08-17, 장부가 …")은 사람이 손으로
# 적어 HTML에 박아 둔 과거이고, 이 제품은 **과거를 고치지 않는다**. 그런
# 문장의 날짜는 내일도 같은 글자다. 반대로 배치가 매일 다시 써 내려보내는
# 문장은 하루 만에 낡는다.
#
# 그래서 세는 기준을 "날짜가 들었는가"에서 **"그 글자가 정적 HTML 안에
# 그대로 있는가"**로 바꾼다. 정적 페이지에 없는(= 화면이 만들어 내는)
# 날짜 열쇠만 빚으로 센다. 아래 목록이 그 빚이다 — 구조 리셋이나 사전등록
# 수정이 나면 그날 한국어로 돌아가고, 위 ③의 바닥값 검사가 알려 준다.
GENERATED_DATED_KEYS_ALLOWED = 7


def _dictionary_keys():
    """사전의 열쇠를 **자바스크립트 이스케이프를 푼 상태로** 돌려준다."""
    body = DICT[DICT.index("strings: {"):DICT.index("rules: [")]
    out = []
    for raw in re.findall(r'\n      "((?:[^"\\]|\\.)*)":', body):
        out.append(json.loads('"' + raw.replace("\\'", "'") + '"'))
    return out


@functools.lru_cache(maxsize=1)
def _static_page_text():
    """공개 페이지 HTML 원문을 한 덩어리로 이어 붙여 돌려준다.

    빈칸은 하나로 줄인다 — HTML은 줄바꿈으로 문장을 접지만 화면에서는
    한 칸이고, 사전 열쇠도 그 모양으로 적히기 때문이다.
    """
    src = "\n".join(
        html.unescape(p.read_text(encoding="utf-8"))
        for p in sorted((ROOT / "docs").glob("*.html")))
    return re.sub(r"\s+", " ", src)


def _is_written_by_hand(key):
    return re.sub(r"\s+", " ", key).strip() in _static_page_text()


def test_no_new_date_is_baked_into_a_dictionary_key():
    """**화면이 만들어 내는** 날짜 열쇠가 늘어나지 않았는가.

    늘리려면 먼저 규칙(rules)으로 옮길 수 없는지 보라. 옮길 수 없어서
    정말 늘려야 한다면 위 숫자와 이유를 함께 고쳐라.
    """
    dated = [k for k in _dictionary_keys()
             if re.search(r"\d{4}-\d{2}-\d{2}", k)]
    grown = [k for k in dated if not _is_written_by_hand(k)]
    assert len(grown) <= GENERATED_DATED_KEYS_ALLOWED, (
        f"화면이 만들어 내는 날짜가 박힌 사전 열쇠가 {len(grown)}개로 "
        f"늘었다(허용 {GENERATED_DATED_KEYS_ALLOWED}) — 날짜가 바뀌면 "
        f"그 문장은 한국어로 돌아간다. 규칙(rules)으로 옮길 것:\n"
        + "\n".join(f"  · {k[:60]}"
                    for k in grown[GENERATED_DATED_KEYS_ALLOWED:]))


def test_the_hand_written_past_is_not_counted_as_debt():
    """대조군 — 정적 HTML에 박힌 과거까지 빚으로 세면 위 검사는 못 쓴다.

    기록 검증 페이지의 정정 이력은 날짜로 시작하는 문장이 수십 개다.
    그것까지 세면 번역을 포기하거나 검사를 꺼야 하는 두 갈래만 남는다.
    이 검사는 **면제가 실제로 작동하고 있는지**를 지킨다.
    """
    dated = [k for k in _dictionary_keys()
             if re.search(r"\d{4}-\d{2}-\d{2}", k)]
    exempt = [k for k in dated if _is_written_by_hand(k)]
    assert len(exempt) >= 20, (
        f"손으로 적힌 과거 열쇠가 {len(exempt)}개뿐이다 — 면제 판정이 "
        "고장 났거나(공백 처리·엔티티) 정정 이력 번역이 사라졌다")


def test_the_exemption_really_reads_the_pages():
    """대조군 — 면제가 아무 글자나 통과시키면 위 면제는 구멍이다."""
    assert not _is_written_by_hand(
        "2099-01-01, 이 문장은 어느 페이지에도 없습니다."), (
        "정적 HTML에 없는 문장이 면제를 통과했다 — 면제 판정이 고장 났다")


def test_the_daily_figures_are_not_baked_into_keys():
    """**매일** 바뀌는 값이 열쇠에 들어가면 영어는 하루도 못 간다.

    금액(원)·회차·일차처럼 배치가 매일 새로 쓰는 숫자가 열쇠 안에 있으면
    안 된다. 이런 문장은 규칙이 숫자를 잡아 그대로 흘려보내야 한다.
    정정 이력처럼 HTML에 손으로 박아 둔 과거 금액은 예외다 — 그 숫자는
    이 제품의 원칙상 다시 쓰이지 않는다.
    """
    bad = [k for k in _dictionary_keys()
           if re.search(r"[\d,]{4,}원|\d+일차|\d+회차|n=\d+", k)
           and not _is_written_by_hand(k)]
    assert not bad, (
        "매일 바뀌는 숫자가 사전 열쇠에 박혀 있다 — 내일이면 영어가 "
        f"사라진다. 규칙으로 옮길 것:\n"
        + "\n".join(f"  · {k[:70]}" for k in bad))


# ── ⑥ 절로 끊어 옮길 때 문장이 부서지지 않는가 ─────────────────

def test_the_seams_are_put_back_exactly_as_they_were(browser, site):
    """절을 잇던 ` — `를 ` · `로 바꿔 놓으면 원문과 다른 문장이 된다.

    매일 만들어지는 판단 설명은 "매수 +32% — 이동평균 교차: … · 🏛 의회 …"
    처럼 **두 가지 이음매**로 이어져 있다. 옮긴 뒤 전부 가운뎃점으로 이어
    붙이면 머리말과 근거의 관계가 사라진다.
    """
    page, _ = _open(browser, site, "us.html?lang=en", wait=1500)
    try:
        got = page.evaluate(
            "() => QuantI18N.look('매수 +32% — 최근 변동성이 커서 위험 조절이"
            " 비중을 낮게 잡음')")
        assert got, "절 단위 번역이 아예 안 걸렸다"
        assert "Buy +32%" in got, got
        assert " — " in got, f"이음매가 바뀌었다: {got}"
        assert " · " not in got, f"없던 가운뎃점이 생겼다: {got}"
    finally:
        page.close()


def test_a_clause_inside_brackets_is_not_split(browser, site):
    """괄호 안의 가운뎃점에서 끊으면 신뢰구간 설명이 조각난다."""
    page, _ = _open(browser, site, "us.html?lang=en", wait=1500)
    try:
        got = page.evaluate(
            "() => QuantI18N.look('참고: 전 종목 합산으로 모델이 60%±10%p라"
            " 말한 50번의 실제 상승 비율 55% (95% 신뢰구간 40%~70% · 봉이"
            " 빠진 3번은 제외 · 이 종목 단독 표본은 2번으로 축적 중)')")
        assert got and "95% CI 40-70%" in got, (
            f"괄호 안이 통째로 옮겨지지 않았다: {got}")
    finally:
        page.close()


def test_the_tooltip_carries_the_whole_reason(browser, site):
    """도움말을 중간에서 자르지 않는다.

    ⚠️ 예전에는 `esc(reason).slice(0,180)`이었다. 두 가지가 잘못이다:
       ① **이스케이프한 뒤** 잘라서 `&amp;` 같은 실체 참조가 중간에서 끊길
          수 있었다(따옴표 속성이 깨진다).
       ② 설명하라고 붙인 도움말이 문장 한가운데서 끝났다.
    끝 20글자가 그대로 들어 있는지로 확인한다 — 길이에 기대지 않는다.
    """
    import json as _json
    st = _json.loads((ROOT / "docs" / "status.json").read_text("utf-8"))
    reasons = []
    for book in (st.get("paper") or {}).values():
        hist = (book or {}).get("history") or []
        if hist:
            r = str((hist[-1] or {}).get("reason") or "")
            if len(r) > 200:
                reasons.append(r)
    if not reasons:
        pytest.skip("지금 장부에 긴 판단 설명이 없다 — 다음 배치에 다시 본다")
    longest = max(len(r) for r in reasons)
    page, _ = _open(browser, site, "index.html", wait=3000)
    try:
        titles = page.locator(".srow").evaluate_all(
            "els => els.map(e => (e.getAttribute('title') || '').length)")
        assert titles, "사이드바에 줄이 하나도 없다 — 검사가 헛돈다"
        # ⚠️ 끝 20글자로 보면 안 된다: 판단 설명은 대부분 같은 문장으로
        #    끝나서(의회 안내), 짧은 줄 하나만 안 잘려도 통과해 버린다.
        #    **가장 긴 도움말의 길이**로 본다 — 자르면 바로 드러난다.
        assert max(titles) > 180, (
            f"도움말이 {max(titles)}자에서 끊긴다(장부의 가장 긴 설명은 "
            f"{longest}자) — 설명하라고 붙인 것이 설명을 못 한다")
    finally:
        page.close()

# ── ⑦ 매일 만들어지는 '판단 재료'는 이름까지 옮겨진다 ──────────
#
# 판단 근거는 "20일선 이격 +4.0%(선 위)"처럼 **값 + 괄호 안의 상태 이름**으로
# 만들어진다(quant/live/explain.py). 이름은 종목·날마다 달라져 값과의 조합이
# 수백 가지라, 규칙 하나에 다 적을 수 없다. 그래서 규칙은 값만 흘려보내고
# 이름은 사전으로 한 번 더 보낸다(치환문의 `$*n`).
#
# 이 검사가 지키는 것: 그 이름들이 **정말 사전에 있는가.** 하나라도 빠지면
# 그날 그 종목의 근거 문장만 반쪽 영어가 된다 — 그런 문장은 한국어보다 나쁘다.

_FEATURE_NOTES = [
    ("20일선 이격 +4.0%(선 위)",
     "distance from the 20-day average +4.0% (above the line)"),
    ("VIX 기간구조(공포의 급성도) 0.77(깊은 콘탱고(안정))",
     "VIX term structure (how acute the fear is) 0.77 (deep contango (calm))"),
    ("GK 변동성(고저가 기반) 일 2.4%",
     "GK volatility (from highs and lows) 2.4%/day"),
    ("외국인 수급 z=+1.4(강한 순매수)",
     "foreign investors flow z=+1.4 (strong net buying)"),
]


@pytest.mark.parametrize("korean,english", _FEATURE_NOTES)
def test_a_reason_ingredient_is_translated_name_and_all(
        browser, site, korean, english):
    """값은 그대로, **이름은 영어로.** 둘 중 하나만 되면 반쪽이다."""
    page, _ = _open(browser, site, "us.html?lang=en", wait=1500)
    try:
        got = page.evaluate("(s) => QuantI18N.look(s)", korean)
        assert got == english, f"{korean!r} → {got!r}"
    finally:
        page.close()


def test_an_unknown_ingredient_name_stays_korean(browser, site):
    """대조군 — 모르는 이름을 **지어내면** 안 된다.

    `$*n`은 "사전에 있으면 옮기고 없으면 그대로 둔다"여야 한다. 없는 것을
    영어처럼 만들어 내면 숫자 옆에서 사실이 아닌 말이 된다.
    """
    page, _ = _open(browser, site, "us.html?lang=en", wait=1500)
    try:
        got = page.evaluate(
            "() => QuantI18N.look('20일선 이격 +4.0%(달나라 기분)')")
        assert got is None or "달나라 기분" in got, (
            f"모르는 상태 이름을 지어냈다: {got!r}")
    finally:
        page.close()


def test_every_reason_ingredient_name_is_in_the_dictionary():
    """근거 문장에 쓰이는 **피처 이름 전부**가 사전에 있는가.

    ⚠️ 같은 목록이 두 곳에 있으면 반드시 갈라진다(FROZEN_IDEAS ①). 이름은
       explain.py가 원본이고 사전은 사본이라, 원본이 늘면 여기서 걸린다.
    """
    from quant.live.explain import FEATURE_KO
    missing = [ko for ko in sorted(set(FEATURE_KO.values()))
               if '"%s"' % ko not in DICT]
    assert not missing, (
        "판단 근거에 나오는 이름인데 영어가 없다 — 그날 그 문장은 반쪽 "
        f"영어가 된다:\n" + "\n".join(f"  · {k}" for k in missing))


def test_a_greedy_rule_cannot_beat_clause_by_clause(browser, site):
    """욕심 많은 규칙을 **일부러 심어** 엔진이 이기는지 본다.

    ⚠️ 이 검사가 규칙을 직접 심는 이유: 지금 사전의 규칙은 전부 가운뎃점을
       못 넘게 좁혀 두었다. 그러니 사전만 보고 있으면 엔진의 이 안전망이
       꺼져도 아무 일이 안 일어난 것처럼 보인다 — 그리고 다음에 누가 넓은
       규칙을 하나 적는 순간 조용히 반쪽 영어가 나간다.
    """
    page, _ = _open(browser, site, "us.html?lang=en", wait=1500)
    try:
        got = page.evaluate("""() => {
          const greedy = ["^(.+) · (.+)$", "$1 GREEDY $2"];
          window.QUANT_EN.rules.unshift(greedy);
          const out = QuantI18N.look("오늘의 체결 · 체결 시점");
          window.QUANT_EN.rules.shift();
          return out;
        }""")
        assert got, "두 절짜리 문장이 아예 안 옮겨졌다"
        assert "GREEDY" not in got, (
            f"통째로 삼킨 규칙이 이겼다 — 절 단위 결과가 더 나은데도: {got}")
        assert not re.search(r"[가-힣]", got), f"한국어가 남았다: {got}"
    finally:
        page.close()


def test_a_greedy_rule_does_not_swallow_a_whole_sentence(browser, site):
    """욕심 많은 규칙이 여러 절을 삼키면 **가운데만** 영어가 된다.

    실제로 당했다(2026-08-26): `^(.+)\\(…원/배정 …원\\)\\. 대신 (.+)$`가 절
    열 개짜리 문장을 통째로 물어 가운데 한 절만 옮기고 앞뒤를 한국어로
    남겼다. 엔진은 절 단위로 다시 해 보고 **한국어가 덜 남는 쪽**을 쓴다.
    """
    long = ("— 이더리움(641원/배정 639원) · 엔비디아(561원/배정 559원) · "
            "아마존(1,715원/배정 1,710원). 대신 SK하이닉스 · NAVER · "
            "133690.KS이(가) 자리를 내줬습니다. 확신도가 높은 쪽부터 채우기 "
            "때문이며, 그만큼 종목 수는 줄어듭니다")
    page, _ = _open(browser, site, "us.html?lang=en", wait=1500)
    try:
        got = page.evaluate("(s) => QuantI18N.look(s)", long)
        assert got, "긴 배분 설명이 아예 안 옮겨졌다"
        assert not re.search(r"[가-힣]", got), f"한국어가 남았다: {got}"
        for money in ("641", "639", "1,715", "1,710", "561", "559"):
            assert money in got, f"금액 {money}이(가) 사라졌다: {got}"
    finally:
        page.close()

# ── ⑧ 남의 글은 옮기지 않는다 ──────────────────────────────────
#
# 커밋 제목(개선 이력)과 뉴스 헤드라인은 **끝이 없는 남의 글**이다. 매일 새로
# 생겨 사전에 담을 수 없고, 일반 규칙이 앞머리만 잡으면 "90 days: 시계가 선언만
# 봤다"처럼 반쪽이 된다. 그 자리는 `data-qi18n="keep"`으로 아예 빼 둔다.

def test_the_engine_leaves_a_marked_place_alone(browser, site):
    """표시해 둔 자리는 영어로 봐도 **한 글자도** 안 바뀐다."""
    page, _ = _open(browser, site, "index.html?lang=en", wait=1500)
    try:
        got = page.evaluate("""() => {
          const box = document.createElement('div');
          box.setAttribute('data-qi18n', 'keep');
          box.innerHTML = '<span>오늘의 판단</span>';
          document.body.appendChild(box);
          const free = document.createElement('div');
          free.innerHTML = '<span>오늘의 판단</span>';
          document.body.appendChild(free);
          QuantI18N.apply();
          return [box.textContent, free.textContent];
        }""")
        assert got[0] == "오늘의 판단", f"표시한 자리를 건드렸다: {got[0]!r}"
        # 대조군 — 표시가 없으면 옮겨져야 한다. 아니면 위 검사는 아무것도
        # 안 지킨다(엔진이 통째로 죽어도 통과한다).
        assert got[1] != "오늘의 판단", (
            "표시 없는 자리도 한국어 그대로다 — 엔진이 안 돌고 있다")
    finally:
        page.close()


def test_a_marked_place_survives_being_drawn_later(browser, site):
    """**나중에 그려지는** 조각도 표시를 지켜야 한다.

    개선 이력도 브리핑도 자료를 받아 온 뒤에 그려진다. 그때는 조각 자신이
    아니라 **조상**에 표시가 붙어 있으므로, 관찰자가 조상까지 거슬러 보지
    않으면 표시는 있으나 마나다.
    """
    page, _ = _open(browser, site, "index.html?lang=en", wait=1500)
    try:
        got = page.evaluate("""async () => {
          const box = document.createElement('div');
          box.setAttribute('data-qi18n', 'keep');
          document.body.appendChild(box);
          const free = document.createElement('div');
          document.body.appendChild(free);
          // 화면이 실제로 하는 일 — 자료를 받은 뒤에 글자를 그려 넣는다.
          box.innerHTML = '<span>오늘의 판단</span>';
          free.innerHTML = '<span>오늘의 판단</span>';
          await new Promise(r => setTimeout(r, 150));
          return [box.textContent, free.textContent];
        }""")
        assert got[0] == "오늘의 판단", (
            f"나중에 그린 조각이 표시를 뚫고 번역됐다: {got[0]!r}")
        # 대조군 — 표시가 없으면 관찰자가 옮겨야 한다.
        assert got[1] != "오늘의 판단", (
            "표시 없는 조각도 한국어 그대로다 — 관찰자가 안 돌고 있다")
    finally:
        page.close()


def test_the_commit_titles_are_marked_as_left_alone():
    """개선 이력의 커밋 제목이 **표시된 자리 안에** 들어 있는가."""
    assert 'data-qi18n="keep"' in IDX, (
        "첫 화면에 옮기지 않을 자리 표시가 없다 — 커밋 제목이 규칙에 "
        "물려 반쪽 영어가 된다")
    assert 'data-qi18n="keep">${esc(e.title)}' in IDX, (
        "커밋 제목이 표시된 자리 밖에 있다")


def test_the_news_headlines_are_marked_as_left_alone():
    """뉴스 헤드라인도 마찬가지 — 남의 글이다."""
    paper = (DOCS / "paper.html").read_text("utf-8")
    # 헤드라인이 나가는 문은 **둘**이다 — 링크가 있을 때와 없을 때.
    # 한쪽만 보면 다른 쪽이 조용히 번역된다(FROZEN_IDEAS ⑭: 형제를 찾아라).
    assert 'rel="noopener" data-qi18n="keep">${esc(b.title)}</a>' in paper, (
        "링크가 붙은 헤드라인이 옮기지 않을 자리에 있지 않다")
    assert '`<span data-qi18n="keep">${esc(b.title)}</span>`' in paper, (
        "링크가 없는 헤드라인이 옮기지 않을 자리에 있지 않다")
    assert 'font-size:12px" data-qi18n="keep">— ${esc(b.source)}' in paper, (
        "매체 이름이 옮기지 않을 자리에 있지 않다")


def test_the_page_says_the_headlines_stay_korean():
    """왜 한국어인지 **적어야** 한다 — 안 적으면 고장으로 읽힌다."""
    assert "commit titles verbatim" in DICT, (
        "커밋 제목이 한국어로 남는 이유가 영어로 적혀 있지 않다")
    assert "original Korean" in DICT, (
        "뉴스 헤드라인이 한국어로 남는 이유가 영어로 적혀 있지 않다")


def test_the_worst_day_reason_is_not_cut_at_ninety_letters():
    """오답 노트의 근거가 90자에서 잘리면 **옮길 문장 자체가 없다.**

    잘린 꼬리("평균 진폭(")는 사전에도 규칙에도 걸리지 않는다. 화면에서
    줄이는 일은 CSS가 하고, 글자는 통째로 둔다(도움말에도 통째로).
    """
    paper = (DOCS / "paper.html").read_text("utf-8")
    assert "String(sym.reason).slice(0,90)" not in paper, (
        "오답 노트의 판단 근거를 90자에서 자르고 있다")
    assert "text-overflow:ellipsis" in paper, (
        "글자를 줄이는 일을 CSS가 하고 있지 않다")


# ── ⑨ 한국 밖에서 들어오면 영어로 맞는다 ───────────────────────
#
# 사장님 지시(2026-08-26): *"한국 말고 다른 나라에서 우리 서비스 들어오면
# 자동으로 영어로 보이게 해줘."*
#
# 버튼이 있어도 못 찾으면 없는 것과 같다. 영어권 방문자는 한국어로 가득 찬
# 첫 화면에서 대개 3초 안에 떠난다 — 그 사람에게 이 사이트는 한국어 전용이다.
#
# 다만 **짐작은 짐작이다.** 사람이 고른 적이 있으면 그 선택이 언제나 이기고,
# 짐작으로 영어가 된 화면은 그렇다고 밝히고 되돌아갈 길을 함께 준다.

_ABROAD = ["en-US", "ja-JP", "de-DE", "zh-CN"]


@pytest.mark.parametrize("lang", _ABROAD)
def test_a_visitor_from_abroad_lands_in_english(browser, site, lang):
    """한국어를 첫째로 원하지 않으면 **아무것도 안 눌러도** 영어다."""
    page, errors = _open(browser, site, "us.html", wait=2000, lang=lang)
    try:
        assert not errors, f"{lang}: {errors}"
        assert page.locator("html").get_attribute("lang") == "en", (
            f"{lang} 브라우저인데 한국어로 떴다")
        left = page.evaluate(_LEFTOVER_JS)
        assert not left, f"{lang}: 영어인데 한국어가 남았다 — {left[:3]}"
    finally:
        page.close()


def test_a_korean_visitor_still_lands_in_korean(browser, site):
    """대조군 — 한국어 브라우저는 **원문 그대로**여야 한다.

    이게 없으면 위 검사는 "무조건 영어"로도 통과한다. 이 사이트의 원본은
    한국어이고, 사장님과 국내 독자가 첫 번째 독자다.
    """
    page, errors = _open(browser, site, "us.html", wait=2000, lang="ko-KR")
    try:
        assert not errors, errors
        assert page.locator("html").get_attribute("lang") == "ko", (
            "한국어 브라우저인데 영어로 떴다")
        assert len(page.evaluate(_LEFTOVER_JS)) > 20, (
            "한국어 브라우저인데 한국어가 거의 없다")
    finally:
        page.close()


def test_a_korean_who_also_reads_english_gets_korean(browser, site):
    """`ko-KR` 다음에 `en-US`가 붙어 있어도 **첫째만 본다.**

    반대로 목록을 훑어 한국어를 '찾아내면', 영어를 더 좋아하지만 한국어도
    읽을 줄 아는 사람에게 한국어가 나간다 — 그건 짐작을 거꾸로 하는 것이다.
    """
    page, _ = _open(browser, site, "us.html", wait=1200, lang="ko-KR")
    try:
        got = page.evaluate("""() => {
          // 둘 다 갈아 끼운다 — `languages`가 비면 엔진은 `language`를
          // 본다. 하나만 비우면 "아무것도 모를 때"를 흉내 낼 수 없다.
          const ask = (list) => {
            Object.defineProperty(navigator, 'languages',
              {get: () => list, configurable: true});
            Object.defineProperty(navigator, 'language',
              {get: () => (list[0] || ''), configurable: true});
            return QuantI18N.guess();
          };
          return [ask(['ko-KR', 'en-US']), ask(['en-US', 'ko-KR']),
                  ask(['ko']), ask([]), ask(['fr'])];
        }""")
        # 아무것도 모르면 **원본(한국어)**이다 — 짐작이 원본을 밀어내면 안 된다.
        assert got == ["ko", "en", "ko", "ko", "en"], got
    finally:
        page.close()


def test_a_choice_beats_the_browser(browser, site):
    """사람이 고른 것이 짐작보다 세다 — 주소로도, 저장값으로도."""
    page, _ = _open(browser, site, "us.html?lang=ko", wait=1500,
                    lang="en-US")
    try:
        assert page.locator("html").get_attribute("lang") == "ko", (
            "?lang=ko 로 들어왔는데 브라우저 언어가 이겼다")
        # 저장값도 마찬가지 — 한 번 고르면 다음 방문부터 그대로다.
        page.evaluate("() => localStorage.setItem('quant.lang', 'ko')")
        page.goto(page.url.split("?")[0])
        page.wait_for_timeout(1500)
        assert page.locator("html").get_attribute("lang") == "ko", (
            "한국어를 골라 뒀는데 브라우저 언어가 이겼다")
    finally:
        page.close()


def test_the_guess_is_not_remembered_as_a_choice(browser, site):
    """짐작을 저장하면 **고른 것과 구별할 수 없어진다.**

    구별이 사라지면 "짐작이라 밝히는 줄"이 영영 안 뜨고, 사람이 한국어를
    골랐는지 브라우저가 그렇게 정한 건지 아무도 모른다.
    """
    page, _ = _open(browser, site, "us.html", wait=1500, lang="en-US")
    try:
        saved = page.evaluate("() => localStorage.getItem('quant.lang')")
        assert saved is None, f"짐작이 선택으로 저장됐다: {saved!r}"
        assert page.evaluate("() => QuantI18N.chosen()") is False
    finally:
        page.close()


def test_the_automatic_switch_says_so_and_shows_the_way_back(browser, site):
    """짐작으로 영어가 됐으면 **그렇다고 적고 한국어 링크를 준다.**"""
    page, _ = _open(browser, site, "us.html", wait=2000, lang="en-US")
    try:
        note = page.locator("#qi18n-auto")
        assert note.count() == 1, "자동 전환을 알리는 줄이 없다"
        assert "browser" in note.inner_text().lower(), note.inner_text()
        back = note.locator("a")
        assert back.count() == 1, "한국어로 돌아갈 링크가 없다"
        assert "lang=ko" in (back.get_attribute("href") or "")
    finally:
        page.close()


def test_a_chosen_english_page_does_not_nag(browser, site):
    """대조군 — **스스로 고른** 영어에는 그 줄이 뜨면 안 된다.

    고른 사람에게 "브라우저가 그래서 영어입니다"는 사실이 아니다.
    """
    page, _ = _open(browser, site, "us.html?lang=en", wait=1500,
                    lang="ko-KR")
    try:
        assert page.locator("#qi18n-auto").count() == 0, (
            "직접 고른 영어인데 '브라우저가 정했다'고 적혀 있다")
    finally:
        page.close()


def test_the_home_button_offers_the_way_back_after_an_auto_switch(
        browser, site):
    """자동으로 영어가 됐을 때 홈 바 버튼이 **'한국어'**를 권하는가.

    실제로 당했다(2026-08-26): 첫 화면이 "지금 영어인가"를 스스로 한 번 더
    판단하는 사본을 갖고 있어서, 자동 전환이 생기자마자 어긋났다. 영어로
    보고 있는 사람에게 버튼은 계속 'EN'이었다 — 되돌아갈 길이 없어 보인다.
    """
    page, _ = _open(browser, site, "index.html", wait=2500, lang="en-US")
    try:
        # ⚠️ 2026-08-26에 홈이 자기 바를 버리고 **공용 바**를 쓰게 되면서
        #    선택자가 바뀌었다(#navlang/#mlang → .qn-lang). 지켜야 할 사실은
        #    그대로다: 영어로 보고 있는 사람에게 버튼이 '한국어'를 권해야
        #    한다. 공용 바는 이 버튼을 **좁은 화면에서도 숨기지 않으므로**
        #    모바일용 사본(#mlang)이 따로 필요 없다 — 사본이 없어진 것은
        #    기능이 빠진 게 아니라 사본을 둘 이유가 없어진 것이다.
        el = page.locator("#qnav .qn-lang")
        assert el.count() == 1, "공용 바에 언어 버튼이 없다"
        assert el.inner_text().strip() == "한국어", (
            f"버튼이 '{el.inner_text().strip()}'라고 적혀 있다 — "
            "영어로 보고 있는 사람에게 영어를 권하고 있다")
    finally:
        page.close()


def test_the_screen_tests_pin_the_browser_language():
    """검사용 브라우저의 언어를 **환경에 맡기지 않는다.**

    자동 전환의 재료는 `navigator.languages`다. 검사용 크로미움은 보통
    영어로 뜨므로, 못박지 않으면 한국어 화면을 보는 검사 수십 개가 조용히
    **영어 화면**을 보게 된다 — 그건 검사가 다른 일을 하는 것이다
    (감사 130·278에서 이미 치른 대가).
    """
    helper = (ROOT / "tests" / "_browser.py").read_text("utf-8")
    assert "navigator, 'languages'" in helper, (
        "화면 검사의 공용 준비가 브라우저 언어를 고정하지 않는다")
    assert 'lang: str = "ko-KR"' in helper, (
        "기본값이 한국어가 아니다 — 원본 화면을 보는 검사가 영어를 본다")
