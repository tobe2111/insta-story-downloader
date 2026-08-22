"""종목마다 지금 얼마 벌고 있나 (감사 306).

사장님 지시(2026-08-22): *"각 페이지들의 결과값들이 종목마다 각 얼마 현재
손해 혹은 이익인지 알려줘야 해."*

맞는 지적이었다. 본 계좌(100만 챌린지) 잔고 표에는 종목마다 평균매입가·
현재가·평가금액·손익이 다 있었는데, **실험 세 트랙의 화면에는 수량밖에
없었다.** "BTC 0.0022개 들고 있음"은 읽는 사람에게 아무것도 말해 주지
않는다 — 그래서 벌고 있나, 잃고 있나.

■ 여기서 지키는 것

  · 계산은 **한 곳**에서 한다(quant/live/holdings.py). 세 트랙이 각자
    쓰면 같은 날 세 페이지가 서로 다른 셈법으로 손익을 말하게 된다
    (FROZEN_IDEAS ①).
  · **숏의 부호는 반대다.** 값이 내리면 번다. 롱 계산을 그대로 쓰면
    선물 페이지의 손익이 통째로 뒤집힌다.
  · **못 재는 줄은 비워 둔다.** 시세를 못 받았거나 살 때 값이 기록에
    없으면 지어내지 않는다. 0으로 적으면 '본전'이라는 뜻이 된다.
  · **합계는 못 잰 줄을 빼고 세되, 몇 줄을 뺐는지 말한다.** 조용히 빼면
    합계가 틀렸다는 사실을 아무도 모른다.
  · 평균매입가는 체결 기록을 **되짚어** 복원한다 — 기록은 안 고친다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.holdings import (  # noqa: E402
    avg_cost_from_rounds, holdings_view, totals,
)


def _round(trades):
    return {"trades": trades}


def _t(sym, notional, price):
    return {"symbol": sym, "notional": notional, "price": price}


# ── ① 평균매입가 되짚기 ────────────────────────────────────────

def test_a_single_buy_gives_its_own_price():
    avg = avg_cost_from_rounds([_round([_t("BTC/USDT", 1000.0, 100.0)])])
    assert avg["BTC/USDT"] == pytest.approx(100.0)


def test_repeated_buys_are_weighted():
    avg = avg_cost_from_rounds([
        _round([_t("BTC/USDT", 100.0, 100.0)]),     # 1주
        _round([_t("BTC/USDT", 600.0, 200.0)]),     # 3주
    ])
    assert avg["BTC/USDT"] == pytest.approx(175.0)  # (100+600)/4


def test_a_partial_sale_keeps_the_average():
    avg = avg_cost_from_rounds([
        _round([_t("BTC/USDT", 400.0, 100.0)]),     # 4주 @100
        _round([_t("BTC/USDT", -120.0, 120.0)]),    # 1주 팔기
    ])
    assert avg["BTC/USDT"] == pytest.approx(100.0), (
        "부분 매도가 남은 재고의 평균 단가를 흔들었다")


def test_selling_everything_forgets_the_average():
    avg = avg_cost_from_rounds([
        _round([_t("BTC/USDT", 100.0, 100.0)]),
        _round([_t("BTC/USDT", -100.0, 100.0)]),
    ])
    assert "BTC/USDT" not in avg, "다 팔았는데 평단이 남았다"


def test_flipping_direction_starts_a_new_entry():
    """롱 → 숏으로 뒤집히면 **뒤집힌 뒤의 값**이 새 진입가다.

    옛 방향의 평단을 들고 가면 그 뒤 손익이 전부 틀린다.
    """
    avg = avg_cost_from_rounds([
        _round([_t("BTC/USDT", 100.0, 100.0)]),     # 롱 1주
        _round([_t("BTC/USDT", -400.0, 200.0)]),    # 2주 팔아 숏 1주로
    ])
    assert avg["BTC/USDT"] == pytest.approx(200.0), avg


# ── ② 손익 계산 ────────────────────────────────────────────────

def test_a_long_makes_money_when_the_price_rises():
    rows = holdings_view({"BTC/USDT": 2.0}, {"BTC/USDT": 150.0},
                         {"BTC/USDT": 100.0})
    assert rows[0]["pnl"] == pytest.approx(100.0)
    assert rows[0]["pnl_pct"] == pytest.approx(50.0)
    assert rows[0]["direction"] == "long"


def test_a_short_makes_money_when_the_price_falls():
    """**숏의 부호는 반대다.** 이걸 놓치면 선물 페이지가 통째로 뒤집힌다."""
    rows = holdings_view({"BTC/USDT": -2.0}, {"BTC/USDT": 80.0},
                         {"BTC/USDT": 100.0})
    assert rows[0]["direction"] == "short"
    assert rows[0]["pnl"] == pytest.approx(40.0), (
        f"값이 내렸는데 숏이 손실로 적혔다: {rows[0]}")
    assert rows[0]["pnl_pct"] == pytest.approx(20.0)


def test_a_short_loses_money_when_the_price_rises():
    """대조군 — 숏이 언제나 이기는 계산이 아니어야 한다."""
    rows = holdings_view({"BTC/USDT": -2.0}, {"BTC/USDT": 120.0},
                         {"BTC/USDT": 100.0})
    assert rows[0]["pnl"] < 0, rows[0]


def test_a_short_value_is_negative():
    """숏의 평가금액은 **음수**다 — 갚아야 할 몫이기 때문이다."""
    rows = holdings_view({"BTC/USDT": -2.0}, {"BTC/USDT": 100.0},
                         {"BTC/USDT": 100.0})
    assert rows[0]["value"] < 0, rows[0]


# ── ③ 모르는 것은 모른다 ───────────────────────────────────────

def test_a_symbol_without_a_price_says_nothing():
    rows = holdings_view({"BTC/USDT": 2.0}, {}, {"BTC/USDT": 100.0})
    assert rows[0]["pnl"] is None, (
        f"시세도 없이 손익을 지어냈다: {rows[0]}")
    assert rows[0]["last_price"] is None


def test_a_symbol_without_an_entry_price_says_nothing():
    rows = holdings_view({"BTC/USDT": 2.0}, {"BTC/USDT": 150.0}, {})
    assert rows[0]["pnl"] is None, (
        f"살 때 값도 없이 손익을 지어냈다: {rows[0]}")


def test_an_empty_position_is_not_a_row():
    rows = holdings_view({"BTC/USDT": 0.0}, {"BTC/USDT": 100.0},
                         {"BTC/USDT": 100.0})
    assert rows == [], "다 판 종목이 표에 남았다"


# ── ④ 합계 — 못 잰 줄을 조용히 빼지 않는다 ────────────────────

def test_the_total_says_how_many_it_could_not_measure():
    rows = holdings_view(
        {"A": 1.0, "B": 1.0, "C": 1.0},
        {"A": 150.0, "B": 90.0},                 # C는 시세가 없다
        {"A": 100.0, "B": 100.0, "C": 100.0})
    t = totals(rows)
    assert t["counted"] == 2 and t["unknown"] == 1, t
    assert t["pnl"] == pytest.approx(40.0), t     # +50 −10


def test_the_total_does_not_count_unknown_rows_as_zero():
    """대조군 — 못 잰 줄을 0으로 치면 '못 쟀다'가 사라진다."""
    rows = holdings_view({"A": 1.0}, {}, {"A": 100.0})
    t = totals(rows)
    assert t["counted"] == 0 and t["unknown"] == 1, t


# ── ⑤ 배선 — 세 트랙의 리포트에 실제로 실리는가 ────────────────

def _fake_state(positions, prices, trades):
    return {"positions": positions, "last_prices": prices,
            "rounds": [{"trades": trades}], "currency": "USDT",
            "start_cash": 10_000.0, "cost_paid": 0.0}


# ⚠️ **부품이 아니라 배선을 잰다.** 처음에는 이 검사들이 `_holdings()`를
#    직접 불렀는데, 그러면 "리포트에서 그 칸을 통째로 비운다"는 변이가
#    그대로 살아남는다 — 계산은 맞는데 화면에 안 실리는 상태다. 이
#    저장소가 감사 135·139·243·277에서 반복해 겪은 자리다(부품을 만들어
#    놓고 안 붙이면 없는 것과 같다). 변이 시험이 그것을 알려 줬다(감사 306).
#    그래서 **진짜 리포트를 만들어** 그 안을 본다.

def test_the_coin_report_carries_it(tmp_path):
    import json
    from quant.live.intraday_challenger import write_public_report
    st = _fake_state({"BTC/USDT": 1.0}, {"BTC/USDT": 150.0},
                     [_t("BTC/USDT", 100.0, 100.0)])
    write_public_report(st, docs_dir=str(tmp_path), state_dir=str(tmp_path))
    out = json.loads((tmp_path / "intraday.json").read_text("utf-8"))
    rows = out.get("holdings") or []
    assert rows, f"코인 리포트에 종목별 손익이 안 실렸다: {sorted(out)}"
    assert rows[0]["pnl"] == pytest.approx(50.0), rows
    assert (out.get("holdings_total") or {}).get("counted") == 1, out.get(
        "holdings_total")


def test_the_futures_report_carries_it_with_shorts():
    from quant.live.futures_challenger import public_report
    st = _fake_state({"BTC/USDT": -1.0}, {"BTC/USDT": 80.0},
                     [_t("BTC/USDT", -100.0, 100.0)])
    out = public_report(st)
    rows = out.get("holdings") or []
    assert rows, f"선물 리포트에 종목별 손익이 안 실렸다: {sorted(out)}"
    assert rows[0]["direction"] == "short", rows
    assert rows[0]["pnl"] == pytest.approx(20.0), (
        f"선물 리포트에서 숏 손익이 뒤집혔다: {rows[0]}")


def test_the_us_report_carries_it_in_dollars(tmp_path):
    import json
    from quant.live.intraday_us import write_public_report
    st = _fake_state({"SPY": 1.0}, {"SPY": 110.0},
                     [_t("SPY", 100.0, 100.0)])
    write_public_report(st, docs_dir=str(tmp_path), state_dir=str(tmp_path))
    out = json.loads((tmp_path / "intraday_us.json").read_text("utf-8"))
    rows = out.get("holdings") or []
    assert rows, f"미국 리포트에 종목별 손익이 안 실렸다: {sorted(out)}"
    assert rows[0]["currency"] == "USD", rows


def test_the_real_coin_ledger_produces_rows():
    """실측 — 진짜 장부에서도 나오는가.

    합성 데이터만으로는 "실전에서 한 줄도 안 나온다"를 못 잡는다.
    """
    import json
    fp = ROOT / "state" / "intraday" / "challenger.json"
    if not fp.exists():
        pytest.skip("장중 장부 없음")
    st = json.loads(fp.read_text("utf-8"))
    if not (st.get("positions") or {}):
        pytest.skip("지금 보유가 없다 — 잴 것이 없다")
    from quant.live.intraday_challenger import _holdings
    rows = _holdings(st)
    assert rows, "보유가 있는데 종목별 줄이 하나도 안 나온다"
    assert any(r.get("pnl") is not None for r in rows), (
        f"진짜 장부인데 손익을 하나도 못 쟀다: {rows}")
