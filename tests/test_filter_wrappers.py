"""필터 래퍼(Liquidity·MTF·ADX·Regime) 엣지케이스 테스트.

감사에서 지적된 커버리지 공백을 메운다: 각 래퍼의 (1) 게이팅 방향 정확성,
(2) 워밍업/결측 처리, (3) 통과(passthrough) 조건, (4) 미래 참조 부재.
필터는 등록 전략이 아니라 test_leakage의 자동 순회에 안 잡히므로 여기서
절단 불변성(truncation invariance)을 직접 검증한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.data import SyntheticDataProvider
from quant.strategies import (
    ADXFilter,
    LiquidityFilter,
    MultiTimeframeFilter,
    RegimeFilter,
    get_strategy,
)

_DF = SyntheticDataProvider(seed=33).get_ohlcv("FLT", "1d", limit=420)
_CUT = 320


def _assert_truncation_invariant(make, name: str, buffer: int = 10):
    """미래를 잘라도 겹치는 과거 신호가 동일해야 한다(룩어헤드 없음)."""
    full = make().generate_signals(_DF)
    trunc = make().generate_signals(_DF.iloc[:_CUT])
    a = full.iloc[: _CUT - buffer].to_numpy()
    b = trunc.iloc[: _CUT - buffer].to_numpy()
    assert np.allclose(a, b, atol=1e-9), f"{name} 필터가 미래를 참조함"


# ── 룩어헤드 (필터는 test_leakage 자동 순회 밖) ─────────────────────────────

def test_liquidity_no_lookahead():
    _assert_truncation_invariant(
        lambda: LiquidityFilter(get_strategy("momentum"), min_dollar_vol=1.0),
        "liquidity")


def test_adx_no_lookahead():
    _assert_truncation_invariant(
        lambda: ADXFilter(get_strategy("momentum"), min_adx=20.0), "adx")


def test_regime_no_lookahead():
    _assert_truncation_invariant(
        lambda: RegimeFilter(get_strategy("momentum"), trend_window=100,
                             max_daily_vol=0.03), "regime")


# ── LiquidityFilter 엣지 ─────────────────────────────────────────────────────

def test_liquidity_warmup_blocks_entry():
    """워밍업(롤링 거래대금 NaN) 구간은 진입 보류(0)여야 한다."""
    liq = LiquidityFilter(get_strategy("momentum"), window=30, min_dollar_vol=1.0)
    sig = liq.generate_signals(_DF)
    assert (sig.iloc[:29] == 0).all()          # 롤링 30봉 완성 전 전부 관망


def test_liquidity_missing_volume_column_passthrough():
    """volume 컬럼이 없으면(일부 데이터 소스) 게이팅 없이 통과한다 — 크래시 금지."""
    d = _DF.drop(columns=["volume"])
    base = get_strategy("momentum").generate_signals(d)
    sig = LiquidityFilter(get_strategy("momentum"),
                          min_dollar_vol=1e9).generate_signals(d)
    assert np.allclose(base.to_numpy(), sig.to_numpy(), atol=1e-12)


def test_liquidity_preserves_short_signals():
    """게이팅은 크기만 죽이고 방향(숏 포함)을 뒤집지 않는다."""
    base = get_strategy("momentum", allow_short=True)
    liq = LiquidityFilter(get_strategy("momentum", allow_short=True),
                          min_dollar_vol=1.0)
    b = base.generate_signals(_DF)
    m = liq.generate_signals(_DF)
    active = (m != 0)
    assert ((np.sign(m[active]) == np.sign(b[active]))).all()


# ── MultiTimeframeFilter 엣지 ────────────────────────────────────────────────

def test_mtf_blocks_shorts_in_uptrend_and_longs_in_downtrend():
    """상위 추세 상승이면 숏 금지, 하락이면 롱 금지 — 방향별 게이팅 정확성."""
    mtf = MultiTimeframeFilter(get_strategy("momentum", allow_short=True),
                               htf="W", trend_window=8)
    sig = mtf.generate_signals(_DF)
    up = mtf._htf_uptrend(_DF["close"])
    assert ((sig > 0) & (up <= 0.0)).sum() == 0    # 하락 상위추세에 롱 없음
    assert ((sig < 0) & (up >= 1.0)).sum() == 0    # 상승 상위추세에 숏 없음


def test_mtf_short_data_no_crash():
    """상위봉이 trend_window보다 적어도(짧은 데이터) 크래시 없이 관망한다."""
    short = _DF.iloc[:30]                          # 주봉 4~5개 < trend_window 8
    sig = MultiTimeframeFilter(get_strategy("momentum"), htf="W",
                               trend_window=8).generate_signals(short)
    assert sig.index.equals(short.index)
    assert (sig == 0).all()                        # 상위 MA 미완성 → 전부 보류


# ── ADXFilter 엣지 ───────────────────────────────────────────────────────────

def test_adx_zero_threshold_is_passthrough():
    """min_adx=0 이면 base 신호를 그대로 통과시킨다(ADX>=0 항상 참)."""
    base = get_strategy("momentum").generate_signals(_DF)
    sig = ADXFilter(get_strategy("momentum"), min_adx=0.0).generate_signals(_DF)
    assert np.allclose(base.to_numpy(), sig.to_numpy(), atol=1e-12)


def test_adx_flat_market_fully_gated():
    """방향성 없는 완전 횡보(고저 동일)에서는 ADX=0 → 전부 관망."""
    n = 120
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    flat = pd.DataFrame({"open": 100.0, "high": 100.0, "low": 100.0,
                         "close": 100.0, "volume": 1.0}, index=idx)

    class AlwaysLong:
        name = "long"
        allow_short = False

        def generate_signals(self, x):
            return pd.Series(1.0, index=x.index)

    sig = ADXFilter(AlwaysLong(), min_adx=25.0).generate_signals(flat)
    assert (sig == 0).all()


# ── RegimeFilter 엣지 ────────────────────────────────────────────────────────

def test_regime_all_off_is_passthrough():
    """use_trend=False + max_daily_vol=None 이면 base 그대로 통과한다."""
    base = get_strategy("momentum").generate_signals(_DF)
    sig = RegimeFilter(get_strategy("momentum"), use_trend=False,
                       max_daily_vol=None).generate_signals(_DF)
    assert np.allclose(base.to_numpy(), sig.to_numpy(), atol=1e-12)


def test_regime_vol_filter_blocks_panic_bars():
    """변동성 필터: 임계 초과 봉에서는 신호가 0이 된다."""
    flt = RegimeFilter(get_strategy("momentum"), use_trend=False,
                       vol_window=20, max_daily_vol=0.0)   # 임계 0 → 전부 초과
    sig = flt.generate_signals(_DF)
    vol = _DF["close"].pct_change().rolling(20).std()
    assert (sig[vol > 0.0] == 0).all()


def test_regime_gates_shorts_too():
    """약세장 회피는 롱뿐 아니라 숏 신호도 관망시킨다(문서화된 의도)."""
    n = 250
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    price = pd.Series(np.linspace(200.0, 100.0, n), index=idx)   # 지속 하락
    d = pd.DataFrame({"open": price, "high": price * 1.01,
                      "low": price * 0.99, "close": price, "volume": 1.0},
                     index=idx)

    class AlwaysShort:
        name = "short"
        allow_short = True

        def generate_signals(self, x):
            return pd.Series(-1.0, index=x.index)

    sig = RegimeFilter(AlwaysShort(), trend_window=50,
                       use_trend=True).generate_signals(d)
    # 장기MA 아래 구간에서는 숏조차 0(현금) — '회피'이지 '수익화'가 아니다
    ma = d["close"].rolling(50).mean()
    below = d["close"] < ma
    assert (sig[below] == 0).all()
