"""주요 거시 이벤트 달력 — 결정적(deterministic) 위험 필터의 데이터.

FOMC(미국 연준 금리 결정) 발표일은 몇 년 치가 미리 공개된다. 날짜가 미리
정해져 있으므로 "그날은 위험을 줄인다" 같은 규칙은 뉴스와 달리 재현 가능하고
과거 검증(백테스트)이 가능하다 — 챔피언/챌린저 관문에 정식으로 태울 수 있다.

⚠️ 이 달력은 '알려진 일정'만 담는다. 전쟁·규제 발표 같은 돌발 이벤트는
예측 대상이 아니며, 그런 뉴스는 브리핑(표시 전용)으로만 다룬다.

의존성 0 (표준 라이브러리만) — 웹 폼 렌더 등 pandas 없는 경로에서도 안전.
"""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

# FOMC 정례회의 '결정 발표일'(미국 동부시간 기준, 회의 2일차).
# 출처: 연준 공개 일정. 2020년의 3/3·3/15는 코로나 긴급회의.
# 과거 구간(2018~)을 포함하는 이유: 재학습 백테스트 창(수년)에서 필터의
# 효과를 검증하려면 그 구간의 이벤트 날짜가 필요하다.
FOMC_DATES: tuple[str, ...] = (
    # 2018
    "2018-01-31", "2018-03-21", "2018-05-02", "2018-06-13",
    "2018-08-01", "2018-09-26", "2018-11-08", "2018-12-19",
    # 2019
    "2019-01-30", "2019-03-20", "2019-05-01", "2019-06-19",
    "2019-07-31", "2019-09-18", "2019-10-30", "2019-12-11",
    # 2020 (3/3, 3/15는 긴급회의)
    "2020-01-29", "2020-03-03", "2020-03-15", "2020-04-29",
    "2020-06-10", "2020-07-29", "2020-09-16", "2020-11-05", "2020-12-16",
    # 2021
    "2021-01-27", "2021-03-17", "2021-04-28", "2021-06-16",
    "2021-07-28", "2021-09-22", "2021-11-03", "2021-12-15",
    # 2022
    "2022-01-26", "2022-03-16", "2022-05-04", "2022-06-15",
    "2022-07-27", "2022-09-21", "2022-11-02", "2022-12-14",
    # 2023
    "2023-02-01", "2023-03-22", "2023-05-03", "2023-06-14",
    "2023-07-26", "2023-09-20", "2023-11-01", "2023-12-13",
    # 2024
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12",
    "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
    # 2025
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
    "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
    # 2026
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
    # 2027
    "2027-01-27", "2027-03-17", "2027-04-28", "2027-06-16",
    "2027-07-28", "2027-09-15", "2027-10-27", "2027-12-08",
)

# 달력이 어디까지 있는가 — **목록에서 직접 계산한다**(감사 154).
# 예전에는 date(2027, 12, 31)로 손으로 적어 두었고, 그 상수를 **읽는 곳이
# 한 곳도 없었다.** 즉 달력이 끝나도 아무 일도 안 일어나고, `is_event_day`가
# 그날부터 매일 False를 돌려준다 — FOMC 가드가 조용히 꺼진 채로 전략은
# "오늘은 주요 이벤트 없음(매매 허용)"이라고 매일 말한다. 꺼진 안전장치보다
# 나쁜 것은 꺼진 줄 모르는 안전장치다.
CALENDAR_END = date.fromisoformat(max(FOMC_DATES))
CALENDAR_END_YEAR = CALENDAR_END.year

# 이 날수보다 남은 달력이 짧아지면 '갱신할 때'로 본다. 반년이면 다음 해
# 일정이 이미 공개돼 있고(연준은 보통 1년 이상 앞서 공지) 고칠 시간도 있다.
CALENDAR_MIN_RUNWAY_DAYS = 180


def calendar_runway_days(today: date | None = None) -> int:
    """달력이 며칠 더 남았는가. 음수면 이미 지났다."""
    return (CALENDAR_END - (today or date.today())).days


def calendar_is_stale(today: date | None = None,
                      min_days: int = CALENDAR_MIN_RUNWAY_DAYS) -> bool:
    """이벤트 필터를 믿어도 되는가 — 안 되면 True.

    True인데도 계속 쓰면 '이벤트 없음'이 **모른다는 뜻**인지 **정말 없다는
    뜻**인지 구분할 수 없다. 호출자는 이 값을 판단문에 그대로 실어야 한다.
    """
    return calendar_runway_days(today) < min_days


@lru_cache(maxsize=8)
def event_dates(pad_days: int = 1) -> frozenset[date]:
    """이벤트일 ± pad_days 를 모두 담은 날짜 집합.

    pad_days=1 기본: 발표는 미국 시간 오후라 한국(KST) 일봉에는 다음 날
    반영된다 — 시차를 흡수하려고 전후 하루를 함께 가린다.
    """
    out: set[date] = set()
    for s in FOMC_DATES:
        d = date.fromisoformat(s)
        for k in range(-pad_days, pad_days + 1):
            out.add(d + timedelta(days=k))
    return frozenset(out)


def is_event_day(d: date, pad_days: int = 1) -> bool:
    return d in event_dates(pad_days)


# ── 마이너 캘린더 — 옵션만기(매월 셋째 금요일)·월말 ─────────────────
# 예측용이 아니라 위험 회피용이다: 만기일 수급 왜곡·월말 리밸런싱 플로우로
# 변동성이 구조적으로 커지는 날, 노출을 줄이는 규칙에 쓴다. 날짜가 순수
# 달력 계산이라 데이터 소스가 필요 없고 결정적(재현 가능)이다.
def _third_friday(year: int, month: int) -> date:
    d = date(year, month, 15)                  # 15~21일 사이에 셋째 금요일이 있다
    while d.weekday() != 4:
        d += timedelta(days=1)
    return d


def _month_end(year: int, month: int) -> date:
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    return nxt - timedelta(days=1)


@lru_cache(maxsize=8)
def minor_event_dates(start_year: int = 2018,
                      end_year: int | None = None) -> frozenset[date]:
    """옵션만기일 + 월말(달력 마지막 날·전일)의 집합.

    end_year 기본값은 주요 달력의 끝 해에 맞춘다 — 손으로 적어 두면 FOMC
    목록을 늘렸을 때 이쪽만 뒤처진다(감사 154).
    """
    end_year = CALENDAR_END_YEAR if end_year is None else int(end_year)
    out: set[date] = set()
    for y in range(start_year, end_year + 1):
        for m in range(1, 13):
            out.add(_third_friday(y, m))
            me = _month_end(y, m)
            out.add(me)
            out.add(me - timedelta(days=1))    # 월말 리밸런싱은 전일부터 시작
    return frozenset(out)


def is_minor_event_day(d: date) -> bool:
    return d in minor_event_dates()
