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


# ── 멈춘 시세가 최대 노출을 받지 않는가 (감사 209) ────────────────
#
# `size_positions`에는 이미 가드가 있었다: `realized > 1e-9`. 그 위 주석은
# 원리를 맞게 적어 놓았다 — *"연율 변동성이므로 크기를 안다"*. 그런데 문턱을
# **부동소수 잡음 크기**(1e-9)로 잡아서, 값이 정확히 0은 아니지만 사실상
# 멈춘 시세가 그대로 통과했다. 실측(고치기 전):
#
#     20봉 중 19봉의 수익률이 정확히 0 · 한 봉만 0.01% 움직임
#     → 연율 실현변동성 0.0022%  →  목표 비중 **1.0000 (100%)**
#     (같은 전략·정상 변동성 2.14%일 때는 0.6631)
#
# 거래정지·호가 고정·시세 피드가 마지막 값을 반복하는 날이 정확히 이 모양이고,
# **데이터 품질 검사도 이걸 안 잡는다**(실측: 위반 0건 · 심각도 False).
# 아무도 안 막고 있었다.
#
# 크기로 막으면 진짜 저변동성 자산(채권 ETF)까지 걸린다. 구별되는 것은 크기가
# 아니라 **움직임의 유무**다 — 창 안의 수익률이 대부분 정확히 0이면 그
# 변동성 추정치는 '작은 값'이 아니라 **없는 값**이다.


def _sized_curve(close, market="kr_stock", window=20, z=2.0):
    import numpy as np
    import pandas as pd

    from quant.live.daily import _risk_for
    from quant.strategies.mean_reversion import MeanReversion

    idx = pd.date_range("2025-01-01", periods=len(close), freq="D")
    df = pd.DataFrame({"open": close, "high": close * 1.001,
                       "low": close * 0.999, "close": close,
                       "volume": 1e6}, index=idx)
    sig = MeanReversion(window=window, z=z).generate_signals(df)
    on = np.flatnonzero(sig.to_numpy())
    w = _risk_for(market).size_positions(df, sig).to_numpy()
    return on, (max(abs(float(w[i])) for i in on) if len(on) else 0.0)


def test_a_frozen_price_gets_no_exposure():
    """거래정지처럼 값이 멈춘 종목이 최대 노출을 받으면 안 된다."""
    import numpy as np

    c = np.full(60, 100.0)
    c[45] = 99.99                       # 20봉 중 한 봉만 0.01% 움직인다
    on, biggest = _sized_curve(c)
    assert len(on) > 0, "전제가 깨졌다 — 신호가 나야 사이징을 잰다"
    assert biggest == 0.0, f"멈춘 시세에 노출 {biggest:.4f}이 실렸다"


def test_a_genuinely_calm_asset_is_not_punished():
    """대조군 — **진짜** 저변동성 자산(연 2~3%)은 계속 거래돼야 한다.

    크기로 막으면 채권 ETF 같은 정상 자산까지 꺼진다. 이 검사가 없으면
    위 검사는 "조금만 조용하면 다 끄는" 구현도 통과시킨다.
    """
    import numpy as np

    rng = np.random.default_rng(3)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.0015, 200)))
    on, biggest = _sized_curve(c)
    assert len(on) > 0 and biggest > 0.0, (
        f"진짜 저변동성 자산이 꺼졌다: 신호 {len(on)}봉 · 최대 {biggest}")


def test_a_normal_asset_is_unchanged():
    """대조군 — 평범한 변동성에서는 예전과 같은 사이징이어야 한다."""
    import numpy as np

    rng = np.random.default_rng(0)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, 200)))
    on, biggest = _sized_curve(c)
    assert len(on) > 0 and 0.0 < biggest <= 1.0, biggest


