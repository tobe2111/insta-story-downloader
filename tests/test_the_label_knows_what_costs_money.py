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
    """전략이 **실제로 쓰는 함수**를 부른다.

    ⚠️ 예전 판은 여기서 식을 다시 적어 놓고 주석에 "전략이 쓰는 것과 같은
       식"이라고 달아 뒀다. 그래서 이 검사는 `quant/strategies/ml.py`의
       그 줄을 **한 번도 실행하지 않았고**, 야간 변이 전수가 그 사실을
       잡았다(감사 313). 소스를 베낀 검사는 그 소스가 안 불려도 초록이다.

       그리고 실제로 결함이 있었다 — 비용 라벨이 동료 데이터 경로에만
       있고 신호 경로에는 없어서, 그 장치가 한 번도 켜진 적이 없었다.
    """
    from quant.strategies.ml import _labels_of
    y, _span = _labels_of(df, "cost", 10, 1.5, cost)
    return y[:-1]


def test_a_rise_that_cannot_pay_the_cost_is_not_a_buy():
    # +0.10% · +0.50% · −0.20%  →  왕복 0.30% 기준이면 가운데만 '산다'
    df = _frame([0.001, 0.005, -0.002])
    got = _labels(df, 0.0030)
    assert list(got) == [0.0, 1.0, 0.0], got
    # 예전 라벨은 셋 중 둘을 '산다'로 세었다 — 그중 하나는 맞혀도 손해다.
    assert list(_labels(df, 0.0)) == [1.0, 1.0, 0.0]


def test_zero_cost_is_exactly_the_old_label():
    """대조군 — 비용이 0이면 예전과 **한 칸도** 달라지면 안 된다."""
    from quant.strategies.ml import _labels_of
    rng = np.random.default_rng(11)
    df = _frame(rng.normal(0.0002, 0.004, 300))
    old, _ = _labels_of(df, "nextbar", 10, 1.5, 0.0)
    assert np.array_equal(_labels(df, 0.0), old[:-1])


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


# ══ 장치가 **실제 신호 경로**에서 켜지는가 (감사 313) ══════════════
#
# ⚠️ 위 검사들은 라벨 계산이 옳은지만 본다. 계산이 옳아도 **전략이 그
#    계산을 안 부르면** 아무 일도 일어나지 않는다. 실제로 그랬다:
#    비용 라벨은 동료 데이터를 붙이는 경로(_build_pool)에만 들어가 있었고,
#    매일의 신호를 만드는 generate_signals는 옛 라벨(nextbar)로 학습했다.
#    "맞혀도 손해인 상승은 사지 않는다"는 장치가 한 번도 켜진 적이 없었다
#    (감사 289와 같은 모양). 야간 변이 전수가 이것을 잡았다.
#
#    그래서 여기서는 **회차를 실제로 돌린다.**


def _bars(n=500, seed=5):
    """저장소의 다른 ML 검사와 같은 모양의 데이터(500봉)."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    close = 100.0 * np.cumprod(1 + rng.normal(0.0005, 0.02, n))
    opn = close * (1 + rng.normal(0, 0.004, n))
    return pd.DataFrame(
        {"open": opn,
         "high": np.maximum(opn, close) * (1 + abs(rng.normal(0, 0.005, n))),
         "low": np.minimum(opn, close) * (1 - abs(rng.normal(0, 0.005, n))),
         "close": close, "volume": 1000.0 + rng.integers(0, 500, n)},
        index=idx)


def _signals(label, cost=0.0, df=None):
    return MLStrategy(model="gb", train_window=200, retrain_every=50,
                      label=label, label_cost=cost
                      ).generate_signals(df if df is not None else _bars()
                                         ).to_numpy()


def test_the_cost_bar_actually_changes_the_signals():
    """비용을 올리면 **실제 신호가 달라져야** 한다.

    안 달라지면 그 설정은 이름만 있고 아무 일도 안 하는 것이다.
    """
    df = _bars()
    a, b = _signals("cost", 0.0, df), _signals("cost", 0.02, df)
    assert not np.allclose(a, b), (
        "비용 문턱을 0 → 2%로 올렸는데 신호가 한 칸도 안 바뀌었다 — "
        "라벨이 신호 경로에 연결돼 있지 않다")


def test_a_higher_bar_makes_the_strategy_buy_less():
    """문턱이 오르면 '산다'가 귀해지므로 실제 매수 신호도 줄어야 한다."""
    df = _bars()
    a = int((_signals("cost", 0.0, df) != 0).sum())
    b = int((_signals("cost", 0.02, df) != 0).sum())
    assert a > 0, "대조군이 아무 신호도 안 냈다 — 비교가 성립하지 않는다"
    assert b < a, f"비용 문턱을 올렸는데 매수가 안 줄었다 ({a} → {b})"


def test_zero_cost_signals_match_the_old_label_exactly():
    """대조군 — 비용 0이면 옛 라벨과 **신호까지** 똑같아야 한다.

    이게 없으면 "cost 라벨은 늘 어딘가 깎는다"는 고장도 위 검사를 통과한다.
    """
    df = _bars()
    assert np.allclose(_signals("cost", 0.0, df), _signals("nextbar", 0.0, df))


# ⚠️ 동료 데이터 경로(_build_pool)의 라벨은 **행동으로 못 잰다.**
#    풀 행을 여섯 종목까지 늘려도 자기 종목 행에 묻혀 최종 신호가 한 칸도
#    안 바뀐다(실측). 그래서 "재는 척만 하는 검사"를 두지 않는다 — 그런
#    검사는 초록이라는 사실로 없는 안전을 판다.
#
#    대신 **구조로** 막았다: 두 경로가 같은 함수(_labels_of)를 부르므로
#    라벨 규칙이 갈라질 자리 자체가 없다. 감사 313의 사고는 규칙이 두 곳에
#    적혀 있어서 생겼고, 그 원인을 없앤 것이 여기서 할 수 있는 최선이다.
