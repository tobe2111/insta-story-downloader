"""거래비용이 **체결되는 봉에 부과되는가** (감사 153).

포트폴리오 백테스터의 시계 규약은 이렇다.

    weights[t]  t에 정한 목표(그날 정보로 결정)
    held[t]     = weights[t-1]        t봉 동안 실제로 들고 있는 것
    returns[t]  t봉 수익

그러면 `weights[t-1] → weights[t]`로 갈아타는 거래는 t와 t+1 사이에
일어난다. 그 비용은 **t+1**에 부과되어야 한다.

예전에는 `turnover[t]`를 그대로 t에 뺐다. 두 가지가 어긋난다.

    · 0봉: 아직 아무것도 안 들었는데(held[0]=0) 진입 비용을 먼저 낸다
    · 마지막 봉: 표본 밖에서 체결될 거래의 비용까지 낸다

크기는 작다 — 600봉 4종목 실측으로 총수익 -34.65% → -34.56%,
샤프 -1.4011 → -1.3962. **결과가 조금 좋아지는 방향**이라 '성능 개선'으로
읽으면 안 된다. 정렬을 맞춘 것뿐이고, 이 파일은 그 정렬을 못 박는다.

크기가 작다고 안 고치면, 나중에 비용 가정이 커졌을 때(실측 슬리피지 반영
등) 같은 어긋남이 커진 채로 남는다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.portfolio.backtest import PortfolioBacktester  # noqa: E402
from quant.strategies.base import Strategy  # noqa: E402

N = 60
IDX = pd.date_range("2025-01-01", periods=N, freq="D")


class _FlipOnce(Strategy):
    """정해진 봉에서 딱 한 번 0 → 1로 바뀌는 신호."""

    name = "flip-once"

    def __init__(self, at: int = 30):
        self.at = at

    def generate_signals(self, df):
        s = pd.Series(0.0, index=df.index)
        s.iloc[self.at:] = 1.0
        return s


def _flat_market() -> dict:
    """가격이 **전혀 안 움직이는** 시장 — 손익이 오직 비용에서만 나온다.

    이래야 '언제 비용이 빠졌는가'를 수익률 계열에서 바로 읽을 수 있다.
    가격이 움직이면 비용이 시장 수익에 묻혀 한 봉 차이를 못 본다.
    """
    c = np.full(N, 100.0)
    df = pd.DataFrame({"open": c, "high": c, "low": c, "close": c,
                       "volume": 1e6}, index=IDX)
    return {"A": df.copy(), "B": df.copy()}


def _run(fee: float = 0.01, at: int = 30):
    return PortfolioBacktester(_FlipOnce(at), allocation="equal",
                               fee=fee, slippage=0.0,
                               periods_per_year=365).run(_flat_market())


def test_the_cost_lands_on_the_bar_the_position_starts():
    """가격이 고정이면 손실은 오직 비용이다 — 그게 체결 봉에 있어야 한다."""
    res = _run(at=30)
    losses = res.returns[res.returns != 0.0]
    assert len(losses) == 1, (
        f"비용이 {len(losses)}개 봉에 흩어져 있다: {losses.to_dict()}")

    when = res.returns.index.get_loc(losses.index[0])
    held_starts = int(np.argmax(res.positions.to_numpy() > 0))
    assert when == held_starts, (
        f"비용은 {when}봉에 부과됐는데 포지션은 {held_starts}봉부터 잡혔다 — "
        "아직 갈아타지도 않은 봉에서 비용을 먼저 낸다")


def test_nothing_is_charged_before_anything_is_held():
    """0봉에는 든 게 없다(held=0) — 비용도 없어야 한다."""
    res = _run(at=30)
    assert res.positions.iloc[0] == 0.0, "전제가 깨졌다 — 0봉에 이미 포지션이 있다"
    assert res.returns.iloc[0] == 0.0, (
        f"아무것도 안 들었는데 0봉에서 {res.returns.iloc[0]:.6f}를 냈다")


def test_a_decision_on_the_last_bar_is_never_charged():
    """마지막 봉의 결정은 표본 밖에서 체결된다 — 그 비용을 미리 내면 안 된다."""
    res = _run(at=N - 1)                  # 마지막 봉에서만 신호가 바뀐다
    assert float(res.returns.abs().sum()) == 0.0, (
        f"마지막 봉 결정의 비용 {res.returns.abs().sum():.6f}를 냈다 — "
        "그 거래는 이 표본 안에서 체결되지 않는다")


def test_the_cost_is_still_actually_charged():
    """대조군 — 정렬한다고 비용을 통째로 빼먹으면 그건 다른 거짓말이다.

    이 검사가 없으면 위 셋은 '비용을 아예 안 매기는' 코드로도 통과한다.
    """
    res = _run(fee=0.01, at=30)
    total = float(res.returns.sum())
    assert total < -0.005, (
        f"왕복 1% 수수료로 전량 진입했는데 총비용이 {total:.6f}뿐이다")
    assert float(res.turnover.sum()) > 0.9, (
        f"회전율 합 {res.turnover.sum():.4f} — 진입 자체가 안 잡혔다")


def test_zero_fee_costs_nothing():
    """대조군 — 수수료 0이면 고정 시장에서 손익도 0이어야 한다."""
    res = _run(fee=0.0, at=30)
    assert float(res.returns.abs().sum()) < 1e-12, (
        f"수수료 0인데 손익 {res.returns.abs().sum():.3e}가 났다")
