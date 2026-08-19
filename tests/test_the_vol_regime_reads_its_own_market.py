"""변동성 국면 필터 — 문턱은 그 시장 자신의 과거에서 나온다 (2026-08-19).

절대 한도(max_daily_vol)는 코인(일 3~5%)과 주식(일 1%)의 체급이 달라
한 값으로 이식이 안 된다. 분위수 문턱은 어느 시장에 씌워도 "평소보다
유난히 흔들리는 구간"이라는 같은 뜻이 된다.

지켜야 할 약속:
- 평온한 시장에서는 기본 전략을 그대로 통과시킨다.
- 급변 구간(자기 과거 상위 분위수 초과)에서는 관망시킨다.
- 수익률 전체를 10배 해도 판정이 같다(체급 무관 — 이식성의 정의).
- '모름'(워밍업)은 보류다 — NaN 통과는 감사 206이 잡은 바로 그 구멍이다.
- 미래 봉이 과거 판정을 바꾸지 않는다(문턱 창은 전부 과거).
- 링에 실제로 서 있다(채택은 오디션이 결정한다).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.strategies import RegimeFilter                # noqa: E402
from quant.strategies.base import Strategy               # noqa: E402


class _Always(Strategy):
    name = "always"

    def generate_signals(self, df):
        return self._finalize(pd.Series(1.0, index=df.index), df.index)


def _df(rets: np.ndarray) -> pd.DataFrame:
    close = 100.0 * np.cumprod(1.0 + rets)
    idx = pd.date_range("2024-01-01", periods=len(rets), freq="D")
    return pd.DataFrame({"open": close, "high": close * 1.01,
                         "low": close * 0.99, "close": close,
                         "volume": np.full(len(rets), 1e6)}, index=idx)


def _spiky(scale: float = 1.0, n: int = 700, spike_at: int = 500,
           spike_len: int = 30) -> np.ndarray:
    rng = np.random.RandomState(7)
    r = rng.normal(0.0, 0.01, n)
    r[spike_at:spike_at + spike_len] = rng.normal(0.0, 0.06, spike_len)
    return r * scale


def _wrap():
    return RegimeFilter(_Always(), use_trend=False, vol_quantile=0.9)


def test_calm_markets_pass_through():
    rng = np.random.RandomState(3)
    sig = _wrap().generate_signals(_df(rng.normal(0.0, 0.01, 700)))
    tail = sig.iloc[400:]
    assert tail.mean() > 0.8, (
        f"평온한 시장에서 {1 - tail.mean():.0%}를 관망한다 — 필터가 아니라 "
        "차단기다(상위 10% 문턱이면 평시 개방률이 높아야 한다)")


def test_a_panic_regime_is_sat_out():
    sig = _wrap().generate_signals(_df(_spiky()))
    in_spike = sig.iloc[505:530]
    assert in_spike.mean() < 0.2, (
        f"6배 변동성 구간에서 {in_spike.mean():.0%}나 들고 있다")
    after = sig.iloc[600:]
    assert after.mean() > 0.5, "급변이 끝났는데 영영 닫혀 있다"


def test_the_verdict_is_scale_invariant():
    """수익률 전체 ×10 — 절대 한도라면 판정이 뒤집히고, 분위수면 같다."""
    a = _wrap().generate_signals(_df(_spiky(1.0))).to_numpy()
    b = _wrap().generate_signals(_df(_spiky(10.0))).to_numpy()
    assert (a == b).all(), (
        "시장 체급을 10배 했더니 판정이 달라졌다 — 문턱이 그 시장 자신의 "
        "과거에서 나오지 않는다는 뜻이다")


def test_unknown_is_held_not_passed():
    """워밍업(문턱 미정) 구간은 보류 — 감사 206의 규칙 그대로."""
    rng = np.random.RandomState(5)
    sig = _wrap().generate_signals(_df(rng.normal(0.0, 0.01, 700)))
    warmup = sig.iloc[:120]                       # 분위수 창(최소 126) 미달 구간
    assert float(warmup.abs().max()) == 0.0, (
        "판정을 못 하는 구간에 매매가 열려 있다 — NaN 통과(감사 206 재발)")


def test_the_future_cannot_change_the_past():
    r = _spiky()
    base = _wrap().generate_signals(_df(r)).iloc[:480]
    r2 = r.copy()
    r2[520:] *= 5.0                               # 미래를 뒤흔든다
    spiked = _wrap().generate_signals(_df(r2)).iloc[:480]
    assert (base == spiked).all(), "미래 봉이 과거 판정을 바꿨다 — 룩어헤드"


def test_the_variant_stands_in_the_ring():
    from quant.live.retrain import build_challengers
    ring = build_challengers({"strategy": "ml", "params": {}}, "2026-08-19")
    vols = [c for c in ring if c.get("strategy") == "regime_wrap"
            and c["params"].get("vol_quantile") is not None]
    assert vols, "변동성 국면 변형이 링에 없다"
    assert vols[0]["params"]["vol_quantile"] == 0.9, (
        f"문턱 분위수가 사전 등록값(0.9)과 다르다: {vols[0]['params']}")
    assert vols[0]["params"].get("use_trend") is False, (
        "추세 필터가 같이 켜져 있다 — 추세 변형과 비교가 오염된다"
        "(둘의 차이가 어느 필터 덕인지 알 수 없게 된다)")
