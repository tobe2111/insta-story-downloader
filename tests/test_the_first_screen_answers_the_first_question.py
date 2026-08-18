"""첫 화면이 **처음 온 사람의 첫 질문**에 답하는가 (감사 274 · 2026-08-18 개정).

감사 274는 사장님의 "너무 정보가 많아" 지적에 접이식 화면('한눈에' 카드 +
간단/자세히 보기)으로 답했다. 하루 뒤 사장님이 다시 지시하셨다:

  *"일단 이 페이지 예전으로 돌려줘. 지금은 페이지 전체를 가득 채우는 형태의
   UI가 무너졌어."* (2026-08-18)

그래서 화면은 **08-17 아침의 전체 화면 구성**으로 되돌렸다. 되돌린 것은
**배치**뿐이다 — 감사 274·275가 고친 데이터 정직성은 옛 화면에 그대로
이식했고, 이 파일이 그것을 지킨다:

  ① 계좌 금액·손익이 화면에 있고 스크립트 오류 없이 그려진다
  ② 오래된 숫자는 오래됐다고 말한다(🚨 경고 — 사장님이 "지금 상황이 이거
     맞아?"라고 물어봐야 했던 그 자리)
  ③ 아무것도 접히지 않는다 — 접이식을 되돌렸으니 접힌 경고도 없어야 한다
  ④ 세 표(잔고·거래내역·종목별 현황) 어디서든 종목을 누르면 차트 창이 열린다
  ⑤ 두 비중 열은 다른 이름을 가진다(같은 질문의 두 답으로 읽히지 않게)
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

# 브라우저를 어디서 찾는지는 **한 곳에서만** 정한다(감사 278).
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


# ── ① 돈 이야기가 화면에 있는가 ──────────────────────────────────

def test_the_account_and_its_profit_are_on_screen(page):
    """히어로 증거 칸이 계좌 금액과 손익률을 말해야 한다."""
    txt = page.locator("#pv-eq").inner_text()
    assert "997,198원" in txt, f"지금 얼마인지가 없다:\n{txt}"
    assert "0.28%" in txt, f"손익 비율이 없다:\n{txt}"
    amt = page.locator("#hero-amt").inner_text()
    assert "1,000,000원" in amt, f"원금이 없다:\n{amt}"


def test_the_glance_card_stays_removed_by_owner_decision(page):
    """'한눈에' 카드는 사장님 지시(2026-08-18)로 내렸다.

    이 검사는 그 결정의 자물쇠다 — 카드를 다시 올리려면 이 검사를
    **의도적으로** 되돌려야 한다. 화면 구성이 소리 없이 오가는 것을 막는다.
    """
    assert page.locator("#glance").count() == 0, (
        "내리기로 한 '한눈에' 카드가 되살아났다 — 의도한 복원이면 이 검사를 "
        "함께 고치라")
    assert page.locator("#morebtn").count() == 0, (
        "내리기로 한 접이식 버튼이 되살아났다")


# ── ② 오래된 숫자를 오늘처럼 말하지 않는가 ───────────────────────

def test_a_stale_number_says_it_is_stale(page):
    """사장님이 "지금 상황이 이거 맞아?"라고 물어야 했던 이유가 여기다.

    기준일(2026-08-15)이 오늘이 아니면 사이드바 경고가 🚨로 말해야 한다.
    """
    side = page.locator("#side-flags").inner_text()
    assert DAY in side, f"기준일이 없다:\n{side[:600]}"
    assert "일 전" in side, f"며칠 전 숫자인지 말하지 않는다:\n{side[:600]}"
    assert "시세로 평가된 금액" in side, (
        f"낡은 숫자의 의미(그날 시세 평가)를 말하지 않는다:\n{side[:600]}")


def test_a_fresh_number_is_not_scolded(browser, site, tmp_path):
    """대조군 — 오늘 기록이면 경고가 뜨면 안 된다.

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
        side = pg.locator("#side-flags").inner_text()
        pg.close()
    finally:
        srv.shutdown()
    assert "기준입니다" not in side, f"오늘 기록인데 낡았다고 말한다:\n{side[:600]}"


# ── ③ 아무것도 접혀 있지 않은가 ──────────────────────────────────

CARDS = ["🕰 판정 시계", "🎯 리스크 설정", "🧾 체결 가정 검증",
         "오답 노트", "탈락자 아카이브"]


def test_every_card_is_visible_from_the_start(page):
    """접이식은 되돌렸다(2026-08-18) — 전부 처음부터 보여야 한다.

    반쯤 되돌리면 최악이다: 접혔는데 펴는 버튼이 없으면 그 숫자는
    공개 장부에서 **지워진 것**과 같다.
    """
    vis = [h.inner_text().split("\n")[0].strip()
           for h in page.locator("main h2").all() if h.is_visible()]
    for name in CARDS:
        assert name in vis, f"'{name}'이 화면에 없다: {vis}"


def test_a_red_alarm_is_visually_urgent(page):
    """🚨 경고는 상태 설명과 **다르게 보여야** 한다.

    여덟 줄이 같은 회색으로 나란히 있으면 급한 것이 배경음이 된다(감사 274).
    낡은 기준일 경고(위 검사)가 켜져 있으므로 crit 표시가 있어야 한다.
    """
    crit = page.locator("#side-flags .flag.crit")
    assert crit.count() > 0, "🚨 경고가 crit 표시 없이 회색으로 묻혀 있다"
    assert "🚨" in crit.first.inner_text()


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
    sym = page.locator("#symtable").inner_text()
    assert "오늘 목표" in sym, "종목표가 목표 노출을 목표라고 말하지 않는다"
