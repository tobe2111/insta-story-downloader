"""시장 레짐 분류기 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.data import SyntheticDataProvider
from quant.robustness import classify_regime, regime_feature, regime_summary


def _df(prices):
    idx = pd.date_range("2020-01-01", periods=len(prices), freq="D")
    return pd.DataFrame({"open": prices, "high": prices, "low": prices,
                         "close": prices, "volume": 1.0}, index=idx)


def test_trend_labels_bull_and_bear():
    """상승 추세 후반은 bull, 하락 추세 후반은 bear로 라벨링된다."""
    up = list(np.linspace(100, 200, 120))
    down = list(np.linspace(200, 100, 120))
    reg = classify_regime(_df(up + down), trend_window=50)
    # 상승 구간 끝 무렵은 강세, 하락 구간 끝 무렵은 약세
    assert reg["trend"].iloc[110] == "bull"
    assert reg["trend"].iloc[-1] == "bear"


def test_regime_columns_and_values():
    df = SyntheticDataProvider(seed=9).get_ohlcv("R", "1d", limit=500)
    reg = classify_regime(df)
    assert list(reg.columns) == ["trend", "vol", "regime"]
    assert set(reg["trend"].unique()) <= {"bull", "bear", "unknown"}
    assert set(reg["vol"].unique()) <= {"high", "low", "unknown"}


def test_regime_no_lookahead():
    """미래를 잘라도 과거 국면 라벨이 바뀌지 않는다(과거 정보만 사용)."""
    df = SyntheticDataProvider(seed=4).get_ohlcv("R", "1d", limit=420)
    cut = 320
    full = classify_regime(df)["regime"].iloc[:cut - 1].tolist()
    trunc = classify_regime(df.iloc[:cut])["regime"].iloc[:cut - 1].tolist()
    assert full == trunc, "레짐 분류가 미래 데이터를 참조함"


def test_regime_summary_sums_to_one():
    df = SyntheticDataProvider(seed=2).get_ohlcv("R", "1d", limit=500)
    s = regime_summary(df)
    assert abs(sum(s.values()) - 1.0) < 1e-9


def test_regime_feature_bounded():
    """레짐 피처는 0~1 범위이고 df 인덱스를 보존한다."""
    df = SyntheticDataProvider(seed=7).get_ohlcv("R", "1d", limit=300)
    feat = regime_feature(df)
    assert list(feat.columns) == ["trend_up", "vol_high"]
    assert feat.index.equals(df.index)
    assert (feat >= 0.0).all().all() and (feat <= 1.0).all().all()


# ── 두 필터가 '모름'을 같은 쪽으로 처리하는가 (감사 206) ──────────
#
# 같은 클래스 안에서 정반대였다:
#   추세 (MA=NaN)  → `| ma.isna()`로 **막는다**(주석에도 "데이터 부족 구간도
#                    진입 보류"라고 적혀 있다)
#   변동성 (vol=NaN) → `vol > 한도` 하나뿐이라 **통과**(NaN 비교는 전부 False)
#
# 실측(추세 필터를 끄고 변동성 필터만, 한도 0.5% · 실제 1.0%):
#     판정 불가(워밍업 20봉) → 신호 살아 있음 20/20
#     판정 가능 구간          → 신호 살아 있음  0/220
# **판정을 못 하는 구간에만 매매가 열려 있었다.**
#
# 기본 설정(use_trend=True)에서는 추세 워밍업이 변동성 워밍업을 덮어 새지
# 않는다 — 추세 필터를 끄는 순간 조용히 열린다(감사 204와 같은 형태:
# 설정을 바꿀 수 있게 만들어 놓고 기본값에만 맞춰 둔 코드).


def _trending(n=240, seed=1):
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0.002, 0.01, n)))
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    return pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99,
                         "close": c, "volume": 1e6}, index=idx)


class _AlwaysLong:
    name = "always"
    allow_short = False

    def generate_signals(self, d):
        import pandas as pd
        return pd.Series(1.0, index=d.index)


def test_the_vol_filter_blocks_while_it_cannot_judge():
    from quant.strategies.regime import RegimeFilter

    df = _trending()
    vol = df["close"].pct_change().rolling(20).std()
    assert int(vol.isna().sum()) == 20, "전제가 깨졌다 — 워밍업 구간이 없다"

    f = RegimeFilter(_AlwaysLong(), use_trend=False, vol_window=20,
                     max_daily_vol=0.005)          # 실제 변동성보다 낮은 한도
    sig = f.generate_signals(df)
    assert int((sig[vol.isna()] != 0).sum()) == 0, (
        "변동성을 판정 못 하는 구간에 매매가 열려 있다")
    assert int((sig[~vol.isna()] != 0).sum()) == 0, "전제가 깨졌다"


def test_a_generous_limit_still_lets_trading_through():
    """대조군 — 판정 가능 구간에서는 한도가 넉넉하면 열려야 한다.

    이게 없으면 위 검사는 "무엇이든 막는" 구현도 통과시키고, 그러면 변동성
    필터를 켜는 순간 매매가 통째로 멈춘다.
    """
    from quant.strategies.regime import RegimeFilter

    df = _trending()
    vol = df["close"].pct_change().rolling(20).std()
    f = RegimeFilter(_AlwaysLong(), use_trend=False, vol_window=20,
                     max_daily_vol=0.99)
    sig = f.generate_signals(df)
    assert int((sig[~vol.isna()] != 0).sum()) == int((~vol.isna()).sum())
    # 그래도 판정 불가 구간은 여전히 막혀야 한다
    assert int((sig[vol.isna()] != 0).sum()) == 0


def test_the_ledger_says_it_could_not_judge_the_volatility():
    """'필터 없음'이라고 적으면 안 된다 — 필터는 켜져 있었다."""
    from quant.strategies.regime import RegimeFilter

    f = RegimeFilter(_AlwaysLong(), use_trend=False, vol_window=20,
                     max_daily_vol=0.005)
    f.generate_signals(_trending(n=10))            # 20봉이 안 된다
    gate = f.last_gate_
    assert gate and gate["open"] is False, gate
    assert gate.get("kind") == "vol_unknown", gate
    assert "10봉" in gate["reason"] and "보류" in gate["reason"], gate


def test_both_filters_treat_unknown_the_same_way():
    """㉞ — 같은 파일 안의 두 판정이 '모름'에서 갈라지면 안 된다."""
    from quant.strategies.regime import RegimeFilter

    short = _trending(n=10)
    trend_only = RegimeFilter(_AlwaysLong(), use_trend=True, trend_window=200)
    vol_only = RegimeFilter(_AlwaysLong(), use_trend=False, vol_window=20,
                            max_daily_vol=0.005)
    a = trend_only.generate_signals(short)
    b = vol_only.generate_signals(short)
    assert int((a != 0).sum()) == 0 and int((b != 0).sum()) == 0, (
        f"판정 불가에서 두 필터의 답이 다르다: 추세 {int((a != 0).sum())}봉 · "
        f"변동성 {int((b != 0).sum())}봉")
