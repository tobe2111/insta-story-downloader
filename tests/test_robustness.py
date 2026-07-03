"""몬테카를로 부트스트랩 + HTML 리포트 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.backtest import Backtester
from quant.data import SyntheticDataProvider
from quant.reporting import generate_report
from quant.robustness import bootstrap_metrics, summarize
from quant.strategies import get_strategy


@pytest.fixture
def result():
    df = SyntheticDataProvider(seed=9).get_ohlcv("MC", "1d", limit=400)
    return Backtester(get_strategy("ma_cross")).run(df)


def test_bootstrap_shapes(result):
    dist = bootstrap_metrics(result.returns, n_sims=200, seed=1)
    for key in ("sharpe", "total_return", "max_drawdown", "cagr"):
        assert key in dist
        assert len(dist[key]) == 200
        assert np.isfinite(dist[key]).all()


def test_bootstrap_deterministic(result):
    a = bootstrap_metrics(result.returns, n_sims=100, seed=7)
    b = bootstrap_metrics(result.returns, n_sims=100, seed=7)
    assert np.allclose(a["sharpe"], b["sharpe"])


def test_bootstrap_maxdd_nonpositive(result):
    dist = bootstrap_metrics(result.returns, n_sims=100, seed=2)
    assert (dist["max_drawdown"] <= 1e-9).all()


def test_summarize_text(result):
    dist = bootstrap_metrics(result.returns, n_sims=100, seed=3)
    text = summarize(dist)
    assert "샤프지수" in text and "신뢰구간" in text


def test_bootstrap_insufficient_data():
    import pandas as pd

    with pytest.raises(ValueError):
        bootstrap_metrics(pd.Series([0.01]), n_sims=10)


def test_html_report_written(result, tmp_path):
    out = generate_report(result, tmp_path / "r.html", title="테스트")
    assert out.exists()
    html = out.read_text(encoding="utf-8")
    assert "<svg" in html and "샤프지수" in html and "테스트" in html
