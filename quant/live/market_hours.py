"""거래 시간(장 개장) 가드 — 닫힌 시장에 주문을 보내지 않는다 (순수 stdlib).

주식 시장은 정해진 시간에만 열린다. 장 마감·주말에 주문을 내면 브로커가 거부하고,
그 거부를 잘못 처리하면 봇이 오작동한다. 이 모듈은 주문 전에 '지금 이 시장이
열려 있는가'를 미리 판정해 불필요한 주문·거부를 막는다.

정직한 한계(반드시 이해할 것):
    · 공휴일은 **알려 주면 본다**(2026-08-14). 이 모듈은 순수 stdlib를 유지하려고
      달력을 스스로 받아 오지 않는다 — 호출자가 `holidays=`로 넘긴다
      (`quant.data.market_calendar.holiday_map()`이 만들어 준다). 안 넘기면
      예전과 똑같이 **요일과 시간만** 본다.
      ⚠️ 넘기지 않았을 때의 결과는 '휴장이 아니다'가 아니라 **'모른다'**이다.
    · 임시 휴장·조기 폐장(반장)은 여전히 반영하지 못한다 — 브로커 거부에 의존.
    · 시간외·동시호가·프리마켓은 다루지 않는다(정규장만).
    · 코인은 24시간이라 항상 열린 것으로 본다. 알 수 없는 시장도 막지 않는다
      (가드가 정상 거래를 막는 것보다 브로커 거부에 맡기는 편이 안전).
"""
from __future__ import annotations

from datetime import datetime, time, timezone

from quant.data.market_calendar import is_holiday

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - py<3.9 방어
    ZoneInfo = None  # type: ignore

# 시장별 정규장: (IANA 시간대, 개장, 폐장). 여기 없는 시장은 '항상 열림'(코인 등).
SCHEDULES: dict[str, tuple[str, time, time]] = {
    "us_stock": ("America/New_York", time(9, 30), time(16, 0)),   # NYSE/NASDAQ 정규장
    "kr_stock": ("Asia/Seoul", time(9, 0), time(15, 30)),          # KRX 정규장
}
# 별칭
_ALIASES = {"us": "us_stock", "kr": "kr_stock", "stock": "us_stock"}


def _market_now(tzname: str, now: datetime | None) -> datetime:
    """기준 시각을 시장 시간대의 aware datetime으로 변환한다."""
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)   # naive는 UTC로 간주
    if ZoneInfo is None:
        return now                                # tz 지원 불가 → 원본(보수적으로 통과)
    return now.astimezone(ZoneInfo(tzname))


def is_market_open(market: str, now: datetime | None = None,
                   holidays: dict | None = None) -> bool:
    """해당 시장이 지금(now, 기본 현재 UTC) 정규장 시간인지 판정한다.

    스케줄이 없는 시장(코인·synthetic·미지정)은 항상 True(막지 않음).
    `holidays`는 {시장: [ISO 날짜...]} — 안 넘기면 요일·시간만 본다.
    """
    key = _ALIASES.get((market or "").lower(), (market or "").lower())
    sched = SCHEDULES.get(key)
    if sched is None:
        return True
    tzname, open_t, close_t = sched
    local = _market_now(tzname, now)
    if local.weekday() >= 5:            # 토(5)·일(6) 휴장
        return False
    if is_holiday(key, local.date(), holidays):
        return False
    return open_t <= local.time() <= close_t


def market_status(market: str, now: datetime | None = None,
                  holidays: dict | None = None) -> str:
    """사람이 읽을 장 상태 한 줄 (로그·알림용)."""
    key = _ALIASES.get((market or "").lower(), (market or "").lower())
    if key not in SCHEDULES:
        return f"{market}: 24시간 거래(장 시간 제한 없음)"
    tzname, open_t, close_t = SCHEDULES[key]
    local = _market_now(tzname, now)
    if is_market_open(market, now, holidays):
        return (f"{market}: 개장 중 "
                f"({local:%Y-%m-%d %H:%M} {tzname}, ~{close_t:%H:%M} 마감)")
    # ⚠️ **'모른다'와 '아니다'를 구분해 말한다.** 달력을 못 받은 날 "공휴일
    #    아님"이라고 단정하면, 그 문장을 읽은 사람이 실제 휴장일을 장애로
    #    오해한다. 달력이 있을 때만 '공휴일'이라고 말하고, 없으면 그 사실을
    #    밝힌다.
    if local.weekday() >= 5:
        reason = "주말"
    elif is_holiday(key, local.date(), holidays):
        reason = "공휴일"
    else:
        reason = "장 시간 외"
    tail = ("" if holidays and holidays.get(key)
            else " ※ 공휴일 달력이 없어 국경일은 판정하지 못합니다"
                 "(브로커 거부에 의존).")
    return (f"{market}: 폐장({reason}) "
            f"— 정규장 {open_t:%H:%M}~{close_t:%H:%M} {tzname}.{tail}")
