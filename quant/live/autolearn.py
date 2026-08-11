"""자동 페이퍼 트레이딩 + 지속 재학습 + 정확도 추적 루프.

매 사이클마다:
    1. 최신 데이터를 받아
    2. 전략의 목표비중을 계산하고 (ML 전략이면 여기서 walk-forward 재학습)
    3. 페이퍼 브로커로 목표비중만큼 매매하고
    4. 방향 예측 '정확도'와 자본을 기록한다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ 정직한 설명 — 이 루프는 정확도를 '영구히 올리지' 않는다.
    재학습은 모델을 '최신 시장에 맞추는' 것이지, 정확도를 100%로 끌어올리는
    게 아니다. 방향 예측 정확도는 대개 50~55% 사이에서 오르내리며, 어떤
    데이터·재학습으로도 그 천장을 뚫지 못한다. 이 루프의 목적은 그 현실을
    '기록하고 보여주는' 것 — 좋아지면 좋아졌다고, 나빠지면 나빠졌다고 알려
    준다. "학습할수록 정확해져서 무조건 수익"은 사기다. 이건 그 반대다.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import time

from quant.broker.base import Broker
from quant.data.base import DataProvider
from quant.live.summary import load_last_summary_date, notify_daily_summary
from quant.risk import RiskManager
from quant.robustness.accuracy import directional_accuracy
from quant.strategies.base import Strategy
from quant.utils.logging import get_logger

log = get_logger("autolearn")


class AutoLearner:
    """페이퍼 브로커 위에서 지속 재학습하며 정확도를 추적하는 자동 러너."""

    def __init__(
        self,
        data: DataProvider,
        strategy: Strategy,
        broker: Broker,
        risk: RiskManager,
        symbol: str,
        timeframe: str = "1d",
        lookback: int = 400,
        accuracy_window: int = 60,
        state_path: str | None = None,
        notifier=None,
    ):
        self.data = data
        self.strategy = strategy
        self.broker = broker
        self.risk = risk
        self.symbol = symbol
        self.timeframe = timeframe
        self.lookback = lookback
        self.accuracy_window = accuracy_window
        self.state_path = state_path
        self.notifier = notifier
        self.history: list[dict] = []
        # 잘려나간 과거의 손익·낙폭 요약 — 아래 fold_history가 채운다.
        self.history_summary: dict = {}
        self._last_error: str | None = None
        # 일일 요약 중복 방지 — 재시작 시 기존 state에서 마지막 전송일을 복원.
        self._last_summary_date = load_last_summary_date(state_path)

    def cycle(self) -> dict:
        """한 사이클: 데이터→(재학습)신호→페이퍼 매매→정확도·자본 기록."""
        df = self.data.get_ohlcv(self.symbol, self.timeframe, limit=self.lookback)
        if df.empty:
            log.warning("데이터 없음, 사이클 스킵")
            return {}

        signals = self.strategy.generate_signals(df)     # ML은 여기서 재학습
        sized = self.risk.size_positions(df, signals)
        weight = float(sized.iloc[-1])
        price = float(df["close"].iloc[-1])
        equity = self.broker.equity({self.symbol: price})

        self.broker.target_weight(self.symbol, weight, price, equity)

        acc = directional_accuracy(df, signals, window=self.accuracy_window)
        # 최근 구간(롤링) 정확도 — 정확도가 시간에 따라 어떻게 변하는지
        recent = float("nan")
        if "rolling" in acc and len(acc["rolling"]):
            tail = acc["rolling"].dropna()
            if len(tail):
                recent = float(tail.iloc[-1])

        record = {
            "time": str(df.index[-1]),
            "price": price,
            "weight": weight,
            "equity": equity,
            "hit_rate": acc["hit_rate"],          # 전체 적중률
            "recent_hit_rate": recent,            # 최근 window봉 적중률
            "n": acc["n"],
        }
        self.history.append(record)
        self._persist()

        hr = acc["hit_rate"]
        log.info("사이클: 자본=%.2f 비중=%.2f 정확도(전체)=%s 정확도(최근)=%s",
                 equity, weight,
                 f"{hr:.1%}" if hr == hr else "N/A",
                 f"{recent:.1%}" if recent == recent else "N/A")
        return record

    def snapshot(self) -> dict:
        """현재 상태를 직렬화 가능한 dict로 반환한다(저장·일일 요약 공용)."""
        pos = self.broker.get_position(self.symbol)
        # 최근 20건만 dict화(전체 order_log를 매번 vars()하지 않는다).
        orders = [vars(o) for o in getattr(self.broker, "order_log", [])[-20:]]
        return {
            "symbol": self.symbol,
            "strategy": getattr(self.strategy, "name", "?"),
            "mode": "paper-autolearn",
            "history": self.history,
            "history_summary": self.history_summary,
            "position": {"symbol": pos.symbol, "quantity": pos.quantity,
                         "avg_price": pos.avg_price},
            "orders": orders,
            # 누적 주문 건수 — orders는 최근 20건만 실리므로 이 값이
            # 없으면 화면의 "거래횟수"가 20에서 영원히 멈춘다.
            "order_count": len(getattr(self.broker, "order_log", [])),
            "last_error": self._last_error,
            "last_summary_date": self._last_summary_date,
        }

    def _persist(self) -> None:
        if not self.state_path:
            return
        from quant.utils.jsonio import atomic_write_json, fold_history

        # 무한 성장 방지 — 자르되 잘린 구간의 손익·낙폭은 요약에 남긴다.
        self.history, self.history_summary = fold_history(
            self.history, self.history_summary)
        # NaN 안전(hit_rate 등이 NaN이면 대시보드 JSON.parse가 멈춘다) + 원자적 쓰기.
        atomic_write_json(self.state_path, self.snapshot())

    def run(self, cycles: int | None = None, interval_sec: int = 3600) -> list[dict]:
        """사이클을 반복한다. cycles=None 이면 무기한(사용자가 멈출 때까지).

        정확도가 계속 오를 거라 기대하지 말 것 — 이 루프는 '현실을 기록'한다.
        """
        i = 0
        while cycles is None or i < cycles:
            try:
                self.cycle()
            except Exception as exc:  # noqa: BLE001
                log.error("사이클 오류: %s", exc)
                self._last_error = str(exc)
                if self.notifier is not None:
                    self.notifier.send(f"⚠️ 자동학습 사이클 오류: {exc}", level="error")
            # UTC 날짜 롤오버 시 일일 요약 1회(알림기 있을 때만, 오류는 삼킴)
            notify_daily_summary(self)
            i += 1
            if cycles is not None and i >= cycles:
                break
            time.sleep(interval_sec)
        return self.history
