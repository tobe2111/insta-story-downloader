"""성과 지표 계산.

과거 성과가 미래를 보장하지 않는다는 점을 항상 기억할 것.
샤프지수가 높아도 과최적화(overfitting)면 실전에서 무너진다.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


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

    def as_dict(self) -> dict:
        return asdict(self)

    def pretty(self) -> str:
        return (
            f"총수익률   : {self.total_return:>10.2%}\n"
            f"CAGR       : {self.cagr:>10.2%}\n"
            f"변동성(연) : {self.volatility:>10.2%}\n"
            f"샤프지수   : {self.sharpe:>10.2f}\n"
            f"소르티노   : {self.sortino:>10.2f}\n"
            f"최대낙폭   : {self.max_drawdown:>10.2%}\n"
            f"칼마지수   : {self.calmar:>10.2f}\n"
            f"승률       : {self.win_rate:>10.2%}\n"
            f"거래횟수   : {self.num_trades:>10d}\n"
            f"시장노출   : {self.exposure:>10.2%}"
        )


def compute_metrics(
    equity: pd.Series,
    returns: pd.Series,
    positions: pd.Series,
    periods_per_year: int = 365,
    risk_free: float = 0.0,
) -> Metrics:
    """자본곡선/수익률/포지션으로 성과 지표를 계산한다."""
    equity = equity.dropna()
    returns = returns.dropna()
    if len(equity) < 2:
        return Metrics(0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

    total_return = equity.iloc[-1] / equity.iloc[0] - 1.0
    n = len(returns)
    years = n / periods_per_year
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1.0 if years > 0 else 0.0

    vol = returns.std() * np.sqrt(periods_per_year)
    excess = returns - risk_free / periods_per_year
    sharpe = (
        excess.mean() / returns.std() * np.sqrt(periods_per_year)
        if returns.std() > 0
        else 0.0
    )
    downside = returns[returns < 0].std()
    sortino = (
        excess.mean() / downside * np.sqrt(periods_per_year)
        if downside and downside > 0
        else 0.0
    )

    cummax = equity.cummax()
    drawdown = equity / cummax - 1.0
    max_dd = drawdown.min()
    calmar = cagr / abs(max_dd) if max_dd < 0 else 0.0

    active = returns[positions.reindex(returns.index).fillna(0) != 0]
    win_rate = (active > 0).mean() if len(active) else 0.0
    num_trades = int((positions.diff().fillna(positions) != 0).sum())
    exposure = (positions != 0).mean()

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
    )
