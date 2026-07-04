"""리스크 서킷브레이커 (kill-switch).

자동매매에서 가장 중요한 안전장치. 버그·이상장·연속 손실 상황에서 계좌가
비어버리기 전에 매매를 강제 중단한다. '잃지 않는 것'이 복리의 핵심이다.

발동 조건:
    - 일일 손실 한도: 하루 시작 자본 대비 -x% 도달
    - 최대 낙폭 한도: 관측 고점 대비 -x% 도달
발동 시 tripped=True가 되어 실시간 루프가 포지션을 청산하고 신규 매매를 멈춘다.
표준 라이브러리만 사용하므로 어디서든 가볍게 쓸 수 있다.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BreakerConfig:
    max_daily_loss: float | None = 0.05   # 하루 -5% 도달 시 중단. None=미사용
    max_drawdown: float | None = 0.20     # 고점 대비 -20% 도달 시 중단. None=미사용


class CircuitBreaker:
    def __init__(self, config: BreakerConfig | None = None, notifier=None):
        self.config = config or BreakerConfig()
        self.notifier = notifier
        self.peak_equity: float | None = None
        self.day_start_equity: float | None = None
        self.current_day: str | None = None
        self.tripped = False
        self.reason = ""

    def update(self, equity: float, day: str) -> bool:
        """현재 자산과 날짜로 상태를 갱신하고, 매매 중단 여부(tripped)를 반환한다.

        day: 날짜 문자열(예: '2026-07-03'). 날짜가 바뀌면 일일 기준을 리셋한다.
        """
        if self.day_start_equity is None or day != self.current_day:
            self.current_day = day
            self.day_start_equity = equity
        self.peak_equity = equity if self.peak_equity is None \
            else max(self.peak_equity, equity)

        cfg = self.config
        if cfg.max_daily_loss is not None and self.day_start_equity > 0:
            daily = equity / self.day_start_equity - 1.0
            if daily <= -cfg.max_daily_loss:
                self._trip(f"일일 손실 한도 도달 ({daily:.2%})")

        if cfg.max_drawdown is not None and self.peak_equity and self.peak_equity > 0:
            dd = equity / self.peak_equity - 1.0
            if dd <= -cfg.max_drawdown:
                self._trip(f"최대 낙폭 한도 도달 ({dd:.2%})")

        return self.tripped

    def _trip(self, reason: str) -> None:
        if not self.tripped:
            self.tripped = True
            self.reason = reason
            if self.notifier is not None:
                self.notifier.send(f"🛑 서킷브레이커 발동: {reason} — 매매 중단", "error")

    def reset(self) -> None:
        """수동 재개 (원인 확인 후에만 호출할 것).

        플래그만 지우면 다음 update()가 여전히 참인 손실 조건을 그대로 재평가해
        즉시 재발동한다(예: 일일 -10%에서 발동 후 reset해도 day_start_equity가
        10,000이면 9,000에서 또 -10%로 재발동). 따라서 기준값(고점·일일 시작
        자본)도 비워, 다음 update()에서 '현재 자산'으로 새 기준 창을 시작한다.
        """
        self.tripped = False
        self.reason = ""
        self.peak_equity = None
        self.day_start_equity = None
        self.current_day = None
