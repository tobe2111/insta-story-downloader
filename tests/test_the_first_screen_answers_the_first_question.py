"""첫 화면이 **처음 온 사람의 첫 질문**에 답하지 않았다 (감사 274).

사장님 2026-08-17:
  *"너무 정보가 많아. 얼마를 언제 투자를 했고, 지금 얼마 손해 혹은 이익인지
   그 정도만 나오는게 맞지 않아? 지금은 처음 보면 복잡해서 이해를 못해."*

맞는 지적입니다. 첫 화면은 다음 순서였습니다.

    ① 다운로드 광고 ("1,000,000원으로 굴리는 자동매매")
    ② 오른쪽 구석에 작은 글씨로 997,198원 · 판정 시계 · 검증한 도전자 3,880개
    ③ 사이드바에 경고 여덟 줄
    ④ 카드 열둘 · 표 셋

**"내 돈이 지금 얼마인가"가 광고 문구보다 아래에 있었습니다.**

그리고 같은 날 사장님이 물으셨습니다: *"997,198원 지금 상황이 이거 맞아?"*
물어봐야 알 수 있었다는 것 자체가 답입니다 — 그 숫자는 **이틀 전** 것이었고
(08-16 밤 배치가 본실행·재시도 모두 실패했고, 08-17 배치는 아직 돌기 전이었습니다)
화면 어디에도 그 사실이 크게 적혀 있지 않았습니다.

**숫자를 지우지는 않습니다.** 공개 장부에서 값을 없애는 것은 답이 아닙니다.
기본을 접어 두고, 누르면 펴지게 합니다.
"""

from __future__ import annotations

import functools
import http.server
import json
import shutil
import socketserver
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 브라우저를 어디서 찾는지는 **한 곳에서만** 정한다(감사 278). 이 줄이
# 파일마다 컨테이너 전용 경로를 적고 있던 탓에, GitHub 러너에서는
# 일곱 파일의 화면 계약이 통째로 조용히 건너뛰어지고 있었다.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _browser import block_external, chromium_or_skip  # noqa: E402


# 실측 장부(2026-08-15) — 이 파일의 숫자는 전부 여기서 온다.
EQ, BASE, DAY = 997197.56, 1_000_000.0, "2026-08-15"


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    pytest.importorskip("playwright.sync_api",
                        reason="playwright 없음 — 화면 검사 생략")
    root = tmp_path_factory.mktemp("site")
    shutil.copytree(ROOT / "docs", root, dirs_exist_ok=True)
    # ⚠️ 실제 status.json을 그대로 쓰면 내일 새벽 배치가 이 검사를 깬다.
    #    사고 당시 상태를 **재현해서** 넣는다.
    st = json.loads((ROOT / "docs" / "status.json").read_text("utf-8"))
    pf = st["paper"]["portfolio:ALL"]
    pf["equity"], pf["principal"], pf["start_cash"] = EQ, BASE, BASE
    pf["history"][-1]["date"] = DAY
    pf["history"][-1]["equity"] = EQ
    (root / "status.json").write_text(json.dumps(st, ensure_ascii=False), "utf-8")

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


@pytest.fixture()
def page(browser, site):
    pg = browser.new_page(viewport={"width": 1440, "height": 900})
    block_external(pg)
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(f"{site}/index.html")
    pg.wait_for_timeout(2400)
    yield pg
    assert not errors, f"스크립트가 던졌다 — {errors}"
    pg.close()


# ── ① 첫 질문에 답하는가 ─────────────────────────────────────────

def test_the_money_answer_comes_first(page):
    """돈 이야기가 **다운로드 광고보다 위에** 있어야 한다.

    순서가 곧 우선순위다. 광고가 먼저면 이 사이트는 '기록 공개'가 아니라
    '제품 판매' 페이지로 읽힌다.
    """
    g = page.locator("#glance").bounding_box()
    hero = page.locator("section.hero").bounding_box()
    assert g and hero, (g, hero)
    assert g["y"] < hero["y"], f"한눈에({g['y']})가 히어로({hero['y']}) 아래에 있다"


def test_it_says_how_much_when_and_the_profit(page):
    txt = page.locator("#glance").inner_text()
    assert "1,000,000원" in txt, f"넣은 돈이 없다:\n{txt}"
    assert "2026-08-13" in txt, f"언제 시작했는지가 없다:\n{txt}"
    assert "997,198원" in txt, f"지금 얼마인지가 없다:\n{txt}"
    assert "2,802원" in txt, f"손익 금액이 없다:\n{txt}"
    assert "0.28%" in txt, f"손익 비율이 없다:\n{txt}"
    assert "손해" in txt, f"이익인지 손해인지 말하지 않는다:\n{txt}"


def test_the_biggest_number_on_the_screen_is_the_account(page):
    """가장 큰 글씨가 계좌 금액이어야 한다 — 크기가 곧 '이게 중요하다'는 말이다."""
    size = page.evaluate(
        """() => parseFloat(getComputedStyle(
             document.querySelector('#glance .gnum')).fontSize)""")
    assert size >= 30, f"계좌 금액이 {size}px로 작다"


