"""전략 A/B 비교 테스트 — '더 나아 보이는 것'이 노이즈인지 검정하는 도구.

핵심 검증: 동일 수익률은 차이 0·비유의, 명백히 나은 시리즈는 prob_a_better가
높고 유의, 같은 seed면 결정론적, 리포트가 정직한 문구를 담는지.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.robustness.compare import (
    compare_report,
    compare_strategies,
)


def test_identical_returns_not_significant():
    """완전히 같은 수익률 → 차이≈0, 유의하지 않음."""
    rng = np.random.default_rng(0)
    r = pd.Series(rng.normal(0.001, 0.01, size=400))
    res = compare_strategies(r, r.copy(), n_sims=500, seed=1)
    assert abs(res["sharpe_diff"]) < 1e-9
    assert res["ci_low"] <= 0.0 <= res["ci_high"]
    assert res["significant"] is False
    assert res["paired"] is True


def test_clearly_better_is_significant():
    """A가 뚜렷하게 나은 시리즈 → prob_a_better 높고 유의."""
    rng = np.random.default_rng(5)
    a = pd.Series(rng.normal(0.002, 0.01, size=500))    # 강한 양의 드리프트
    b = pd.Series(rng.normal(-0.001, 0.01, size=500))   # 음의 드리프트
    res = compare_strategies(a, b, n_sims=1000, seed=2)
    assert res["sharpe_a"] > res["sharpe_b"]
    assert res["prob_a_better"] > 0.9
    assert res["significant"] is True
    assert res["ci_low"] > 0.0


def test_determinism_with_fixed_seed():
    rng_data = np.random.default_rng(9)
    a = pd.Series(rng_data.normal(0.001, 0.01, size=300))
    b = pd.Series(rng_data.normal(0.0005, 0.01, size=300))
    r1 = compare_strategies(a, b, n_sims=400, seed=123)
    r2 = compare_strategies(a, b, n_sims=400, seed=123)
    assert r1 == r2
    # 다른 seed면 부트스트랩 분포가 달라져야 한다
    r3 = compare_strategies(a, b, n_sims=400, seed=124)
    assert r1["ci_low"] != r3["ci_low"] or r1["ci_high"] != r3["ci_high"]


def test_independent_when_different_length():
    rng = np.random.default_rng(3)
    a = pd.Series(rng.normal(0.001, 0.01, size=400))
    b = pd.Series(rng.normal(0.001, 0.01, size=250))
    res = compare_strategies(a, b, n_sims=300, seed=7)
    assert res["paired"] is False


def test_too_short_raises():
    with pytest.raises(ValueError):
        compare_strategies([0.1], [0.1, 0.2, 0.3], n_sims=10)


def test_report_significant_phrases():
    rng = np.random.default_rng(5)
    a = pd.Series(rng.normal(0.002, 0.01, size=500))
    b = pd.Series(rng.normal(-0.001, 0.01, size=500))
    text = compare_report(compare_strategies(a, b, n_sims=800, seed=2))
    assert "유의" in text and "보장" in text


def test_report_noise_phrases():
    """유의하지 않은 경우 '노이즈일 수 있다'는 취지를 담는다."""
    fake = {
        "sharpe_a": 1.2, "sharpe_b": 1.1, "sharpe_diff": 0.1,
        "ci_low": -0.5, "ci_high": 0.7, "prob_a_better": 0.6,
        "significant": False, "paired": True,
    }
    text = compare_report(fake)
    assert "노이즈" in text
    assert "파라미터를 바꿨다고 개선된 게 아니다" in text


def test_ab_test_end_to_end():
    """ab_test가 두 전략을 백테스트해 비교 결과를 낸다."""
    from quant.data import SyntheticDataProvider
    from quant.strategies import Momentum, MovingAverageCross

    df = SyntheticDataProvider(seed=4).get_ohlcv("AB", "1d", limit=400)
    from quant.robustness.compare import ab_test

    res = ab_test(
        df,
        lambda: MovingAverageCross(fast=5, slow=20),
        lambda: Momentum(),
        n_sims=300,
        seed=11,
    )
    assert set(res) >= {"sharpe_a", "sharpe_b", "sharpe_diff", "significant"}
    assert res["paired"] is True     # 같은 데이터 → 같은 길이


# ── 분산이 사실상 0인 계열 (감사 146) ─────────────────────────


def test_a_constant_arm_does_not_win_by_infinite_sharpe():
    """매 봉 똑같이 오르는 쪽이 부동소수 잡음으로 압승하면 안 된다.

    `sd > 0`으로 막으면 np.full(...).std() == 1e-19이 통과해 샤프가 1e15가
    되고, 그 팔이 모든 부트스트랩 재추출에서 이긴다 — A/B 검정이 통째로
    잡음에 넘어간다.
    """
    const = np.full(300, 0.001)
    real = np.random.default_rng(7).normal(0.002, 0.01, 300)
    res = compare_strategies(const, real, n_sims=200, seed=3)
    assert abs(res["sharpe_a"]) < 1e-9, (
        f"상수 계열의 샤프가 {res['sharpe_a']:.3e} — 분산이 없으면 판정 불가(0)다")
    assert res["sharpe_b"] != 0.0, "대조군: 정상 계열은 샤프가 나와야 한다"


def test_a_small_but_real_arm_is_not_mistaken_for_degenerate():
    """대조군 — 크기만 작은 정상 계열을 퇴화로 몰면 가드가 덫이 된다."""
    tiny = np.random.default_rng(9).normal(1e-6, 1e-5, 300)
    res = compare_strategies(tiny, tiny * 0.5, n_sims=200, seed=3)
    assert res["sharpe_a"] != 0.0, "크기가 작을 뿐 정상인 계열을 퇴화로 오판한다"
