"""휴장일 달력 — **오늘 이 시장이 아예 안 여는 날인가**.

⚠️ 왜 만들었나. `quant/live/market_hours.py`가 스스로 이렇게 적어 두고 있었다:

    "정직한 한계: 공휴일 달력이 없다. 요일(월~금)과 정규장 시간만 본다.
     국경일·임시 휴장·조기 폐장(반장)은 반영하지 못한다."

그 한계 때문에 실제로 생기는 일:

  · **사이트가 명절 내내 15초마다 시세를 조른다.** 무료 시세 한도를
    아무도 안 보는 휴장일에 태운다.
  · 화면이 '지연'인지 '휴장'인지 구분하지 못한다 — 값이 안 변하는 것이
    정상인지 고장인지 사람도 알 수 없다. 이 저장소가 가장 싫어하는 상태다.
  · 배치의 `bar_age` 경고가 정상 연휴에 울린다. 가끔 울리는 경보는
    무시하게 되고, 그러면 진짜 신호도 함께 묻힌다(감사 226과 같은 교훈).

출처를 **API가 아니라 라이브러리**로 고른 이유:
    한국 공휴일은 음력(설·추석)이라 표에 박아 둘 수 없다. 증권사 API로
    받아 올 수도 있지만, 그러면 키가 없는 환경·네트워크가 끊긴 환경에서
    달력이 통째로 사라지고 **그 사실이 조용하다.** `exchange_calendars`는
    오프라인으로 같은 답을 주고, 검사에서 값으로 확인할 수 있다.

    실측(이 저장소에서 확인): XKRX 2026 = 01-01 · 02-16~18(설) · 03-02 ·
    05-01 · 05-05 · 05-24(부처님오신날) … / XNYS 2026-11-26 휴장.

없으면 어떻게 되나: **오늘까지와 똑같이 동작한다**(요일만 본다). 달력은
'더 아는 것'이지 '없으면 못 도는 것'이 아니다 — 배포판·최소 설치 환경에서
조용히 죽으면 안 된다. 다만 **아는지 모르는지는 말한다**(`calendar_source`).
"""
from __future__ import annotations

import datetime as _dt
import json
import os

from quant.utils.logging import get_logger

log = get_logger("data.market_calendar")

CACHE_FILE = "holidays.json"
REFRESH_DAYS = 30          # 달력은 연 단위로만 바뀐다 — 매일 다시 만들 이유가 없다
HORIZON_DAYS = 400         # 앞으로 이만큼을 미리 받아 둔다(연말 경계 포함)
# 지나간 날도 담는다 — "며칠째 새 봉이 없나"를 세려면 **어제가 휴장이었는지**를
# 알아야 한다(감사 243). 앞만 보는 달력으로 세면 방금 지난 연휴가 통째로
# '빠뜨린 세션'으로 잡혀, 정상 휴장이 장애로 보고된다.
LOOKBACK_DAYS = 40

# 이 저장소의 시장 이름 → 거래소 달력 코드
EXCHANGES = {"kr_stock": "XKRX", "us_stock": "XNYS"}


def _compute(market: str, start: _dt.date, end: _dt.date) -> list[str] | None:
    """그 구간의 휴장일(주말 제외)을 ISO 문자열로. 달력이 없으면 None.

    주말은 빼고 돌려준다 — 요일 판정은 이미 `market_hours`가 한다. 여기서
    같이 주면 두 곳이 같은 판정을 하게 되고, 그러면 언젠가 갈라진다(㉞).
    """
    code = EXCHANGES.get(market)
    if not code:
        return None
    try:
        import exchange_calendars as xcals
        cal = xcals.get_calendar(code)
    except Exception as exc:  # noqa: BLE001 — 미설치·초기화 실패 모두 '모름'
        log.info("휴장일 달력 없음(%s): %s", code, exc)
        return None
    out = []
    day = start
    while day <= end:
        if day.weekday() < 5:                      # 주말은 이미 아는 사실
            try:
                if not cal.is_session(day.isoformat()):
                    out.append(day.isoformat())
            except Exception:  # noqa: BLE001 — 달력 범위 밖은 '모름'으로 둔다
                pass
        day += _dt.timedelta(days=1)
    return out


_MEMO: dict = {}          # (state_dir, 오늘) → 달력. 루프마다 파일을 열지 않는다


def holiday_map(state_dir: str = "state", today: _dt.date | None = None,
                horizon_days: int = HORIZON_DAYS,
                refresh_days: int = REFRESH_DAYS,
                lookback_days: int = LOOKBACK_DAYS) -> dict:
    """{시장: [휴장일 ISO...]} — 캐시를 쓰고 오래되면 다시 만든다.

    캐시는 `state/holidays.json`에 남는다. 그날 어떤 달력으로 판단했는지가
    파일로 남아야 나중에 "그날 왜 안 돌았나"에 답할 수 있다(이 저장소의
    재현성 규칙).
    """
    today = today or _dt.date.today()
    memo_key = (state_dir, today.isoformat(), horizon_days, refresh_days,
                lookback_days)
    if memo_key in _MEMO:
        return _MEMO[memo_key]
    out = _holiday_map_uncached(state_dir, today, horizon_days, refresh_days,
                                lookback_days)
    _MEMO[memo_key] = out
    return out


