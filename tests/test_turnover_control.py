"""회전율 통제 계약 검사 — 비용이 수익을 먹지 않게.

배경(2026-08-11 실측): 매일 20종목 중 7.4개(37%)를 갈아타고 있었다. 총노출
100% 기준 연 40%(낙관 가정으로도 11%)의 비용인데 기대수익은 8.8% —
엣지가 있든 없든 수익이 날 수 없는 구조였다. 원인은 포트폴리오가 밴드를
종목 수로 나눠(0.05/20=0.25%) 사실상 무력화한 것.

핵심 계약:
  ① 상대 밴드 — 목표 포지션 대비 비율로 판단해, 노출이 커져도 밴드가
     상대적으로 촘촘해지지 않는다
  ② 비용 비례 — 비싼 시장(한국주식)일수록 더 벗어나야 고쳐 잡는다
  ③ 청산은 밴드와 무관하게 항상 실행 — 빠져나오는 길은 막지 않는다
  ④ 신호 평활은 진입만 늦추고 청산은 즉시 반영한다
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.broker import PaperBroker  # noqa: E402
from quant.live.daily import (  # noqa: E402
    REBALANCE_BAND_REL_MAX,
    REBALANCE_BAND_REL_MIN,
    _rebalance_band_rel,
    _smooth_weights,
)


# ── ① 상대 밴드 ────────────────────────────────────────────────


def test_relative_band_skips_small_drift_but_allows_real_move():
    b = PaperBroker(cash=100_000.0)
    # 목표 10% 신규 진입 — 밴드와 무관하게 전액이 '변화'라 체결된다
    assert b.target_weight("X", 0.10, 100.0, 100_000.0,
                           rebalance_band_rel=0.25) is not None
    eq = b.equity({"X": 100.0})
    # 목표를 10%→11%로: 변화 1%p는 목표(11%)의 9% → 밴드 25% 미만 → 생략
    assert b.target_weight("X", 0.11, 100.0, eq,
                           rebalance_band_rel=0.25) is None
    # 목표를 10%→20%로: 변화가 목표의 50% → 체결
    assert b.target_weight("X", 0.20, 100.0, eq,
                           rebalance_band_rel=0.25) is not None


def test_relative_band_is_scale_invariant():
    """노출을 키워도 '몇 %나 벗어나야 고치는가'는 그대로여야 한다."""
    for base in (0.01, 0.10, 0.50):
        b = PaperBroker(cash=100_000.0)
        b.target_weight("X", base, 100.0, 100_000.0)
        eq = b.equity({"X": 100.0})
        small = base * 1.10          # 10% 드리프트 → 밴드(25%) 안 → 생략
        big = base * 1.60            # 60% 드리프트 → 체결
        assert b.target_weight("X", small, 100.0, eq,
                               rebalance_band_rel=0.25) is None, base
        assert b.target_weight("X", big, 100.0, eq,
                               rebalance_band_rel=0.25) is not None, base


def test_liquidation_ignores_band():
    b = PaperBroker(cash=100_000.0)
    b.target_weight("X", 0.10, 100.0, 100_000.0)
    eq = b.equity({"X": 100.0})
    assert b.target_weight("X", 0.0, 100.0, eq,
                           rebalance_band_rel=0.99) is not None


# ── ② 비용 비례 ────────────────────────────────────────────────


def test_band_stays_within_bounds():
    for m in ("kr_stock", "us_stock", "crypto"):
        v = _rebalance_band_rel(m)
        assert REBALANCE_BAND_REL_MIN <= v <= REBALANCE_BAND_REL_MAX


def test_band_widens_when_measured_cost_is_high(monkeypatch):
    """실측 비용이 크면 밴드가 넓어진다 — 측정이 행동으로 이어지는 고리."""
    def fake(state_dir="state"):
        return {"markets": {
            "kr_stock": {"n": 40, "assumed_bp": 14.0, "mean_adverse_bp": 79.0},
            "us_stock": {"n": 40, "assumed_bp": 6.0, "mean_adverse_bp": -9.0},
        }}
    monkeypatch.setattr("quant.reporting.fill_gap.fill_gap_report", fake)
    kr = _rebalance_band_rel("kr_stock")
    us = _rebalance_band_rel("us_stock")
    assert kr > us                            # 93bp vs 6bp
    assert kr == pytest.approx(0.279, abs=1e-3)
    assert us == REBALANCE_BAND_REL_MIN       # 유리했던 시장은 하한


def test_thin_sample_falls_back_to_assumption(monkeypatch):
    """표본이 얇으면 실측을 믿지 않고 가정으로 돌아간다."""
    monkeypatch.setattr(
        "quant.reporting.fill_gap.fill_gap_report",
        lambda state_dir="state": {"markets": {
            "kr_stock": {"n": 3, "assumed_bp": 14.0,
                         "mean_adverse_bp": 500.0}}})
    assert _rebalance_band_rel("kr_stock") == REBALANCE_BAND_REL_MIN


# ── ④ 신호 평활 ────────────────────────────────────────────────


def test_smoothing_slows_entry_but_not_exit():
    prev = {"a": 0.0, "b": 0.40}
    new = {"a": 0.40, "b": 0.0}
    out = _smooth_weights(new, prev, alpha=0.5)
    assert out["a"] == pytest.approx(0.20)   # 진입은 절반만 — 서서히
    assert out["b"] == 0.0                   # 청산은 즉시 — 미련 없이


def test_smoothing_converges_and_is_bounded():
    prev, target = {"a": 0.0}, {"a": 1.0}
    w = prev
    for _ in range(6):
        w = _smooth_weights(target, w, alpha=0.5)
        assert 0.0 <= w["a"] <= 1.0
    assert w["a"] > 0.95                     # 며칠이면 목표에 도달


# ── ⑤ 재조정 쿨다운 ────────────────────────────────────────────


def test_cooldown_blocks_frequent_readjustment():
    from quant.live.daily import _in_cooldown
    lt = {"crypto:BTC/USDT": "2026-08-10"}
    # 이틀 뒤 소폭 이탈 → 쿨다운(5거래일 미만)으로 보류
    assert _in_cooldown("crypto:BTC/USDT", lt, "2026-08-12",
                        target_w=0.10, held_w=0.11)
    # 열흘 뒤면 다시 손댈 수 있다
    assert not _in_cooldown("crypto:BTC/USDT", lt, "2026-08-24",
                            target_w=0.10, held_w=0.11)


def test_cooldown_yields_to_liquidation_and_big_moves():
    from quant.live.daily import _in_cooldown
    lt = {"x": "2026-08-10"}
    # 청산은 달력과 무관
    assert not _in_cooldown("x", lt, "2026-08-11", 0.0, 0.10)
    # 큰 이탈(목표의 100% 초과 = 두 배/반토막)은 즉시 대응
    assert not _in_cooldown("x", lt, "2026-08-11", 0.10, 0.21)
    # 첫 진입(기록 없음)도 막지 않는다
    assert not _in_cooldown("y", lt, "2026-08-11", 0.10, 0.0)


def test_cooldown_override_is_market_agnostic():
    """예외 기준이 시장별 밴드에 좌우되면 같은 변화가 시장 따라 달라진다."""
    from quant.live.daily import _in_cooldown
    lt = {"a": "2026-08-10", "b": "2026-08-10"}
    # 동일한 60% 드리프트는 어느 시장이든 동일하게 '예외 아님'(쿨다운 유지)
    for key in ("a", "b"):
        assert _in_cooldown(key, lt, "2026-08-11",
                            target_w=0.10, held_w=0.16)


def test_wired_into_portfolio_and_recorded():
    src = (Path(__file__).resolve().parent.parent
           / "quant" / "live" / "daily.py").read_text("utf-8")
    assert "_smooth_weights(weights" in src and "prev_weights" in src
    assert "rebalance_band_rel=_rebalance_band_rel" in src
    assert '"turnover"' in src               # 회전율을 매일 기록한다
    assert "REBALANCE_BAND / n" not in src   # 종목 수로 나누던 밴드 제거
