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
        # 상대 밴드 — 목표 대비 비율. 절대 밴드만 쓰면 포지션이 커질수록
        # 밴드가 상대적으로 촘촘해져 회전율이 폭증한다(통합 계좌에서 실제로
        # 겪은 문제). 두 밴드 중 더 큰 문턱이 적용된다(2026-08-11 통일).
        rebalance_band_rel: float = 0.15,
        market: str | None = None,
        # 합성 폴백 시세로는 매매하지 않는다(감사 85). 일부러 고른 합성
        # 시장에는 표식이 붙지 않으므로 기본 True로 둬도 안전하다.
        require_real_data: bool = True,
    ):
        self.data = data
        self.strategy = strategy
        self.broker = broker
        self.circuit_breaker = circuit_breaker
        self.symbols = list(symbols)
        self.timeframe = timeframe
        self.lookback = lookback
        # 장 시간 가드 — 지정 시 정규장이 아니면 그 사이클을 건너뛴다(코인=항상 통과).
        self.market = market
        self.require_real_data = require_real_data
        self.allocation = allocation
        self.max_gross = max_gross
        self.vol_window = vol_window
        # 리밸런스 데드밴드 — 종목별 |목표-현재| 비중 차가 이 값 미만이면 주문
        # 생략(잔조정 왕복비용의 결정론적 환급). 청산은 항상 실행. 0=비활성.
        self.rebalance_band = max(0.0, rebalance_band)
        self.rebalance_band_rel = max(0.0, rebalance_band_rel)
        self.state_path = state_path
        self.dashboard_path = dashboard_path
        self.notifier = notifier
        self.mode = mode
        self.history: list[dict] = []
        # 잘려나간 과거의 손익·낙폭 요약 — 아래 fold_history가 채운다.
        self.history_summary: dict = {}
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
        # 킬스위치가 발동했는데 비우지 못한 종목(감사 80). 빈 리스트는
        # '전부 비웠다'는 확인이고, 값이 있으면 그 종목은 아직 열려 있다.
        self._kill_unflattened: list[str] = []
        # 이번 사이클에 거부된 주문(감사 81). 한 종목 실패가 나머지를
        # 막지 않되, 실패했다는 사실은 장부에 남는다.
        self._failed_orders: list[str] = []
        # 데이터 때문에 제외된 종목과 그 이유(감사 85)
        self._skipped_data: dict[str, str] = {}

    def _strategy_for(self, symbol: str) -> Strategy:
        return self.strategy(symbol) if callable(self.strategy) else self.strategy

    def _target_weights(self) -> tuple[dict[str, float], dict[str, float]]:
        """각 종목의 목표비중과 현재가를 계산한다."""
        from quant.data.guard import unusable_reason

        closes, sigs, prices = {}, {}, {}
        self._skipped_data: dict[str, str] = {}
        for s in self.symbols:
            df = self.data.get_ohlcv(s, self.timeframe, limit=self.lookback)
            # 매매해도 되는 데이터인가 — 종목별로 거른다(감사 85). 예전에는
            # df.empty만 봤다. 거래소 조회가 전부 실패하면 GBM 난수 걷기가
            # 오는데 그걸로 실주문을 내면 존재하지 않는 시장에 매매하는 셈이다.
            # 한 종목이 나쁘다고 나머지까지 멈추지는 않는다.
            why = unusable_reason(df, require_real_data=self.require_real_data)
            if why:
                log.warning("%s 제외 — %s", s, why)
                self._skipped_data[s] = why
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
        # 장 시간 가드: 정규장이 아니면 주문 사이클을 건너뛴다.
        if self.market is not None:
            from quant.data.market_calendar import holiday_map
            from quant.live.market_hours import is_market_open, market_status
            _hol = holiday_map(getattr(self, "state_dir", "state"))
            if not is_market_open(self.market, holidays=_hol):
                log.info("⏸ %s", market_status(self.market, holidays=_hol))
                return

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
                self._flatten_all(prices, equity, "킬스위치")
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
                self._flatten_all(prices, equity, "서킷브레이커")
                self._persist(prices)
                return

        # ⚠️ 주문은 종목마다 독립적으로 실패할 수 있다(감사 81). 예전에는
        #    try 없이 돌아서 한 종목이 거부되면 **나머지 종목 주문이 아예 안
        #    나가고, 그 사이클 기록조차 장부에 남지 않았다** — 매매는 일부
        #    일어났는데 장부에는 그날이 없는 상태다. 실패는 삼키지 않고
        #    장부·알림에 남긴다.
        # 사장님의 전역 스위치(감사 83) — 킬스위치·서킷브레이커 **뒤**에 둔다.
        # 일시정지는 "신규 매매 중단, 보유 유지"이지 "위험 통제를 끈다"가 아니다.
        from quant.utils.settings import owner_gate
        paused, exposure = owner_gate()
        if paused:
            log.info("⏸ 어드민 일시정지 — 신규 주문 없음(보유 유지)")
            return
        if exposure != 1.0:
            weights = {k: v * exposure for k, v in weights.items()}

        failed: list[str] = []
        # 기록할 노출은 '목표'가 아니라 **실제로 주문이 나간 종목**의 합이다
        # (2026-08-11 감사 93 — 91·92와 같은 계열). 가격이 없어 건너뛰거나
        # 주문이 예외로 실패한 종목까지 세면, 장부가 들지도 않은 포지션을
        # 노출로 말한다 — 하필 데이터·브로커가 흔들리는 날에 과대 보고한다.
        placed: dict[str, float] = {}
        for s, w in weights.items():
            price = prices.get(s)
            if not price:
                continue
            try:
                order = self.broker.target_weight(
                    s, float(w), price, equity,
                    rebalance_band=self.rebalance_band,
                    rebalance_band_rel=self.rebalance_band_rel)
            except Exception as exc:  # noqa: BLE001 — 한 종목 실패가 전체를 막지 않게
                log.error("주문 실패(%s): %s", s, exc)
                failed.append(f"{s}({type(exc).__name__})")
                continue
            # order is None = 밴드 안(이미 목표 근처) — 노출은 유지되므로 센다.
            placed[s] = float(w)
            if order is not None and self.notifier is not None:
                self.notifier.send(
                    f"[{self.mode}] {order.side.upper()} {s} "
                    f"{order.quantity:.6f} @ {price:.2f}"
                )
        self._failed_orders = failed
        if failed:
            msg = f"⚠️ 주문 실패 {len(failed)}건 — {', '.join(failed)}"
            log.error(msg)
            if self.notifier is not None:
                try:
                    self.notifier.send(msg, level="error")
                except Exception as exc:  # noqa: BLE001
                    log.error("주문 실패 알림 전송 실패: %s", exc)

        self.history.append({
            "time": str(pd.Timestamp.utcnow()),
            "equity": equity,
            "weight": float(sum(abs(v) for v in placed.values())),
            "price": 0.0,
        })
        self._persist(prices)

    def _flatten_all(self, prices: dict, equity: float, why: str) -> list[str]:
        """전 종목 청산을 시도하고 **비우지 못한 종목**을 돌려준다.

        ⚠️ 킬스위치와 서킷브레이커가 반드시 이 함수를 쓴다(감사 80). 예전에는
        두 곳에 청산 루프가 따로 적혀 있었고, 둘 다 `prices.items()`를 돌았다.
        `prices`는 `_target_weights()`가 만드는데 거기서 **데이터가 빈 종목은
        건너뛴다** — 즉 그 사이클에 시세를 못 받은 종목은 청산 시도조차 되지
        않았다. 두 장치 모두 그날 매매를 멈추므로 그 포지션은 다음 날까지
        열린 채 남는다. 손실이 커져서 멈춘 바로 그 상황에서다.

        가장 나쁜 건 **아무도 모른다는 것**이었다 — 로그와 알림은 "전 종목
        청산"이라고 말한다. 시세 없이 주문을 낼 수는 없으니, 대신 **확인한
        사실만 말한다**: 못 비운 종목을 장부와 알림에 남긴다.
        """
        unflat: list[str] = []
        for s in self.symbols:
            try:
                held = float(self.broker.get_position(s).quantity)
            except Exception as exc:  # noqa: BLE001
                log.error("보유 조회 실패(%s): %s", s, exc)
                held = float("nan")       # 모름 — '없음'으로 반올림하지 않는다
            if held == 0.0:
                continue                  # 이미 비어 있다
            price = prices.get(s)
            if not price:
                unflat.append(f"{s}(시세 없음)")
                continue
            try:
                self.broker.target_weight(s, 0.0, price, equity)
            except Exception as exc:  # noqa: BLE001 — 하나 실패해도 나머지는 계속
                log.error("%s 청산 실패(%s): %s", why, s, exc)
                unflat.append(f"{s}({type(exc).__name__})")
        self._kill_unflattened = unflat
        if unflat:
            msg = (f"🛑 {why} 청산 **미완료** — 아래 종목은 비우지 못했습니다"
                   f"(포지션 유지 중): {', '.join(unflat)}")
            log.error(msg)
            if self.notifier is not None:
                try:
                    self.notifier.send(msg, level="error")
                except Exception as exc:  # noqa: BLE001
                    log.error("%s 미완료 알림 실패: %s", why, exc)
        return unflat

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
            "history_summary": self.history_summary,
            "positions": positions,
            "orders": orders,
            # 누적 주문 건수 — orders는 최근 20건만 실리므로 이 값이
            # 없으면 화면의 "거래횟수"가 20에서 영원히 멈춘다.
            "order_count": len(getattr(self.broker, "order_log", [])),
            # 상관 레짐 모니터 — 1에 가까울수록 분산 효과가 약한 국면
            "avg_correlation": self._avg_corr,
            "last_error": self._last_error,
            "last_summary_date": self._last_summary_date,
            # 감시 탭 배지용 — 킬스위치 발동(오늘 매매 중단) 여부
            "kill_switch_halted": bool(
                self.kill_switch is not None
                and self.kill_switch.halted_until is not None),
            # 킬스위치가 발동했는데 비우지 못한 종목(감사 80). None/빈 값은
            # '전부 비웠다'는 확인이고, 값이 있으면 그 종목은 아직 열려 있다.
            # "전 종목 청산"이라는 문구를 그대로 믿으면 안 되는 유일한 경우다.
            "kill_switch_unflattened": list(self._kill_unflattened) or None,
            # 이번 사이클에 거부된 주문(감사 81) — 목표 비중과 실제
            # 보유가 왜 다른지에 답할 수 있어야 한다.
            "failed_orders": list(self._failed_orders) or None,
            # 데이터 때문에 빠진 종목(감사 85) — 조용히 건너뛴 사이클은
            # 나중에 "왜 이 종목이 없었나"에 답할 수 없다.
            "skipped_data": dict(self._skipped_data) or None,
        }

    def _persist(self, prices: dict[str, float] | None = None) -> None:
        from quant.utils.jsonio import atomic_write_json, fold_history

        # 무한 성장 방지 — 자르되 잘린 구간의 손익·낙폭은 요약에 남긴다.
        self.history, self.history_summary = fold_history(
            self.history, self.history_summary)
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
