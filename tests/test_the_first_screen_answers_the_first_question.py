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

def test_the_money_answer_comes_first(page):
    """돈 이야기가 **다운로드 광고보다 위에** 있어야 한다.

    순서가 곧 우선순위다. 광고가 먼저면 이 사이트는 '기록 공개'가 아니라
    '제품 판매' 페이지로 읽힌다.

    ⚠️ 2026-08-18(감사 282)에 한 걸음 더 갔다. 사장님이 *"근본적인 문제를
       해결해. 지금 이 홈페이지의 내용이 어려워"*라고 하셔서, 큰 제품 소개는
       **첫 화면에서 아예 뺐다.** 지운 것이 아니라 '자세히 보기' 안으로
       옮겼고, 대신 한 줄짜리 안내만 남겼다. 그래서 '위에 있는가'가 아니라
       **'첫 화면에 없는가'**를 본다.
    """
    assert page.locator("#glance").bounding_box(), "한눈에가 안 보인다"
    assert not page.locator("section.hero").is_visible(), (
        "큰 제품 소개가 첫 화면에 그대로 있다 — 처음 온 사람은 계좌보다 "
        "광고를 먼저 읽게 된다")
    slim = page.locator(".dlslim")
    assert slim.is_visible(), "내려받기 통로가 통째로 사라졌다 — 접는 것과 지우는 것은 다르다"
    assert slim.bounding_box()["y"] > page.locator("#glance").bounding_box()["y"]


def test_it_says_how_much_when_and_the_profit(page):
    txt = page.locator("#glance").inner_text()
    assert "1,000,000원" in txt, f"넣은 돈이 없다:\n{txt}"
    assert "2026-08-13" in txt, f"언제 시작했는지가 없다:\n{txt}"
    assert "997,198원" in txt, f"지금 얼마인지가 없다:\n{txt}"
    assert "0.28%" in txt, f"손익 비율이 없다:\n{txt}"
    amt = page.locator("#hero-amt").inner_text()
    assert "1,000,000원" in amt, f"원금이 없다:\n{amt}"


def test_the_glance_card_is_back_by_owner_decision(page):
    """'한눈에' 카드와 접이식은 **되살렸다** (사장님 지시, 2026-08-18 오후).

    ⚠️ 이 자리에는 정반대의 잠금 검사가 있었다 —
       `test_the_glance_card_stays_removed_by_owner_decision`
       ("사장님 지시(2026-08-18)로 내렸다"). 그 검사는 스스로 이렇게 적어
       두었다: *"카드를 다시 올리려면 이 검사를 **의도적으로** 되돌려야
       한다."* 지금이 그 순간이고, 절차대로 되돌린다.

    같은 날 오후에 사장님이 다시 말씀하셨다:
        *"근본적인 문제를 해결해. 지금 이 홈페이지의 내용이 어려워. 복잡하고"*

    그래서 첫 화면은 세 질문에만 답한다 — 얼마를 언제 넣었나 · 지금
    얼마인가 · 그래서 잘하고 있나. 나머지는 지우지 않고 접는다.

    화면 구성이 **소리 없이** 오가는 것을 막는 자물쇠라는 성격은 그대로다.
    다음에 또 내리려면 이 검사를 다시 의도적으로 고쳐야 한다.
    """
    assert page.locator("#glance").count() == 1, (
        "'한눈에' 카드가 없다 — 되살리기로 한 결정이 소리 없이 뒤집혔다")
    assert page.locator("#morebtn").count() == 1, (
        "접이식 버튼이 없다 — 접은 것을 펼 방법이 사라지면 그건 지운 것이다")


# ── ② 오래된 숫자를 오늘처럼 말하지 않는가 ───────────────────────

def test_a_stale_number_says_it_is_stale(page):
    """사장님이 "지금 상황이 이거 맞아?"라고 물어야 했던 이유가 여기다.

    기준일(2026-08-15)이 오늘이 아니면 **금액 바로 아래에서** 말해야 한다.

    ⚠️ 잠시 이 경고가 사이드바에만 있었다(2026-08-18 오전, 한눈에 카드가
       내려가 있던 동안). 같은 사실을 두 곳에 띄우는 대신, 사람이 금액을
       읽는 바로 그 자리에서 말한다 — 경고는 숫자 옆에 있을 때만 읽힌다.
    """
    txt = page.locator("#glance").inner_text()
    assert DAY in txt, f"기준일이 없다:\n{txt}"
    assert "일 전" in txt, f"며칠 전 숫자인지 말하지 않는다:\n{txt}"
    assert "시세로 평가된 금액" in txt, (
        f"낡은 숫자의 의미(그날 시세 평가)를 말하지 않는다:\n{txt}")


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

