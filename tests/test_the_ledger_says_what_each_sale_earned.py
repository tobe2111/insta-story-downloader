"""판 시점의 손익 — 되짚어 계산하되, 모르는 것은 모른다고 한다 (감사 303).

사장님 요청(2026-08-22): *"메인 페이지의 최근 체결에 매도 시점 손익을 써
달라."*

거래내역 표에는 "언제 얼마에 얼마어치를 사고팔았나"만 있었다. 표를 봐도
**그 매도가 이익 실현인지 손절인지 알 수가 없었다.**

    실현 손익 = 판 수량 × (판 가격 − 평균 매입가) − 그 거래 비용

■ 왜 장부에 적지 않고 되짚는가

장중 실험 트랙은 파는 자리에서 바로 확정해 기록에 적는다 — 오늘 시작한
계좌라 처음부터 셀 수 있었다. 이 계좌는 **이미 지난 매도가 여덟 건 쌓여
있고**, 그 기록에는 평균 매입가가 없다. 앞으로 것만 적으면 지난 매도는
영영 '—'로 남는다.

매수와 매도가 전부 기록에 있으므로 처음부터 따라가면 복원된다. 기록을
한 글자도 고치지 않고 **계산만** 하는 것이다.

■ 여기서 지키는 것

  · 비용을 뺀 뒤의 값이다 — 수수료로 다 까먹은 매도는 이익이 아니다.
  · 기록이 스스로 "못 샀다"고 적어 둔 체결은 재고로 세지 않는다
    (2026-08-15 아마존 — 현금이 모자라 거부됐는데 체결처럼 남아 있다).
  · 살 때 값을 모르는 매도는 **0이 아니라 '모른다'**다.
  · 되짚기는 **전체 기록**을 봐야 한다. 최근 몇 건만 보면 그 앞의 매수를
    못 보고 평균 단가가 통째로 틀린다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.daily import _fill_cost                    # noqa: E402
from quant.live.realized import attach_realized, realized_by_fill  # noqa: E402

CRYPTO = _fill_cost("crypto")


def _rec(date, fills, **extra):
    return {"date": date, "fills": fills, **extra}


def _fill(key, side, price, qty):
    return {"key": key, "side": side, "price": price,
            "quantity": qty, "amount": round(price * qty, 2)}


# ── ① 기본 계산이 맞는가 ────────────────────────────────────────

def test_a_profitable_sale_reports_the_profit_after_cost():
    hist = [_rec("2026-01-01", [_fill("crypto:BTC/USDT", "buy", 100.0, 2.0)]),
            _rec("2026-01-02", [_fill("crypto:BTC/USDT", "sell", 150.0, 2.0)])]
    got = realized_by_fill(hist)[("2026-01-02", 0)]
    fee = 150.0 * 2.0 * CRYPTO
    assert got["realized_pnl"] == pytest.approx(2.0 * (150 - 100) - fee, abs=0.01)
    assert got["avg_cost"] == pytest.approx(100.0)


def test_a_losing_sale_reports_the_loss():
    hist = [_rec("2026-01-01", [_fill("crypto:BTC/USDT", "buy", 100.0, 2.0)]),
            _rec("2026-01-02", [_fill("crypto:BTC/USDT", "sell", 90.0, 2.0)])]
    got = realized_by_fill(hist)[("2026-01-02", 0)]
    assert got["realized_pnl"] < 0, got


def test_a_tiny_gain_eaten_by_cost_is_not_a_gain():
    """대조군 — 비용을 안 빼면 이익으로 보이는 매도.

    이 검사가 없으면 "비용을 빼지 않는다"도 위 검사들을 통과한다(둘 다
    부호가 안 바뀌므로). 팔아서 조금 벌었는데 수수료가 그보다 크면 그
    매도는 **이익이 아니다.**
    """
    # 0.01% 올랐는데 편도 비용은 0.15%다.
    hist = [_rec("2026-01-01", [_fill("crypto:BTC/USDT", "buy", 100.0, 10.0)]),
            _rec("2026-01-02", [_fill("crypto:BTC/USDT", "sell", 100.01, 10.0)])]
    got = realized_by_fill(hist)[("2026-01-02", 0)]
    assert got["realized_pnl"] < 0, (
        f"비용을 안 뺐다 — 0.01% 상승은 0.15% 수수료를 못 이긴다: {got}")


def test_the_average_follows_repeated_buys():
    hist = [_rec("2026-01-01", [_fill("crypto:BTC/USDT", "buy", 100.0, 1.0)]),
            _rec("2026-01-02", [_fill("crypto:BTC/USDT", "buy", 200.0, 3.0)]),
            _rec("2026-01-03", [_fill("crypto:BTC/USDT", "sell", 200.0, 4.0)])]
    got = realized_by_fill(hist)[("2026-01-03", 0)]
    assert got["avg_cost"] == pytest.approx(175.0), got   # (100+600)/4


def test_a_partial_sale_keeps_the_average_for_the_rest():
    hist = [_rec("2026-01-01", [_fill("crypto:BTC/USDT", "buy", 100.0, 4.0)]),
            _rec("2026-01-02", [_fill("crypto:BTC/USDT", "sell", 120.0, 1.0)]),
            _rec("2026-01-03", [_fill("crypto:BTC/USDT", "sell", 130.0, 3.0)])]
    tbl = realized_by_fill(hist)
    assert tbl[("2026-01-02", 0)]["avg_cost"] == pytest.approx(100.0)
    assert tbl[("2026-01-03", 0)]["avg_cost"] == pytest.approx(100.0), (
        "부분 매도가 남은 재고의 평균 단가를 흔들었다")


def test_selling_everything_then_buying_again_starts_a_new_average():
    hist = [_rec("2026-01-01", [_fill("crypto:BTC/USDT", "buy", 100.0, 1.0)]),
            _rec("2026-01-02", [_fill("crypto:BTC/USDT", "sell", 100.0, 1.0)]),
            _rec("2026-01-03", [_fill("crypto:BTC/USDT", "buy", 500.0, 1.0)]),
            _rec("2026-01-04", [_fill("crypto:BTC/USDT", "sell", 500.0, 1.0)])]
    got = realized_by_fill(hist)[("2026-01-04", 0)]
    assert got["avg_cost"] == pytest.approx(500.0), (
        f"다 팔고 다시 샀는데 옛 평단이 남아 있다: {got}")


# ── ② 모르는 것은 모른다 ────────────────────────────────────────

def test_a_sale_with_no_recorded_purchase_says_nothing():
    """장부가 살 때 값을 모르는 매도는 **0이 아니라 없음**이다.

    0으로 적으면 '본전'이라는 뜻이 되고, 그건 모르는 것을 아는 척하는 것이다.
    """
    hist = [_rec("2026-01-02", [_fill("crypto:BTC/USDT", "sell", 150.0, 2.0)])]
    assert realized_by_fill(hist) == {}, "살 때 값도 없이 손익을 지어냈다"


def test_a_buy_never_gets_a_realized_number():
    hist = [_rec("2026-01-01", [_fill("crypto:BTC/USDT", "buy", 100.0, 2.0)])]
    assert realized_by_fill(hist) == {}, (
        "매수에 실현 손익을 적었다 — 아직 확정된 것이 없다")


def test_a_fill_without_quantity_is_not_guessed():
    """수량이 없던 옛 기록(2026-08-13 이전)은 셀 수 없다."""
    hist = [{"date": "2026-01-01",
             "fills": [{"key": "crypto:BTC/USDT", "side": "buy",
                        "price": 100.0}]},
            _rec("2026-01-02", [_fill("crypto:BTC/USDT", "sell", 150.0, 2.0)])]
    assert realized_by_fill(hist) == {}, "수량 없는 매수를 재고로 세었다"


# ── ③ 기록이 스스로 부인한 체결 ────────────────────────────────

def test_a_purchase_the_record_denies_is_not_inventory():
    """**이 검사가 이 파일에서 가장 중요하다.**

    2026-08-15 장부에는 현금이 모자라 거부된 주문이 체결처럼 남아 있다.
    그걸 매수로 세면 없던 재고가 생기고, 그 뒤의 모든 평균 단가와 실현
    손익이 통째로 틀린다(감사 273·290이 이미 만난 자리).
    """
    hist = [_rec("2026-01-01", [_fill("us_stock:AMZN", "buy", 10.0, 100.0)],
                 cash_short=[{"key": "us_stock:AMZN",
                              "need": 1000.0, "cash": 5.0}]),
            _rec("2026-01-02", [_fill("us_stock:AMZN", "sell", 20.0, 100.0)])]
    assert realized_by_fill(hist) == {}, (
        "기록이 '못 샀다'고 적어 둔 체결을 재고로 세었다 — 없던 이익이 생긴다")


def test_a_real_purchase_is_still_counted():
    """대조군 — 부인 표식이 없으면 정상적으로 센다.

    없으면 "전부 부인으로 친다"도 위 검사를 통과하고, 그러면 이 표는
    영원히 비어 있다.
    """
    hist = [_rec("2026-01-01", [_fill("us_stock:AMZN", "buy", 10.0, 100.0)]),
            _rec("2026-01-02", [_fill("us_stock:AMZN", "sell", 20.0, 100.0)])]
    assert ("2026-01-02", 0) in realized_by_fill(hist), (
        "정상적인 매수까지 부인으로 쳤다")


# ── ④ 줄에 제대로 붙는가 ────────────────────────────────────────

def test_the_number_lands_on_the_right_row():
    """같은 날 같은 종목을 두 번 팔아도 줄이 안 섞인다.

    날짜와 종목만으로는 줄을 특정할 수 없다 — 그래서 그 기록 안 몇 번째
    체결인지를 함께 싣는다. 엉뚱한 줄에 붙으면 그 표는 증거가 아니다.
    """
    hist = [_rec("2026-01-01", [_fill("crypto:BTC/USDT", "buy", 100.0, 4.0)]),
            _rec("2026-01-02", [_fill("crypto:BTC/USDT", "sell", 200.0, 2.0),
                                _fill("crypto:BTC/USDT", "sell", 50.0, 2.0)])]
    rows = [{**f, "date": "2026-01-02", "fill_index": i}
            for i, f in enumerate(hist[1]["fills"])]
    out = attach_realized(rows, hist)
    assert out[0]["realized_pnl"] > 0, f"비싸게 판 줄이 손실로 붙었다: {out}"
    assert out[1]["realized_pnl"] < 0, f"싸게 판 줄이 이익으로 붙었다: {out}"


def test_attaching_does_not_touch_the_original_rows():
    hist = [_rec("2026-01-01", [_fill("crypto:BTC/USDT", "buy", 100.0, 1.0)]),
            _rec("2026-01-02", [_fill("crypto:BTC/USDT", "sell", 150.0, 1.0)])]
    rows = [{**hist[1]["fills"][0], "date": "2026-01-02", "fill_index": 0}]
    attach_realized(rows, hist)
    assert "realized_pnl" not in rows[0], "원본 줄을 고쳤다"


def test_the_lookback_uses_the_whole_history_not_the_visible_rows():
    """되짚기는 **보이는 줄**이 아니라 **전체 기록**을 봐야 한다.

    표에는 최근 60건만 실린다. 그 앞의 매수를 못 보면 평균 단가가 통째로
    틀리고, 실현 손익이 사실이 아닌 숫자가 된다.
    """
    hist = [_rec("2026-01-01", [_fill("crypto:BTC/USDT", "buy", 100.0, 1.0)])]
    hist += [_rec(f"2026-02-{d:02d}", []) for d in range(1, 20)]
    hist.append(_rec("2026-03-01", [_fill("crypto:BTC/USDT", "sell", 150.0, 1.0)]))
    rows = [{**hist[-1]["fills"][0], "date": "2026-03-01", "fill_index": 0}]
    out = attach_realized(rows, hist)          # 전체 기록을 넘긴다
    assert out[0].get("avg_cost") == pytest.approx(100.0), out
    # 보이는 줄만 넘기면 살 때 값을 모르므로 **아무 숫자도 안 나와야** 한다.
    blind = attach_realized(rows, hist[-1:])
    assert "realized_pnl" not in blind[0], (
        "앞선 매수를 못 봤는데도 손익을 지어냈다")


# ── ⑤ 진짜 장부에서도 나오는가 ─────────────────────────────────

def test_the_real_ledger_recovers_its_past_sales():
    """실측 — 진짜 장부의 지난 매도가 실제로 복원된다.

    합성 데이터만으로는 "실전에서 한 건도 안 나온다"를 못 잡는다.
    """
    fp = ROOT / "state" / "paper" / "portfolio_ALL.json"
    if not fp.exists():
        pytest.skip("장부 없음(새 설치)")
    import json
    hist = json.loads(fp.read_text("utf-8")).get("history") or []
    sells = sum(1 for rec in hist for f in (rec.get("fills") or [])
                if str(f.get("side") or "").lower() == "sell")
    if sells == 0:
        pytest.skip("아직 매도가 없다 — 잴 것이 없다")
    tbl = realized_by_fill(hist)
    assert tbl, f"매도가 {sells}건인데 복원된 손익이 하나도 없다"
    # 2026-08-15 아마존은 기록이 부인한 체결이다 — 절대 재고가 되면 안 된다.
    assert not any(k[0] == "2026-08-15" for k in tbl), (
        f"기록이 부인한 그 체결에서 손익을 만들었다: {tbl}")


# ── ⑥ 배선 — 사이트 재료에 실제로 실리는가 ─────────────────────

def _paper_state(tmp_path):
    """최소 장부 하나 — 사고, 팔고, 다시 산다."""
    import json
    d = tmp_path / "paper"
    d.mkdir(parents=True, exist_ok=True)
    hist = [
        {"date": "2026-01-01", "equity": 1_000_000, "price": 100.0,
         "principal": 1_000_000, "return_pct": 0.0,
         "fills": [_fill("crypto:BTC/USDT", "buy", 100.0, 1000.0)]},
        {"date": "2026-01-02", "equity": 1_050_000, "price": 150.0,
         "principal": 1_000_000, "return_pct": 5.0,
         "fills": [_fill("crypto:BTC/USDT", "sell", 150.0, 1000.0)]},
    ]
    (d / "portfolio_ALL.json").write_text(json.dumps({
        "market": "portfolio", "symbol": "ALL", "currency": "KRW",
        "start_cash": 1_000_000.0, "cash": 1_050_000.0, "deposits": [],
        "positions": {}, "history": hist,
    }, ensure_ascii=False), "utf-8")
    return hist


def test_the_site_material_carries_the_realized_number(tmp_path):
    """**배선 검사.** 계산이 맞아도 안 실으면 화면은 못 그린다.

    이 저장소가 감사 135·139·243·277에서 반복해 겪은 자리다 — 부품을
    만들어 놓고 안 붙이면 없는 것과 같다.
    """
    import json
    from quant.live.daily import write_docs_status
    _paper_state(tmp_path)
    docs = tmp_path / "status.json"
    write_docs_status(str(tmp_path), docs_path=str(docs))
    st = json.loads(docs.read_text("utf-8"))
    trades = st["paper"]["portfolio:ALL"]["trades"]
    sells = [t for t in trades if str(t.get("side")).lower() == "sell"]
    assert sells, f"매도 줄이 재료에 없다: {trades}"
    assert sells[0].get("realized_pnl") is not None, (
        f"매도 줄에 실현 손익이 안 실렸다 — 화면이 그릴 것이 없다: {sells[0]}")
    assert all("fill_index" in t for t in trades), (
        "체결 순번이 안 실렸다 — 같은 날 같은 종목을 두 번 팔면 줄이 섞인다")
    fee = 150.0 * 1000.0 * CRYPTO
    assert sells[0]["realized_pnl"] == pytest.approx(
        1000.0 * (150 - 100) - fee, abs=0.01), sells[0]


def test_the_buy_row_stays_empty_in_the_site_material(tmp_path):
    """대조군 — 매수 줄에는 숫자가 붙으면 안 된다."""
    import json
    from quant.live.daily import write_docs_status
    _paper_state(tmp_path)
    docs = tmp_path / "status.json"
    write_docs_status(str(tmp_path), docs_path=str(docs))
    st = json.loads(docs.read_text("utf-8"))
    buys = [t for t in st["paper"]["portfolio:ALL"]["trades"]
            if str(t.get("side")).lower() == "buy"]
    assert buys, "매수 줄이 없다 — 이 대조군이 아무것도 안 지킨다"
    assert all(t.get("realized_pnl") is None for t in buys), (
        f"매수에 실현 손익이 붙었다 — 아직 확정된 것이 없다: {buys}")


# ── ⑦ 화면이 실제로 그리는가 (진짜 브라우저) ───────────────────

def _render_trades(tmp_path, trades):
    """거래내역 표를 진짜 브라우저로 그려 그 글자를 돌려준다."""
    import functools
    import http.server
    import json
    import shutil
    import socketserver
    import threading
    pytest.importorskip("playwright.sync_api",
                        reason="playwright 없음 — 화면 검사 생략")
    sys.path.insert(0, str(ROOT / "tests"))
    from _browser import block_external, chromium_or_skip
    from playwright.sync_api import sync_playwright

    site = tmp_path / "site"
    shutil.copytree(ROOT / "docs", site, dirs_exist_ok=True)
    st = json.loads((ROOT / "docs" / "status.json").read_text("utf-8"))
    pf = st["paper"]["portfolio:ALL"]
    pf["trades"] = trades
    (site / "status.json").write_text(json.dumps(st, ensure_ascii=False), "utf-8")

    class _Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    srv = socketserver.TCPServer(
        ("127.0.0.1", 0), functools.partial(_Quiet, directory=str(site)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=chromium_or_skip())
            pg = b.new_page(viewport={"width": 1440, "height": 1200})
            block_external(pg)
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{srv.server_address[1]}/index.html")
            pg.wait_for_timeout(2400)
            rows = []
            for tr in pg.locator("#trtable tbody tr").all():
                rows.append(tr.locator("td").all_inner_texts())
            head = pg.locator("#trtable thead").inner_text()
            b.close()
        assert not errs, f"페이지 오류 {errs[:2]}"
    finally:
        srv.shutdown()
    return head, rows


def _row(date, key, side, price, qty, **extra):
    return {"date": date, "key": key, "side": side, "price": price,
            "quantity": qty, "amount": round(price * qty, 2),
            "type": "즉시", "fill_index": 0, **extra}


# 표의 칸 차례: 날짜 · 종목 · 구분 · 체결가 · 수량 · 금액 · **실현 손익** · 체결 방식
_PNL_CELL = 6


def _pnl_cell(rows):
    assert rows, "줄이 아예 안 그려졌다"
    cells = rows[0]
    assert len(cells) > _PNL_CELL, (
        f"실현 손익 칸이 없다 — 칸 {len(cells)}개뿐이다: {cells}")
    return cells[_PNL_CELL].strip()


def test_the_screen_draws_the_realized_number(tmp_path):
    head, rows = _render_trades(tmp_path, [
        _row("2026-08-21", "crypto:BTC/USDT", "sell", 150.0, 10.0,
             realized_pnl=1234.0, avg_cost=100.0),
    ])
    assert "실현 손익" in head, f"표에 실현 손익 칸이 없다:\n{head}"
    got = _pnl_cell(rows)
    assert "1,234" in got, f"판 값이 그 칸에 안 나온다: {got!r}"
    assert got.startswith("+"), f"이익인데 부호가 없다: {got!r}"


def test_the_screen_stays_quiet_when_it_cannot_know(tmp_path):
    """대조군 — 모르는 매도는 그 칸을 '—'로 비운다.

    없으면 "없는 값을 0으로 그린다"도 위 검사를 통과하고, 그러면 화면이
    '모른다'를 '본전'이라고 말하게 된다. 0원과 '모른다'는 다른 사건이다.

    ⚠️ 줄 전체 문자열이 아니라 **그 칸**을 본다. 다른 칸에도 '—'가 있어서
       (수량·금액이 없던 옛 기록) 줄 전체로 찾으면 헐거운 검사가 된다.
    """
    _, rows = _render_trades(tmp_path, [
        _row("2026-08-21", "crypto:BTC/USDT", "sell", 150.0, 10.0),
    ])
    got = _pnl_cell(rows)
    assert got == "—", f"모르는 손익 자리에 숫자를 그렸다: {got!r}"


def test_a_loss_is_drawn_as_a_loss(tmp_path):
    _, rows = _render_trades(tmp_path, [
        _row("2026-08-21", "crypto:BTC/USDT", "sell", 90.0, 10.0,
             realized_pnl=-567.0, avg_cost=100.0),
    ])
    got = _pnl_cell(rows)
    assert "567" in got, f"손실 금액이 그 칸에 없다: {got!r}"
    assert got.startswith("−") or got.startswith("-"), (
        f"손실인데 부호가 안 붙었다 — 이익과 구별이 안 된다: {got!r}")


def test_an_unfilled_order_row_keeps_the_columns_lined_up(tmp_path):
    """미체결 줄도 칸 수가 같아야 한다 — 하나만 어긋나도 표 전체가 밀린다."""
    import json
    st = json.loads((ROOT / "docs" / "status.json").read_text("utf-8"))
    pf = st["paper"]["portfolio:ALL"]
    day = str((pf["history"][-1] or {}).get("date") or "2026-08-21")
    _, rows = _render_trades(tmp_path, [
        _row(day, "crypto:BTC/USDT", "sell", 90.0, 10.0,
             realized_pnl=-567.0, avg_cost=100.0),
    ])
    assert all(len(r) == len(rows[0]) for r in rows), (
        f"줄마다 칸 수가 다르다: {[len(r) for r in rows]}")
