"""포트폴리오 리스크 지표(VaR/CVaR·상관 집중도·롤링 평균 상관) 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.risk import (
    correlation_concentration,
    rolling_avg_correlation,
    var_cvar,
)


# ---------------------------- VaR / CVaR ----------------------------

def test_var_cvar_constant_loss():
    """매일 -1%면 VaR=CVaR=1% (분포에 흩어짐이 없는 극단 케이스)."""
    r = pd.Series([-0.01] * 100)
    var, cvar = var_cvar(r, alpha=0.95)
    assert var == pytest.approx(0.01)
    assert cvar == pytest.approx(0.01)


def test_var_cvar_known_tail():
    """꼬리에 큰 손실이 있으면 CVaR > VaR (꼬리 위험을 더 정직하게 반영)."""
    r = pd.Series([0.01] * 95 + [-0.02, -0.03, -0.05, -0.08, -0.20])
    var, cvar = var_cvar(r, alpha=0.95)
    assert var > 0                      # 손실 방향이면 양수
    assert cvar > var                   # 꼬리 평균은 경계보다 크다
    assert cvar <= 0.20 + 1e-12         # 최악 손실을 넘을 수는 없다


def test_var_cvar_all_gains_gives_negative_var():
    """전부 이익인 표본이면 '손실 한계'가 음수로 나온다(이득 경계)."""
    r = pd.Series(np.linspace(0.001, 0.02, 100))
    var, _ = var_cvar(r, alpha=0.95)
    assert var < 0


def test_var_cvar_empty_returns_nan():
    """표본이 없으면 0(무위험처럼 보임)이 아니라 NaN을 반환한다."""
    var, cvar = var_cvar(pd.Series(dtype=float))
    assert np.isnan(var) and np.isnan(cvar)


def test_var_cvar_dataframe_per_column():
    df = pd.DataFrame({
        "a": [-0.01] * 50,
        "b": [-0.02] * 50,
    })
    out = var_cvar(df, alpha=0.95)
    assert list(out.index) == ["var", "cvar"]
    assert out.loc["var", "a"] == pytest.approx(0.01)
    assert out.loc["var", "b"] == pytest.approx(0.02)


def test_var_cvar_invalid_alpha_raises():
    with pytest.raises(ValueError):
        var_cvar(pd.Series([0.01]), alpha=1.5)


# ----------------------- 상관 집중도 -----------------------

def _corr_frame(rho_sign: float = 1.0, n: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    x = rng.normal(size=n)
    return pd.DataFrame({"a": x, "b": rho_sign * x, "c": rng.normal(size=n)})


def test_correlation_concentration_perfect_pair():
    out = correlation_concentration(_corr_frame(1.0))
    assert out["max_correlation"] == pytest.approx(1.0)
    assert out["n_assets"] == 3
    assert out["effective_n"] == pytest.approx(3.0)   # 균등 가중 기본


def test_correlation_concentration_weights_concentrated():
    df = _corr_frame(1.0)
    out = correlation_concentration(df, weights=[1.0, 0.0, 0.0])
    assert out["effective_n"] == pytest.approx(1.0)   # 한 종목 몰빵 → 유효 1종목


def test_correlation_concentration_anticorrelated():
    df = pd.DataFrame({"a": [1., -1., 1., -1., 1., -1.],
                       "b": [-1., 1., -1., 1., -1., 1.]})
    out = correlation_concentration(df)
    assert out["avg_correlation"] == pytest.approx(-1.0)
    assert out["effective_n"] == pytest.approx(2.0)


def test_correlation_concentration_single_asset_nan_corr():
    out = correlation_concentration(pd.DataFrame({"a": [0.01, -0.02, 0.03]}))
    assert np.isnan(out["avg_correlation"]) and np.isnan(out["max_correlation"])
    assert out["effective_n"] == pytest.approx(1.0)


# ----------------------- 롤링 평균 상관 -----------------------

def test_rolling_avg_correlation_identical_series():
    rng = np.random.default_rng(3)
    x = pd.Series(rng.normal(size=100))
    df = pd.DataFrame({"a": x, "b": x})
    out = rolling_avg_correlation(df, window=20)
    assert out.iloc[-1] == pytest.approx(1.0)
    assert out.iloc[:19].isna().all()                 # 윈도우 미달 구간은 NaN


def test_rolling_avg_correlation_regime_shift():
    """전반부 독립 → 후반부 동조화 데이터에서 후반 평균 상관이 더 높아야 한다."""
    rng = np.random.default_rng(5)
    n = 300
    a = rng.normal(size=n)
    b = rng.normal(size=n)
    b[n // 2:] = a[n // 2:] + 0.05 * rng.normal(size=n - n // 2)  # 후반 동조화
    out = rolling_avg_correlation(pd.DataFrame({"a": a, "b": b}), window=50)
    assert out.iloc[-1] > out.iloc[n // 2 - 1]


def test_rolling_avg_correlation_single_column_all_nan():
    out = rolling_avg_correlation(pd.DataFrame({"a": [1., 2., 3.]}), window=2)
    assert out.isna().all()


def test_rolling_avg_correlation_invalid_window():
    with pytest.raises(ValueError):
        rolling_avg_correlation(pd.DataFrame({"a": [1.], "b": [2.]}), window=1)
