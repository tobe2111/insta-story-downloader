"""성과 지표 계산.

과거 성과가 미래를 보장하지 않는다는 점을 항상 기억할 것.
샤프지수가 높아도 과최적화(overfitting)면 실전에서 무너진다.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from quant.utils.numerics import degenerate_spread


@dataclass
class Metrics:
    total_return: float      # 총 수익률
    cagr: float              # 연평균 복리 수익률
    volatility: float        # 연율 변동성
    sharpe: float            # 샤프 지수
    sortino: float           # 소르티노 지수
    max_drawdown: float      # 최대 낙폭 (MDD)
    calmar: float            # CAGR / |MDD|
    win_rate: float          # 승률 (양의 수익 기간 비율)
    num_trades: int          # 거래(포지션 변경) 횟수
    exposure: float          # 시장 노출 시간 비율
    profit_factor: float = 0.0  # 총이익 / 총손실 (봉 단위). >1 이면 손실보다 이익이 큼

    def as_dict(self) -> dict:
        return asdict(self)

    def pretty(self) -> str:
        pf = "∞" if not np.isfinite(self.profit_factor) else f"{self.profit_factor:.2f}"
        return (
            f"총수익률   : {self.total_return:>10.2%}\n"
            f"CAGR       : {self.cagr:>10.2%}\n"
            f"변동성(연) : {self.volatility:>10.2%}\n"
            f"샤프지수   : {self.sharpe:>10.2f}\n"
            f"소르티노   : {self.sortino:>10.2f}\n"
            f"최대낙폭   : {self.max_drawdown:>10.2%}\n"
            f"칼마지수   : {self.calmar:>10.2f}\n"
            f"승률       : {self.win_rate:>10.2%}\n"
            f"이익팩터   : {pf:>10}\n"
            f"거래횟수   : {self.num_trades:>10d}\n"
            f"시장노출   : {self.exposure:>10.2%}"
        )


def compute_metrics(
    equity: pd.Series,
    returns: pd.Series,
    positions: pd.Series,
    periods_per_year: int = 365,
    risk_free: float = 0.0,
    positions_are_decision_time: bool = True,
) -> Metrics:
    """자본곡선/수익률/포지션으로 성과 지표를 계산한다.

    positions_are_decision_time:
        True  — positions[t]가 '봉 t 종가에 정한' 결정시점 포지션(단일종목 엔진의
                규약). t봉 수익은 t-1봉 포지션으로 실현되므로 내부에서 shift(1)해
                수익과 정렬한다.
        False — positions[t]가 이미 '봉 t 수익을 실현한' 포지션(포트폴리오
                백테스터·워크포워드처럼 weights.shift(1)를 먼저 적용한 경우).
                이땐 추가 시프트 없이 그대로 정렬해야 이중 시프트를 피한다.
    """
    equity = equity.dropna()
    returns = returns.dropna()
    if len(equity) < 2:
        return Metrics(0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

    total_return = equity.iloc[-1] / equity.iloc[0] - 1.0
    # 복리 기간 수는 '수익률 구간(interval)' 개수다. equity가 m개 점이면 실제
    # 수익 구간은 m-1개이므로 years를 그만큼으로 잡아야 CAGR이 부풀지 않는다.
    intervals = max(1, len(equity) - 1)
    years = intervals / periods_per_year
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1.0 if years > 0 else 0.0

    # ⚠️ `std() > 0`으로 막으면 안 된다(감사 146) — 값이 전부 같아도
    #    표준편차는 1e-19 언저리라 통과하고, 샤프가 천문학적 수치가 된다.
    _sd = float(returns.std())
    _degenerate = degenerate_spread(_sd, float(returns.abs().mean()))
    vol = _sd * np.sqrt(periods_per_year)
    excess = returns - risk_free / periods_per_year
    sharpe = (
        0.0 if _degenerate
        else excess.mean() / _sd * np.sqrt(periods_per_year)
    )
    # 하방편차: 목표(0) 대비 손실의 제곱평균제곱근. 음수 수익만의 표준편차(ddof=1,
    # 평균 차감)를 쓰면 손실이 균일할 때 0이 되어 '하방위험 없음'으로 오판하고,
    # 일반적으로도 분모가 작아져 소르티노가 과대평가된다.
    downside = float(np.sqrt((np.minimum(excess, 0.0) ** 2).mean()))
    sortino = (
        excess.mean() / downside * np.sqrt(periods_per_year)
        if downside > 0
        else 0.0
    )

    cummax = equity.cummax()
    drawdown = equity / cummax - 1.0
    max_dd = drawdown.min()
    calmar = cagr / abs(max_dd) if max_dd < 0 else 0.0

    # 룩어헤드 방지 규약상 t봉의 수익은 t-1봉에서 정한 포지션으로 실현된다
    # (엔진: '이번 봉 종가 결정 → 다음 봉 보유'). 따라서 어떤 봉의 수익이
    # '실제 포지션으로 번 것'인지 판정하려면 포지션을 한 봉 시프트해서 맞춰야
    # 한다. 시프트하지 않으면 진입/청산 경계에서 승률·이익팩터가 한 봉씩 어긋난다.
    held = positions.shift(1) if positions_are_decision_time else positions
    held = held.reindex(returns.index).fillna(0.0)
    active = returns[held != 0]
    win_rate = (active > 0).mean() if len(active) else 0.0
    num_trades = int((positions.diff().fillna(positions) != 0).sum())
    exposure = (positions != 0).mean()

    gross_win = float(active[active > 0].sum())
    gross_loss = float(-active[active < 0].sum())
    if gross_loss > 0:
        profit_factor = gross_win / gross_loss
    else:
        profit_factor = float("inf") if gross_win > 0 else 0.0

    return Metrics(
        total_return=float(total_return),
        cagr=float(cagr),
        volatility=float(vol),
        sharpe=float(sharpe),
        sortino=float(sortino),
        max_drawdown=float(max_dd),
        calmar=float(calmar),
        win_rate=float(win_rate),
        num_trades=num_trades,
        exposure=float(exposure),
        profit_factor=profit_factor,
    )
