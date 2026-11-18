"""감사 384 — 하락장 자산(인버스 ETF · 매니지드 퓨처스)을 **후보로** 세운다.

사장님(2026-11-17): "거시적으로 손실 상황에서도 이익을 내는 것이 진정한 실력이야."

지키는 것:
1. 'hedge' 후보는 내림장에서 인버스 ETF를 **저절로** 담고 돈을 번다(규칙을 손으로
   쓰지 않는다 — 추세 엔진이 인버스 ETF의 추세를 양수로 볼 뿐이다).
2. 기존 후보(40종목·넓은 목록)는 하락장 자산을 **안 본다** — 보면 이미 잰 후보가
   이름만 같고 다른 것이 된다. 생존 편향 점검(core_keys 없음)에서도 마찬가지다.
3. 매일 배치가 그 종목들의 시세를 받는다(엔진 전용 목록에 들어 있다).
4. 선물 선택기에 양방향 후보가 선다.
"""
import numpy as np
import pandas as pd

from quant.portfolio import engine_select as E
from quant.portfolio import trend_core as T

SPY = "us_stock:SPY"
IEF = "us_stock:IEF"
SH = "us_stock:SH"
CORE = (SPY, IEF)


def _bear_market(n=700):
    """첫 400일 오르고 나머지 300일 꾸준히 빠지는 시장. SH는 SPY의 −1배."""
    idx = pd.bdate_range("2015-01-01", periods=n)
    rng = np.random.default_rng(7)
    drift = np.where(np.arange(n) < 400, 0.0008, -0.0015)
    r_spy = drift + rng.normal(0, 0.008, n)
    r_ief = 0.0001 + rng.normal(0, 0.003, n)
    spy = 100 * np.cumprod(1 + r_spy)
    ief = 100 * np.cumprod(1 + r_ief)
    sh = 100 * np.cumprod(1 - r_spy)
    return pd.DataFrame({SPY: spy, IEF: ief, SH: sh}, index=idx)


def test_hedge_candidate_buys_the_inverse_etf_and_earns_in_a_falling_market():
    closes = _bear_market()
    tgt, cfg = E.candidate_targets(closes, "risk12h", core_keys=CORE)
    late = tgt.iloc[-60:]
    assert late[SH].mean() > 0.05, "내림장에서 인버스 ETF를 담아야 한다"
    # 추세는 최장 1년을 보므로 내림 초기에는 지수를 잠시 더 든다 — 끝에서 본다.
    assert (tgt[SPY].iloc[-20:] == 0).all(), "내리는 지수는 안 담는다"
    res = T.simulate(closes, {}, cfg, targets=tgt)
    bear = res.equity.iloc[450:]
    assert bear.iloc[-1] > bear.iloc[0], "하락 구간에서 이익을 내야 한다"

    base_tgt, base_cfg = E.candidate_targets(closes, "risk12", core_keys=CORE)
    base = T.simulate(closes, {}, base_cfg, targets=base_tgt).equity.iloc[450:]
    assert bear.iloc[-1] / bear.iloc[0] > base.iloc[-1] / base.iloc[0]


def test_existing_candidates_never_see_bear_market_assets():
    closes = _bear_market()
    for name in E.CANDIDATES:
        if E.universe_of(name) == "hedge" or E.CANDIDATES[name]["kind"] == "ml":
            continue
        for keys in (CORE, None):          # 실계좌 규칙 · 생존 편향 점검
            tgt, _ = E.candidate_targets(closes, name, core_keys=keys)
            assert (tgt[SH] == 0).all(), f"{name}이(가) 하락장 자산을 봤다"


def test_daily_batch_fetches_the_bear_market_assets():
    extra = E.wide_extra_keys(CORE)
    for t in T.HEDGE_ETFS:
        assert f"us_stock:{t}" in extra
    assert len(extra) == len(set(extra))


def test_only_minus_one_x_inverse_and_managed_futures():
    # 2·3배 레버리지 인버스는 매일 재조정 손실이 커서 넣지 않는다.
    leveraged = {"SDS", "QID", "SPXU", "SQQQ", "TZA", "SH2", "TMV", "TBT"}
    assert not leveraged & set(T.HEDGE_ETFS)
    assert set(T.HEDGE_ETFS.values()) <= {"short", "alt"}


def test_every_new_candidate_has_a_label_and_is_counted():
    from scripts.managed_futures_research import TRIAL_LEDGER
    counted = set(sum(TRIAL_LEDGER.values(), []))
    for n in ("risk12h", "notional50h", "xs12h"):
        assert n in E.LABELS and n in counted
    assert "fut_ls20" in E.FUT_CANDIDATES and "fut_ls20" in E.FUT_LABELS
    assert E.fut_config("fut_ls20").allow_short
