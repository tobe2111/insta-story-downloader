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
import http.server
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
DONE = ["us.html", "intraday.html", "futures.html", "weekly.html"]

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

def test_no_dictionary_key_pins_a_date():
    """사전 열쇠에 **날짜를 박지 않는다** (2026-08-26에 값비싸게 배운 것).

    사전은 한국어 문장 **전체**를 열쇠로 쓴다. 그런데 화면의 어떤 문장에는
    새벽 배치가 매일 새 날짜를 끼워 넣는다. 그 문장을 통째로 사전에 넣으면
    열쇠에 그날의 날짜가 박히고, **다음 날 밤 배치가 도는 순간 열쇠가
    어긋난다** — 영어 화면에 한국어가 남고, 이 파일의 검사가 빨개진다.

    실제로 그렇게 됐다: 사전을 쓴 08-25 아침에는 장부가 2026-08-24였고
    검사가 초록이었다. 그날 밤 배치가 2026-08-25를 쓰자 세 페이지가
    빨개졌다. 하루짜리 초록불이었던 셈이고, 사전에 오늘 날짜를 다시
    넣어 봐야 내일 또 빨개진다 — 매일 헛울리는 관문은 곧 무시당한다.

    날짜처럼 매일 바뀌는 자리는 사전이 아니라 **rules(정규식)** 가 잡는다.
    엔진에 그 장치가 이미 있었는데(i18n.js의 rules) 안 쓴 것이 문제였다.
    """
    import re as _re
    # 사전 열쇠만 훑는다 — 영어 값에는 "corrected 2026-08-19"처럼 날짜가
    # 사실로 들어갈 수 있고(역사적 기록), 그건 낡지 않는다. 열쇠가 문제다.
    keys = _re.findall(r'^\s+"((?:[^"\\]|\\.)*)":', DICT, _re.M)
    assert len(keys) > 50, f"사전 열쇠를 못 읽었다({len(keys)}개) — 검사가 헛돈다"
    pinned = [k for k in keys if _re.search(r"\d{4}-\d{2}-\d{2}", k)]
    assert not pinned, (
        "사전 열쇠에 날짜가 박혀 있다 — 그 항목은 장부 날짜가 바뀌는 다음 "
        f"밤에 스스로 만료된다. rules(정규식)로 옮길 것: {pinned}")


def test_the_rules_catch_the_dates_instead():
    """대조군 — 사전에서 뺐는데 규칙에도 없으면 그냥 번역을 지운 것이다."""
    assert "^마지막 갱신: " in DICT, "주간 페이지의 갱신일 규칙이 없다"
    assert "마지막 확정일" in DICT, "단타 페이지의 확정일 규칙이 없다"


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
    if (n.parentNode && /qn-lang|navlang|mlang/.test(
        n.parentNode.className + " " + (n.parentNode.id || ""))) continue;
    const t = n.nodeValue.trim().replace(/\\s+/g, ' ');
    if (t && /[가-힣]/.test(t)) left.push(t);
  }
  return left;
}"""


def _open(browser, site, path, wait=2500):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    block_external(page)
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
