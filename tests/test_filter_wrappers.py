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


# ── 설명이 실제 행동과 어긋나지 않는다 (감사 69) ──────────────


def _regime_case(n, tw, drift, vol=None):
    import numpy as np
    import pandas as pd

    from quant.live.explain import explain_signal
    from quant.live.retrain import build_strategy

    close = 100 * np.exp(np.cumsum(
        np.random.default_rng(1).normal(drift, 0.01, n)))
    df = pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99,
                       "close": close, "volume": 1e6},
                      index=pd.date_range("2025-01-01", periods=n, freq="D"))
    params = {"inner": {"strategy": "ma_cross", "params": {"fast": 5, "slow": 20}},
              "trend_window": tw}
    if vol is not None:
        params["max_daily_vol"] = vol
    spec = {"strategy": "regime_wrap", "params": params}
    strat = build_strategy(spec)
    w = float(strat.generate_signals(df).iloc[-1])
    return w, explain_signal(spec, df, w, strategy=strat)


def test_explanation_never_says_allowed_while_the_filter_blocks():
    """사이트·SNS에 나가는 '왜 이 비중인가'가 실제 행동과 반대면 안 된다.

    설명문이 레짐 조건을 **다시 계산**하고 있었고, 그 재계산이 필터와
    어긋났다(감사 69):

      · MA가 NaN(데이터 부족) → 필터는 '진입 보류'로 막는데, 설명의
        `px < ma`는 NaN 비교가 False라 "200일선 위(매매 허용)"이라고
        **정반대**로 말했다.
      · 변동성 한도 초과로 막힌 날 → 설명은 변동성 필터를 아예 언급하지
        않아 역시 "매매 허용"이라고 말했다.

    같은 규칙을 두 곳에 적으면 어긋난다. 이제 판단한 쪽이 결과를 남기고
    (RegimeFilter.last_gate_) 설명은 읽기만 한다.
    """
    cases = [
        ("MA 미정(데이터 부족)", dict(n=60, tw=200, drift=-0.002)),
        ("약세장", dict(n=400, tw=200, drift=-0.003)),
        ("강세장", dict(n=400, tw=200, drift=+0.003)),
        ("변동성 한도 초과", dict(n=400, tw=200, drift=+0.003, vol=0.001)),
    ]
    for label, kw in cases:
        w, txt = _regime_case(**kw)
        blocked = abs(w) < 1e-9
        says_allowed = "매매 허용" in txt
        if blocked:
            assert not says_allowed, (
                f"[{label}] 비중 0인데 설명은 '매매 허용'이라 말한다:\n{txt}")
        else:
            assert says_allowed, (
                f"[{label}] 매매했는데 설명은 막혔다고 말한다:\n{txt}")


def test_regime_filter_records_why_it_decided():
    """설명이 읽을 수 있도록 필터가 판단 근거를 남기는가."""
    from quant.live.retrain import build_strategy
    import numpy as np
    import pandas as pd

    close = 100 * np.exp(np.cumsum(
        np.random.default_rng(2).normal(-0.003, 0.01, 400)))
    df = pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99,
                       "close": close, "volume": 1e6},
                      index=pd.date_range("2025-01-01", periods=400, freq="D"))
    s = build_strategy({"strategy": "regime_wrap", "params": {
        "inner": {"strategy": "ma_cross", "params": {}}, "trend_window": 200}})
    assert s.last_gate_ is None, "실행 전인데 판단 흔적이 있다"
    s.generate_signals(df)
    assert isinstance(s.last_gate_, dict)
    assert "open" in s.last_gate_ and "reason" in s.last_gate_


def test_explanation_works_before_the_strategy_has_run():
    """실행 전에 미리 설명을 보는 경로도 죽지 않는다(폴백)."""
    w, txt = _regime_case(n=60, tw=200, drift=-0.002)
    from quant.live.explain import explain_signal
    import numpy as np
    import pandas as pd
    close = 100 * np.ones(60)
    df = pd.DataFrame({"open": close, "high": close, "low": close,
                       "close": close, "volume": 1e6},
                      index=pd.date_range("2025-01-01", periods=60, freq="D"))
    spec = {"strategy": "regime_wrap", "params": {
        "inner": {"strategy": "ma_cross", "params": {}}, "trend_window": 200}}
    out = explain_signal(spec, df, 0.0, strategy=None)   # strategy 없음
    assert "레짐 필터" in out and "판정 보류" in out
