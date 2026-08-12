"""성과 지표를 **손계산과 맞춰 본다** (감사 140).

`compute_metrics`는 이 시스템에서 가장 많이 쓰이는 함수다. 샤프지수 하나가
틀리면

    · 오디션의 DSR(다중검정 보정 샤프)
    · 엣지 입증 게이트(연 12% → 20% 잠금 해제)
    · 검증 리포트의 '신뢰할 만함' 판정
    · 사이트에 나가는 모든 성과 숫자

가 **동시에** 틀린다. 그런데 변이 시험을 처음 걸어 보니

    excess.mean() / returns.std() * np.sqrt(periods_per_year)
    →  excess.mean() / returns.std()          # 연율화 제거(√252배 축소)

를 해도 검사가 전부 통과했다. 값을 손으로 확인한 검사가 하나도 없었고,
있던 검사는 '정렬 규칙'과 '부호' 같은 성질만 봤다.

감사 120(킬스위치)과 같은 계열이다 — 가장 중요한 장치인데 아무도 **값**을
확인하지 않았다. 그래서 이 파일은 답을 손으로 계산해 못 박는다.

기준 계열(일별 수익률 4개, 시작 자본 100):

    r      = [+10%, -5%, +10%, -5%]
    equity = [100, 110, 104.5, 114.95, 109.2025]

    총수익률 = 109.2025/100 - 1        = 0.092025
    평균     = 0.025
    표준편차 = √(4×0.075² / 3)          = 0.0866025…   (ddof=1)
    하방편차 = √((0.05²+0.05²)/4)       = 0.0353553…   (0 대비 RMS)
    최대낙폭 = 114.95 → 109.2025        = -0.05        (고점 대비)
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.backtest.metrics import compute_metrics  # noqa: E402

PPY = 252
R = [0.10, -0.05, 0.10, -0.05]
EQ = [100.0, 110.0, 104.5, 114.95, 109.2025]

MEAN = 0.025
STD = math.sqrt(4 * 0.075 ** 2 / 3)          # 0.08660254…
DOWNSIDE = math.sqrt((0.05 ** 2 + 0.05 ** 2) / 4)   # 0.03535533…


def _m(ppy: int = PPY, **kw):
    idx = pd.date_range("2026-01-01", periods=len(R), freq="D")
    return compute_metrics(
        pd.Series(EQ, index=pd.date_range("2025-12-31", periods=len(EQ),
                                          freq="D")),
        pd.Series(R, index=idx),
        pd.Series(1.0, index=idx),           # 내내 롱
        periods_per_year=ppy,
        positions_are_decision_time=False,   # 이미 정렬된 포지션
        **kw)


# ── 손계산 대조 ───────────────────────────────────────────────


def test_total_return_matches_the_equity_curve():
    assert abs(_m().total_return - 0.092025) < 1e-9


def test_volatility_is_the_annualised_standard_deviation():
    assert abs(_m().volatility - STD * math.sqrt(PPY)) < 1e-9


def test_sharpe_matches_the_hand_calculation():
    got = _m().sharpe
    want = MEAN / STD * math.sqrt(PPY)       # ≈ 4.5826
    assert abs(got - want) < 1e-9, f"{got} vs 손계산 {want}"
    assert got > 4.0, "연율화가 빠지면 이 값이 0.29 언저리로 떨어진다"


def test_sortino_uses_downside_deviation_from_zero():
    got = _m().sortino
    want = MEAN / DOWNSIDE * math.sqrt(PPY)  # ≈ 11.2249
    assert abs(got - want) < 1e-9, f"{got} vs 손계산 {want}"
    assert got > _m().sharpe, "하방편차가 전체 표준편차보다 작으니 더 커야 한다"


def test_max_drawdown_is_measured_from_the_running_peak():
    """고점 114.95 → 109.2025 = -5%. 시작(100) 대비로 재면 +9.2%가 된다."""
    assert abs(_m().max_drawdown - (-0.05)) < 1e-9


def test_win_rate_and_profit_factor_match_by_hand():
    m = _m()
    assert abs(m.win_rate - 0.5) < 1e-12          # 4봉 중 2봉 이익
    assert abs(m.profit_factor - 2.0) < 1e-12     # (0.10+0.10)/(0.05+0.05)


# ── 연율화가 실제로 걸려 있는가 ───────────────────────────────


def test_annualisation_scales_with_the_square_root_of_periods():
    """√ppy 배 — 이 관계가 깨지면 코인(365)과 주식(252)이 뒤섞인다."""
    base = _m(ppy=1)
    for ppy in (252, 365):
        got = _m(ppy=ppy)
        assert abs(got.sharpe - base.sharpe * math.sqrt(ppy)) < 1e-9
        assert abs(got.volatility - base.volatility * math.sqrt(ppy)) < 1e-9
        assert abs(got.sortino - base.sortino * math.sqrt(ppy)) < 1e-9


def test_a_crypto_year_and_a_stock_year_differ():
    """365와 252를 섞어 쓰면 샤프가 20% 부풀거나 줄어든다 — 실제로 다른 값이어야."""
    assert _m(ppy=365).sharpe > _m(ppy=252).sharpe * 1.1


# ── CAGR의 복리 구간 수 ───────────────────────────────────────


def test_cagr_compounds_over_intervals_not_points():
    """자본곡선의 **점**이 5개면 수익 **구간**은 4개다.

    구간을 하나 더 세면 연수가 길어져 CAGR이 조용히 작아진다. 짧은 검증
    구간일수록 오차가 커진다(10봉이면 11%).
    """
    growth = EQ[-1] / EQ[0]
    years = (len(EQ) - 1) / PPY              # 4/252
    assert abs(_m().cagr - (growth ** (1 / years) - 1)) < 1e-6


def test_calmar_is_cagr_over_the_drawdown():
    m = _m()
    assert abs(m.calmar - m.cagr / 0.05) < 1e-6


# ── 빈 입력에서 무너지지 않는가 ───────────────────────────────


def test_a_too_short_series_returns_zeros_not_an_error():
    idx = pd.date_range("2026-01-01", periods=1, freq="D")
    m = compute_metrics(pd.Series([100.0], index=idx),
                        pd.Series([0.0], index=idx),
                        pd.Series([0.0], index=idx))
    assert m.sharpe == 0.0 and m.max_drawdown == 0.0


# ── 분산이 사실상 0인 계열 (감사 146) ─────────────────────────
#
# `returns.std() > 0`으로 막으면 부동소수 잡음이 통과한다.
# np.full(100, 0.001).std(ddof=1) == 2.18e-19 이므로 샤프가 1e15가 된다.
# 그 값이 오디션 성적표·검증 리포트·사이트로 그대로 나간다.


def test_a_constant_return_series_has_no_sharpe():
    idx = pd.date_range("2026-01-01", periods=100, freq="D")
    r = pd.Series(0.001, index=idx)
    eq = pd.Series(100.0 * (1.001 ** np.arange(101)),
                   index=pd.date_range("2025-12-31", periods=101, freq="D"))
    m = compute_metrics(eq, r, pd.Series(1.0, index=idx),
                        periods_per_year=PPY,
                        positions_are_decision_time=False)
    assert m.sharpe == 0.0, (
        f"매 봉 똑같이 오르는 계열의 샤프가 {m.sharpe:.3e} — 분산이 없으면 "
        "샤프를 계산할 수 없다(판정 불가는 0으로 둔다)")
    assert abs(m.total_return - (eq.iloc[-1] / eq.iloc[0] - 1)) < 1e-9, (
        "다른 지표까지 망가뜨리면 안 된다")


def test_a_small_but_real_series_still_gets_a_sharpe():
    """대조군 — 크기만 작은 정상 계열을 퇴화로 오판하면 안 된다."""
    idx = pd.date_range("2026-01-01", periods=200, freq="D")
    r = pd.Series(np.random.default_rng(3).normal(1e-6, 1e-5, 200), index=idx)
    eq = pd.Series(100.0 * (1 + r).cumprod().to_numpy(), index=idx)
    m = compute_metrics(eq, r, pd.Series(1.0, index=idx),
                        periods_per_year=PPY,
                        positions_are_decision_time=False)
    assert m.sharpe != 0.0, "크기가 작을 뿐 정상인 계열을 퇴화로 오판한다"
