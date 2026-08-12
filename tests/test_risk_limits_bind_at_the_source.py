"""위험 한도가 **사이징 단계에서** 실제로 구속하는가 (감사 141).

감사 121·122에서 통합 계좌의 한도(엣지 게이트·과집중 상한)가 무방비였던
것을 고쳤다. 같은 방법을 한 단계 아래 — 종목별 사이징 본체(`RiskManager`)와
비용 모델에 걸어 보니 셋이 더 나왔다.

    scale = (target_vol / realized).clip(upper=3.0)   → upper=1e9      ❌
    sized = (target*scale).clip(-max_position, ...)   → clip 제거       ❌
    max(-CAP, min(CAP, funding_rate))                 → 그대로 반환      ❌

셋 다 전 검사가 통과했다. 각각이 풀리면

  · 레버리지 상한 — 변동성이 아주 낮은 구간(횡보·거래 부진)에서 배수가
    수십 배로 뛴다. 하필 변동성 폭발 **직전**에 최대로 실린다.
  · 최대 포지션 — 전략이 목표 2.0을 말하면 그대로 2배를 산다.
  · 펀딩비 상한 — 소스 주석이 이유를 이미 적어 뒀다: "|rate|>=1 인 오염
    값 하나가 cash_equity *= 1-hold 에서 **자본 부호를 뒤집어** 백테스트
    전체를 조용히 망가뜨린다."

셋 다 '한도'다. 한도는 평소에 아무 일도 하지 않기 때문에, 사라져도 티가
안 난다 — 그래서 반드시 **걸리는 상황을 만들어** 확인해야 한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.backtest.costs import CostModel  # noqa: E402
from quant.risk.manager import RiskConfig, RiskManager  # noqa: E402

IDX = pd.date_range("2026-01-01", periods=120, freq="D")


def _df(daily_vol: float) -> pd.DataFrame:
    """일별 변동성이 정확히 daily_vol인 가격 계열(부호만 번갈아)."""
    steps = np.where(np.arange(len(IDX)) % 2 == 0, daily_vol, -daily_vol)
    close = 100.0 * np.cumprod(1.0 + steps)
    return pd.DataFrame({"open": close, "high": close, "low": close,
                         "close": close, "volume": 1000.0}, index=IDX)


def _sized(daily_vol: float, **cfg) -> pd.Series:
    base = dict(sizing="vol_target", target_vol=0.20, vol_window=30,
                periods_per_year=365, max_position=10.0)
    base.update(cfg)
    rm = RiskManager(RiskConfig(**base))
    return rm.size_positions(_df(daily_vol), pd.Series(1.0, index=IDX))


# ── ① 레버리지 상한 ───────────────────────────────────────────


def test_the_leverage_cap_binds_when_volatility_is_tiny():
    """변동성이 거의 0인 구간에서 배수가 3배를 못 넘는다.

    일 0.01% 변동성 → 연율 약 0.19% → target 20% / 0.19% ≈ 105배.
    상한이 없으면 그대로 실린다.
    """
    got = _sized(0.0001).max()
    assert got > 0, "노출이 0이면 이 검사가 헛것이 된다"
    assert got <= 3.0 + 1e-9, f"레버리지 상한 3배를 넘겼다: {got}"
    assert abs(got - 3.0) < 1e-9, (
        f"상한에 딱 붙어야 하는 구간인데 {got} — 전제가 깨졌다")


def test_a_normal_volatility_is_not_capped():
    """대조군 — 상한이 늘 걸리면 '한도'가 아니라 상수다."""
    got = _sized(0.03).max()          # 연율 약 57% → 배수 0.35
    assert 0 < got < 3.0 - 1e-6, f"상한이 안 걸려야 하는데 {got}"


# ── ② 종목당 최대 노출 ────────────────────────────────────────


def test_the_max_position_clips_the_final_weight():
    rm = RiskManager(RiskConfig(sizing="fixed", max_position=0.25))
    got = rm.size_positions(_df(0.01), pd.Series(2.0, index=IDX))
    assert abs(got.max() - 0.25) < 1e-12, f"최대 노출 한도가 안 걸린다: {got.max()}"


def test_the_max_position_clips_shorts_too():
    """부호만 다른 실수 — 롱만 막고 숏을 놓치면 반대로 터진다."""
    rm = RiskManager(RiskConfig(sizing="fixed", max_position=0.25))
    got = rm.size_positions(_df(0.01), pd.Series(-2.0, index=IDX))
    assert abs(got.min() + 0.25) < 1e-12, f"숏 한도가 안 걸린다: {got.min()}"


def test_a_target_inside_the_limit_is_untouched():
    """대조군 — 한도 안이면 그대로 통과해야 한다."""
    rm = RiskManager(RiskConfig(sizing="fixed", max_position=1.0))
    got = rm.size_positions(_df(0.01), pd.Series(0.4, index=IDX))
    assert abs(got.max() - 0.4) < 1e-12


# ── ③ 거래정지(변동성 0) 가드 ─────────────────────────────────


def test_a_frozen_price_gets_zero_exposure_not_maximum():
    """종가가 고정되면(거래정지) 변동성 0 → target/0 = +inf가 된다.

    가드가 없으면 clip이 그것을 **최대 레버리지**로 만든다 — 거래가 멎은
    종목에 최대로 싣는 정반대 결과다.
    """
    close = pd.Series(100.0, index=IDX)
    df = pd.DataFrame({"open": close, "high": close, "low": close,
                       "close": close, "volume": 0.0}, index=IDX)
    rm = RiskManager(RiskConfig(sizing="vol_target", max_position=10.0))
    got = rm.size_positions(df, pd.Series(1.0, index=IDX))
    assert float(got.abs().max()) == 0.0, f"거래정지 종목에 실렸다: {got.max()}"


# ── ④ 펀딩비 이상치 상한 ──────────────────────────────────────


def test_a_corrupt_funding_rate_is_clamped():
    """|rate| ≥ 1 이면 자본 부호가 뒤집힌다 — 소스 주석이 적어 둔 그 사고."""
    cap = CostModel._FUNDING_RATE_CAP
    ts = IDX[0]
    cm = CostModel(funding_series={ts: 12.5})     # 단위 오류(1250%)
    assert abs(cm.holding_cost(1.0, ts=ts)) <= cap + 1e-12, (
        "오염된 펀딩률이 그대로 비용에 들어간다")
    cm_neg = CostModel(funding_series={ts: -99.0})
    assert abs(cm_neg.holding_cost(1.0, ts=ts)) <= cap + 1e-12


def test_a_normal_funding_rate_passes_through():
    """대조군 — 정상 범위는 손대지 않는다(클램프가 덫이 되면 안 된다)."""
    ts = IDX[0]
    cm = CostModel(funding_series={ts: 0.0004})   # 8시간당 0.04%
    assert abs(cm.holding_cost(1.0, ts=ts) - 0.0004) < 1e-12


def test_a_non_finite_funding_rate_is_zero_not_nan():
    """NaN이 흘러들면 자본곡선 전체가 NaN이 된다 — 조용히 0으로."""
    ts = IDX[0]
    for bad in (float("nan"), float("inf"), float("-inf")):
        cm = CostModel(funding_series={ts: bad})
        assert cm.holding_cost(1.0, ts=ts) == 0.0, bad
