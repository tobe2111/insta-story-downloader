"""다중 종목 실시간 동시 운용 (MultiTrader).

여러 종목의 신호를 계산하고, 포트폴리오 자산배분(균등/변동성역가중)으로
자본을 나눠 각 종목에 목표비중 주문을 낸다. 단일 종목 대비 분산 효과로
변동성과 낙폭이 줄어든다.

상태(state)에는 종목별 포지션과 통합 자본곡선이 함께 기록되어, 하나의
대시보드에서 전체 포트폴리오를 모니터링할 수 있다.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable, Sequence

import pandas as pd

from quant.broker.base import Broker
from quant.data.base import DataProvider
from quant.portfolio.allocation import get_scheme
from quant.strategies.base import Strategy
from quant.utils.logging import get_logger

log = get_logger("live.multi")


class MultiTrader:
    def __init__(
        self,
        data: DataProvider,
        strategy: Strategy | Callable[[str], Strategy],
        broker: Broker,
        symbols: Sequence[str],
        timeframe: str = "1h",
        lookback: int = 300,
        allocation: str = "inverse_vol",
        max_gross: float = 1.0,
        vol_window: int = 30,
        state_path: str | None = None,
        dashboard_path: str | None = None,
        notifier=None,
        circuit_breaker=None,
        mode: str = "paper",
    ):
        self.data = data
        self.strategy = strategy
        self.broker = broker
        self.circuit_breaker = circuit_breaker
        self.symbols = list(symbols)
        self.timeframe = timeframe
        self.lookback = lookback
        self.allocation = allocation
        self.max_gross = max_gross
        self.vol_window = vol_window
        self.state_path = state_path
        self.dashboard_path = dashboard_path
        self.notifier = notifier
        self.mode = mode
        self.history: list[dict] = []
        self._last_bar_ts = None        # 최근 데이터 봉의 타임스탬프(서킷브레이커 일자 기준)

    def _strategy_for(self, symbol: str) -> Strategy:
        return self.strategy(symbol) if callable(self.strategy) else self.strategy

    def _target_weights(self) -> tuple[dict[str, float], dict[str, float]]:
        """각 종목의 목표비중과 현재가를 계산한다."""
        closes, sigs, prices = {}, {}, {}
        for s in self.symbols:
            df = self.data.get_ohlcv(s, self.timeframe, limit=self.lookback)
            if df.empty:
                continue
            closes[s] = df["close"]
            sigs[s] = self._strategy_for(s).generate_signals(df)
            prices[s] = float(df["close"].iloc[-1])

        if not closes:
            return {}, {}

        close_df = pd.DataFrame(closes).dropna()
        if len(close_df.index):
            self._last_bar_ts = close_df.index[-1]
        returns = close_df.pct_change().fillna(0.0)
        signals = pd.DataFrame(
            {s: sigs[s].reindex(close_df.index).ffill().fillna(0.0) for s in closes}
        )
        weights = get_scheme(self.allocation)(returns, signals, self.vol_window)

        # 총 노출 한도
        last = weights.iloc[-1]
        gross = last.abs().sum()
        if gross > self.max_gross and gross > 0:
            last = last * (self.max_gross / gross)
        return last.to_dict(), prices

    def step(self) -> None:
        weights, prices = self._target_weights()
        if not weights:
            log.warning("유효한 종목 데이터 없음, 스킵")
            return

        if hasattr(self.broker, "equity"):
            equity = self.broker.equity(prices)
        else:
            equity = self.broker.get_cash() + sum(
                self.broker.get_position(s).quantity * prices.get(s, 0.0)
                for s in self.symbols
            )

        # 서킷브레이커: 발동 시 전 종목 청산 후 신규 매매 중단.
        # 일자 기준은 벽시계(utcnow)가 아니라 '최근 데이터 봉'의 날짜를 쓴다.
        # 백테스트/재생·시간대 차이에서 벽시계를 쓰면 손실 한도의 '하루'가
        # 데이터와 어긋나(예: 장 마감 후 자정 넘어 실행) 잘못 리셋될 수 있다.
        if self.circuit_breaker is not None:
            day = str(self._last_bar_ts or pd.Timestamp.utcnow())[:10]
            if self.circuit_breaker.update(equity, day):
                log.error("🛑 서킷브레이커 발동(%s) — 전 종목 청산 후 중단",
                          self.circuit_breaker.reason)
                for s, price in prices.items():
                    if price:
                        self.broker.target_weight(s, 0.0, price, equity)
                self._persist(prices)
                return

        for s, w in weights.items():
            price = prices.get(s)
            if not price:
                continue
            order = self.broker.target_weight(s, float(w), price, equity)
            if order is not None and self.notifier is not None:
                self.notifier.send(
                    f"[{self.mode}] {order.side.upper()} {s} "
                    f"{order.quantity:.6f} @ {price:.2f}"
                )

        self.history.append({
            "time": str(pd.Timestamp.utcnow()),
            "equity": equity,
            "weight": float(sum(abs(v) for v in weights.values())),
            "price": 0.0,
        })
        self._persist(prices)

    def snapshot(self, prices: dict[str, float] | None = None) -> dict:
        prices = prices or {}
        positions = []
        for s in self.symbols:
            pos = self.broker.get_position(s)
            if pos.quantity:
                positions.append({
                    "symbol": pos.symbol,
                    "quantity": pos.quantity,
                    "avg_price": pos.avg_price,
                })
        orders = [vars(o) for o in getattr(self.broker, "order_log", [])]
        return {
            "symbol": ", ".join(self.symbols),
            "strategy": getattr(self.strategy, "name", "multi"),
            "mode": self.mode,
            "history": self.history,
            "positions": positions,
            "orders": orders[-30:],
        }

    def _persist(self, prices: dict[str, float] | None = None) -> None:
        snap = self.snapshot(prices)
        if self.state_path:
            p = Path(self.state_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
        if self.dashboard_path:
            from quant.reporting.dashboard import generate_dashboard

            generate_dashboard(snap, self.dashboard_path)

    def run(self, interval_sec: int = 3600, max_iters: int | None = None) -> None:
        i = 0
        while max_iters is None or i < max_iters:
            try:
                self.step()
            except Exception as exc:  # noqa: BLE001
                log.error("사이클 오류: %s", exc)
                if self.notifier is not None:
                    self.notifier.send(f"⚠️ 사이클 오류: {exc}", level="error")
            i += 1
            if max_iters is not None and i >= max_iters:
                break
            time.sleep(interval_sec)
