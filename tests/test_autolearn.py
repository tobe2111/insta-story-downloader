"""정확도 추적 + 자동 페이퍼 학습 루프 테스트."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.broker import PaperBroker
from quant.data import SyntheticDataProvider
from quant.live import AutoLearner
from quant.risk import RiskManager
from quant.robustness import directional_accuracy
from quant.strategies import get_strategy


def _df(prices):
    idx = pd.date_range("2020-01-01", periods=len(prices), freq="D")
    return pd.DataFrame({"open": prices, "high": prices, "low": prices,
                         "close": prices, "volume": [1.0] * len(prices)}, index=idx)


def test_accuracy_perfect_long_in_uptrend():
    """오르는 시장에서 항상 롱이면 적중률 100%, 마지막 봉은 제외(다음 봉 없음)."""
    df = _df([100, 101, 102, 103, 104])
    sig = pd.Series(1.0, index=df.index)
    acc = directional_accuracy(df, sig)
    assert acc["n"] == 4                    # 마지막 봉은 미래가 없어 제외
    assert acc["hit_rate"] == 1.0


def test_accuracy_wrong_direction():
    """오르는 시장에서 항상 숏이면 적중률 0%."""
    df = _df([100, 101, 102, 103, 104])
    sig = pd.Series(-1.0, index=df.index)
    acc = directional_accuracy(df, sig)
    assert acc["hit_rate"] == 0.0


def test_accuracy_ignores_flat_positions():
    """비중 0(관망)인 봉은 정확도 계산에서 제외된다."""
    df = _df([100, 101, 102, 103, 104])
    sig = pd.Series([0.0, 1.0, 0.0, 1.0, 0.0], index=df.index)
    acc = directional_accuracy(df, sig)
    assert acc["n"] == 2 and acc["hit_rate"] == 1.0


def test_accuracy_rolling_series():
    df = _df([100, 101, 102, 101, 102, 103])
    sig = pd.Series(1.0, index=df.index)
    acc = directional_accuracy(df, sig, window=2)
    assert "rolling" in acc
    assert acc["rolling"].dropna().max() <= 1.0 + 1e-9
    assert acc["rolling"].dropna().min() >= -1e-9


def test_autolearn_cycle_records_and_persists(tmp_path):
    state = tmp_path / "auto.json"
    learner = AutoLearner(
        data=SyntheticDataProvider(seed=2),
        strategy=get_strategy("ma_cross"),
        broker=PaperBroker(cash=10_000),
        risk=RiskManager(),
        symbol="X", lookback=200, accuracy_window=30,
        state_path=str(state),
    )
    rec = learner.cycle()
    assert "hit_rate" in rec and "recent_hit_rate" in rec and rec["n"] >= 0
    assert state.exists()
    saved = json.loads(state.read_text(encoding="utf-8"))
    assert saved["mode"] == "paper-autolearn" and len(saved["history"]) == 1


def test_autolearn_run_multiple_cycles(tmp_path):
    learner = AutoLearner(
        data=SyntheticDataProvider(seed=5),
        strategy=get_strategy("momentum"),
        broker=PaperBroker(cash=10_000),
        risk=RiskManager(),
        symbol="Y", lookback=150,
        state_path=str(tmp_path / "s.json"),
    )
    hist = learner.run(cycles=3, interval_sec=0)
    assert len(hist) == 3
    # 자본은 항상 양수(페이퍼)여야 한다
    assert all(h["equity"] > 0 for h in hist)
