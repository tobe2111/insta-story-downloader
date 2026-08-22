"""맞혀도 손해면 맞힌 게 아니다 — 비용 기준 라벨 (감사 298).

기본 라벨(`nextbar`)은 **다음 봉이 오르기만 하면 1**이다. 그런데 우리가
실제로 벌어야 하는 것은 왕복 비용을 넘는 움직임이다. 편도 0.15%(코인)면
왕복 0.30%이고, 그 아래 상승은 **맞혀도 손해**다.

즉 모델은 지금까지 "맞히면 이기는 게임"이 아니라 "맞혀도 질 수 있는
게임"을 배우고 있었다. 2026-08-20 실측이 그 그림자를 보여준다 — 장중
실험이 순 +2.03%인데 비용 전으로는 +2.32%였다.

⚠️ **이것은 가설이지 개선이 아니다.** 문턱을 올리면 '산다' 라벨이 귀해져
   표본이 불균형해지고(실측 47.6% → 19.8%), 그 자체가 학습을 어렵게 만들
   수 있다. 그래서 강제 적용 없이 오디션 후보로만 세운다 — 2단계 관문을
   통과할 때만 챔피언이 된다.

여기서 지키는 것:
  · 비용을 못 넘는 상승은 '산다'가 아니다.
  · **비용이 0이면 예전 라벨과 완전히 같다**(대조군). 이게 없으면
    "늘 어딘가 깎는다"는 고장도 통과한다.
  · 오디션 링에 실제로 서 있다(선언만 하고 안 세우면 아무 일도 안 난다).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.strategies.ml import MLStrategy  # noqa: E402


def _frame(rets):
    px = 100.0 * np.cumprod(1.0 + np.asarray([0.0] + list(rets)))
    return pd.DataFrame(
        {"open": px, "high": px * 1.001, "low": px * 0.999, "close": px,
         "volume": 1e6},
        index=pd.date_range("2025-01-01", periods=len(px), freq="D"))


def _labels(df, cost):
    """전략이 쓰는 것과 같은 식 — 검사가 식을 다시 적지 않게."""
    nxt = df["close"].shift(-1)
    return ((nxt / df["close"] - 1.0) > cost).astype(float)[:-1].to_numpy()


def test_a_rise_that_cannot_pay_the_cost_is_not_a_buy():
    # +0.10% · +0.50% · −0.20%  →  왕복 0.30% 기준이면 가운데만 '산다'
    df = _frame([0.001, 0.005, -0.002])
    got = _labels(df, 0.0030)
    assert list(got) == [0.0, 1.0, 0.0], got
    # 예전 라벨은 셋 중 둘을 '산다'로 세었다 — 그중 하나는 맞혀도 손해다.
    assert list(_labels(df, 0.0)) == [1.0, 1.0, 0.0]


def test_zero_cost_is_exactly_the_old_label():
    """대조군 — 비용이 0이면 예전과 **한 칸도** 달라지면 안 된다."""
    rng = np.random.default_rng(11)
    df = _frame(rng.normal(0.0002, 0.004, 300))
    old = (df["close"].shift(-1) > df["close"]).astype(float)[:-1].to_numpy()
    assert np.array_equal(_labels(df, 0.0), old)


def test_a_higher_bar_makes_buying_rarer():
    """문턱이 오르면 '산다'가 줄어야 한다 — 방향이 뒤집히면 부호가 틀린 것."""
    rng = np.random.default_rng(7)
    df = _frame(rng.normal(0.0002, 0.004, 400))
    a, b, c = (_labels(df, x).mean() for x in (0.0, 0.0012, 0.0030))
    assert a > b > c, (a, b, c)


def test_the_strategy_accepts_the_new_label_and_refuses_nonsense():
    MLStrategy(model="logreg", label="cost", label_cost=0.003)
    MLStrategy(model="logreg", label="cost")          # 기본 0.0 = 예전과 같음
    with pytest.raises(ValueError):
        MLStrategy(model="logreg", label="없는라벨")
    # 음수 비용은 조용히 0으로 — '비용이 마이너스'인 세상은 없다.
    assert MLStrategy(model="logreg", label="cost",
                      label_cost=-0.5).label_cost == 0.0


def test_the_cost_label_is_actually_in_the_ring():
    """선언만 하고 링에 안 세우면 아무 일도 안 난다(이 저장소의 단골 실패)."""
    from quant.live.retrain import DEFAULT_CHALLENGERS

    ring = [c for c in DEFAULT_CHALLENGERS if c.get("label") == "cost"]
    assert ring, "비용 라벨 후보가 오디션 링에 없다"
    costs = {c.get("label_cost") for c in ring}
    # 시장마다 왕복 비용이 다르다 — 미국(0.12%)과 코인·한국(0.30%)을 덮는다.
    assert 0.0012 in costs and 0.0030 in costs, costs
    for c in ring:
        assert c.get("label_cost", 0) > 0, (
            f"비용 문턱이 0이면 예전 라벨과 같아 링에 설 이유가 없다: {c}")
