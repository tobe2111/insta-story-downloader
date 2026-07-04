"""다중 종목 포트폴리오 백테스트.

여러 종목에 동일 전략을 적용하고, 자산배분 방식으로 자본을 나눠 담아
포트폴리오 전체의 성과를 시뮬레이션한다. 단일 종목보다 변동성이 낮아지고
특정 종목 급락에 대한 방어력이 생긴다.

룩어헤드 방지: t 시점에 결정한 비중은 t+1 수익에만 반영된다(shift).
"""
from __future__ import annotations

from typing import Callable, Mapping

import numpy as np
import pandas as pd

from quant.backtest.engine import BacktestResult
from quant.backtest.metrics import compute_metrics
from quant.portfolio.allocation import get_scheme
from quant.strategies.base import Strategy


class PortfolioBacktester:
    def __init__(
        self,
        strategy: Strategy | Callable[[str], Strategy],
        allocation: str = "inverse_vol",
        initial_capital: float = 10_000.0,
        fee: float = 0.001,
        slippage: float = 0.0005,
        max_gross: float = 1.0,
        vol_window: int = 30,
        periods_per_year: int = 365,
    ):
        self.strategy = strategy
        self.allocation = allocation
        self.initial_capital = initial_capital
        self.cost = fee + slippage
        self.max_gross = max_gross
        self.vol_window = vol_window
        self.periods_per_year = periods_per_year

    def _strategy_for(self, symbol: str) -> Strategy:
        return self.strategy(symbol) if callable(self.strategy) else self.strategy

    def run(self, data: Mapping[str, pd.DataFrame]) -> BacktestResult:
        symbols = list(data)
        if not symbols:
            raise ValueError("종목이 하나도 없습니다.")

        # 공통 거래일로 정렬 (교집합)
        close = pd.DataFrame({s: data[s]["close"] for s in symbols}).dropna()
        if len(close) < 2:
            raise ValueError("공통 구간 데이터가 부족합니다.")
        returns = close.pct_change().fillna(0.0)

        # 종목별 전략 신호
        sig = {}
        for s in symbols:
            raw = self._strategy_for(s).generate_signals(data[s])
            sig[s] = raw.reindex(close.index).ffill().fillna(0.0)
        signals = pd.DataFrame(sig)

        # 자산배분 → 목표 비중
        weights = get_scheme(self.allocation)(returns, signals, self.vol_window)

        # 총 노출(gross) 한도 적용
        gross = weights.abs().sum(axis=1)
        scale = pd.Series(1.0, index=gross.index)
        mask = gross > self.max_gross
        scale[mask] = self.max_gross / gross[mask]
        weights = weights.mul(scale, axis=0).fillna(0.0)

        # 룩어헤드 방지: 전일 종가에 정한 비중으로 당일 수익 실현
        held = weights.shift(1).fillna(0.0)
        port_ret_gross = (held * returns).sum(axis=1)

        # 회전율 기반 거래비용
        turnover = (weights - weights.shift(1)).abs().sum(axis=1)
        turnover.iloc[0] = weights.iloc[0].abs().sum()
        cost = self.cost * turnover.fillna(0.0)

        port_ret = (port_ret_gross - cost).rename("returns")
        equity = ((1 + port_ret).cumprod() * self.initial_capital).rename("equity")
        exposure = held.abs().sum(axis=1).rename("position")

        # exposure = |weights.shift(1)| 은 이미 '수익을 실현한' 포지션(realized-aligned)
        # 이므로 compute_metrics가 다시 shift하지 않도록 False를 준다(이중 시프트 방지).
        metrics = compute_metrics(equity, port_ret, exposure, self.periods_per_year,
                                  positions_are_decision_time=False)
        return BacktestResult(equity, port_ret, exposure, metrics, close)
