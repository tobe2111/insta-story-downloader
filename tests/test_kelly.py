"""부분 켈리 상한 헬퍼 테스트 (순수 stdlib — 손으로 계산한 값과 대조)."""
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 패키지 __init__(pandas 의존)을 거치지 않고 파일 경로로 직접 로드 →
# pandas 없는 환경에서도 이 테스트만은 돌릴 수 있다 (test_circuit_breaker 관례).
_spec = importlib.util.spec_from_file_location(
    "kelly", str(Path(__file__).resolve().parent.parent
                 / "quant" / "risk" / "kelly.py"))
kelly = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = kelly
_spec.loader.exec_module(kelly)


# ── kelly_fraction ──────────────────────────────────────────────────────

def test_kelly_known_value():
    """p=0.6, b=1 → f* = (0.6·1 − 0.4)/1 = 0.2 (교과서 값)."""
    assert abs(kelly.kelly_fraction(0.6, 0.10, -0.10) - 0.2) < 1e-12


def test_kelly_asymmetric_payoff():
    """p=0.5, 이익 2%·손실 1% → b=2, f* = (0.5·2 − 0.5)/2 = 0.25."""
    assert abs(kelly.kelly_fraction(0.5, 0.02, -0.01) - 0.25) < 1e-12


def test_kelly_loss_sign_convention_irrelevant():
    """avg_loss는 음수(trade_stats 관례)든 양의 크기든 같은 값을 낸다."""
    assert kelly.kelly_fraction(0.6, 0.1, -0.05) == kelly.kelly_fraction(0.6, 0.1, 0.05)


def test_kelly_no_edge_is_zero():
    """p=0.5, b=1 → 엣지 없음 → 0."""
    assert kelly.kelly_fraction(0.5, 0.1, -0.1) == 0.0


def test_kelly_negative_edge_clipped_to_zero():
    """음의 엣지는 숏 켈리가 아니라 '걸지 말라'(0)이다."""
    assert kelly.kelly_fraction(0.4, 0.1, -0.1) == 0.0


def test_kelly_degenerate_inputs_are_zero():
    """퇴화 입력(NaN·범위 밖·손실 없음·이익 없음)은 전부 0 — 모르면 안 건다."""
    nan = float("nan")
    assert kelly.kelly_fraction(nan, 0.1, -0.1) == 0.0
    assert kelly.kelly_fraction(0.6, nan, -0.1) == 0.0
    assert kelly.kelly_fraction(0.6, 0.1, nan) == 0.0
    assert kelly.kelly_fraction(0.6, float("inf"), -0.1) == 0.0
    assert kelly.kelly_fraction(1.5, 0.1, -0.1) == 0.0      # 승률 > 1
    assert kelly.kelly_fraction(-0.1, 0.1, -0.1) == 0.0     # 승률 < 0
    assert kelly.kelly_fraction(0.6, 0.0, -0.1) == 0.0      # 이익 없음
    assert kelly.kelly_fraction(0.6, -0.1, -0.1) == 0.0     # 이익이 음수
    assert kelly.kelly_fraction(0.6, 0.1, 0.0) == 0.0       # 손실 0 → b 무한대
    assert kelly.kelly_fraction("x", 0.1, -0.1) == 0.0      # 형 오류도 삼킨다


def test_kelly_bounded_by_win_rate():
    """f* = p − q/b ≤ p — 이 공식의 풀 켈리는 승률을 넘지 못한다."""
    f = kelly.kelly_fraction(0.9, 0.10, -0.05)   # b=2 → (1.8−0.1)/2 = 0.85
    assert abs(f - 0.85) < 1e-12
    for p in (0.55, 0.7, 0.99):
        assert kelly.kelly_fraction(p, 0.2, -0.01) <= p + 1e-12


# ── fractional_kelly_cap ────────────────────────────────────────────────

_STATS = {  # trade_stats() 반환 형태 그대로
    "num_trades": 100, "win_rate": 0.6, "avg_win": 0.10, "avg_loss": -0.10,
    "expectancy": 0.02, "profit_factor": 1.5, "avg_bars_held": 5.0,
}


def test_fractional_cap_quarter_kelly():
    """풀 켈리 0.2의 1/4 = 0.05가 max_position 제안이 된다."""
    assert abs(kelly.fractional_kelly_cap(_STATS, fraction=0.25) - 0.05) < 1e-12


def test_fractional_cap_respects_absolute_cap():
    """fraction·켈리 곱이 커도 cap을 넘는 제안은 하지 않는다."""
    hot = dict(_STATS, win_rate=0.99, avg_win=0.2, avg_loss=-0.01)  # f*≈0.9895
    assert kelly.fractional_kelly_cap(hot, fraction=2.0, cap=1.0) == 1.0
    assert kelly.fractional_kelly_cap(hot, fraction=1.0, cap=0.5) == 0.5


def test_fractional_cap_too_few_trades_is_zero():
    """표본이 min_trades 미만이면 0 — 거래 몇 번의 승률은 잡음이다."""
    thin = dict(_STATS, num_trades=5)
    assert kelly.fractional_kelly_cap(thin) == 0.0
    assert kelly.fractional_kelly_cap(thin, min_trades=5) > 0.0   # 완화하면 계산


def test_fractional_cap_empty_stats_is_zero():
    """trade_stats([])(거래 없음) 형태 → 0."""
    empty = {"num_trades": 0, "win_rate": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
             "expectancy": 0.0, "profit_factor": 0.0, "avg_bars_held": 0.0}
    assert kelly.fractional_kelly_cap(empty) == 0.0
    assert kelly.fractional_kelly_cap({}) == 0.0
    assert kelly.fractional_kelly_cap(None) == 0.0            # dict 아님도 0


def test_fractional_cap_degenerate_params_are_zero():
    """fraction·cap이 퇴화하면 0 — 이상한 파라미터로 큰 포지션을 주지 않는다."""
    assert kelly.fractional_kelly_cap(_STATS, fraction=0.0) == 0.0
    assert kelly.fractional_kelly_cap(_STATS, fraction=-1.0) == 0.0
    assert kelly.fractional_kelly_cap(_STATS, cap=0.0) == 0.0
    assert kelly.fractional_kelly_cap(_STATS, fraction=float("nan")) == 0.0


def test_fractional_cap_never_negative_or_above_cap():
    """어떤 승률·손익비 조합에서도 결과는 [0, cap] 안이다."""
    for p in (0.0, 0.3, 0.5, 0.7, 1.0):
        for w, l in ((0.1, -0.1), (0.2, -0.05), (0.01, -0.2)):
            s = dict(_STATS, win_rate=p, avg_win=w, avg_loss=l)
            v = kelly.fractional_kelly_cap(s, fraction=0.5, cap=0.8)
            assert 0.0 <= v <= 0.8
            assert math.isfinite(v)