def test_the_rule_is_movement_not_size():
    """직접 확인 — 같은 변동성 크기라도 '움직였는가'로 갈린다.

    ① 창의 95%가 정확히 0        → 꺼진다
    ② 같은 표준편차인데 매 봉 움직인다 → 살아 있다
    """
    import numpy as np
    import pandas as pd

    from quant.live.daily import _risk_for

    n = 60
    frozen = np.full(n, 100.0)
    frozen[45] = 99.99
    moving = 100.0 + np.tile([0.0, 0.0025], n // 2)[:n]   # 매 봉 작게 움직임

    fs = float(pd.Series(frozen).pct_change().rolling(20).std().iloc[45])
    ms = float(pd.Series(moving).pct_change().rolling(20).std().iloc[45])
    assert fs > 0 and ms > 0, "전제가 깨졌다 — 둘 다 0이 아니어야 한다"

    def scale_at(c, i):
        idx = pd.date_range("2025-01-01", periods=len(c), freq="D")
        df = pd.DataFrame({"open": c, "high": c * 1.001, "low": c * 0.999,
                           "close": c, "volume": 1e6}, index=idx)
        target = pd.Series(1.0, index=idx)
        return float(_risk_for("kr_stock").size_positions(df, target).iloc[i])

    assert scale_at(frozen, 45) == 0.0, "멈춘 쪽이 안 꺼졌다"
    assert scale_at(moving, 45) > 0.0, "움직이는 쪽이 꺼졌다"


# ── 두 가드는 서로 다른 것을 막는다 (2026-08-13 변이 전수에서 드러남) ──


def _prices_from(returns):
    px = [100.0]
    for r in returns:
        px.append(px[-1] * (1 + r))
    return px


def test_a_price_that_moves_but_not_really_gets_zero_exposure():
    """**크기 가드**(realized > 1e-9)가 막는 자리 — 검사가 없어서 무방비였다.

    2026-08-13 야간 변이 전수가 이걸 잡았다: 크기 가드를 빼도 아무 검사도
    빨개지지 않았다. 이유는 기존 검사가 전부 **완전히 멈춘** 시세만 썼기
    때문이다 — 그 경우는 움직임 가드(zero_share ≥ 0.8)가 먼저 막으므로,
    크기 가드를 떼어내도 결과가 같아 보인다.

    두 가드는 서로 다른 것을 막는다.
        움직임 가드 : 창의 대부분이 **정확히 0**인 경우(거래정지·호가 고정)
        크기   가드 : 값은 있는데 **실질적으로 없는** 경우(마지막 자리 잡음)

    아래는 두 번째다 — 창의 47%만 0이라 움직임 가드를 통과하지만, 실현
    변동성이 1.4e-11이라 목표/변동성이 폭발한다. 실측:

        가드 있음 → 목표 비중 0.0000
        가드 없음 → 목표 비중 1.0000  (레버리지 상한 3배가 그대로 걸린다)
    """
    pattern = ([0.0, 0.0, 1e-12, -1e-12]) * 30
    close = _prices_from(pattern)
    idx = pd.date_range("2025-01-01", periods=len(close), freq="D")
    df = pd.DataFrame({"close": close}, index=idx)

    rets = df["close"].pct_change()
    zero_share = float((rets.fillna(0.0) == 0.0).rolling(30).mean().iloc[-1])
    realized = float((rets.rolling(30).std() * np.sqrt(365)).iloc[-1])
    # 전제 — 움직임 가드는 통과하고, 크기 가드만이 막을 수 있는 구간이다
    assert zero_share < 0.8, f"움직임 가드가 먼저 막는다(zero_share={zero_share})"
    assert 0 < realized <= 1e-9, f"크기 가드 구간이 아니다(realized={realized})"

    rm = RiskManager(RiskConfig(sizing="vol_target", vol_window=30,
                                periods_per_year=365))
    sized = rm.size_positions(df, pd.Series(1.0, index=idx))
    assert float(sized.iloc[-1]) == 0.0, (
        f"실질적으로 안 움직인 종목에 비중 {float(sized.iloc[-1]):.4f}를 준다 "
        "— 변동성 폭발 직전에 최대 노출이 되는 정반대 결과다")


def test_a_genuinely_quiet_asset_still_gets_exposure():
    """대조군 — 진짜 저변동성 자산(채권 ETF 같은)까지 끄면 안 된다.

    ⚠️ 이 대조군이 없으면 "변동성이 작으면 무조건 0"으로 고쳐도 위 검사가
       통과한다. 구별하는 것은 **크기가 아니라 움직임의 유무**다.
    """
    pattern = [0.0004, -0.0003, 0.0002, -0.0002] * 30      # 매 봉 실제로 움직임
    close = _prices_from(pattern)
    idx = pd.date_range("2025-01-01", periods=len(close), freq="D")
    df = pd.DataFrame({"close": close}, index=idx)

    rm = RiskManager(RiskConfig(sizing="vol_target", vol_window=30,
                                periods_per_year=365))
    sized = rm.size_positions(df, pd.Series(1.0, index=idx))
    assert float(sized.iloc[-1]) > 0.0, "조용하지만 살아 있는 자산을 껐다"
