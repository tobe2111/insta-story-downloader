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
from quant.live.summary import load_last_summary_date, notify_daily_summary
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
        daily_max_loss: float | None = None,
        rebalance_band: float = 0.02,
        # 상대 밴드 — 목표 대비 비율. 절대 밴드만 쓰면 포지션이 커질수록
        # 밴드가 상대적으로 촘촘해져 회전율이 폭증한다(통합 계좌 실측).
        # 네 실행 경로(통합·실거래·연속 다종목·단일 종목)를 같은 규칙으로
        # 통일한다 — 규칙을 복사하면 반드시 한 곳이 뒤처진다(2026-08-11).
        rebalance_band_rel: float = 0.15,
        market: str | None = None,
        # 합성 폴백 시세로는 매매하지 않는다(감사 85). 거래소 조회가
        # 전부 실패하면 GBM 난수 걷기가 오는데, 그걸로 실주문을 내면
        # 존재하지 않는 시장에 대고 매매하는 셈이다. 일부러 고른 합성
        # 시장에는 표식이 붙지 않으므로 기본 True로 둬도 안전하다.
        require_real_data: bool = True,
    ):
        self.data = data
        self.strategy = strategy
        self.broker = broker
        self.risk = risk
        self.symbol = symbol
        self.timeframe = timeframe
        self.lookback = lookback
        # 장 시간 가드 — 지정 시(예: 'us_stock'·'kr_stock') 정규장이 아니면 그
        # 사이클의 주문을 건너뛴다. 코인·미지정은 24시간이라 항상 통과. None=미적용.
        self.market = market
        self.require_real_data = require_real_data
        # 리밸런스 데드밴드 — |목표-현재| 비중 차가 이 값 미만이면 주문 생략.
        # vol targeting 등이 만드는 매 봉 잔조정은 기대수익 0에 왕복비용만
        # 확정 지불한다(비용 수학). 청산은 항상 실행. 0이면 비활성.
        self.rebalance_band = max(0.0, rebalance_band)
        self.rebalance_band_rel = max(0.0, rebalance_band_rel)
        self.state_path = state_path
        self.dashboard_path = dashboard_path
        self.notifier = notifier
        self.circuit_breaker = circuit_breaker
        self.mode = mode
        self.history: list[dict] = []
        # 잘려나간 과거의 손익·낙폭 요약(fold_history가 채운다) — 상한에
        # 걸려도 총손익·최대낙폭이 전 기간 기준을 유지하게 한다.
        self.history_summary: dict = {}
        # 일일 최대손실 킬스위치(자동 손실 차단기) — 기본 None=미사용(하위 호환).
        # 상태를 디스크에 영속화해 재시작해도 '오늘은 쉼'이 유지된다.
        self.kill_switch = None
        if daily_max_loss is not None:
            from quant.live.killswitch import DailyLossKillSwitch

            kill_path = (str(Path(state_path).with_suffix(".kill.json"))
                         if state_path else None)
            self.kill_switch = DailyLossKillSwitch(
                daily_max_loss, kill_path, notifier)
        self._last_error: str | None = None
        # 일일 요약 중복 방지 — 재시작 시 기존 state에서 마지막 전송일을 복원.
        self._last_summary_date = load_last_summary_date(state_path)

    def step(self) -> None:
        """한 사이클 실행 (데이터 → 신호 → 사이징 → 주문 → 기록)."""
        # 장 시간 가드: 정규장이 아니면 주문을 내지 않는다(닫힌 시장 주문·거부 방지).
        if self.market is not None:
            from quant.data.market_calendar import holiday_map
            from quant.live.market_hours import is_market_open, market_status
            _hol = holiday_map(getattr(self, "state_dir", "state"))
            if not is_market_open(self.market, holidays=_hol):
                log.info("⏸ %s", market_status(self.market, holidays=_hol))
                return

        df = self.data.get_ohlcv(self.symbol, self.timeframe, limit=self.lookback)
        # 매매해도 되는 데이터인가 — 합성 폴백·무결성 위반을 여기서 거른다.
        # 예전에는 df.empty만 봤다(감사 85). 거래소가 전부 실패해 GBM 난수
        # 걷기가 와도 그대로 매매했다 — 실제 BTC 6천만 원인데 폴백 시세는
        # 100이라 주문 수량이 60만 배 틀린다.
        from quant.data.guard import unusable_reason
        why = unusable_reason(df, require_real_data=self.require_real_data)
        if why:
            log.warning("%s 매매 건너뜀 — %s", self.symbol, why)
            self._last_error = why
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

        # 일일 최대손실 킬스위치: 발동 시 청산(best-effort) 후 다음 UTC 일까지 중단.
        # 리스크 통제 장치이며 손실이 한도 내로 '보장'되지는 않는다(갭 위험).
        if self.kill_switch is not None and self.kill_switch.update(equity):
            if self.kill_switch.just_tripped:
                log.error("🛑 일일 손실 킬스위치 발동 — 포지션 청산 후 "
                          "다음 UTC 일까지 매매 중단")
                try:
                    self.broker.target_weight(self.symbol, 0.0, price, equity)
                except Exception as exc:  # noqa: BLE001 — 청산 실패해도 중단 상태는 유지
                    log.error("킬스위치 청산 주문 실패: %s", exc)
                self.history.append({"time": str(df.index[-1]), "price": price,
                                     "weight": 0.0, "equity": equity})
                self._persist()
            else:
                log.info("일일 킬스위치 할트 중 — 매매 건너뜀 (다음 UTC 일에 재개)")
            return

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

        # 사장님의 전역 스위치(감사 83) — 킬스위치·서킷브레이커 **뒤**에 둔다.
        # 일시정지는 "신규 매매 중단, 보유 유지"이지 "위험 통제를 끈다"가
        # 아니므로, 청산은 위에서 이미 끝난 상태여야 한다.
        from quant.utils.settings import owner_gate
        paused, exposure = owner_gate()
        if paused:
            log.info("⏸ 어드민 일시정지 — 신규 주문 없음(보유 유지)")
            return
        weight *= exposure

        log.info("%s 목표비중=%.2f 가격=%.2f 자산=%.2f",
                 self.symbol, weight, price, equity)
        order = self.broker.target_weight(
            self.symbol, weight, price, equity,
            rebalance_band=self.rebalance_band,
            rebalance_band_rel=self.rebalance_band_rel)
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
            "history_summary": self.history_summary,
            "position": {
                "symbol": pos.symbol,
                "quantity": pos.quantity,
                "avg_price": pos.avg_price,
            },
            "orders": orders,
            # 누적 주문 건수 — orders는 최근 20건만 실리므로 이 값이
            # 없으면 화면의 "거래횟수"가 20에서 영원히 멈춘다.
            "order_count": len(getattr(self.broker, "order_log", [])),
            "last_error": self._last_error,
            "last_summary_date": self._last_summary_date,
            # 감시 탭 배지용 — 킬스위치 발동(오늘 매매 중단) 여부
            "kill_switch_halted": bool(
                self.kill_switch is not None
                and self.kill_switch.halted_until is not None),
        }

    def _persist(self) -> None:
        from quant.utils.jsonio import atomic_write_json, fold_history

        # 무한 성장 방지 — 자르되 잘린 구간의 손익·낙폭은 요약에 남긴다.
        self.history, self.history_summary = fold_history(
            self.history, self.history_summary)
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
                self._last_error = str(exc)
                if self.notifier is not None:
                    self.notifier.send(f"⚠️ 사이클 오류: {exc}", level="error")
            # UTC 날짜 롤오버 시 일일 요약 1회(알림기 있을 때만, 오류는 삼킴)
            notify_daily_summary(self)
            i += 1
            if max_iters is not None and i >= max_iters:
                break
            time.sleep(interval_sec)
