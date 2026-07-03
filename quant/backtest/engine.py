"""백테스트 엔진 (bar-by-bar).

핵심 설계 원칙:
    1. 룩어헤드 편향 방지 — t 시점 종가로 계산한 신호는 t+1 시점부터 반영된다.
       (엔진은 '이번 봉 종가에 결정 → 다음 봉에 보유'를 명시적으로 처리)
    2. 현실 비용 반영 — 수수료 + 슬리피지를 회전율(turnover)에 비례해 차감.
    3. 경로 의존적 손절/익절 — 봉마다 진입가 대비 손익을 확인해 청산.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from quant.backtest.metrics import Metrics, compute_metrics
from quant.risk import RiskConfig, RiskManager
from quant.strategies.base import Strategy


@dataclass
class BacktestResult:
    equity: pd.Series
    returns: pd.Series
    positions: pd.Series
    metrics: Metrics
    df: pd.DataFrame
    benchmark: pd.Series | None = None  # 단순 매수후보유(buy & hold) 자본곡선

    @property
    def benchmark_return(self) -> float:
        """벤치마크(매수후보유) 총수익률."""
        if self.benchmark is None or len(self.benchmark) < 2:
            return 0.0
        return float(self.benchmark.iloc[-1] / self.benchmark.iloc[0] - 1.0)

    @property
    def excess_return(self) -> float:
        """전략 총수익률 − 벤치마크 총수익률 (초과수익). 음수면 그냥 보유가 나았다는 뜻."""
        return self.metrics.total_return - self.benchmark_return

    def summary(self) -> str:
        lines = [self.metrics.pretty()]
        if self.benchmark is not None:
            lines.append(f"매수후보유 : {self.benchmark_return:>10.2%}")
            verdict = "✅ 벤치마크 초과" if self.excess_return >= 0 else "⚠️ 벤치마크 하회"
            lines.append(f"초과수익   : {self.excess_return:>10.2%}  {verdict}")
        return "\n".join(lines)

    def to_frame(self) -> pd.DataFrame:
        """자본곡선·수익률·포지션(·벤치마크)을 하나의 DataFrame으로 반환한다."""
        data = {
            "equity": self.equity,
            "returns": self.returns,
            "position": self.positions,
        }
        if self.benchmark is not None:
            data["benchmark"] = self.benchmark
        return pd.DataFrame(data)

    def to_csv(self, path: str) -> str:
        """결과를 CSV로 저장한다 (엑셀 등에서 추가 분석용). 저장 경로를 반환."""
        from pathlib import Path

        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        self.to_frame().to_csv(out, index_label="time")
        return str(out)


class Backtester:
    def __init__(
        self,
        strategy: Strategy,
        risk: RiskManager | None = None,
        initial_capital: float = 10_000.0,
        fee: float = 0.001,        # 편도 수수료 0.1%
        slippage: float = 0.0005,  # 슬리피지 0.05%
        periods_per_year: int = 365,
    ):
        self.strategy = strategy
        self.risk = risk or RiskManager(RiskConfig(periods_per_year=periods_per_year))
        self.initial_capital = initial_capital
        self.fee = fee
        self.slippage = slippage
        self.periods_per_year = periods_per_year

    def run(self, df: pd.DataFrame) -> BacktestResult:
        if df.empty:
            raise ValueError("빈 데이터로 백테스트할 수 없습니다.")

        target = self.strategy.generate_signals(df)
        desired = self.risk.size_positions(df, target)

        close = df["close"].to_numpy()
        want = desired.to_numpy()
        cost = self.fee + self.slippage

        n = len(df)
        equity = np.empty(n)
        held = np.zeros(n)

        cash_equity = self.initial_capital
        pos = 0.0        # 현재 보유 비중
        entry = 0.0      # 진입가
        extreme = 0.0    # 보유 중 유리한 방향 극값(롱=최고가, 숏=최저가) — 트레일링용

        for i in range(n):
            price = close[i]

            # 1) 이전 봉에서 설정한 pos로 이번 봉 수익 실현
            if i > 0:
                bar_ret = price / close[i - 1] - 1.0
                cash_equity *= 1.0 + pos * bar_ret

            # 2) 보유 중이면 유리한 극값 갱신 (트레일링 스톱 기준점)
            if pos > 0:
                extreme = max(extreme, price)
            elif pos < 0:
                extreme = min(extreme, price)

            # 3) 손절/익절/트레일링 확인 (경로 의존)
            pos_after = self.risk.apply_stops(pos, entry, price)
            pos_after = self.risk.apply_trailing_stop(pos_after, extreme, price)
            stop_triggered = pos_after != pos

            # 4) 다음 봉에 보유할 목표 결정
            new_pos = 0.0 if stop_triggered else float(want[i])

            # 5) 회전율에 따른 거래비용 차감
            turnover = abs(new_pos - pos)
            if turnover > 1e-12:
                cash_equity *= 1.0 - cost * turnover
                if new_pos == 0.0:
                    entry = 0.0
                    extreme = 0.0
                elif pos == 0.0 or np.sign(new_pos) != np.sign(pos):
                    entry = price      # 신규 진입 또는 방향 전환
                    extreme = price    # 극값도 진입가로 초기화

            pos = new_pos
            equity[i] = cash_equity
            held[i] = pos

        equity_s = pd.Series(equity, index=df.index, name="equity")
        returns_s = equity_s.pct_change().fillna(0.0).rename("returns")
        positions_s = pd.Series(held, index=df.index, name="position")

        metrics = compute_metrics(
            equity_s, returns_s, positions_s, self.periods_per_year
        )
        # 매수후보유(buy & hold) 벤치마크: 첫 봉에 전액 매수해 그대로 보유
        benchmark = (self.initial_capital * df["close"] / df["close"].iloc[0]).rename(
            "benchmark"
        )
        return BacktestResult(
            equity_s, returns_s, positions_s, metrics, df, benchmark
        )
