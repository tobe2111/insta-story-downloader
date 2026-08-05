"""신호 근거 해설(quant/live/explain.py) — 사람이 읽는 문장이 정확해야 한다."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from quant.live.explain import explain_signal


def _df(up=True, n=260):
    drift = 0.002 if up else -0.002
    close = 100 * np.cumprod(1 + np.full(n, drift))
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    return pd.DataFrame({"open": close, "high": close * 1.01,
                         "low": close * 0.99, "close": close,
                         "volume": 1.0}, index=idx)


def test_explain_ma_cross_up():
    text = explain_signal({"strategy": "ma_cross",
                           "params": {"fast": 20, "slow": 60}}, _df(True), 0.5)
    assert "매수 +50%" in text and "20일선이 60일선 위" in text


def test_explain_regime_blocked():
    text = explain_signal(
        {"strategy": "regime_wrap",
         "params": {"inner": {"strategy": "ma_cross",
                              "params": {"fast": 20, "slow": 60}},
                    "trend_window": 200}},
        _df(False), 0.0)
    assert "레짐 필터" in text and "약세 국면" in text and "관망" in text


def test_explain_ml_watching():
    text = explain_signal({"strategy": "ml",
                           "params": {"model": "gb", "threshold": 0.55}},
                          _df(True), 0.0)
    assert "그라디언트부스팅" in text and "관망" in text and "55%" in text


def test_explain_ml_long_with_prob():
    text = explain_signal({"strategy": "ml",
                           "params": {"model": "logreg", "threshold": 0.55}},
                          _df(True), 0.6)
    assert "매수 +60%" in text and "상승확률" in text


def test_explain_never_raises():
    """어떤 입력에도 예외 없이 폴백 문장을 낸다 — 해설이 매매를 막으면 안 된다."""
    text = explain_signal({"strategy": "없는전략"}, None, 0.3)
    assert "챔피언 전략 신호에 따름" in text


def test_ml_small_weight_not_contradictory():
    """확률이 기준을 넘었는데 위험 조절로 비중이 작으면 '관망'이라 말하지 않는다."""
    import numpy as np
    import pandas as pd

    from quant.live.explain import explain_signal

    idx = pd.date_range("2026-01-01", periods=120, freq="D")
    close = pd.Series(np.linspace(100, 120, len(idx)), index=idx)
    df = pd.DataFrame({"open": close, "high": close, "low": close,
                       "close": close, "volume": 1.0})
    spec = {"strategy": "ml", "params": {"model": "logreg", "threshold": 0.55}}
    out = explain_signal(spec, df, 0.02)          # 신호 있음 + 비중 2%
    assert "관망" not in out
    assert "소액 매수" in out and "비중을 낮게" in out
