"""공개 페이지가 **하나도 빠짐없이** 실제로 그려지는가 (감사 264).

`docs/today.html`이 2026-08-16부터 공개 사이트에서 **통째로 죽어 있었습니다.**

    <script src="assets/tradingview.js">   ← 그런 파일은 없다 (tv-symbols.js)

`QuantTV`가 없으니 렌더가 던지고, 바깥 `catch(()=>{…})`가 그것을 삼켜
화면에는 "기록을 불러오지 못했습니다." 한 줄만 남았습니다. 읽는 사람은
그것을 **"오늘은 기록이 없나 보다"**로 읽습니다.

같은 자리에서 첫 화면의 인라인 차트 칸도 죽어 있었습니다 — 아무 줄에도
붙지 않는 `tr.clickable`을 기다리고 있었고, 그 안에 역시 존재하지 않는
`QuantTV.symbol(...)` 호출이 숨어 있었습니다.

**검사는 매일 초록이었습니다.** 감사 245가 브라우저 검사를 세웠지만
`index.html` 하나뿐이었고, 나머지 페이지는 아무도 띄워 보지 않았습니다.

그래서 이 파일은 공개되는 모든 페이지를 **진짜 브라우저로 띄웁니다.**
페이지가 죽었는지 판단하는 기준은 세 가지입니다.

    ① 스크립트가 던지지 않았는가 (pageerror)
    ② 우리 서버의 파일 중 404가 없는가 (오타 난 <script src>가 여기 걸린다)
    ③ 그 페이지의 **실패 문구**가 화면에 없는가
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

# 브라우저를 어디서 찾는지도, 없을 때 건너뛸지도 **한 곳에서만** 정한다.
# 감사 278에서 찾기만 모았더니 `Path("")`가 현재 디렉터리가 되어 관문이
# 통과해 버렸고, 그날 밤 배치 넷이 통째로 멈췄다(감사 280).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _browser import block_external, chromium_or_skip  # noqa: E402

# (경로, 그 페이지가 '못 그렸다'고 말할 때 쓰는 문구)
PAGES = [
    ("index.html", "다 그리지 못했습니다"),
    ("today.html", "다 그리지 못했습니다"),
    ("paper.html", None),
    ("intraday.html", None),
    # 트랙마다 한 장씩(2026-08-22 감사 305) — 새 페이지가 이 목록에 안
    # 들어오면 "그리다 죽는 페이지"가 조용히 생긴다.
    ("us.html", None),
    ("futures.html", None),
    # ⚠️ 머신러닝 페이지(감사 311)가 이 목록에 안 들어와 있었다 — 새 페이지를
    #    만들면서 "그리다 죽는가"를 아무도 안 보고 있었다(감사 317).
    ("ml.html", None),
    ("weekly.html", None),
    ("trust.html", None),
    ("admin.html", None),
    ("sns_card.html?n=4", None),
    ("404.html", None),
    ("index-standalone.html", None),
]

# 정적 서버가 흉내 낼 수 없는 것들 — 운영에서는 워커가 준다. 여기서 404가
# 나는 것은 정상이므로 세지 않는다. **경로를 명시한다** — "무시할 것"을
# 뭉뚱그리면 진짜 오타까지 함께 무시된다.
SERVED_BY_WORKER = ("/api/",)


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    """docs 사본을 정적 서버로 띄운다. 반환: base URL."""
    pytest.importorskip("playwright.sync_api",
                        reason="playwright 없음 — 화면 렌더 검사 생략")
    root = tmp_path_factory.mktemp("site")
    shutil.copytree(ROOT / "docs", root, dirs_exist_ok=True)

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


def _visit(browser, site, path):
    """반환: (본문 텍스트, 스크립트 예외들, 우리 서버 404들)."""
    page = browser.new_page()
    block_external(page)
    errors, missing = [], []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("response", lambda r: (
        missing.append(f"{r.status} {r.url}")
        if (r.status == 404 and site in r.url
            and not any(s in r.url for s in SERVED_BY_WORKER)) else None))
    page.on("requestfailed", lambda r: (
        missing.append(f"실패 {r.url}")
        if (site in r.url
            and not any(s in r.url for s in SERVED_BY_WORKER)) else None))
    try:
        page.goto(f"{site}/{path}")
        page.wait_for_timeout(2200)
        text = page.locator("body").inner_text()
    finally:
        page.close()
    return text, errors, missing


@pytest.mark.parametrize("path,failure_phrase", PAGES,
                         ids=[p.split("?")[0] for p, _ in PAGES])
def test_the_page_is_actually_alive(browser, site, path, failure_phrase):
    text, errors, missing = _visit(browser, site, path)
    assert not errors, f"{path}: 스크립트가 던졌다 — {errors}"
    # 없는 파일을 부르는 <script src>가 여기서 잡힌다. today.html이 딱 그랬다.
    assert not missing, f"{path}: 우리 서버에 없는 파일을 부른다 — {missing}"
    assert text.strip(), f"{path}: 화면이 비었다"
    if failure_phrase:
        assert failure_phrase not in text, (
            f"{path}: 페이지가 '못 그렸다'고 말하고 있다\n{text[:400]}")


def test_the_harness_would_notice_a_dead_page(browser, site):
    """대조군 — **이 검사가 진짜로 죽은 페이지를 잡는지** 스스로 확인한다.

    today.html을 죽였던 것과 같은 일(없는 스크립트를 부르기)을 일부러 시켜
    본다. 이게 통과해 버리면 위의 검사들은 아무것도 지키지 않는 장식이다
    (감사 229 — 검사는 초록인데 기능은 죽어 있다).
    """
    page = browser.new_page()
    block_external(page)
    missing = []
    page.on("response", lambda r: (
        missing.append(r.url) if r.status == 404 else None))
    try:
        page.goto(f"{site}/index.html")
        page.evaluate("""() => {
            const s = document.createElement("script");
            s.src = "assets/definitely-not-here.js";
            document.head.appendChild(s);
        }""")
        page.wait_for_timeout(800)
    finally:
        page.close()
    assert any("definitely-not-here" in u for u in missing), (
        f"없는 파일을 불렀는데 하네스가 못 봤다: {missing}")


def test_clicking_a_symbol_opens_its_chart(browser, site):
    """종목 줄을 눌렀을 때 차트가 **실제로 뜨는가**(사장님 2026-08-14 요청).

    페이지가 통째로 살아 있어도 이 기능은 따로 죽을 수 있다 — 실제로 그랬다:
    같은 클릭에 화면 두 개가 달려 있었고, 그중 하나는 아무 줄에도 붙지 않는
    클래스를 기다리며 없는 함수를 부르고 있었다(감사 264).
    """
    page = browser.new_page()
    block_external(page)
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    try:
        page.goto(f"{site}/index.html")
        page.wait_for_timeout(2200)
        # 종목별 현황은 첫 화면에서 접혀 있다(감사 282) — 펴고 눌러야 한다.
        if not page.locator("#symtable").is_visible():
            page.click("#morebtn")
            page.wait_for_timeout(300)
        rows = page.locator("#symtable tbody tr[data-k]:visible")
        assert rows.count() > 0, "종목표가 안 그려졌다"
        rows.first.click()
        page.wait_for_timeout(1200)
        assert page.locator("dialog[open]").count() == 1, "상세 창이 안 열렸다"
        assert page.locator("#dlg-chart iframe").count() == 1, (
            "차트가 안 붙었다 — 창은 열렸는데 안이 비어 있다")
    finally:
        page.close()
    assert not errors, f"줄을 누르자 스크립트가 던졌다 — {errors}"


def test_the_weekly_table_really_appears_on_the_home(browser, site):
    """주간 표가 홈에서 **실제로 그려지는가** (2026-08-26 병합).

    소스 계약(test_the_hundred_man_account_lives_on_one_page)은 배선이
    적혀 있는지만 본다. 여기서는 진짜 브라우저가 카드를 열어 숫자를
    확인한다 — 옛 주간 페이지가 스크립트 이름 하나 때문에 통째로 죽어
    있던 적이 있다(감사 264). 옮긴 화면도 같은 방식으로 죽을 수 있다.
    """
    page = browser.new_page()
    block_external(page)
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    try:
        page.goto(f"{site}/index.html")
        page.wait_for_timeout(2200)
        page.click("#morebtn")
        page.wait_for_timeout(500)
        card = page.locator("#weekly-card")
        assert card.is_visible(), (
            "주간 카드가 안 열렸다 — 배선은 있는데 그려지지 않는다")
        txt = card.inner_text()
        assert "불러오는 중" not in txt, "주간 카드가 영원히 불러오는 중이다"
        assert "주간 수익률" in txt, f"주간 표가 비어 있다:\n{txt[:300]}"
        # 주 하나라도 실제 숫자가 있어야 한다 — 머리글만 있으면 빈 표다.
        assert re.search(r"[+-]\d+\.\d\d%", txt), (
            f"주간 표에 숫자가 없다 — 머리글만 그렸다:\n{txt[:300]}")
        # 옮기면서 길을 끊지 않았는지 — 더 깊은 화면으로 가는 링크.
        for href in ("paper.html", "today.html", "weekly.html"):
            assert card.locator(f'a[href="{href}"]').count() == 1, (
                f"{href}로 가는 길이 화면에 없다")
    finally:
        page.close()
    assert not errors, f"주간 카드를 그리다 스크립트가 던졌다 — {errors}"


# ── 소스 계약 — 페이지가 실패를 **말하는가** ──────────────────────

@pytest.mark.parametrize("name", ["index.html", "today.html"])
def test_the_render_does_not_swallow_its_error(name):
    """`catch(()=>{})`는 '아무 일도 없었다'와 같은 말이다.

    감사 245가 첫 화면에 세운 계약인데, '오늘의 판단'에는 없었다 — 그래서
    이 페이지가 하루 넘게 죽어 있는 동안 콘솔조차 조용했다.
    """
    src = (ROOT / "docs" / name).read_text("utf-8")
    assert "catch(()=>{document.getElementById" not in src, (
        f"{name}: 렌더 실패를 통째로 삼킨다")
    assert "console.error" in src, f"{name}: 콘솔에도 안 남기면 개발자도 못 본다"


# ── 모바일 삼단 바 — 진짜 화면에서 열리는가 ──────────────────────

# ⚠️ 2026-08-26부터 홈도 공용 바를 쓴다(사장님: "상단바도 페이지마다 구성이
#    다르고 일치시켜줘"). 그전에는 홈만 선택자가 달랐다(.burger/.mnav) —
#    선택자가 둘이라는 사실 자체가 구현이 둘이라는 증거였다. 그래도 홈은
#    목록에 남긴다: 바를 실어야 할 페이지가 실제로 싣는지는 페이지마다 봐야
#    한다(스크립트 한 줄이 빠지면 그 페이지만 조용히 바를 잃는다).
@pytest.mark.parametrize("path,burger_sel,menu_link_sel", [
    ("index.html", "#qnav .qn-burger", "#qnav .qn-menu a"),
    ("trust.html", "#qnav .qn-burger", "#qnav .qn-menu a"),
])
def test_the_mobile_menu_actually_opens(browser, site, path,
                                        burger_sel, menu_link_sel):
    """모바일 폭에서 삼단 바를 누르면 다른 페이지로 가는 메뉴가 열린다.

    2026-08-23 사장님: "모바일로 보면 다른 페이지를 볼 수가 없어."
    소스 계약(test_the_site_wears_one_navbar)은 글자를 보고, 여기는
    **진짜 브라우저**가 390px 화면에서 버튼이 보이고 눌리는지를 본다 —
    CSS 한 줄(display:none)이면 글자는 남고 기능만 죽는다.
    """
    page = browser.new_page(viewport={"width": 390, "height": 800})
    block_external(page)
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    try:
        page.goto(f"{site}/{path}")
        page.wait_for_timeout(1500)
        burger = page.locator(burger_sel)
        assert burger.is_visible(), f"{path}: 모바일인데 삼단 바가 안 보인다"
        links = page.locator(menu_link_sel)
        assert not links.first.is_visible(), (
            f"{path}: 누르기도 전에 메뉴가 열려 있다")
        burger.click()
        page.wait_for_timeout(300)
        assert links.count() >= 5, f"{path}: 메뉴 링크가 이상하게 적다"
        assert links.first.is_visible(), f"{path}: 삼단 바를 눌러도 안 열린다"
        # 바깥을 누르면 닫힌다(모바일 관례) — 본문을 가리는 채로 남지 않게
        page.mouse.click(200, 600)
        page.wait_for_timeout(300)
        assert not links.first.is_visible(), f"{path}: 메뉴가 안 닫힌다"
    finally:
        page.close()
    assert not errors, f"{path}: 메뉴 조작 중 스크립트가 던졌다 — {errors}"


# ── 대시보드로 가는 문이 **정말 눌리는가** (2026-08-25 사장님 지시) ──

def _dash_href(page):
    """화면에 보이는 대시보드 링크의 주소. 안 보이면 None."""
    for sel in (".navdash", "#qnav .qn-dash", ".mnav .mdash",
                "#qnav .qn-menu .qn-mdash"):
        loc = page.locator(sel)
        if loc.count() and loc.first.is_visible():
            return loc.first.get_attribute("href")
    return None


@pytest.mark.parametrize("path", ["index.html", "paper.html"],
                         ids=["home", "shared-bar"])
def test_the_dashboard_door_opens_on_a_desktop(browser, site, path):
    """넓은 화면 — 상단 바에 대시보드 버튼이 보이고 admin.html로 간다."""
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    block_external(page)
    try:
        page.goto(f"{site}/{path}")
        page.wait_for_timeout(1200)
        assert _dash_href(page) == "admin.html", (
            f"{path}: 넓은 화면에서 대시보드 문이 안 보인다")
    finally:
        page.close()


@pytest.mark.parametrize("path", ["index.html", "paper.html"],
                         ids=["home", "shared-bar"])
def test_the_dashboard_door_opens_on_a_phone(browser, site, path):
    """좁은 화면 — 삼단 바를 열면 대시보드로 가는 문이 나온다.

    사장님 지시가 **"모바일 기준으로도"**였다. 좁은 화면에서 버튼을 숨기기만
    하면 그건 정리가 아니라 차단이다(2026-08-23에 같은 지적을 받았다).
    """
    page = browser.new_page(viewport={"width": 390, "height": 780})
    block_external(page)
    try:
        page.goto(f"{site}/{path}")
        page.wait_for_timeout(1200)
        # 대조군 — 열기 전에는 메뉴가 닫혀 있어야 한다(항상 펼쳐져 있으면
        # "모바일에서도 보인다"가 아무것도 증명하지 않는다).
        assert _dash_href(page) is None, f"{path}: 메뉴가 처음부터 열려 있다"
        burger = page.locator(".burger, #qnav .qn-burger").first
        assert burger.is_visible(), f"{path}: 좁은 화면에 삼단 바가 없다"
        burger.click()
        page.wait_for_timeout(400)
        assert _dash_href(page) == "admin.html", (
            f"{path}: 삼단 바를 열어도 대시보드로 갈 길이 없다 — 막다른 길이다")
    finally:
        page.close()
