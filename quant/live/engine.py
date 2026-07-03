"""실시간/페이퍼 트레이딩 루프.

주기적으로:
    1. 최신 시세를 가져오고
    2. 전략으로 목표 비중을 계산하고
    3. 리스크 관리자로 사이징한 뒤
    4. 브로커에 목표 비중만큼 주문을 내고
    5. 상태를 기록하고(선택) 모니터링 대시보드를 갱신한다(선택).

--paper 모드에서는 PaperBroker로 안전하게 검증하고,
검증이 끝난 뒤에만 실거래 브로커로 전환하는 것을 강력히 권장한다.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from quant.broker.base import Broker
from quant.data.base import DataProvider
from quant.risk import RiskManager
from quant.strategies.base import Strategy
from quant.utils.logging import get_logger

log = get_logger("live")


class LiveTrader:
    def __init__(
        self,
        data: DataProvider,
        strategy: Strategy,
        broker: Broker,
        risk: RiskManager,
        symbol: str,
        timeframe: str = "1h",
        lookback: int = 300,
        state_path: str | None = None,
        dashboard_path: str | None = None,
        notifier=None,
        mode: str = "paper",
    ):
        self.data = data
        self.strategy = strategy
        self.broker = broker
        self.risk = risk
        self.symbol = symbol
        self.timeframe = timeframe
        self.lookback = lookback
        self.state_path = state_path
        self.dashboard_path = dashboard_path
        self.notifier = notifier
        self.mode = mode
        self.history: list[dict] = []

    def step(self) -> None:
        """한 사이클 실행 (데이터 → 신호 → 사이징 → 주문 → 기록)."""
        df = self.data.get_ohlcv(self.symbol, self.timeframe, limit=self.lookback)
        if df.empty:
            log.warning("데이터 없음, 스킵")
            return

        target = self.strategy.generate_signals(df)
        sized = self.risk.size_positions(df, target)
        weight = float(sized.iloc[-1])
        price = float(df["close"].iloc[-1])

        # 총 자산 추정 (페이퍼 브로커는 equity() 지원)
        if hasattr(self.broker, "equity"):
            equity = self.broker.equity({self.symbol: price})
        else:
            pos = self.broker.get_position(self.symbol)
            equity = self.broker.get_cash() + pos.quantity * price

        log.info("%s 목표비중=%.2f 가격=%.2f 자산=%.2f",
                 self.symbol, weight, price, equity)
        order = self.broker.target_weight(self.symbol, weight, price, equity)
        if order is None:
            log.info("포지션 조정 불필요")
        elif self.notifier is not None:
            self.notifier.send(
                f"[{self.mode}] {order.side.upper()} {self.symbol} "
                f"{order.quantity:.6f} @ {price:.2f}"
            )

        self.history.append({
            "time": str(df.index[-1]),
            "price": price,
            "weight": weight,
            "equity": equity,
        })
        self._persist()

    def snapshot(self) -> dict:
        """현재 상태를 직렬화 가능한 dict로 반환한다."""
        pos = self.broker.get_position(self.symbol)
        orders = [vars(o) for o in getattr(self.broker, "order_log", [])]
        return {
            "symbol": self.symbol,
            "strategy": getattr(self.strategy, "name", "?"),
            "mode": self.mode,
            "history": self.history,
            "position": {
                "symbol": pos.symbol,
                "quantity": pos.quantity,
                "avg_price": pos.avg_price,
            },
            "orders": orders[-20:],
        }

    def _persist(self) -> None:
        snap = None
        if self.state_path:
            snap = self.snapshot()
            p = Path(self.state_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
        if self.dashboard_path:
            from quant.reporting.dashboard import generate_dashboard

            generate_dashboard(snap or self.snapshot(), self.dashboard_path)

    def run(self, interval_sec: int = 3600, max_iters: int | None = None) -> None:
        """주기적으로 step()을 반복한다."""
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
