"""DSR·PSR이 **논문 공식대로 계산되는가** (감사 146).

DSR은 검증 리포트 세 칸 중 하나이고, 엣지 입증 게이트가 읽는 값이다.
"N번 시도했으면 이 정도 샤프는 운으로도 나온다"를 빼는 것이 전부다.

    PSR(SR*) = Φ( (SR − SR*)·√(T−1) / √(1 − γ₃·SR + (γ₄−1)/4·SR²) )
    E[max SR] ≈ σ_SR·[ (1−γ)·Z⁻¹(1 − 1/N) + γ·Z⁻¹(1 − 1/(N·e)) ]

                                        (Bailey & López de Prado)

감사 140(샤프)·145(PBO)에서 같은 병이 연속으로 나왔다 — **값을 아무도
손으로 확인하지 않았다.** 방향(시도가 늘면 DSR이 낮아진다)만 보면
계수를 뒤바꾸거나 고차 모멘트 보정을 통째로 빼도 방향은 유지된다.

그래서 이 파일은 **손계산과 대조**한다. 실측 앵커:

    PSR 손계산 0.990777  =  함수 0.990777
    E[max] N=10 1.5746 · N=1,000 3.2551 · N=100,000 4.3908
    DSR  N=1 0.9908 → N=100 0.4309 → N=10,000 0.0663
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from statistics import NormalDist

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.robustness.deflated_sharpe import (  # noqa: E402
    _EULER,
    deflated_sharpe_ratio,
    expected_max_sharpe,
    probabilistic_sharpe_ratio,
)

ND = NormalDist()


def _series(seed: int = 5, n: int = 500, mu: float = 0.001,
            sd: float = 0.01) -> np.ndarray:
    return np.random.default_rng(seed).normal(mu, sd, n)


def _hand_psr(r: np.ndarray, benchmark: float = 0.0) -> float:
    """논문 식을 그대로 손으로 옮긴 것 — 구현과 독립적인 두 번째 계산."""
    T = len(r)
    mu, sd = r.mean(), r.std(ddof=1)
    sr = mu / sd
    z = (r - mu) / sd
    skew = float((z ** 3).mean())
    kurt = float((z ** 4).mean())
    den = math.sqrt(1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr ** 2)
    return ND.cdf((sr - benchmark) * math.sqrt(T - 1.0) / den)


# ── PSR ───────────────────────────────────────────────────────


def test_psr_matches_the_formula_by_hand():
    r = _series()
    assert abs(probabilistic_sharpe_ratio(r) - _hand_psr(r)) < 1e-12


def test_psr_falls_when_the_benchmark_rises():
    r = _series()
    assert (probabilistic_sharpe_ratio(r, 0.0)
            > probabilistic_sharpe_ratio(r, 0.05)
            > probabilistic_sharpe_ratio(r, 0.20))


def test_negative_skew_lowers_confidence_at_similar_sharpe():
    """왼쪽 꼬리가 두꺼우면 같은 샤프여도 신뢰가 낮아야 한다.

    고차 모멘트 보정(γ₃·γ₄)이 분모에서 빠지면 이 차이가 사라진다 —
    '가끔 크게 터지는' 전략이 안전한 전략과 같은 점수를 받게 된다.
    """
    rng = np.random.default_rng(5)
    sym = rng.normal(0.001, 0.01, 500)
    fat = np.concatenate([rng.normal(0.0015, 0.007, 490),
                          rng.normal(-0.05, 0.005, 10)])   # 좌왜도 −2.85
    assert probabilistic_sharpe_ratio(fat) < probabilistic_sharpe_ratio(sym), (
        "좌왜도 계열이 대칭 계열보다 높은 신뢰를 받는다 — 꼬리 보정이 없다")


def test_a_tiny_sample_is_zero_not_a_guess():
    """3봉 미만은 판정하지 않는다 — 모르면 숫자를 만들지 않는다."""
    assert probabilistic_sharpe_ratio(np.array([0.01, 0.01])) == 0.0


def test_a_flat_series_is_a_coin_flip_never_skill():
    """변동이 전혀 없는 계열(관망만 했거나 시세가 고정)은 0.5다.

    ⚠️ 처음에 이 검사를 0.0으로 기대했는데 **내가 틀렸다.** 표준편차가 0이면
       샤프가 정의되지 않고, 구현은 sr=0으로 두어 Φ(0)=0.5 — "이 계열로는
       아무것도 말할 수 없다"는 정직한 답이다. 0.0(=확실히 나쁨)이라고
       단언하는 쪽이 오히려 없는 정보를 만드는 것이다.

    지켜야 할 성질은 값이 0이라는 게 아니라 **실력으로 오인되지 않는 것**이다.
    """
    flat = probabilistic_sharpe_ratio(np.zeros(100))
    assert abs(flat - 0.5) < 1e-12
    assert flat < 0.95, "변동이 없는 계열이 '실력' 문턱을 넘는다"
    # 상수 수익(예: 버그로 매 봉 +0.1%)도 마찬가지로 실력이 아니다
    assert deflated_sharpe_ratio(np.full(100, 0.001), 100) < 0.95


# ── 기대 최대 샤프(다중검정 허들) ─────────────────────────────


def test_expected_max_sharpe_matches_the_formula():
    for n in (10, 1_000, 100_000):
        want = 1.0 * ((1.0 - _EULER) * ND.inv_cdf(1.0 - 1.0 / n)
                      + _EULER * ND.inv_cdf(1.0 - 1.0 / (n * math.e)))
        assert abs(expected_max_sharpe(n, 1.0) - want) < 1e-12, n


def test_the_hurdle_rises_with_the_number_of_trials():
    """시도를 많이 할수록 '운으로 나올 최대 샤프'가 커진다."""
    a, b, c = (expected_max_sharpe(n, 1.0) for n in (10, 1_000, 100_000))
    assert a < b < c
    assert 1.5 < a < 1.7 and 3.2 < b < 3.4 and 4.3 < c < 4.5, (a, b, c)


def test_the_hurdle_scales_linearly_with_the_spread():
    """σ가 2배면 허들도 정확히 2배 — 계수가 뒤바뀌면 이 비례가 깨진다."""
    assert abs(expected_max_sharpe(1_000, 2.0)
               / expected_max_sharpe(1_000, 1.0) - 2.0) < 1e-12


# ── DSR ───────────────────────────────────────────────────────


def test_a_single_trial_needs_no_deflation():
    r = _series()
    assert abs(deflated_sharpe_ratio(r, 1) - probabilistic_sharpe_ratio(r)) < 1e-12


def test_more_trials_deflate_the_confidence():
    r = _series()
    one, hundred, many = (deflated_sharpe_ratio(r, n) for n in (1, 100, 10_000))
    assert one > hundred > many, (one, hundred, many)
    assert one > 0.95, f"단일 시행 신뢰가 {one:.4f} — 전제가 깨졌다"
    assert many < 0.2, (
        f"10,000번 시도한 승자의 신뢰가 {many:.4f} — 보정이 거의 안 걸린다")


def test_the_deflation_actually_uses_the_hurdle():
    """DSR(N) == PSR(기대 최대 샤프) 여야 한다 — 허들이 벤치마크로 들어가는가."""
    r = _series()
    T = len(r)
    mu, sd = r.mean(), r.std(ddof=1)
    sr = mu / sd
    z = (r - mu) / sd
    skew, kurt = float((z ** 3).mean()), float((z ** 4).mean())
    sigma = math.sqrt((1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr ** 2) / (T - 1.0))
    want = _hand_psr(r, expected_max_sharpe(500, sigma))
    assert abs(deflated_sharpe_ratio(r, 500) - want) < 1e-12


# ── 분산이 사실상 0인 계열 (감사 146) ─────────────────────────
#
# `sd <= 0`으로 막으면 부동소수 잡음이 통과한다.
#
#     np.full(100, 0.001).std(ddof=1) == 2.18e-19   (0이 아니다)
#     샤프 = 0.001 / 2.18e-19 = 4.59e15
#     DSR  = 1.0                      ← "확실한 실력"
#
# 매 봉 똑같이 오르는 계열(관망 중 고정 비용, 거래정지된 시세, 아주 짧은
# 검증 구간에서 우연히 같은 값)이 검증 3종을 만점으로 통과하고, 그 판정이
# 엣지 게이트를 풀어 목표 변동성을 12%→20%로 올린다.


def test_a_constant_return_series_is_not_certain_skill():
    got = deflated_sharpe_ratio(np.full(100, 0.001), 100)
    assert got < 0.5, (
        f"매 봉 똑같이 오르는 계열의 DSR이 {got:.4f} — 분산이 없으면 "
        "샤프를 계산할 수 없다(0으로 나눈 결과를 실력이라 부르면 안 된다)")


def test_the_guard_is_relative_not_absolute():
    """크기가 작은 계열(고빈도·소수점)도 정상 판정을 받아야 한다.

    절대 문턱으로 막으면 진짜 계열까지 퇴화로 몰아 0점을 준다 —
    가드가 덫이 되면 안 된다(FROZEN_IDEAS ④).
    """
    tiny = np.random.default_rng(5).normal(1e-6, 1e-5, 500)   # 크기만 작다
    assert probabilistic_sharpe_ratio(tiny) > 0.5, (
        "크기가 작을 뿐 정상인 계열을 퇴화로 오판한다")


def test_the_normal_path_is_unchanged():
    """고침이 정상 계열의 값을 바꾸지 않았는가 — 회귀 방지."""
    r = _series()
    assert abs(probabilistic_sharpe_ratio(r) - 0.990777) < 1e-5
    assert abs(deflated_sharpe_ratio(r, 1) - 0.990777) < 1e-5
