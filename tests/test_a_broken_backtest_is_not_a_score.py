"""망가진 백테스트가 그럴듯한 성적을 낸다 (2026-08-14 감사 234).

엔진에는 이미 **파산 바닥**이 있다(감사 184). 자본이 0 이하로 내려가면 그
계좌는 끝이라고 못박는 장치인데, 그 주석이 이렇게 경고한다:

    "오디션은 NaN·가짜 수익을 걸러내지 않는다 —
     **파산한 백테스트가 챔피언이 될 수 있다.**"

그런데 그 판정이 `cash_equity <= 0.0`이다. **NaN도 inf도 이 비교에서
False다.** 즉 경고문이 가리킨 구멍의 절반이 그대로 남아 있었다.

실측(종가 한 칸이 NaN인 프레임, 60봉):

    자본곡선 60칸 중 30칸이 NaN · 최종 자산 nan
    ────────────────────────────────────────────
    보고된 총수익률   -10.77%      ← 그럴듯하다
    보고된 CAGR       -76.18%
    보고된 MDD        -13.26%

숫자만 보고는 아무도 이상하다고 못 한다. 왜 이런 숫자가 나왔나 —
`compute_metrics`가 `equity.dropna()`로 **NaN 구간을 조용히 버리고**
남은 점들로 성적을 냈기 때문이다. 그 `dropna()`는 곡선 앞머리의 빈 칸을
자르려고 넣은 것인데, 곡선 **중간이 고장 난 경우**까지 똑같이 지웠다.

종가가 inf면 총수익률이 `+inf`로 나온다. 이쪽은 눈에 띄지만, 오디션이
숫자 크기로 고르는 이상 **가장 높은 점수**가 된다.

지키는 계약:
  · 자본이 유한수가 아니게 되면 **성적을 내지 않는다**(예외)
  · 0으로 눌러 '파산'으로 둔갑시키지 않는다 — 고장은 고장이다
  · 지표 계산은 **결측을 자르는 것**과 **고장을 자르는 것**을 구분한다
  · 진짜 파산(0 이하)은 지금까지처럼 -100%로 남는다
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.backtest.costs import CostModel  # noqa: E402
from quant.backtest.engine import Backtester  # noqa: E402
from quant.backtest.metrics import compute_metrics  # noqa: E402
from quant.risk.manager import RiskConfig, RiskManager  # noqa: E402


class _Always:
    name, allow_short = "always", False

    def generate_signals(self, df):
        return pd.Series(1.0, index=df.index)


def _frame(n: int = 60, seed: int = 5):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0, 0.02, n)))
    return pd.DataFrame(
        {"open": close, "high": close * 1.01, "low": close * 0.99,
         "close": close, "volume": 1e9},
        index=pd.date_range("2025-01-01", periods=n, freq="D"))


def _run(df):
    risk = RiskManager(RiskConfig(periods_per_year=365, sizing="fixed",
                                  stop_loss=None, max_position=1.0))
    bt = Backtester(_Always(), risk=risk, initial_capital=10_000.0,
                    cost_model=CostModel(fee=0.001, slippage=0.0005))
    return bt.run(df)


# ── 고장은 성적이 되지 않는다 ─────────────────────────────────

@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_a_broken_equity_curve_refuses_to_report(bad):
    """자본이 유한수가 아니게 되면 숫자를 내지 않는다."""
    df = _frame()
    df.loc[df.index[30], "close"] = bad
    with pytest.raises(ValueError, match="계산 불가"):
        _run(df)


def test_the_healthy_case_still_reports():
    """대조군 — 막는 것만 검사하면 '전부 막는' 코드도 통과한다."""
    r = _run(_frame())
    assert np.isfinite(r.equity.to_numpy()).all()
    assert np.isfinite(r.metrics.total_return)
    assert r.equity.iloc[-1] > 0


def test_a_broken_run_is_not_relabelled_as_a_loss():
    """0으로 눌러 '파산'으로 만들지 않는다 — 고장을 손실로 둔갑시키는 것이다.

    -100%는 '전부 잃었다'는 **사실 주장**이다. 계산이 망가진 것을 그렇게
    적으면 장부가 거짓말을 하게 된다. 낼 수 없는 성적은 안 낸다.
    """
    df = _frame()
    df.loc[df.index[30], "close"] = np.nan
    with pytest.raises(ValueError):
        _run(df)          # -1.0을 돌려주는 것도 정답이 아니다


# ── 진짜 파산은 지금까지처럼 -100% ─────────────────────────────

@pytest.mark.parametrize("wipeout", [0.0, -50.0])
def test_a_real_wipeout_still_reads_minus_one_hundred(wipeout):
    """대조군 — 감사 184가 세운 파산 바닥을 흔들지 않았는가.

    종가가 0이면 전액 롱은 실제로 전부 잃는다. 그건 고장이 아니라 결과다.
    """
    df = _frame()
    df.loc[df.index[30], "close"] = wipeout
    r = _run(df)
    assert r.metrics.total_return == pytest.approx(-1.0)
    assert r.equity.iloc[-1] == 0.0
    assert np.isfinite(r.equity.to_numpy()).all(), (
        "파산 뒤에도 루프가 돌아 0 × inf = NaN이 됐다")


def test_a_dead_account_stays_flat_and_holds_nothing():
    """파산한 계좌는 그 뒤로 아무 일도 하지 않는다."""
    df = _frame()
    df.loc[df.index[30], "close"] = 0.0
    r = _run(df)
    after = r.equity.to_numpy()[31:]
    assert (after == 0.0).all(), "죽은 계좌가 다시 움직였다"
    assert (r.positions.to_numpy()[31:] == 0.0).all(), "죽은 계좌가 종목을 들고 있다"


# ── 지표: 결측을 자르는 것과 고장을 자르는 것은 다르다 ──────────

def test_metrics_refuse_a_curve_with_a_hole():
    """`equity.dropna()`가 곡선 한가운데 구멍까지 지워 버리던 자리."""
    idx = pd.date_range("2025-01-01", periods=10, freq="D")
    eq = pd.Series([100.0, 101, 102, np.nan, np.nan, 103, 104, 105, 106, 107],
                   index=idx)
    with pytest.raises(ValueError, match="계산 불가"):
        compute_metrics(eq, eq.pct_change().fillna(0.0),
                        pd.Series(1.0, index=idx), 365)


def test_metrics_refuse_an_infinite_curve():
    idx = pd.date_range("2025-01-01", periods=6, freq="D")
    eq = pd.Series([100.0, 101, np.inf, 103, 104, 105], index=idx)
    with pytest.raises(ValueError):
        compute_metrics(eq, eq.pct_change().fillna(0.0),
                        pd.Series(1.0, index=idx), 365)


def test_metrics_still_trim_a_leading_gap():
    """대조군 — 앞머리 빈 칸을 자르는 원래 동작은 그대로여야 한다.

    이걸 같이 막아 버리면 첫 봉이 비는 정상 곡선까지 성적을 못 낸다.
    """
    idx = pd.date_range("2025-01-01", periods=6, freq="D")
    eq = pd.Series([np.nan, 100.0, 101, 102, 103, 104], index=idx)
    m = compute_metrics(eq, eq.pct_change().fillna(0.0),
                        pd.Series(1.0, index=idx), 365)
    assert m.total_return == pytest.approx(104 / 100 - 1.0)


def test_the_hole_is_what_makes_the_number_a_lie():
    """구멍을 지우면 **왜** 거짓이 되는지를 숫자로 못박는다.

    구멍 뒤 구간만 남기면 곡선은 100 → 107(+7%)로 보인다. 실제로는 중간에
    계산이 끊긴 곡선이라 +7%도 -10%도 사실이 아니다. 예전 코드가 낸 것이
    바로 이런 종류의 숫자였다.
    """
    idx = pd.date_range("2025-01-01", periods=10, freq="D")
    eq = pd.Series([100.0, 101, 102, np.nan, np.nan, 103, 104, 105, 106, 107],
                   index=idx)
    trimmed = eq.dropna()
    assert trimmed.iloc[-1] / trimmed.iloc[0] - 1.0 == pytest.approx(0.07)
    with pytest.raises(ValueError):
        compute_metrics(eq, eq.pct_change().fillna(0.0),
                        pd.Series(1.0, index=idx), 365)
