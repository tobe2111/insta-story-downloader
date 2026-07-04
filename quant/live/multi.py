"""다중 종목 실시간 동시 운용 (MultiTrader).

여러 종목의 신호를 계산하고, 포트폴리오 자산배분(균등/변동성역가중)으로
자본을 나눠 각 종목에 목표비중 주문을 낸다. 단일 종목 대비 분산 효과로
변동성과 낙폭이 줄어든다.

상태(state)에는 종목별 포지션과 통합 자본곡선이 함께 기록되어, 하나의
대시보드에서 전체 포트폴리오를 모니터링할 수 있다.
"""
from __future__ import annotations

import time
from typing import Callable, Sequence

import pandas as pd

from quant.broker.base import Broker
from quant.data.base import DataProvider
from quant.live.summary import load_last_summary_date, notify_daily_summary
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
        daily_max_loss: float | None = None,
        rebalance_band: float = 0.02,
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
        # 리밸런스 데드밴드 — 종목별 |목표-현재| 비중 차가 이 값 미만이면 주문
        # 생략(잔조정 왕복비용의 결정론적 환급). 청산은 항상 실행. 0=비활성.
        self.rebalance_band = max(0.0, rebalance_band)
        self.state_path = state_path
        self.dashboard_path = dashboard_path
        self.notifier = notifier
        self.mode = mode
        self.history: list[dict] = []
        self._last_bar_ts = None        # 최근 데이터 봉의 타임스탬프(서킷브레이커 일자 기준)
        self._avg_corr: float | None = None   # 최근 롤링 평균 상관(상관 레짐 모니터)
        # 일일 최대손실 킬스위치(자동 손실 차단기) — 기본 None=미사용(하위 호환).
        self.kill_switch = None
        if daily_max_loss is not None:
            from pathlib import Path

            from quant.live.killswitch import DailyLossKillSwitch

            kill_path = (str(Path(state_path).with_suffix(".kill.json"))
                         if state_path else None)
            self.kill_switch = DailyLossKillSwitch(
                daily_max_loss, kill_path, notifier)
        self._last_error: str | None = None
        # 일일 요약 중복 방지 — 재시작 시 기존 state에서 마지막 전송일을 복원.
        self._last_summary_date = load_last_summary_date(state_path)

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
        # 상관 레짐 모니터: 쌍별 상관의 롤링 평균(최근값). 급등하면 분산 효과가
        # 사라지는 국면일 수 있다 — 대시보드/알림에서 노출 축소 판단 참고용.
        self._avg_corr = None
        if returns.shape[1] >= 2 and len(returns) >= self.vol_window:
            try:
                from quant.risk.portfolio import rolling_avg_correlation

                v = rolling_avg_correlation(returns, self.vol_window).iloc[-1]
                self._avg_corr = float(v) if pd.notna(v) else None
            except Exception as exc:  # noqa: BLE001 — 모니터링 실패가 매매를 막지 않게
                log.warning("평균 상관 계산 실패: %s", exc)
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

        # 일일 최대손실 킬스위치: 발동 시 전 종목 청산(best-effort) 후
        # 다음 UTC 일까지 중단. 리스크 통제 장치 — 갭에서는 한도 초과 손실 가능.
        if self.kill_switch is not None and self.kill_switch.update(equity):
            if self.kill_switch.just_tripped:
                log.error("🛑 일일 손실 킬스위치 발동 — 전 종목 청산 후 "
                          "다음 UTC 일까지 매매 중단")
                for s, price in prices.items():
                    if not price:
                        continue
                    try:
                        self.broker.target_weight(s, 0.0, price, equity)
                    except Exception as exc:  # noqa: BLE001 — 일부 실패해도 계속 청산 시도
                        log.error("킬스위치 청산 실패(%s): %s", s, exc)
                self._persist(prices)
            else:
                log.info("일일 킬스위치 할트 중 — 매매 건너뜀 (다음 UTC 일에 재개)")
            return

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
            order = self.broker.target_weight(s, float(w), price, equity,
                                              rebalance_band=self.rebalance_band)
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
        # 최근 30건만 dict화(전체 order_log를 매번 vars()하지 않는다).
        orders = [vars(o) for o in getattr(self.broker, "order_log", [])[-30:]]
        return {
            "symbol": ", ".join(self.symbols),
            "strategy": getattr(self.strategy, "name", "multi"),
            "mode": self.mode,
            "history": self.history,
            "positions": positions,
            "orders": orders,
            # 상관 레짐 모니터 — 1에 가까울수록 분산 효과가 약한 국면
            "avg_correlation": self._avg_corr,
            "last_error": self._last_error,
            "last_summary_date": self._last_summary_date,
        }

    def _persist(self, prices: dict[str, float] | None = None) -> None:
        from quant.utils.jsonio import atomic_write_json, cap_history

        self.history = cap_history(self.history)      # 무한 성장 방지(대시보드 점 수도 제한)
        snap = self.snapshot(prices)
        if self.state_path:
            # NaN 안전 + 원자적 쓰기(부분/손상 방지).
            atomic_write_json(self.state_path, snap)
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
                self._last_error = str(exc)
                if self.notifier is not None:
                    self.notifier.send(f"⚠️ 사이클 오류: {exc}", level="error")
            # UTC 날짜 롤오버 시 일일 요약 1회(알림기 있을 때만, 오류는 삼킴)
            notify_daily_summary(self)
            i += 1
            if max_iters is not None and i >= max_iters:
                break
            time.sleep(interval_sec)