# ── ② 오래된 숫자를 오늘처럼 말하지 않는가 ───────────────────────

def test_a_stale_number_says_it_is_stale(page):
    """사장님이 "지금 상황이 이거 맞아?"라고 물어야 했던 이유가 여기다."""
    txt = page.locator("#glance").inner_text()
    assert DAY in txt, f"기준일이 없다:\n{txt}"
    assert "일 전" in txt, f"며칠 전 숫자인지 말하지 않는다:\n{txt}"
    assert "지금" not in txt.split("기준입니다")[0].split("넣은 돈")[0], txt


def test_the_gap_says_it_was_not_a_market_holiday(page):
    """**왜 없는지를 말하지 않으면 읽는 사람이 지어낸다**(감사 281).

    사장님이 이 띠를 보시고 *"8월 17일은 광복절 대체휴무긴 했지만 미국
    주식은 쉬지 않잖아"*라고 하셨다. 정확한 지적이고, 그 추측을 하게 만든
    것이 화면이다 — "새벽 배치가 기록을 남기지 못했습니다"는 **누가 왜**를
    말하지 않아, 읽는 사람이 달력에서 이유를 찾게 된다.

    빈칸의 이유는 우리가 먼저 말한다: 휴장이 아니라 **우리 쪽 고장**이다.
    """
    txt = page.locator("#glance").inner_text()
    assert "시장이 쉰 것이 아니라" in txt, (
        f"빈칸이 휴장 때문인지 고장 때문인지 말하지 않는다:\n{txt}")
    assert "배치가" in txt and "실패" in txt, (
        f"무엇이 실패했는지 말하지 않는다:\n{txt}")
    assert "채워 넣지 않습니다" in txt, (
        f"빠진 날을 나중에 채우지 않는다는 사실을 말하지 않는다 — "
        f"읽는 사람은 '곧 채워지겠지'로 읽는다:\n{txt}")


