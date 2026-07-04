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
        circuit_breaker=None,
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
        self.circuit_breaker = circuit_breaker
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

        # 서킷브레이커: 발동 시 포지션 청산 후 신규 매매 중단
        if self.circuit_breaker is not None:
            day = str(df.index[-1])[:10]
            if self.circuit_breaker.update(equity, day):
                log.error("🛑 서킷브레이커 발동(%s) — 포지션 청산 후 중단",
                          self.circuit_breaker.reason)
                self.broker.target_weight(self.symbol, 0.0, price, equity)
                self.history.append({"time": str(df.index[-1]), "price": price,
                                     "weight": 0.0, "equity": equity})
                self._persist()
                return

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
        # 최근 20건만 dict화 — 전체 order_log를 매번 vars()하지 않는다(장기 실행 비용).
        orders = [vars(o) for o in getattr(self.broker, "order_log", [])[-20:]]
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
            "orders": orders,
        }

    def _persist(self) -> None:
        from quant.utils.jsonio import atomic_write_json, cap_history

        self.history = cap_history(self.history)      # 무한 성장 방지
        snap = None
        if self.state_path:
            snap = self.snapshot()
            # NaN 안전(대시보드 JSON.parse 방지) + 원자적 쓰기(부분/손상 방지).
            atomic_write_json(self.state_path, snap)
        if self.dashboard_path:
            from quant.reporting.dashboard import generate_dashboard

            generate_dashboard(snap or self.snapshot(), self.dashboard_path)

    def reconcile(self) -> None:
        """재시작 시 실제 브로커 포지션과 직전 저장 상태를 대조한다.

        봇이 꺼진 사이 수동매매·부분체결·미체결 등으로 실제 보유가 예상과
        달라질 수 있다. 시작할 때 실제 포지션을 확인해 로그·알림으로 남긴다.
        """
        actual = self.broker.get_position(self.symbol)
        prev = None
        if self.state_path and Path(self.state_path).exists():
            try:
                prev = json.loads(Path(self.state_path).read_text(encoding="utf-8"))
            except (ValueError, OSError):
                prev = None

        msg = f"🔄 재시작 정합성 확인: {self.symbol} 실제 보유 {actual.quantity:.6f}"
        if prev and prev.get("history"):
            last_w = prev["history"][-1].get("weight", 0.0)
            msg += f" · 직전 목표비중 {last_w:+.2f}"
            # 직전엔 관망(비중 0)이었는데 실제 포지션이 남아 있으면 경고
            if abs(last_w) < 1e-9 and abs(actual.quantity) > 0:
                msg += "  ⚠️ 관망 상태였는데 잔여 포지션 있음 — 확인 필요"
        log.info(msg)
        if self.notifier is not None:
            self.notifier.send(msg)

    def run(self, interval_sec: int = 3600, max_iters: int | None = None) -> None:
        """주기적으로 step()을 반복한다 (시작 시 포지션 정합성 확인 포함)."""
        try:
            self.reconcile()
        except Exception as exc:  # noqa: BLE001
            log.warning("정합성 확인 실패: %s", exc)
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
