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


def test_bootstrap_cagr_finite_with_extreme_losses():
    """한 봉이 -100% 이하(레버리지/숏)여도 CAGR이 NaN으로 붕괴하지 않는다(버그 수정)."""
    import pandas as pd

    r = pd.Series([0.01] * 49 + [-1.5])          # 마지막 봉 -150% → equity 음수 가능
    dist = bootstrap_metrics(r, n_sims=200, seed=1)
    assert np.isfinite(dist["cagr"]).all()       # 음수의 분수승(NaN)이 없어야
    assert (dist["cagr"] >= -1.0 - 1e-9).all()   # 최악은 -100%
    assert "nan" not in summarize(dist).lower()  # 요약도 NaN 없이


def test_html_report_creates_missing_parent_dirs(result, tmp_path):
    """부모 폴더가 없는 경로도 자동 생성해 저장한다(FileNotFoundError 방지)."""
    out = generate_report(result, tmp_path / "new" / "deep" / "r.html")
    assert out.exists()


def test_html_report_written(result, tmp_path):
    out = generate_report(result, tmp_path / "r.html", title="테스트")
    assert out.exists()
    html = out.read_text(encoding="utf-8")
    assert "<svg" in html and "샤프지수" in html and "테스트" in html
    # 벤치마크 오버레이 + 이익팩터가 리포트에 포함되어야 한다
    assert "매수후보유" in html and "이익팩터" in html
    # 자본곡선 카드에 두 개의 선(전략+벤치마크)이 그려져야 한다
    assert html.count("<polyline") >= 2
    # 거래 단위 통계 섹션(기대값)도 포함되어야 한다
    assert "거래 통계" in html and "기대값" in html
    # 가격 차트 + 매매 시점 마커(진입/청산) 섹션이 포함되어야 한다
    assert "매매 시점" in html and "진입" in html and "청산" in html