# ⚠️ 2026-08-18(감사 282) 첫 화면은 **세 질문에만** 답한다:
#    ① 얼마를 언제 넣었나 ② 지금 얼마인가 ③ 그래서 잘하고 있나.
#    종목별 현황과 제품 소개는 그 세 질문의 답이 아니라서 접힘으로 옮겼다.
FOLDED = ["🕰 이 성적, 언제부터 공식인가", "🎯 리스크 설정",
          "🧾 거래 비용, 가정이 실제와 맞나",
          "오답 노트", "탈락자 아카이브", "종목별 현황",
          "지금 받아서 5분 안에 첫 백테스트"]
ALWAYS = ["한눈에", "통합 계좌", "잔고", "거래내역"]


def _visible_headings(pg):
    return [h.inner_text().split("\n")[0].strip()
            for h in pg.locator("main h2").all() if h.is_visible()]


def test_the_advanced_cards_start_folded(page):
    """첫 화면은 세 질문에만 답한다 — 나머지는 접혀 있어야 한다."""
    vis = _visible_headings(page)
    for name in FOLDED:
        assert name not in vis, f"'{name}'이 처음부터 펴져 있다: {vis}"
    for name in ALWAYS:
        assert name in vis, f"'{name}'이 사라졌다: {vis}"


def test_pressing_the_button_unfolds_everything(page):
    """접는 것과 지우는 것은 다르다 — 누르면 전부 나와야 한다."""
    page.locator("#morebtn").click()
    page.wait_for_timeout(400)
    vis = _visible_headings(page)
    for name in FOLDED + ALWAYS:
        assert name in vis, f"'{name}'이 펴지지 않았다: {vis}"
    # 다시 누르면 접힌다 — 한 방향으로만 가는 버튼은 함정이다.
    page.locator("#morebtn").click()
    page.wait_for_timeout(400)
    assert "탈락자 아카이브" not in _visible_headings(page), "다시 접히지 않는다"


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
    if not page.locator(f"#{table}").is_visible():
        page.click("#morebtn")          # 접힌 표는 펴고 눌러야 한다(감사 282)
        page.wait_for_timeout(300)
    rows = page.locator(f"#{table} tbody tr[data-k]:visible")
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


# ── ⑥ 종목별 현황: 접기 + 보유 먼저 (감사 281 · 282) ────────────

def test_the_symbol_table_is_not_on_the_first_screen(page):
    """사장님: *"근본적인 문제를 해결해. 지금 이 홈페이지의 내용이 어려워."*

    종목별 현황은 스무 줄짜리 전략 표다. **첫 화면의 세 질문**(얼마 넣었나 ·
    지금 얼마인가 · 잘하고 있나)의 답이 아니다. 지우지 않고 접는다.
    """
    assert not page.locator("#symtable").is_visible(), (
        "종목별 현황이 첫 화면에 그대로 있다 — 처음 온 사람에게 벽이 된다")


def test_unfolded_it_shows_what_we_actually_hold_first(page):
    """펴 봤을 때도 **오늘 돈이 들어간 종목**이 먼저 보여야 한다.

    스무 줄 중 열다섯 줄이 '보유 없음 · 0.00%'였다. 접어 두었다가 펴면
    그 벽이 그대로 나온다면 접은 의미가 없다.
    """
    page.click("#morebtn")
    page.wait_for_timeout(300)
    rows = page.locator("#symtable tbody tr[data-k]")
    assert rows.count() > 0, "펴도 표가 비어 있다"
    held = [i for i in range(rows.count())
            if "nohold" not in (rows.nth(i).get_attribute("class") or "")]
    assert held, "보유 종목 표시가 하나도 없다 — 표식이 사라졌다"
    assert held == list(range(len(held))), (
        f"보유 종목이 관망 종목 뒤로 섞여 있다: 보유 줄 위치 {held}")


def test_it_says_how_many_rows_it_folded(page):
    """말없이 접으면 그건 숨긴 것이다."""
    tag = page.locator("#sym-tag").inner_text()
    assert "관망" in tag and "자세히 보기" in tag, (
        f"몇 종목을 접었는지, 어디서 볼 수 있는지 말하지 않는다: {tag!r}")
