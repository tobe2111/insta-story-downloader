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
