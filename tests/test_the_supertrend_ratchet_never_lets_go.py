"""슈퍼트렌드 — 공개 수식의 재현 (일일 수집 라운드, 2026-08-19).

지켜야 할 약속:
- 추세장에서는 올라타고, 급반전이 밴드를 깨면 내린다.
- 래칫: 상승 추세 중 하단 밴드는 절대 내려가지 않는다(되풀리는 밴드는
  추격 손절선이 아니다).
- 워밍업(ATR '모름')은 관망 — 감사 206의 규칙.
- 미래 봉이 과거 판정을 못 바꾼다(룩어헤드 없음).
- 같은 데이터 → 언제나 같은 신호.
- 링에 실제로 서 있다(채택은 오디션이 결정).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.strategies.supertrend import SuperTrendStrategy   # noqa: E402


def _df(rets, seed=None):
    close = 100.0 * np.cumprod(1.0 + np.asarray(rets))
    idx = pd.date_range("2025-01-01", periods=len(close), freq="D")
    return pd.DataFrame({"open": close, "close": close,
                         "high": close * 1.01, "low": close * 0.99,
                         "volume": np.full(len(close), 1e6)}, index=idx)


def test_a_trend_is_ridden_and_a_crash_is_exited():
    rng = np.random.RandomState(3)
    r = rng.normal(0.004, 0.006, 300)                  # 꾸준한 상승
    r[200:210] = -0.06                                 # 열흘 급락(밴드 붕괴)
    sig = SuperTrendStrategy().generate_signals(_df(r)).to_numpy()
    assert sig[100:200].mean() > 0.9, "추세장에 올라타지 않는다"
    assert sig[212:240].mean() < 0.1, "밴드가 깨졌는데 들고 있다"


def test_warmup_is_quiet():
    rng = np.random.RandomState(1)
    sig = SuperTrendStrategy(period=10).generate_signals(
        _df(rng.normal(0.004, 0.006, 60)))
    assert float(sig.iloc[:10].abs().max()) == 0.0, (
        "ATR이 서기 전에 판정한다 — '모름'은 보류다")


def test_the_future_cannot_change_the_past():
    rng = np.random.RandomState(5)
    r = rng.normal(0.001, 0.01, 300)
    base = SuperTrendStrategy().generate_signals(_df(r)).iloc[:200]
    r2 = r.copy()
    r2[250:] = -0.08                                   # 미래를 뒤흔든다
    spiked = SuperTrendStrategy().generate_signals(_df(r2)).iloc[:200]
    assert (base == spiked).all(), "미래 봉이 과거 판정을 바꿨다 — 룩어헤드"


def test_same_data_same_signals_always():
    rng = np.random.RandomState(7)
    d = _df(rng.normal(0, 0.01, 250))
    a = SuperTrendStrategy().generate_signals(d)
    b = SuperTrendStrategy().generate_signals(d)
    assert (a == b).all(), "재현성 위반"


def test_the_ratchet_is_in_the_code_not_just_the_docstring():
    """래칫 두 줄이 이 지표의 정체다 — 소스 계약으로 못박는다."""
    src = (ROOT / "quant" / "strategies" / "supertrend.py").read_text("utf-8")
    assert "bu if (bu < up_f or c[i - 1] > up_f) else up_f" in src
    assert "bl if (bl > lo_f or c[i - 1] < lo_f) else lo_f" in src, (
        "래칫이 사라졌다 — 되풀리는 밴드는 추격 손절선이 아니다")


def test_the_challenger_is_in_the_ring():
    from quant.live.retrain import build_challengers
    ring = build_challengers({"strategy": "ml", "params": {}}, "2026-08-19")
    st = [c for c in ring if c.get("strategy") == "supertrend"]
    assert st and st[0]["params"] == {"period": 10, "mult": 3.0}, "링에 없다"
