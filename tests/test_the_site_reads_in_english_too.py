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


def test_both_bars_have_a_language_button():
    assert 'class="navlang"' in IDX, "홈 바에 언어 버튼이 없다"
    assert "qn-lang" in NAV, "공용 바에 언어 버튼이 없다"


def test_the_language_button_survives_a_narrow_screen():
    """대시보드 버튼과 달리 **좁은 화면에서 숨기지 않는다.**

    글자 두 개라 자리를 거의 안 먹는다. 숨기면 영어권 방문자에게 이
    사이트는 한국어 전용이 된다.
    """
    assert "@media(max-width:820px){.navlang{display:none}}" not in IDX, (
        "홈: 좁은 화면에서 언어 버튼이 사라진다")
    assert "#qnav .qn-lang{display:none}" not in NAV, (
        "공용 바: 좁은 화면에서 언어 버튼이 사라진다")
    # 홈의 삼단 바 메뉴에도 길이 있다(버튼을 못 봐도 메뉴에서 찾는다).
    assert 'id="mlang"' in IDX, "홈의 모바일 메뉴에 언어 항목이 없다"


# ── ② 사전 자체의 계약 ────────────────────────────────────────

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
