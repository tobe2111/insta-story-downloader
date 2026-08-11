"""봉내 손절 × 시가 체결 상호작용 계약 검사.

배경(2026-08-11 감사): 두 기능을 함께 켜면 봉내 청산 뒤에도 pending_delta가
남아, **이미 청산된 포지션에 손익이 한 번 더** 붙었다. intrabar_stops는
수동 백테스트에서만 켜져 실전 경로에는 닿지 않았지만, 켜는 순간 숫자가
틀린다 — 켜기 전에 잡는다.

핵심 계약:
  ① 봉내 청산 후 그 봉에서 손익이 두 번 계상되지 않는다
  ② 시가에 체결된 몫은 시가를, 이전부터 들고 있던 몫은 전 종가를 기준으로
  ③ 갭이 0이면 두 체결 방식의 결과가 같다(회귀 기준선)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.backtest.costs import CostModel  # noqa: E402
from quant.backtest.engine import Backtester  # noqa: E402
from quant.risk import RiskConfig, RiskManager  # noqa: E402
from quant.strategies.base import Strategy  # noqa: E402


class _AlwaysLong(Strategy):
    """항상 만기 롱 — 체결 회계만 보기 위한 최소 전략."""

    name = "always_long"

    def generate_signals(self, df):
        return pd.Series(1.0, index=df.index)


def _frame(n=60, gap=0.0, seed=7):
    rng = np.random.default_rng(seed)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.01, n))
    # 시가 = 전 종가 × (1+갭) — 진짜 오버나이트 갭 구조
    open_ = np.empty(n)
    open_[0] = close[0]
    open_[1:] = close[:-1] * (1 + gap)
    high = np.maximum(open_, close) * 1.005
    low = np.minimum(open_, close) * 0.995
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close,
         "volume": np.full(n, 1e9)},
        index=pd.date_range("2026-01-01", periods=n, freq="D"))


def _run(df, *, stop_loss=None, take_profit=None, **kw):
    risk = RiskManager(RiskConfig(
        sizing="fixed", max_position=1.0,
        stop_loss=stop_loss, take_profit=take_profit))
    bt = Backtester(_AlwaysLong(), risk=risk, initial_capital=10_000.0,
                    cost_model=CostModel(fee=0.0, slippage=0.0), **kw)
    return bt.run(df).equity.iloc[-1]


# ── ③ 갭 0이면 두 방식이 같다(회귀 기준선) ────────────────────


def test_zero_gap_makes_both_fill_models_identical():
    df = _frame(gap=0.0)
    assert abs(_run(df) - _run(df, next_open_fill=True)) < 1e-6


def test_gap_changes_the_result():
    """갭이 있으면 달라야 한다 — 같으면 시가 체결이 실제로 안 도는 것이다."""
    df = _frame(gap=0.004)
    assert abs(_run(df) - _run(df, next_open_fill=True)) > 1e-6


# ── ①② 봉내 청산과의 상호작용 ────────────────────────────────


def test_intrabar_stop_with_next_open_is_finite_and_sane():
    df = _frame(gap=0.004)
    eq = _run(df, next_open_fill=True, intrabar_stops=True,
              stop_loss=0.01, take_profit=0.02)
    assert np.isfinite(eq) and eq > 0


def test_intrabar_exit_does_not_double_count():
    """청산된 봉에서 pending 손익이 다시 붙지 않는다(소스 계약)."""
    src = (Path(__file__).resolve().parent.parent
           / "quant" / "backtest" / "engine.py").read_text("utf-8")
    body = src.split("intrabar_exit = True")[0]
    assert "pending_delta * (fill / open_[i] - 1.0)" in body
    assert "pending_delta = 0.0" in src.split("intrabar_exit = True")[1][:200]


def test_stops_still_cut_losses():
    """회계를 고치면서 손절 자체가 죽지 않았는지 — 기능 확인."""
    df = _frame(gap=0.0, seed=3)
    loose = _run(df, next_open_fill=True, intrabar_stops=True, stop_loss=0.50)
    tight = _run(df, next_open_fill=True, intrabar_stops=True, stop_loss=0.005)
    assert loose != tight        # 손절 폭이 결과를 실제로 바꾼다


# ── 주식은 결정 당일 종가에 체결되지 않는다 (감사 61) ─────────


def test_stocks_never_fill_at_the_decision_day_close(monkeypatch, tmp_path):
    """주식 결정은 '다음 세션 시가' 대기열로 가야 한다.

    변이 시험에서 IMMEDIATE_FILL_MARKETS에 주식을 넣어(결정 당일 종가에
    즉시 체결) 아무 검사가 실패하지 않았다. 마감 종가로 즉시 체결하는 것은
    실현 불가능한 가격이고, 백테스트가 그만큼 낙관적이 된다 — 오늘 하루
    고쳐 온 오디션-현실 격차의 원형이다.
    """
    import json as _json

    import numpy as _np
    import pandas as _pd

    from quant.live import daily as dl

    assert "us_stock" not in dl.IMMEDIATE_FILL_MARKETS
    assert "kr_stock" not in dl.IMMEDIATE_FILL_MARKETS

    rng = _np.random.default_rng(4)
    close = 100 * _np.exp(_np.cumsum(rng.normal(0.0004, 0.02, 300)))
    idx = _pd.date_range("2025-01-01", periods=300, freq="D")
    bars = _pd.DataFrame({"open": close * 0.995, "high": close * 1.01,
                          "low": close * 0.99, "close": close,
                          "volume": 1e6}, index=idx)

    class _P:
        def get_ohlcv(self, *a, **k):
            return bars.copy()

    class _S:
        name = "fixed"
        allow_short = False

        def generate_signals(self, df):
            return _pd.Series(0.9, index=df.index)

    monkeypatch.setattr("quant.data.get_provider", lambda m: _P())
    monkeypatch.setattr(dl, "champion_strategy", lambda *a, **k: _S())
    monkeypatch.setattr(dl, "champion_spec",
                        lambda *a, **k: {"strategy": "fixed", "params": {}})
    dl.run_daily_portfolio([("us_stock", "SPY")], state_dir=str(tmp_path),
                           require_real_data=False)
    st = _json.loads((tmp_path / "paper" / "portfolio_ALL.json")
                     .read_text(encoding="utf-8"))
    rec = st["history"][-1]

    assert not rec["fills"], "주식이 결정 당일에 체결됐다(실현 불가 가격)"
    assert rec["pending_next_open"], "다음 시가 대기열에 올라가지 않았다"
    assert not st.get("positions"), "체결 전인데 포지션이 잡혔다"


def test_pending_stock_order_fills_at_the_next_session_open(monkeypatch,
                                                            tmp_path):
    """어제 결정한 주식 주문이 오늘 '시가'에 실제로 체결되는가.

    커버리지로 확인해 보니(감사 63) 통합 계좌의 다음-시가 체결 블록
    (daily.py의 pending 처리 16줄)이 **어떤 테스트에서도 한 번도 실행된 적이
    없었다.** 8마일 계좌에서 주식이 실제로 체결되는 유일한 경로이고,
    사이트가 "실현 불가능한 가격으로 체결하지 않는다"고 말하는 근거인데,
    그 코드가 도는 것을 아무도 본 적이 없었던 셈이다.

    하루차: 결정만 하고 대기열에 올린다(체결 없음).
    이틀차: 새 봉이 생기면 그 봉의 **시가**로 체결되고 fills에 남는다.
    """
    import json as _json

    import numpy as _np
    import pandas as _pd

    from quant.live import daily as dl

    rng = _np.random.default_rng(5)
    close = 100 * _np.exp(_np.cumsum(rng.normal(0.0005, 0.02, 302)))
    idx = _pd.date_range("2025-01-01", periods=302, freq="D")
    full = _pd.DataFrame({"open": close * 0.97,      # 시가 ≠ 종가(갭 확인용)
                          "high": close * 1.02, "low": close * 0.95,
                          "close": close, "volume": 1e6}, index=idx)

    cut = {"n": 300}

    class _P:
        def get_ohlcv(self, *a, **k):
            return full.iloc[:cut["n"]].copy()

    class _S:
        name = "fixed"
        allow_short = False

        def generate_signals(self, df):
            return _pd.Series(0.9, index=df.index)

    monkeypatch.setattr("quant.data.get_provider", lambda m: _P())
    monkeypatch.setattr(dl, "champion_strategy", lambda *a, **k: _S())
    monkeypatch.setattr(dl, "champion_spec",
                        lambda *a, **k: {"strategy": "fixed", "params": {}})

    def _run():
        dl.run_daily_portfolio([("us_stock", "SPY")], state_dir=str(tmp_path),
                               require_real_data=False)
        return _json.loads((tmp_path / "paper" / "portfolio_ALL.json")
                           .read_text(encoding="utf-8"))

    # ── 하루차: 결정만, 체결 없음 ──
    st1 = _run()
    rec1 = st1["history"][-1]
    assert not rec1["fills"], "결정 당일에 체결됐다(실현 불가 가격)"
    pend = st1["pending"]["us_stock:SPY"]
    decided = pend["decided_bar"]
    assert not st1.get("positions")

    # ── 이틀차: 새 봉 하나 추가 → 그 봉의 시가로 체결 ──
    cut["n"] = 301
    st2 = _run()
    rec2 = st2["history"][-1]
    assert rec2["fills"], "다음 세션이 왔는데도 체결되지 않았다"
    fill = rec2["fills"][0]
    assert fill["key"] == "us_stock:SPY"
    assert fill["type"] == "시가"

    # 체결가는 '결정 다음 봉의 시가'와 정확히 같아야 한다 — 종가가 아니라
    import pytest as _pt
    nxt_bar, nxt_open = dl._first_bar_after(full.iloc[:301], decided)
    assert fill["bar"] == nxt_bar
    assert fill["price"] == _pt.approx(round(nxt_open, 6))
    assert fill["price"] != _pt.approx(float(full.loc[nxt_bar, "close"])), \
        "체결가가 그 봉의 종가와 같다 — 시가 체결이 아니다"

    # 체결됐으니 포지션이 잡힌다
    assert st2.get("positions"), "체결됐는데 포지션이 없다"
    # ⚠️ 기록된 체결가만 보면 부족하다. 장부에는 '시가'라 적고 실제로는
    #    종가로 체결해도 fills만 보는 검사는 통과한다(변이 시험에서 실제로
    #    그랬다 — 감사 63). 브로커가 잡은 평균단가로 '실제 체결가'를 본다.
    pos = st2["positions"]["us_stock:SPY"]
    assert float(pos["avg_price"]) == _pt.approx(nxt_open, rel=1e-6), (
        f"장부는 시가 {nxt_open:.4f} 체결이라는데 실제 평균단가는 "
        f"{pos['avg_price']:.4f} — 기록과 체결이 다른 가격을 가리킨다")
    # 어제 결정분은 소비됐다 — 남아 있는 대기열은 '오늘' 결정분이어야 한다
    # (같은 결정이 두 번 체결되면 노출이 두 배가 된다)
    still = (st2.get("pending") or {}).get("us_stock:SPY") or {}
    assert still.get("decided_bar") != decided, (
        "체결된 결정이 대기열에 그대로 남았다 — 내일 또 체결된다")
