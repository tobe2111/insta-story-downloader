"""봉 내(intrabar) 스톱 체결 + 시장별 비용 프리셋 테스트.

종가 판정 스톱은 봉 중간에 스톱선을 관통했다가 종가가 회복하면 스톱을 놓쳐
손실을 과소평가한다. 봉 내 판정은 그 관통 자체를 체결로 처리한다(더 정직).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.backtest import Backtester
from quant.backtest.costs import MARKET_COST_PRESETS, CostModel
from quant.risk import RiskConfig, RiskManager
from quant.strategies.base import Strategy


class _AlwaysLong(Strategy):
    name = "always"
    allow_short = False

    def generate_signals(self, df):
        return pd.Series(1.0, index=df.index)


def _risk(stop_loss=0.10, take_profit=None):
    return RiskManager(RiskConfig(stop_loss=stop_loss, take_profit=take_profit,
                                  trailing_stop=None, sizing="fixed"))


def _df(rows):
    """rows: (open, high, low, close) 목록 → OHLCV 프레임."""
    idx = pd.date_range("2020-01-01", periods=len(rows), freq="D")
    o, h, l, c = zip(*rows)
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c,
                         "volume": 1.0}, index=idx)


def test_intrabar_catches_wick_through_stop():
    """봉 중간 -12% 관통 후 종가 회복: 종가 판정은 스톱을 놓치고,
    봉 내 판정은 스톱 가격(-10%)에 체결한다."""
    d = _df([
        (100, 101, 99, 100),      # 진입 봉 (종가 100에서 롱)
        (100, 101, 99, 100),
        (100, 100, 88, 99),       # 저가 88 = -12% 관통, 종가 99 회복
        (99, 100, 98, 99),
    ])
    close_based = Backtester(_AlwaysLong(), risk=_risk(0.10), fee=0.0,
                             slippage=0.0).run(d)
    intrabar = Backtester(_AlwaysLong(), risk=_risk(0.10), fee=0.0,
                          slippage=0.0, intrabar_stops=True).run(d)
    # 종가 판정: pnl 종가 기준 -1% → 스톱 미발동, 포지션 유지
    assert close_based.positions.iloc[2] != 0.0
    # 봉 내 판정: 스톱 발동 → 그 봉 종가 시점 포지션 0
    assert intrabar.positions.iloc[2] == 0.0
    # 체결가는 스톱 가격(90): 자본 = 10000 × 90/100 = 9000 (그 봉에서)
    assert abs(intrabar.equity.iloc[2] - 9_000.0) < 1e-6
    # 종가 판정은 -1%만 반영 → 봉 내 판정이 손실을 더 정직하게(크게) 기록
    assert intrabar.equity.iloc[2] < close_based.equity.iloc[2]


def test_intrabar_gap_down_fills_at_open():
    """시가가 이미 스톱 아래(갭 하락)면 스톱 가격이 아니라 시가(더 불리)에 체결."""
    d = _df([
        (100, 101, 99, 100),      # 진입
        (85, 86, 84, 85),         # 시가 85 < 스톱 90 → 85 체결
        (85, 86, 84, 85),
    ])
    res = Backtester(_AlwaysLong(), risk=_risk(0.10), fee=0.0,
                     slippage=0.0, intrabar_stops=True).run(d)
    assert abs(res.equity.iloc[1] - 8_500.0) < 1e-6   # 90이 아니라 85


def test_intrabar_take_profit_fills_at_target():
    """익절은 목표가에 정확히 체결(갭 상승 이익 미반영 — 보수적)."""
    d = _df([
        (100, 101, 99, 100),      # 진입
        (100, 125, 99, 110),      # 고가 125 → 익절 +15% 관통, 목표 115 체결
        (110, 111, 109, 110),
    ])
    res = Backtester(_AlwaysLong(), risk=_risk(stop_loss=None, take_profit=0.15),
                     fee=0.0, slippage=0.0, intrabar_stops=True).run(d)
    assert res.positions.iloc[1] == 0.0
    assert abs(res.equity.iloc[1] - 11_500.0) < 1e-6  # 125가 아니라 115


def test_intrabar_stop_loss_wins_ambiguous_bar():
    """같은 봉에서 손절·익절 모두 관통하면 순서 불명 → 손절 우선(보수적)."""
    d = _df([
        (100, 101, 99, 100),
        (100, 130, 85, 100),      # 저가 85(-15% 관통), 고가 130(+15% 관통)
        (100, 101, 99, 100),
    ])
    res = Backtester(_AlwaysLong(), risk=_risk(stop_loss=0.10, take_profit=0.15),
                     fee=0.0, slippage=0.0, intrabar_stops=True).run(d)
    assert abs(res.equity.iloc[1] - 9_000.0) < 1e-6   # 익절(11500)이 아니라 손절


def test_intrabar_off_is_bit_identical():
    """intrabar_stops=False(기본)는 기존 결과와 비트 단위로 동일하다."""
    from quant.data import SyntheticDataProvider

    d = SyntheticDataProvider(seed=8).get_ohlcv("IB", "1d", limit=300)
    a = Backtester(_AlwaysLong(), risk=_risk(0.10)).run(d)
    b = Backtester(_AlwaysLong(), risk=_risk(0.10), intrabar_stops=False).run(d)
    assert (a.equity.to_numpy() == b.equity.to_numpy()).all()


def test_intrabar_respects_cooldown():
    """봉 내 스톱도 쿨다운을 발동시킨다(같은 봉·직후 봉 재진입 금지)."""
    d = _df([
        (100, 101, 99, 100),
        (100, 100, 88, 99),       # 봉 내 스톱
        (99, 100, 98, 99),
        (99, 100, 98, 99),
    ])
    res = Backtester(_AlwaysLong(), risk=_risk(0.10), fee=0.0, slippage=0.0,
                     intrabar_stops=True, stop_cooldown=2).run(d)
    assert (res.positions.iloc[1:4] == 0.0).all()     # 스톱 봉 + 쿨다운 2봉


def test_intrabar_short_symmetric():
    """숏 손절: 고가가 스톱선(진입가+10%) 관통 시 체결."""
    class AlwaysShort(Strategy):
        name = "short"
        allow_short = True

        def generate_signals(self, df):
            return pd.Series(-1.0, index=df.index)

    d = _df([
        (100, 101, 99, 100),      # 숏 진입
        (100, 113, 99, 101),      # 고가 113 = +13% 관통 → 스톱 110 체결
        (101, 102, 100, 101),
    ])
    res = Backtester(AlwaysShort(), risk=_risk(0.10), fee=0.0,
                     slippage=0.0, intrabar_stops=True).run(d)
    assert res.positions.iloc[1] == 0.0
    # 숏 -1 × (110/100 - 1) = -10% → 자본 9000
    assert abs(res.equity.iloc[1] - 9_000.0) < 1e-6


# ── 시장별 비용 프리셋 ───────────────────────────────────────────────────────

def test_market_presets_exist_and_ordered():
    for m in ("crypto", "crypto_upbit", "us_stock", "kr_stock", "synthetic"):
        assert m in MARKET_COST_PRESETS
    kr = CostModel.for_market("kr_stock")
    us = CostModel.for_market("us_stock")
    up = CostModel.for_market("crypto_upbit")
    # 프리셋의 핵심 사실: 한국주식은 거래세 때문에 '수수료 무료 시대'에도
    # 미국주식·업비트보다 왕복 비용이 비싸고, 위탁수수료(0.015%)만 넣은
    # 순진한 백테스트 대비 실비용이 수 배다.
    assert (kr.fee + kr.slippage) > (us.fee + us.slippage) * 1.5
    assert (kr.fee + kr.slippage) > (up.fee + up.slippage)
    assert kr.fee > 0.00015 * 4          # 세금이 위탁수수료를 압도


def test_for_market_unknown_uses_defaults_and_overrides():
    cm = CostModel.for_market("no_such_market")
    assert cm.fee == 0.001 and cm.slippage == 0.0005   # dataclass 기본값
    cm2 = CostModel.for_market("crypto", fee=0.0002)
    assert cm2.fee == 0.0002 and cm2.slippage == 0.0005  # override 우선
