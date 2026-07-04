"""시장 레짐 분류기 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.data import SyntheticDataProvider
from quant.robustness import classify_regime, regime_feature, regime_summary


def _df(prices):
    idx = pd.date_range("2020-01-01", periods=len(prices), freq="D")
    return pd.DataFrame({"open": prices, "high": prices, "low": prices,
                         "close": prices, "volume": 1.0}, index=idx)


def test_trend_labels_bull_and_bear():
    """상승 추세 후반은 bull, 하락 추세 후반은 bear로 라벨링된다."""
    up = list(np.linspace(100, 200, 120))
    down = list(np.linspace(200, 100, 120))
    reg = classify_regime(_df(up + down), trend_window=50)
    # 상승 구간 끝 무렵은 강세, 하락 구간 끝 무렵은 약세
    assert reg["trend"].iloc[110] == "bull"
    assert reg["trend"].iloc[-1] == "bear"


def test_regime_columns_and_values():
    df = SyntheticDataProvider(seed=9).get_ohlcv("R", "1d", limit=500)
    reg = classify_regime(df)
    assert list(reg.columns) == ["trend", "vol", "regime"]
    assert set(reg["trend"].unique()) <= {"bull", "bear", "unknown"}
    assert set(reg["vol"].unique()) <= {"high", "low", "unknown"}


def test_regime_no_lookahead():
    """미래를 잘라도 과거 국면 라벨이 바뀌지 않는다(과거 정보만 사용)."""
    df = SyntheticDataProvider(seed=4).get_ohlcv("R", "1d", limit=420)
    cut = 320
    full = classify_regime(df)["regime"].iloc[:cut - 1].tolist()
    trunc = classify_regime(df.iloc[:cut])["regime"].iloc[:cut - 1].tolist()
    assert full == trunc, "레짐 분류가 미래 데이터를 참조함"


def test_regime_summary_sums_to_one():
    df = SyntheticDataProvider(seed=2).get_ohlcv("R", "1d", limit=500)
    s = regime_summary(df)
    assert abs(sum(s.values()) - 1.0) < 1e-9


def test_regime_feature_bounded():
    """레짐 피처는 0~1 범위이고 df 인덱스를 보존한다."""
    df = SyntheticDataProvider(seed=7).get_ohlcv("R", "1d", limit=300)
    feat = regime_feature(df)
    assert list(feat.columns) == ["trend_up", "vol_high"]
    assert feat.index.equals(df.index)
    assert (feat >= 0.0).all().all() and (feat <= 1.0).all().all()
