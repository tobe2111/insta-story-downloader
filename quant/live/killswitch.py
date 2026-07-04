"""일일 최대손실 킬스위치 — 자동 손실 차단기 (리스크 통제 장치).

하루(UTC 일자) 시작 자본 대비 손실이 한도(daily_max_loss)에 도달하면:
    1. 발동 사이클에서 포지션을 청산하고(호출자 책임, best-effort)
    2. '다음 UTC 일자까지 매매 중단' 플래그를 상태 파일에 영속화한다.
       → 프로세스가 재시작돼도 그날은 다시 매매하지 않는다.
    3. 다음 UTC 일자가 되면 자동으로 재개한다.

CircuitBreaker(circuit_breaker.py)와의 차이: 서킷브레이커는 수동 reset까지
영구 정지(메모리 상태)이고, 킬스위치는 '그날 하루만' 쉬고 자동 재개하며
재시작에도 살아남는 디스크 영속 상태를 가진다. 둘은 함께 써도 된다.

⚠️ 이것은 리스크 통제 장치일 뿐이다 — 손실을 '제한'하려는 시도이지 수익을
   보장하지 않으며, 갭·유동성 공백에서는 한도보다 큰 손실이 날 수 있다.
   구독·기능 게이팅과는 무관하다.
표준 라이브러리만 사용한다.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from quant.utils.logging import get_logger

log = get_logger("live.killswitch")


class DailyLossKillSwitch:
    def __init__(
        self,
        daily_max_loss: float | None = None,
        state_path: str | None = None,
        notifier=None,
    ):
        """daily_max_loss: 예 0.03 = 하루 -3% 도달 시 발동. None = 미사용(기본).

        state_path 지정 시 발동 상태를 JSON으로 영속화한다(원자적 쓰기).
        """
        self.daily_max_loss = daily_max_loss
        self.state_path = state_path
        self.notifier = notifier
        self.day: str | None = None                 # 현재 UTC 일자
        self.day_start_equity: float | None = None  # 그날 시작 자본
        self.halted_until: str | None = None        # 이 UTC 일자 전까지 매매 중단
        self.just_tripped = False                   # 이번 update에서 갓 발동했는가
        self._load()

    @staticmethod
    def _utc_day(now: datetime | None = None) -> str:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:                       # naive는 UTC로 간주
            now = now.replace(tzinfo=timezone.utc)
        return now.astimezone(timezone.utc).date().isoformat()

    def update(self, equity: float, now: datetime | None = None) -> bool:
        """현재 자산으로 상태를 갱신한다. True = 이번 사이클 매매를 건너뛸 것.

        갓 발동한 사이클에서는 just_tripped=True 이므로, 호출자는 그때 한 번만
        포지션 청산(best-effort)을 수행하면 된다.
        """
        self.just_tripped = False
        if self.daily_max_loss is None:              # 기본: 비활성(하위 호환)
            return False

        today = self._utc_day(now)

        # 할트 중이면 만료 확인 — 다음 UTC 일자가 되면 자동 재개
        if self.halted_until is not None:
            if today < self.halted_until:
                return True
            log.info("일일 킬스위치 할트 해제 (UTC %s) — 매매 재개", today)
            self.halted_until = None
            self.day = None                          # 새 날 기준으로 재시작

        # UTC 일자 경계에서 하루 시작 자본 리셋
        if self.day != today or self.day_start_equity is None:
            self.day = today
            self.day_start_equity = equity
            self._save()
            return False                             # 하루 첫 관측은 손실 0

        if self.day_start_equity > 0:
            daily = equity / self.day_start_equity - 1.0
            if daily <= -self.daily_max_loss:
                next_day = (date.fromisoformat(today)
                            + timedelta(days=1)).isoformat()
                self.halted_until = next_day
                self.just_tripped = True
                self._save()
                msg = (f"🛑 일일 손실 킬스위치 발동 ({daily:.2%} ≤ "
                       f"-{self.daily_max_loss:.2%}) — 포지션 청산 후 "
                       f"UTC {next_day}까지 매매 중단")
                log.error(msg)
                if self.notifier is not None:
                    try:
                        self.notifier.send(msg, "error")
                    except Exception as exc:  # noqa: BLE001 — 알림 실패로 차단을 막지 않는다
                        log.warning("킬스위치 알림 실패: %s", exc)
                return True
        return False

    # ---------------- 영속화 (재시작에도 '오늘은 쉼'이 유지되도록) ----------------

    def _save(self) -> None:
        if not self.state_path:
            return
        from quant.utils.jsonio import atomic_write_json

        try:
            atomic_write_json(self.state_path, {
                "day": self.day,
                "day_start_equity": self.day_start_equity,
                "halted_until": self.halted_until,
            })
        except OSError as exc:
            log.warning("킬스위치 상태 저장 실패: %s", exc)

    def _load(self) -> None:
        if not self.state_path or not Path(self.state_path).exists():
            return
        try:
            raw = json.loads(Path(self.state_path).read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            log.warning("킬스위치 상태 로드 실패(%s) — 새로 시작합니다.", exc)
            return
        if not isinstance(raw, dict):
            return
        self.day = raw.get("day") or None
        eq = raw.get("day_start_equity")
        self.day_start_equity = float(eq) if isinstance(eq, (int, float)) else None
        self.halted_until = raw.get("halted_until") or None