def _holiday_map_uncached(state_dir, today, horizon_days, refresh_days,
                          lookback_days=LOOKBACK_DAYS) -> dict:
    path = os.path.join(state_dir, CACHE_FILE)
    cache: dict = {}
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                cache = json.load(f)
    except (OSError, ValueError):
        cache = {}

    fetched = str(cache.get("fetched") or "")
    fresh = False
    try:
        fresh = (today - _dt.date.fromisoformat(fetched)).days < refresh_days
    except ValueError:
        fresh = False
    covered = str(cache.get("until") or "")
    try:
        fresh = fresh and _dt.date.fromisoformat(covered) > today
    except ValueError:
        fresh = False
    # 뒤쪽도 덮고 있어야 한다 — 앞만 담긴 옛 캐시를 그대로 쓰면 지나간
    # 연휴가 '빠뜨린 세션'으로 잡힌다(감사 243).
    start = today - _dt.timedelta(days=lookback_days)
    try:
        fresh = fresh and _dt.date.fromisoformat(
            str(cache.get("since") or "")) <= start
    except ValueError:
        fresh = False
    if fresh and isinstance(cache.get("markets"), dict):
        return cache["markets"]

    end = today + _dt.timedelta(days=horizon_days)
    markets: dict = {}
    for market in EXCHANGES:
        days = _compute(market, start, end)
        if days is not None:
            markets[market] = days
    if not markets:
        # 달력을 못 만들었으면 **옛 캐시라도 쓴다** — 오래된 달력이 없는
        # 달력보다 낫다(연 단위로만 바뀌는 정보다).
        return cache.get("markets") or {}
    try:
        os.makedirs(state_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"fetched": today.isoformat(), "since": start.isoformat(),
                       "until": end.isoformat(),
                       "source": "exchange_calendars", "markets": markets},
                      f, ensure_ascii=False, indent=1)
    except OSError as exc:
        log.warning("휴장일 캐시 저장 실패: %s", exc)
    return markets


def _as_date(day) -> _dt.date | None:
    try:
        return day if isinstance(day, _dt.date) else _dt.date.fromisoformat(
            str(day)[:10])
    except ValueError:
        return None


def missed_sessions(market: str, last_day, today=None,
                    holidays: dict | None = None) -> int | None:
    """마지막 봉 다음 날부터 오늘까지, **그 시장이 열렸어야 한 날**의 수.

    달력 일수로 세면 안 된다(감사 243). 시장마다 여는 날이 다르기 때문이다:

        실측 2026-08-15(토) · 마지막 봉 08-13 기준
            crypto  → 놓친 세션 **2** (08-14 · 08-15 — 코인은 매일 연다)
            kr/us   → 놓친 세션 **1** (08-14 — 토요일은 애초에 안 연다)

    같은 이틀이지만 뜻이 다르다. 달력 일수 하나로 세면 코인 시세가 얼어붙은
    사고와 주말이 구별되지 않고, **주말과 구별되지 않는 경보는 꺼진 경보다.**

    달력에 없는 시장(코인 등)은 24시간·연중무휴로 본다. 날짜를 못 읽으면
    `None`(모른다)을 돌려준다 — 0(정상)과 섞지 않는다.
    """
    start, end = _as_date(last_day), _as_date(today or _dt.date.today())
    if start is None or end is None:
        return None
    n, day = 0, start + _dt.timedelta(days=1)
    while day <= end:
        if market not in EXCHANGES:                 # 24/7 시장 — 매일이 세션
            n += 1
        elif day.weekday() < 5 and not is_holiday(market, day, holidays):
            n += 1
        day += _dt.timedelta(days=1)
    return n


def is_holiday(market: str, day, holidays: dict | None) -> bool:
    """그 시장의 그날이 **휴장일로 알려져 있는가**.

    ⚠️ 모르는 것과 아닌 것을 구분한다. 달력이 없으면(None·빈 dict) 여기서는
       항상 False다 — 즉 '휴장이 아니다'가 아니라 **'모른다, 그러니 막지
       않는다'**이다. 가드가 정상 거래를 막는 것보다 브로커 거부에 맡기는
       편이 안전하다는 `market_hours`의 원칙을 그대로 따른다.
    """
    if not holidays:
        return False
    days = holidays.get(market)
    if not days:
        return False
    try:
        key = day.isoformat()[:10]
    except AttributeError:
        key = str(day)[:10]
    return key in set(days)
