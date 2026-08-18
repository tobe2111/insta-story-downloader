"""수급 SOM 도전자 — 논문 방식의 재현 가능한 이식 (2026-08-18).

지켜야 할 약속:
- 수급 피처(x_frgn5·x_inst5)가 없는 시장에서는 언제나 관망(0).
- 같은 데이터 → 언제나 같은 신호(고정 시드 — 시드 채택 편향 금지).
- 오늘 봉·오늘의 다음날 수익은 학습에 쓰지 않는다(룩어헤드 금지).
- 수급 상태와 다음날 수익이 실제로 묶여 있는 데이터에서는 그 군집을
  찾아 매수하고, 반대 군집에서는 관망한다.
- 도전자 링에 실제로 서 있다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.strategies.supplysom import SupplyDemandSOM      # noqa: E402


def _regime_df(n=420, seed=7):
    """수급이 +2 z인 날의 **다음날**은 +0.8%, -2 z인 날의 다음날은 -0.8%.

    수급 상태 → 다음날 수익의 결합이 명확한 합성 데이터 — SOM이 이걸
    못 찾으면 구현이 죽은 것이고, 반대로 결합이 없는 데이터에서 신호를
    내면 잡음을 신호로 승격하는 것이다.
    """
    rng = np.random.RandomState(seed)
    regime = rng.randint(0, 2, size=n)          # 0=음의 수급, 1=양의 수급
    close = np.empty(n)
    close[0] = 100.0
    for i in range(1, n):
        drift = 0.008 if regime[i - 1] == 1 else -0.008
        close[i] = close[i - 1] * (1.0 + drift)
    z = np.where(regime == 1, 2.0, -2.0)
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame({
        "open": close, "close": close, "high": close * 1.01,
        "low": close * 0.99, "volume": np.full(n, 1e6),
        "x_frgn5": z, "x_inst5": z}, index=idx), regime


def test_no_flow_columns_means_no_opinion():
    n = 400
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    close = 100 + np.cumsum(np.random.RandomState(1).normal(0, 1, n))
    df = pd.DataFrame({"open": close, "close": close, "high": close + 1,
                       "low": close - 1, "volume": np.full(n, 1e6)}, index=idx)
    sig = SupplyDemandSOM().generate_signals(df)
    assert float(sig.abs().max()) == 0.0, (
        "수급 데이터가 없는데 의견을 낸다 — 재료 없는 신호는 잡음이다")


def test_the_som_finds_the_profitable_cluster():
    df, regime = _regime_df()
    sig = SupplyDemandSOM().generate_signals(df).to_numpy()
    tail = slice(300, 419)                       # 학습창 이후 구간
    pos = sig[tail][regime[tail] == 1]
    neg = sig[tail][regime[tail] == 0]
    assert pos.mean() > 0.9, f"양의 수급 군집을 못 찾는다: {pos.mean():.2f}"
    assert neg.mean() < 0.1, f"음의 수급 군집에서 산다: {neg.mean():.2f}"


def test_same_data_same_signals_always():
    df, _ = _regime_df()
    a = SupplyDemandSOM().generate_signals(df)
    b = SupplyDemandSOM().generate_signals(df)
    assert (a == b).all(), "같은 데이터에서 다른 신호 — 재현성 위반"


def test_the_future_cannot_change_the_past():
    df, _ = _regime_df()
    base = SupplyDemandSOM().generate_signals(df).iloc[:400]
    df2 = df.copy()
    df2.iloc[410:, df2.columns.get_loc("close")] *= 3.0   # 미래를 뒤흔든다
    spiked = SupplyDemandSOM().generate_signals(df2).iloc[:400]
    assert (base == spiked).all(), "미래 봉이 과거 신호를 바꿨다 — 룩어헤드"


def test_thin_history_stays_quiet():
    df, _ = _regime_df(n=120)                    # 학습창(250) 미달
    sig = SupplyDemandSOM().generate_signals(df)
    assert float(sig.abs().max()) == 0.0, "표본 미달인데 신호를 낸다"


def test_the_challenger_is_in_the_ring_with_fixed_seed():
    from quant.live.retrain import build_challengers
    ring = build_challengers({"strategy": "ml", "params": {}}, "2026-08-18",
                             evolve=False)
    assert any(c.get("strategy") == "supply_som" for c in ring), "링에 없다"
    src = (ROOT / "quant" / "strategies" / "supplysom.py").read_text("utf-8")
    assert "seed: int = 42" in src and "시드 채택" in src, (
        "시드 고정과 그 이유(시드 채택 편향 금지)가 코드에 없다")
