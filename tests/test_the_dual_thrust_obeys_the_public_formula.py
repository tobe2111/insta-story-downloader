"""듀얼 스러스트 — 자동 자료 수집 라운드(2026-08-18)의 첫 도전자.

공개 수식(마이클 챌렉, 1980년대)을 옮긴 것이므로, 이 검사가 지키는 것은
"옮긴 코드가 수식과 갈라지지 않았는가"다:
  · Range는 직전 N일에서만 나온다(현재 봉 제외 — 룩어헤드 금지)
  · 종가가 시가+K1×Range를 넘으면 매수, 시가−K2×Range 아래면 정리
  · Range가 0이거나 워밍업 구간이면 신호가 없다
  · 도전자 링에 실제로 서 있다
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.strategies import get_strategy                    # noqa: E402
from quant.strategies.dualthrust import DualThrustStrategy   # noqa: E402


def _frame(open_, high, low, close):
    idx = pd.date_range("2024-01-01", periods=len(close), freq="D")
    return pd.DataFrame({"open": np.asarray(open_, float),
                         "high": np.asarray(high, float),
                         "low": np.asarray(low, float),
                         "close": np.asarray(close, float),
                         "volume": np.full(len(close), 1e6)}, index=idx)


def _calm(n=30, px=100.0, span=1.0):
    """조용한 박스권 — Range가 작고 일정하다."""
    o = [px] * n
    h = [px + span] * n
    lo = [px - span] * n
    c = [px] * n
    return o, h, lo, c


def test_a_breakout_above_the_buy_line_goes_long():
    o, h, lo, c = _calm(30)
    # 마지막 날: Range≈2(고저폭). 시가 100 + 0.5×2 = 101을 넘는 종가 → 매수.
    c[-1] = 102.0
    h[-1] = 102.5
    sig = DualThrustStrategy(window=4).generate_signals(_frame(o, h, lo, c))
    assert sig.iloc[-1] == 1.0, "매수선 돌파에 매수하지 않는다"
    assert sig.iloc[-2] == 0.0, "돌파 전에 이미 포지션을 들고 있다"


def test_a_drop_below_the_sell_line_exits():
    o, h, lo, c = _calm(30)
    c[-3] = 102.0; h[-3] = 102.5           # 진입
    c[-1] = 98.0; lo[-1] = 97.5            # 시가 100 − 0.5×Range 아래 → 정리
    sig = DualThrustStrategy(window=4).generate_signals(_frame(o, h, lo, c))
    assert sig.iloc[-3] == 1.0 and sig.iloc[-1] == 0.0, (
        "청산선 이탈에 정리하지 않는다")


def test_the_range_cannot_see_today():
    """오늘 고가를 아무리 키워도 오늘의 Range(전일까지)는 그대로여야 한다."""
    o, h, lo, c = _calm(30)
    c[-1] = 102.0
    base = DualThrustStrategy(window=4).generate_signals(_frame(o, h, lo, c))
    h2 = list(h); h2[-1] = 200.0           # 오늘 고가 폭등 — 내일에야 Range에 반영
    spiked = DualThrustStrategy(window=4).generate_signals(_frame(o, h2, lo, c))
    assert base.iloc[-1] == spiked.iloc[-1], (
        "오늘 봉이 오늘의 Range에 들어갔다 — 룩어헤드")


def test_a_bigger_k1_makes_entry_harder():
    o, h, lo, c = _calm(30)
    c[-1] = 102.0; h[-1] = 102.5
    easy = DualThrustStrategy(window=4, k1=0.5).generate_signals(_frame(o, h, lo, c))
    hard = DualThrustStrategy(window=4, k1=5.0).generate_signals(_frame(o, h, lo, c))
    assert easy.iloc[-1] == 1.0 and hard.iloc[-1] == 0.0, (
        "K1을 키워도 진입 문턱이 안 올라간다")


def test_the_challenger_is_actually_in_the_ring():
    from quant.live.retrain import build_challengers
    ring = build_challengers({"strategy": "ml", "params": {}}, "2026-08-18",
                             evolve=False)
    assert any(c.get("strategy") == "dual_thrust" for c in ring), (
        "듀얼 스러스트가 링에 없다 — 수집만 하고 세우지 않았다")
    assert get_strategy("dual_thrust").name == "dual_thrust"