def test_a_fresh_number_is_not_scolded(browser, site, tmp_path):
    """대조군 — 오늘 기록이면 경고 띠가 뜨면 안 된다.

    이게 없으면 "항상 낡았다고 적는다"도 통과하고, 그러면 진짜 정체를
    구별할 수 없다.
    """
    import datetime

    root = tmp_path / "fresh"
    shutil.copytree(ROOT / "docs", root, dirs_exist_ok=True)
    st = json.loads((ROOT / "docs" / "status.json").read_text("utf-8"))
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    st["paper"]["portfolio:ALL"]["history"][-1]["date"] = today
    (root / "status.json").write_text(json.dumps(st, ensure_ascii=False), "utf-8")

    class _Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    srv = socketserver.TCPServer(
        ("127.0.0.1", 0), functools.partial(_Quiet, directory=str(root)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        pg = browser.new_page()
        block_external(pg)
        pg.goto(f"http://127.0.0.1:{srv.server_address[1]}/index.html")
        pg.wait_for_timeout(2400)
        txt = pg.locator("#glance").inner_text()
        pg.close()
    finally:
        srv.shutdown()
    assert "일 전" not in txt, f"오늘 기록인데 낡았다고 말한다:\n{txt}"
    assert today in txt, txt


# ── ③ 처음에는 접혀 있고, 누르면 펴지는가 ────────────────────────

FOLDED = ["🕰 판정 시계", "🎯 리스크 설정", "🧾 체결 가정 검증",
          "오답 노트", "탈락자 아카이브"]
ALWAYS = ["한눈에", "통합 계좌", "잔고", "거래내역", "종목별 현황"]


def _visible_headings(pg):
    return [h.inner_text().split("\n")[0].strip()
            for h in pg.locator("main h2").all() if h.is_visible()]


def test_the_advanced_cards_start_folded(page):
    vis = _visible_headings(page)
    for name in FOLDED:
        assert name not in vis, f"'{name}'이 처음부터 펴져 있다: {vis}"
    for name in ALWAYS:
        assert name in vis, f"'{name}'이 사라졌다: {vis}"


def test_pressing_the_button_unfolds_everything(page):
    page.locator("#morebtn").click()
    page.wait_for_timeout(400)
    vis = _visible_headings(page)
    for name in FOLDED + ALWAYS:
        assert name in vis, f"'{name}'이 펴지지 않았다: {vis}"
    # 다시 누르면 접힌다 — 한 방향으로만 가는 버튼은 함정이다.
    page.locator("#morebtn").click()
    page.wait_for_timeout(400)
    assert "오답 노트" not in _visible_headings(page)


def test_nothing_is_deleted_only_folded(page):
    """접는 것은 화면뿐이다 — 값은 문서 안에 그대로 있어야 한다.

    공개 장부에서 숫자를 **지우면** 그때부터 이건 장부가 아니다.
    """
    for name in FOLDED:
        assert page.get_by_text(name, exact=False).count() > 0, (
            f"'{name}'이 문서에서 아예 사라졌다")


def test_a_red_alarm_survives_the_fold(page):
    """🚨 경고는 접으면 안 된다 — 접힌 경고는 없는 경고다."""
    side = page.locator("aside.side").inner_text()
    assert "🚨" in side, f"급한 경고가 간단 보기에서 사라졌다:\n{side[:400]}"


# ── ④ 세 표 모두에서 차트가 열리는가 ─────────────────────────────

@pytest.mark.parametrize("table,label",
                         [("baltable", "잔고"), ("trtable", "거래내역"),
                          ("symtable", "종목별 현황")])
def test_clicking_a_row_opens_that_symbols_chart(page, table, label):
    """사장님 2026-08-17: "잔고, 거래내역, 운용종목 탭에서도 주식을 클릭하면
    해당 트레이딩뷰 차트가 보이게끔 해주고."

    한 표에서만 눌리면 읽는 사람은 나머지를 **고장**으로 읽는다.
    """
    rows = page.locator(f"#{table} tbody tr[data-k]")
    assert rows.count() > 0, f"{label} 표에 누를 수 있는 줄이 없다"
    rows.first.click()
    page.wait_for_timeout(1000)
    assert page.locator("dialog[open]").count() == 1, f"{label}: 창이 안 열렸다"
    assert page.locator("#dlg-chart iframe").count() == 1, (
        f"{label}: 창은 열렸는데 차트가 없다")


def test_the_dialog_reads_that_tables_own_headers(page):
    """창은 **그 표의 머리글**을 읽어야 한다.

    예전에는 칸을 번호로 집어서(`pick(1)`=현재가) 종목표에서만 맞았다.
    잔고에서 열면 '보유수량'을 '현재가'라고 부르게 된다.
    """
    page.locator("#baltable tbody tr[data-k]").first.click()
    page.wait_for_timeout(800)
    book = page.locator("#dlg-book").inner_text()
    assert "보유수량" in book and "평균매입가" in book, book
    assert "종목계좌 비중" not in book, f"잔고 표에 없는 열 이름이 나온다:\n{book}"


# ── ⑤ 같은 이름으로 다른 값을 말하지 않는가 ──────────────────────

def test_the_two_percent_columns_have_different_names(page):
    """사장님 지적 — 잔고는 12.4%, 종목표는 15.18%를 같은 이름으로 불렀다.

    둘 다 맞는 값이다(앞은 실제 평가 비중, 뒤는 오늘 목표). 틀린 것은
    **이름**이었다 — 같은 질문의 두 답으로 읽힌다.
    """
    heads = page.locator("#baltable thead").inner_text()
    assert "계좌 비중" in heads and "실제 보유" in heads, heads
    assert "통합 비중" not in heads, f"옛 이름이 남아 있다:\n{heads}"
    page.locator("#morebtn").click()
    page.wait_for_timeout(300)
    sym = page.locator("#symtable").inner_text()
    assert "오늘 목표" in sym, "종목표가 목표 노출을 목표라고 말하지 않는다"


# ── ⑥ 안 들고 있는 종목까지 벽처럼 늘어놓지 않는가 (감사 281) ────

def test_the_symbol_table_shows_what_we_actually_hold_first(page):
    """사장님: *"지금 홈페이지는 보기 힘들어. 이해하기 어렵게 구성이 되어있어."*

    종목별 현황이 20줄이었고 그중 대부분이 '보유 없음 · 0.00%'였다. 처음 온
    사람에게 그 표는 정보가 아니라 벽이다. **지우지는 않는다** — 오늘 관망한
    종목도 공개 장부의 일부다. 다만 오늘 돈이 들어가 있는 것부터 보이게 하고
    나머지는 접는다.
    """
    all_rows = page.locator("#symtable tbody tr[data-k]")
    shown = page.locator("#symtable tbody tr[data-k]:visible")
    assert all_rows.count() > shown.count(), (
        f"접힌 줄이 하나도 없다({all_rows.count()}줄 전부 보임) — "
        "관망 종목까지 전부 펼쳐져 있으면 처음 온 사람에게 벽이 된다")
    assert shown.count() >= 1, "보유 종목까지 접혔다 — 그러면 표가 비어 보인다"
    for i in range(shown.count()):
        assert "nohold" not in (shown.nth(i).get_attribute("class") or ""), (
            "안 들고 있는 종목이 간단 보기에 남아 있다")


def test_it_says_how_many_rows_it_folded(page):
    """말없이 접으면 그건 숨긴 것이다."""
    tag = page.locator("#sym-tag").inner_text()
    assert "관망" in tag and "자세히 보기" in tag, (
        f"몇 종목을 접었는지, 어디서 볼 수 있는지 말하지 않는다: {tag!r}")


def test_detail_view_shows_every_symbol(page):
    """대조군 — 펴면 전부 보여야 한다. 접는 것과 지우는 것은 다르다."""
    before = page.locator("#symtable tbody tr[data-k]:visible").count()
    page.click("#morebtn")
    page.wait_for_timeout(200)
    after = page.locator("#symtable tbody tr[data-k]:visible").count()
    total = page.locator("#symtable tbody tr[data-k]").count()
    assert after == total > before, (
        f"자세히 보기에서도 전부 안 보인다 — 접힌 {total}줄 중 {after}줄만")
