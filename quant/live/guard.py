"""장중 감시 — **하루 1회 판단으로는 레버리지를 지킬 수 없다.**

⚠️ 왜 이 파일이 생겼나 (2026-08-14, 선물 준비 ②단계).

    킬스위치(-15%/-25%)와 서킷브레이커는 **새벽 배치에서 하루 한 번** 돈다.
    현물은 그래도 된다 — 최악이어도 자산이 0 아래로 안 가니 다음 아침에
    처리하면 된다.

    레버리지는 그 전제가 깨진다. 거래소는 실시간으로 청산하고 우리는 배치가
    돌 때만 본다. 그 사이에 끝나면 킬스위치는 **선언만 남는다.**

⚠️ **이 파일의 핵심은 감시가 아니라 '얼마나 자주 봤는지를 기록하는 것'이다.**

    감시 루프를 15분마다 돌게 설정해 놓고 "15분마다 봅니다"라고 적는 것은
    쉽다. 그런데 워크플로가 밀리거나, 네트워크가 죽거나, 잡이 조용히 실패하면
    실제 간격은 몇 시간이 된다. **의도한 주기로 레버리지 한도를 계산하면
    그 한도는 거짓이다.**

    그래서 매 회차 심장박동을 남기고, 레버리지 관문은 **실제로 관측된 최악의
    간격**을 쓴다(observed_gap_minutes). 설정값이 아니라 실측이다 — 이
    저장소가 계속 지켜온 규칙이고, 여기서는 그게 돈과 직결된다.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from quant.utils.logging import get_logger

log = get_logger("live.guard")

HEARTBEAT_FILE = "guard_heartbeat.json"

# 심장박동을 몇 개나 되짚어 '최악의 간격'을 볼 것인가.
# 짧으면 어제의 장애를 잊고, 길면 옛 사고가 영원히 발목을 잡는다.
HEARTBEAT_KEEP = 500

# 기록이 이만큼도 없으면 **관측된 간격을 모른다**고 본다.
MIN_BEATS_FOR_GAP = 10

# 예약한 감시 주기(분) — .github/workflows/guard.yml의 cron과 같아야 한다.
# 여기에 적는 이유: 배포판에는 .github/가 안 실린다. 두 곳이 갈라지지 않게
# 검사가 워크플로의 cron과 이 값을 맞대어 본다.
GUARD_INTERVAL_MINUTES = 5   # 2026-08-18 주기 사다리(5분봉 트랙)와 함께 상향

# 실제 간격이 예약 주기의 몇 배를 넘으면 '예약대로 안 돌고 있다'고 보는가.
# ⚠️ 2026-08-16 실측: 예약은 15분인데 관측 최악 간격이 **558분**이었다
#    (GitHub의 공용 러너는 촘촘한 cron을 크게 밀거나 건너뛴다). 즉 "15분마다
#    본다"는 문장은 **설정을 옮겨 적은 것이지 사실이 아니었다.** 레버리지
#    한도는 이미 실측을 쓰므로 안전 쪽으로 계산되지만, 그 사실이 사람에게
#    닿지 않으면 문서와 대외 문구는 계속 거짓말을 한다.
# 2026-08-18 주기 상향(15→5분)과 함께 4.0 → 12.0. 문턱의 뜻을 지키기
# 위해서다: 크론이 한두 번 밀린 정도(공용 러너에서 30분은 일상)로 울리면
# 아무도 안 보게 되고, 진짜 사고(실측 558분)는 반드시 걸려야 한다.
# 5×12=60분 — 두 조건을 모두 만족하는 문턱이다.
GUARD_LATE_FACTOR = 12.0


@dataclass
class GuardState:
    beats: list[str] = field(default_factory=list)     # ISO 타임스탬프
    actions: list[dict] = field(default_factory=list)  # 실제로 한 조치


def _path(state_dir: str) -> str:
    return os.path.join(state_dir, HEARTBEAT_FILE)


def load_heartbeat(state_dir: str = "state") -> GuardState:
    try:
        with open(_path(state_dir), encoding="utf-8") as f:
            d = json.load(f)
        return GuardState(list(d.get("beats") or []), list(d.get("actions") or []))
    except (OSError, json.JSONDecodeError):
        return GuardState()


def record_heartbeat(now_iso: str, *, state_dir: str = "state",
                     action: dict | None = None) -> GuardState:
    """감시가 **실제로 돌았다**는 사실을 남긴다.

    ⚠️ 시각을 인자로 받는 이유: 이 저장소는 `Date.now()`류 숨은 입력을
       쓰지 않는다. 부르는 쪽이 시각을 대면 검사가 시간을 통제할 수 있고,
       기록의 재현도 가능해진다.
    """
    st = load_heartbeat(state_dir)
    st.beats.append(str(now_iso))
    st.beats = st.beats[-HEARTBEAT_KEEP:]
    if action:
        st.actions.append({"time": str(now_iso), **action})
        st.actions = st.actions[-HEARTBEAT_KEEP:]
    os.makedirs(state_dir, exist_ok=True)
    from quant.utils.jsonio import atomic_write_json
    atomic_write_json(_path(state_dir),
                      {"beats": st.beats, "actions": st.actions})
    return st


def observed_gap_minutes(state_dir: str = "state",
                         *, now_iso: str | None = None) -> float | None:
    """**실제로 관측된 최악의 감시 간격**(분). 모르면 None.

    ⚠️ 설정한 주기가 아니라 **일어난 일**을 돌려준다. 레버리지 한도는 이
       값으로 계산해야 한다 — 15분마다 돌기로 해 놓고 실제로 3시간 벌어진
       날이 있었다면, 그 3시간이 우리가 감당해야 할 진실이다.

    now_iso를 주면 '마지막 심장박동 이후 지금까지'도 간격으로 센다.
    감시가 **지금 멈춰 있는** 상태를 못 보면 이 함수는 반쪽이다.
    """
    import datetime as dt

    st = load_heartbeat(state_dir)
    stamps = []
    for b in st.beats:
        try:
            stamps.append(dt.datetime.fromisoformat(str(b).replace("Z", "+00:00")))
        except ValueError:
            continue
    if now_iso:
        try:
            stamps.append(dt.datetime.fromisoformat(
                str(now_iso).replace("Z", "+00:00")))
        except ValueError:
            pass
    if len(stamps) < MIN_BEATS_FOR_GAP:
        return None
    stamps.sort()
    gaps = [(b - a).total_seconds() / 60.0
            for a, b in zip(stamps, stamps[1:]) if b > a]
    return max(gaps) if gaps else None


@dataclass(frozen=True)
class GuardVerdict:
    """감시 한 회차의 판정."""

    drawdown: float          # 현재 낙폭(0 이하)
    scale: float             # 킬스위치가 정한 노출 배수
    acted: bool              # 노출을 실제로 줄였는가
    reason: str


def guard_once(equity_now: float, peak_equity: float, prev_scale: float,
               *, now_iso: str, state_dir: str = "state") -> GuardVerdict:
    """감시 한 회차 — 지금 자산으로 낙폭을 재고 킬스위치를 **즉시** 적용한다.

    ⚠️ 킬스위치 규칙 자체는 여기 다시 적지 않고 `daily.py`의 것을 **부른다.**
       같은 규칙을 두 곳에 적으면 반드시 어긋나고(FROZEN_IDEAS ①), 그러면
       새벽 배치와 장중 감시가 서로 다른 선에서 물러난다.
    """
    from quant.live.daily import _kill_switch_scale

    if peak_equity <= 0:
        v = GuardVerdict(0.0, prev_scale, False, "고점이 없어 낙폭을 잴 수 없습니다")
        record_heartbeat(now_iso, state_dir=state_dir)
        return v

    dd = float(equity_now) / float(peak_equity) - 1.0
    scale = _kill_switch_scale(float(prev_scale), dd)
    acted = scale < float(prev_scale)
    reason = (f"낙폭 {dd:.2%} → 노출 {scale:.0%}"
              + (f" (직전 {prev_scale:.0%}에서 축소)" if acted else " (유지)"))
    record_heartbeat(now_iso, state_dir=state_dir,
                     action=({"drawdown": round(dd, 6), "scale": scale}
                             if acted else None))
    if acted:
        log.warning("🛑 장중 킬스위치 — %s", reason)
    return GuardVerdict(dd, scale, acted, reason)
