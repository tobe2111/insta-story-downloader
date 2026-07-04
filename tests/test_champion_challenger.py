"""챔피언-챌린저 검증 하네스 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.data import SyntheticDataProvider
from quant.live import ChampionChallenger
from quant.strategies import get_strategy


class _AlwaysLong:
    name = "always_long"
    allow_short = False

    def generate_signals(self, df):
        return pd.Series(1.0, index=df.index, name="target")


class _AlwaysFlat:
    name = "flat"
    allow_short = False

    def generate_signals(self, df):
        return pd.Series(0.0, index=df.index, name="target")


def _rising(n=120):
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    price = np.linspace(100, 200, n)
    return pd.DataFrame({"open": price, "high": price, "low": price,
                         "close": price, "volume": 1.0}, index=idx)


def test_same_strategy_no_swap():
    """챔피언과 챌린저가 같으면 차이가 0 → 교체하지 않는다."""
    df = SyntheticDataProvider(seed=8).get_ohlcv("CC", "1d", limit=300)
    cc = ChampionChallenger(get_strategy("ma_cross"), get_strategy("ma_cross"))
    res = cc.evaluate(df)
    assert res["swap"] is False
    assert abs(res["mean_diff"]) < 1e-9


def test_clearly_better_challenger_swaps():
    """상승장에서 롱(챌린저)이 관망(챔피언)을 유의하게 이기면 교체 권고."""
    df = _rising()
    cc = ChampionChallenger(_AlwaysFlat(), _AlwaysLong(), min_obs=30)
    res = cc.evaluate(df)
    assert res["challenger_return"] > res["champion_return"]
    assert res["swap"] is True
    assert cc.active(df) is cc.challenger


def test_worse_challenger_no_swap():
    """반대로 챌린저가 나쁘면 교체하지 않고 챔피언을 유지한다."""
    df = _rising()
    cc = ChampionChallenger(_AlwaysLong(), _AlwaysFlat(), min_obs=30)
    res = cc.evaluate(df)
    assert res["swap"] is False
    assert cc.active(df) is cc.champion


def test_insufficient_obs_no_swap():
    """표본이 min_obs보다 적으면 교체를 보류한다."""
    df = _rising(n=40)
    cc = ChampionChallenger(_AlwaysFlat(), _AlwaysLong(), min_obs=1000)
    assert cc.evaluate(df)["swap"] is False
