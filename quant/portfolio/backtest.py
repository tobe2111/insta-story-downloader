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
        rebalance_band: float = 0.0,
    ):
        self.strategy = strategy
        self.allocation = allocation
        self.initial_capital = initial_capital
        self.cost = fee + slippage
        self.max_gross = max_gross
        self.vol_window = vol_window
        self.periods_per_year = periods_per_year
        # 종목별 |목표-보유| 비중 차가 이 밴드 미만이면 그 종목 리밸런스를 생략한다.
        # 역변동성 배분·vol 가중은 매 봉 미세하게 달라져 기대수익 0의 왕복비용만
        # 확정 지불하는 거래를 만든다(비용 수학 — 예측 아님). 권장 0.01~0.05.
        # 청산(목표=0)은 밴드와 무관하게 항상 실행. 0=기존 동작(비트 동일).
        self.rebalance_band = max(0.0, rebalance_band)

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

        # 리밸런스 데드밴드: 직전 '실제 보유' 대비 변화가 밴드 미만인 종목은
        # 그 봉 리밸런스를 생략(보유 유지). 청산(목표=0)은 항상 실행.
        if self.rebalance_band > 0.0:
            w = weights.to_numpy()
            out = np.empty_like(w)
            prev = np.zeros(w.shape[1])
            for i in range(w.shape[0]):
                row = w[i].copy()
                hold = (np.abs(row - prev) < self.rebalance_band) & (row != 0.0)
                row[hold] = prev[hold]
                out[i] = row
                prev = row
            weights = pd.DataFrame(out, index=weights.index,
                                   columns=weights.columns)

        # 룩어헤드 방지: 전일 종가에 정한 비중으로 당일 수익 실현
        held = weights.shift(1).fillna(0.0)
        port_ret_gross = (held * returns).sum(axis=1)

        # 회전율 기반 거래비용.
        #
        # ⚠️ 비용은 **체결되는 봉**에 부과한다(감사 153). weights[t]는 t에
        #    정한 목표이고 실제로 들고 있는 건 held[t] = weights[t-1]이다.
        #    즉 weights[t-1] → weights[t]로 갈아타는 거래는 t와 t+1 사이에
        #    일어나고, 그 비용은 t+1에 부과되어야 한다.
        #
        #    예전에는 turnover[t]를 그대로 t에 뺐다 — 아직 갈아타지도 않은
        #    봉에서 비용을 먼저 냈고, 마지막 봉의 '표본 밖에서 체결될 거래'
        #    비용까지 냈다. shift로 held와 같은 시계에 맞춘다.
        #
        #    크기는 작다(실측 600봉 4종목: 총수익 -34.65% → -34.56%,
        #    샤프 -1.4011 → -1.3962). **결과가 조금 좋아지는 방향**이므로
        #    '성능 개선'으로 읽으면 안 된다 — 정렬을 맞춘 것뿐이다.
        turnover = (weights - weights.shift(1)).abs().sum(axis=1)
        turnover.iloc[0] = weights.iloc[0].abs().sum()
        cost = self.cost * turnover.shift(1).fillna(0.0)

        port_ret = (port_ret_gross - cost).rename("returns")
        equity = ((1 + port_ret).cumprod() * self.initial_capital).rename("equity")
        exposure = held.abs().sum(axis=1).rename("position")

        # exposure = |weights.shift(1)| 은 이미 '수익을 실현한' 포지션(realized-aligned)
        # 이므로 compute_metrics가 다시 shift하지 않도록 False를 준다(이중 시프트 방지).
        metrics = compute_metrics(equity, port_ret, exposure, self.periods_per_year,
                                  positions_are_decision_time=False)
        result = BacktestResult(equity, port_ret, exposure, metrics, close)
        # 봉별 '종목별 |Δ비중| 합'(실제 비용이 부과되는 회전율)을 결과에 노출한다.
        # positions(총노출)의 변동은 종목 간 상쇄 때문에 회전율 대용으로 부적합.
        result.turnover = turnover.rename("turnover")
        return result
