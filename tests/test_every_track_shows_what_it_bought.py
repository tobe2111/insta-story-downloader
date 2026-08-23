""""투자를 하는 모습"이 화면에 보이는가 (감사 309).

사장님 지적(2026-08-23): *"미국 주식은 투자를 하는 모습을 못봤네?"*

맞는 지적이었다. 미국주식 트랙은 나흘 동안 **48번 체결**했는데도 화면에서
투자하는 것처럼 보이지 않았다. 세어 보니 이유가 셋이었고, 셋 다 "장부는
아는데 화면이 말하지 않는다"였다:

  ① **체결 표가 통째로 없었다.** 코인·선물 페이지에는 있는 표가 미국
     페이지에만 빠져 있었다. 화면에 남은 것은 "체결 48건 / 21회"라는 숫자
     하나뿐이라, 무엇을 언제 얼마에 샀는지 알 방법이 없었다.
  ② **마지막으로 판단한 시각이 없었다.** 그래서 지금 멈춰 있는 것이
     "장이 닫혀서"인지 "배치가 죽어서"인지 화면이 답을 못 했다.
  ③ **자산의 몇 %를 굴리는지 아무 데도 없었다.** 미국 트랙은 10,000 중
     200~600만 들고 있었다(평균 2.6%). 그런데 화면에는 수익률만 있어서,
     읽는 사람은 "10,000을 다 굴려서 -0.17%"로 읽게 된다. 실제로는
     "300쯤 굴려서 -0.17%"였다 — 전혀 다른 이야기다.

■ 여기서 지키는 것

  · **넷 다 같은 그리기 규칙을 쓴다**(docs/assets/trades.js). 페이지마다
    베껴 넣으면 언젠가 또 한 페이지에만 표가 빠진다 — 실제로 그랬다
    (FROZEN_IDEAS ①·⑭).
  · **굴리는 비중을 장부가 센다**(quant/live/holdings.py: deployed).
    화면이 자기 계산을 시작하면 장부와 갈라진다(감사 197).
  · **전량 현금은 고장이 아니다.** 다만 화면이 그렇게 **말해야** 한다.
    아무 말 없이 빈 표만 있으면 읽는 사람은 고장으로 읽는다.
  · **못 잰 줄은 세지 않되, 몇 줄인지 말한다.** 시세를 못 받은 종목을
    조용히 빼고 "3% 굴리는 중"이라 하면 실제로는 30%였을 수도 있다.

⚠️ 아래 화면 검사는 **직접 만든 장부**를 먹인다. 살아 있는 기록으로 검사
   하면 그날 마침 전량 현금인 날에 조용히 통과해 버린다 — 매일 바뀌는 값
   위에 전제를 세우면 언젠가 반드시 깨진다(2026-08-22에 배운 것).
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
sys.path.insert(0, str(ROOT / "tests"))

from _browser import block_external, chromium_or_skip  # noqa: E402
from quant.live.holdings import deployed  # noqa: E402


# ══ ① 장부가 굴리는 비중을 센다 ═══════════════════════════════════════

def _row(value):
    return {"symbol": "X", "value": value}


def test_it_says_what_fraction_is_working():
    d = deployed([_row(300.0), _row(100.0)], 10_000.0)
    assert d["gross"] == pytest.approx(400.0)
    assert d["pct"] == pytest.approx(4.0)
    assert d["cash"] == pytest.approx(9_600.0)


def test_a_short_counts_as_working_money_too():
    """숏은 평가금액이 음수다 — 부호 그대로 더하면 롱과 상쇄돼 사라진다.

    상쇄되면 "롱 500 · 숏 500"인 계좌가 화면에 **아무것도 안 굴리는 중**
    으로 나온다. 실제로는 1,000어치 위험을 지고 있다.
    """
    d = deployed([_row(500.0), _row(-500.0)], 10_000.0)
    assert d["gross"] == pytest.approx(1_000.0)
    assert d["pct"] == pytest.approx(10.0)


def test_holding_nothing_is_zero_percent_not_missing():
    """대조군 — 전량 현금은 **0%**이지 '모름'이 아니다."""
    d = deployed([], 10_000.0)
    assert d["pct"] == pytest.approx(0.0)
    assert d["cash"] == pytest.approx(10_000.0)
    assert d["unknown"] == 0


def test_rows_it_could_not_price_are_counted_and_named():
    d = deployed([_row(300.0), _row(None), _row("얼마인지몰라")], 10_000.0)
    assert d["unknown"] == 2, "못 잰 줄을 조용히 삼켰다"
    assert d["gross"] == pytest.approx(300.0)


def test_a_measurable_book_reports_no_unknowns():
    """대조군 — 다 잴 수 있으면 0이어야 한다.

    없으면 "늘 1을 돌려준다"도 위 검사를 통과한다.
    """
    assert deployed([_row(1.0), _row(2.0)], 100.0)["unknown"] == 0


@pytest.mark.parametrize("equity", [0, -1, None, "많이", float("nan")])
def test_it_refuses_to_divide_by_an_unusable_equity(equity):
    """자산을 모르면 비중도 모른다 — 지어내지 않는다."""
    assert deployed([_row(300.0)], equity) is None


# ══ ② 세 트랙의 공개 장부가 그 값을 싣는다 ═══════════════════════════
#
# ⚠️ deployed()를 직접 부르지 않는다. 리포트 작성기를 부른다 — 계산이
#    맞아도 **리포트에 안 실리면** 화면은 여전히 아무 말도 못 한다.

def _fake_round(sym, notional, price, equity):
    return {"time": "2026-08-22T00:00:00+09:00",
            "at": "2026-08-22T00:00:00+09:00",
            "equity": equity,
            "trades": [{"symbol": sym, "side": "buy", "notional": notional,
                        "price": price, "cost": 0.1, "signal": 0.5}]}


def _state(sym="AAA", currency="USDT"):
    return {"cash": 9_000.0, "start_cash": 10_000.0, "currency": currency,
            "positions": {sym: 10.0}, "cost_paid": 0.1,
            "last_prices": {sym: 100.0}, "risk_scale": 1.0,
            "rounds": [_fake_round(sym, 1_000.0, 100.0, 10_000.0)]}


def test_the_us_ledger_publishes_the_working_fraction(tmp_path):
    from quant.live import intraday_us
    out = intraday_us.write_public_report(_state(currency="USD"),
                                          docs_dir=str(tmp_path),
                                          state_dir=str(ROOT / "state"))
    assert out["deployed"]["pct"] == pytest.approx(10.0)
    on_disk = json.loads((tmp_path / "intraday_us.json").read_text("utf-8"))
    assert on_disk["deployed"]["pct"] == pytest.approx(10.0)


def test_the_coin_ledger_publishes_the_working_fraction(tmp_path):
    from quant.live import intraday_challenger
    out = intraday_challenger.write_public_report(
        _state(), docs_dir=str(tmp_path), state_dir=str(ROOT / "state"))
    assert out["deployed"]["pct"] == pytest.approx(10.0)


def test_the_futures_ledger_publishes_the_working_fraction():
    from quant.live import futures_challenger
    out = futures_challenger.public_report(_state())
    assert out["deployed"]["pct"] == pytest.approx(10.0)


# ══ ③ 화면이 실제로 그린다 ══════════════════════════════════════════

# 페이지 → (장부 파일, 통화, 거래 표의 종목 이름)
_PAGES = {
    "us.html": ("intraday_us.json", "USD", "AAPL"),
    "intraday.html": ("intraday.json", "USDT", "ETH/USDT"),
    "futures.html": ("futures.json", "USDT", "SOL/USDT"),
}


def _ledger(page: str, *, trades: bool, working: bool) -> dict:
    """검사용 장부를 손으로 짓는다 — 살아 있는 기록에 기대지 않는다."""
    sym = _PAGES[page][2]
    cur = _PAGES[page][1]
    rows = ([{"symbol": sym, "direction": "long", "quantity": 10.0,
              "avg_cost": 100.0, "last_price": 110.0, "currency": cur,
              "value": 1_100.0, "cost": 1_000.0, "pnl": 100.0,
              "pnl_pct": 10.0}] if working else [])
    recent = ([{"time": "2026-08-22T02:00:00+09:00",
                "at": "2026-08-22T02:00:00+09:00",
                "symbol": sym, "side": "buy", "notional": 1_000.0,
                "price": 100.0, "cost": 0.6, "signal": 0.42,
                "direction": "long"},
               {"time": "2026-08-22T03:00:00+09:00",
                "at": "2026-08-22T03:00:00+09:00",
                "symbol": sym, "side": "sell", "notional": -500.0,
                "price": 110.0, "cost": 0.3, "signal": 0.1,
                "direction": "long", "realized_pnl": 49.7}]
              if trades else [])
    base = {
        "kind": "test", "label": "검사용 장부", "currency": cur,
        "start_cash": 10_000.0, "equity": 10_100.0, "return_pct": 1.0,
        "cost_paid": 0.9, "trades_total": len(recent), "rounds_total": 2,
        "since": "2026-08-19T13:52:01+00:00",
        "last_time": "2026-08-22T04:46:38+09:00",
        "updated": "2026-08-22T04:46:38+09:00",
        "observed_gap_minutes": 61.0,
        "positions": ({sym: 10.0} if working else {}),
        "holdings": rows,
        "holdings_total": {"pnl": (100.0 if working else 0.0),
                           "counted": (1 if working else 0), "unknown": 0},
        "deployed": ({"gross": 1_100.0, "pct": 10.891, "cash": 9_000.0,
                      "unknown": 0} if working else
                     {"gross": 0.0, "pct": 0.0, "cash": 10_100.0,
                      "unknown": 0}),
        "recent_trades": recent,
        "equity_curve": [["2026-08-22T02:00:00+09:00", 10_000.0],
                         ["2026-08-22T04:46:38+09:00", 10_100.0]],
        "curve": [["2026-08-22T02:00:00+09:00", 10_000.0],
                  ["2026-08-22T04:46:38+09:00", 10_100.0]],
        "rounds": 2, "liquidations": 0, "margin_ratio": 0.9,
        "maintenance_margin_rate": 0.05, "max_gross_exposure": 3.0,
        "gross_exposure": (1_100.0 if working else 0.0),
        "long_positions": (1 if working else 0), "short_positions": 0,
        "honest_limits": ["가상 자금입니다"], "limits": ["가상 자금입니다"],
    }
    return base


@pytest.fixture(scope="module")
def browser():
    pytest.importorskip("playwright.sync_api",
                        reason="playwright 없음 — 화면 검사 생략")
    from playwright.sync_api import sync_playwright
    exe = chromium_or_skip()
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=exe)
        try:
            yield b
        finally:
            b.close()


def _render(browser, tmp_path, page, *, trades=True, working=True):
    """docs 사본에 **우리가 만든 장부**를 덮어씌우고 그 페이지를 연다."""
    root = tmp_path / page.replace(".", "_")
    shutil.copytree(ROOT / "docs", root, dirs_exist_ok=True)
    (root / _PAGES[page][0]).write_text(
        json.dumps(_ledger(page, trades=trades, working=working),
                   ensure_ascii=False), encoding="utf-8")

    class _Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    srv = socketserver.TCPServer(
        ("127.0.0.1", 0), functools.partial(_Quiet, directory=str(root)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    pg = browser.new_page()
    block_external(pg)
    try:
        pg.goto(f"http://127.0.0.1:{srv.server_address[1]}/{page}")
        pg.wait_for_timeout(1500)
        return pg.locator("body").inner_text(), _table(pg)
    finally:
        pg.close()
        srv.shutdown()


def _table(pg) -> str:
    """체결 표의 본문만. 이웃 문단이 대신 말해 주는 것을 막는다.

    (2026-08-22에 배운 것: 이웃이 대신 말해 주는 검사는 그 항목을 하나도
    안 지킨다 — 표가 통째로 없어도 페이지 어딘가에 종목 이름이 있으면
    통과해 버린다.)
    """
    tbl = pg.locator("#tr tbody")
    return tbl.inner_text() if tbl.count() else ""


@pytest.mark.parametrize("page", sorted(_PAGES))
def test_the_page_shows_each_fill_it_made(browser, tmp_path, page):
    """넷 중 하나만 표가 빠져 있어도 여기서 걸린다."""
    _text, table = _render(browser, tmp_path, page)
    assert table, f"{page}에 체결 표(#tr)가 없다"
    sym = _PAGES[page][2]
    assert sym in table, f"{page} 체결 표가 산 종목({sym})을 안 적는다"
    assert "1,000" in table, f"{page} 체결 표가 금액을 안 적는다"
    assert "49.7" in table, f"{page} 체결 표가 판 값의 실현 손익을 안 적는다"


@pytest.mark.parametrize("page", sorted(_PAGES))
def test_an_opening_fill_shows_a_dash_not_a_zero(browser, tmp_path, page):
    """새로 여는 주문의 실현 손익은 '—'다.

    0으로 그리면 '본전'이라는 뜻이 되고, 그건 모르는 것을 아는 척하는 것이다.
    """
    _text, table = _render(browser, tmp_path, page)
    buy = [ln for ln in table.splitlines() if "0.42" in ln]
    assert buy, "매수 줄을 못 찾았다"
    assert "—" in buy[0], f"{page}: 매수 줄의 실현 손익이 '—'가 아니다"


@pytest.mark.parametrize("page", sorted(_PAGES))
def test_a_page_with_no_fills_says_so(browser, tmp_path, page):
    """대조군 — 체결이 없으면 **없다고 말한다.**

    빈 장부에 유령 줄을 그리는 것을 막는다. 그리고 "아직 없다"와 "그런 일이
    없었다"는 다른 말이므로, 화면이 앞의 것을 말해야 한다.
    """
    _text, table = _render(browser, tmp_path, page, trades=False,
                           working=False)
    assert "아직 체결이 없습니다" in table, f"{page}: 빈 표가 말이 없다"
    assert _PAGES[page][2] not in table, f"{page}: 없는 체결을 그렸다"


@pytest.mark.parametrize("page", sorted(_PAGES))
def test_the_page_says_how_much_money_is_actually_working(browser, tmp_path,
                                                          page):
    line = _line(browser, tmp_path, page, working=True)
    assert "10.9%" in line, f"{page}: 굴리는 비중을 안 적는다 ({line!r})"
    assert "9,000" in line, f"{page}: 남은 현금을 안 적는다 ({line!r})"


@pytest.mark.parametrize("page", sorted(_PAGES))
def test_all_cash_is_explained_as_a_decision_not_a_breakdown(browser, tmp_path,
                                                             page):
    """전량 현금일 때 **왜 비었는지**를 화면이 말해야 한다.

    아무 말 없이 빈 표만 있으면 읽는 사람은 고장으로 읽는다 — 사장님이
    "투자를 하는 모습을 못봤다"고 하신 상태가 정확히 그것이었다.
    """
    line = _line(browser, tmp_path, page, working=False)
    assert "0.0%" in line, f"{page}: 0%라고 말하지 않는다 ({line!r})"
    assert "고장이 아니라" in line, f"{page}: 빈 이유를 설명하지 않는다"


@pytest.mark.parametrize("page", sorted(_PAGES))
def test_a_working_book_does_not_get_the_idle_excuse(browser, tmp_path, page):
    """대조군 — 굴리고 있을 때 "지금은 살 이유가 없다"를 붙이면 거짓말이다."""
    line = _line(browser, tmp_path, page, working=True)
    assert "고장이 아니라" not in line, f"{page}: 굴리는 중인데 관망이라 한다"


def _line(browser, tmp_path, page, *, working):
    return _element(browser, tmp_path, page, "#deployed", working=working)


def _element(browser, tmp_path, page, selector, *, working=True):
    """그 칸 **하나만** 읽는다.

    페이지 전체 글자에서 찾으면 이웃 문단이 대신 답해 준다 — 실제로 미국
    페이지 요약에는 "지금 (마지막 회차 기준)"이라는 다른 라벨이 있어서,
    본문 검색으로는 "마지막 회차:" 줄을 통째로 지워도 통과했다.
    """
    root = tmp_path / f"{page}-{selector.strip('#')}-{working}"
    root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "docs", root, dirs_exist_ok=True)
    (root / _PAGES[page][0]).write_text(
        json.dumps(_ledger(page, trades=True, working=working),
                   ensure_ascii=False), encoding="utf-8")

    class _Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    srv = socketserver.TCPServer(
        ("127.0.0.1", 0), functools.partial(_Quiet, directory=str(root)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    pg = browser.new_page()
    block_external(pg)
    try:
        pg.goto(f"http://127.0.0.1:{srv.server_address[1]}/{page}")
        pg.wait_for_timeout(1500)
        el = pg.locator(selector)
        return el.inner_text() if el.count() else ""
    finally:
        pg.close()
        srv.shutdown()


def test_the_us_page_says_when_it_last_looked(browser, tmp_path):
    """미국 페이지가 **마지막으로 판단한 시각**을 적는다.

    이게 없으면 "왜 안 움직이나"에 화면이 답을 못 한다 — 장이 닫혀서인지,
    배치가 죽어서인지. 미국 트랙은 주말 내내 멈춰 있는 것이 정상이라 이
    질문이 특히 자주 생긴다.
    """
    line = _element(browser, tmp_path, "us.html", "#last-round")
    assert "마지막 회차" in line, f"마지막으로 판단한 시각이 화면에 없다 ({line!r})"
    assert "2026-08-22 04:46" in line, "마지막 회차 시각이 한국 시간이 아니다"
