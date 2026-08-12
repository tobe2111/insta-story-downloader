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

# 공표된 달력이 어디까지 있는가 — **목록에서 직접 계산한다**(감사 154).
# 손으로 적으면 목록을 늘렸을 때 상수만 뒤처진다(실제로 12/31로 적혀 있었고
# 목록의 마지막은 12/08이었다).
PUBLISHED_END = date.fromisoformat(max(FOMC_DATES))
PUBLISHED_END_YEAR = PUBLISHED_END.year
CALENDAR_END = PUBLISHED_END          # 옛 이름 유지(읽는 곳이 있을 수 있다)
CALENDAR_END_YEAR = PUBLISHED_END_YEAR
CALENDAR_MIN_RUNWAY_DAYS = 180

# 공표 목록 뒤로 몇 해까지 추정 일정을 만들어 둘지. 날짜 몇 개라 비용은 0에
# 가깝다 — '평생 도는 가드'를 위해 넉넉히 잡는다.
PROJECT_YEARS_AHEAD = 30

# 추정 일정의 패딩. 공표 일정은 ±1일이면 시차 흡수로 충분하지만, 추정은
# 며칠 어긋날 수 있으므로 더 넓게 가린다 — **모르면 더 조심한다**.
ESTIMATED_PAD_DAYS = 3


def _valid(y: int, m: int, k: int) -> bool:
    try:
        date(y, m, k)
        return True
    except ValueError:
        return False


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """그 달의 n번째 weekday. n<0이면 뒤에서부터(-1 = 마지막)."""
    days = [date(year, month, k) for k in range(1, 32)
            if _valid(year, month, k)
            and date(year, month, k).weekday() == weekday]
    return days[n if n < 0 else n - 1]


def _ordinal_of(d: date) -> int:
    """이 날짜가 그 달의 몇 번째 요일인가. **마지막이면 -1**로 본다.

    '1월 마지막 수요일'과 '1월 넷째 수요일'은 어떤 해엔 같고 어떤 해엔
    다르다. FOMC는 전자 쪽이 안정적이라 마지막이면 마지막으로 잡는다.
    """
    same = [date(d.year, d.month, k) for k in range(1, 32)
            if _valid(d.year, d.month, k)
            and date(d.year, d.month, k).weekday() == d.weekday()]
    return -1 if same[-1] == d else same.index(d) + 1


@lru_cache(maxsize=1)
def _slot_rules() -> tuple[tuple[int, int, int], ...]:
    """마지막 공표 연도에서 (월, 요일, 서수) 규칙 8개를 **자동으로 뽑는다**.

    손으로 규칙을 적으면 목록을 갱신했을 때 규칙만 뒤처진다 — 감사 154에서
    CALENDAR_END가 정확히 그랬다. 공표 목록이 늘면 규칙도 저절로 최신이 된다.

    실측 정확도(2027년 규칙으로 과거를 재생성):
        2026년 8/8 정확 · 2025년 7/8 정확(5월 회의만 7일 어긋남)
    """
    last = [date.fromisoformat(s) for s in FOMC_DATES
            if s.startswith(str(PUBLISHED_END_YEAR))]
    return tuple((d.month, d.weekday(), _ordinal_of(d)) for d in sorted(last))


@lru_cache(maxsize=64)
def projected_fomc_dates(year: int) -> tuple[date, ...]:
    """공표 목록 뒤의 해에 대한 **추정** FOMC 일정.

    ⚠️ 추정이지 확정이 아니다. 연준은 보통 1년 이상 앞서 공표하므로 이
       값이 실제로 쓰이면 '목록 갱신이 늦었다'는 뜻이다. 그래도 가드가
       통째로 꺼지는 것보다는 낫다 — 꺼지면 그 사실조차 안 보인다.
    """
    if year <= PUBLISHED_END_YEAR:
        return ()
    out = []
    for month, weekday, ordinal in _slot_rules():
        try:
            out.append(_nth_weekday(year, month, weekday, ordinal))
        except IndexError:                 # 그 달에 n번째 요일이 없다
            continue
    return tuple(out)


def _horizon(today: date | None = None) -> int:
    return max(PUBLISHED_END_YEAR,
               (today or date.today()).year + PROJECT_YEARS_AHEAD)


def is_projected_day(d: date) -> bool:
    """이 날짜가 **추정** 달력에서 온 것인가(공표 목록 밖인가)."""
    return d > PUBLISHED_END


def calendar_runway_days(today: date | None = None) -> int:
    """**공표** 달력이 며칠 더 남았는가. 음수면 추정으로 돌고 있다."""
    return (PUBLISHED_END - (today or date.today())).days


def calendar_is_stale(today: date | None = None,
                      min_days: int = CALENDAR_MIN_RUNWAY_DAYS) -> bool:
    """공표 달력이 얼마 안 남았거나 이미 지났는가.

    True여도 가드는 계속 돈다(추정 일정) — 다만 판단문이 그 사실을 밝힌다.
    '이벤트 없음'과 '추정으로 판단함'은 다른 말이다.
    """
    return calendar_runway_days(today) < min_days


@lru_cache(maxsize=32)
def published_event_dates(pad_days: int = 1) -> frozenset[date]:
    """**공표된** 이벤트일 ± pad_days (추정 제외)."""
    out: set[date] = set()
    for s in FOMC_DATES:
        d = date.fromisoformat(s)
        for k in range(-pad_days, pad_days + 1):
            out.add(d + timedelta(days=k))
    return frozenset(out)


@lru_cache(maxsize=64)
def event_dates(pad_days: int = 1,
                through_year: int | None = None) -> frozenset[date]:
    """이벤트일 ± pad 를 모두 담은 날짜 집합 — **공표 + 추정**.

    pad_days=1 기본: 발표는 미국 시간 오후라 한국(KST) 일봉에는 다음 날
    반영된다 — 시차를 흡수하려고 전후 하루를 함께 가린다.

    공표 목록이 끝난 뒤의 해는 추정 일정으로 메운다(감사 155). 예전에는
    거기서 집합이 비어 `is_event_day`가 매일 False를 돌려줬고, FOMC 가드가
    **조용히 영구 정지**했다. 추정은 ±ESTIMATED_PAD_DAYS로 더 넓게 가린다 —
    며칠 어긋날 수 있으니 모르는 만큼 더 조심하는 쪽으로 기운다.
    """
    end = _horizon() if through_year is None else int(through_year)
    out = set(published_event_dates(pad_days))
    for y in range(PUBLISHED_END_YEAR + 1, end + 1):
        for d in projected_fomc_dates(y):
            for k in range(-ESTIMATED_PAD_DAYS, ESTIMATED_PAD_DAYS + 1):
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
    # 마이너 달력은 순수 달력 계산이라 얼마든지 앞으로 만들 수 있다 —
    # 주요 달력이 끝났다고 이쪽까지 멈출 이유가 없다(감사 155).
    end_year = _horizon() if end_year is None else int(end_year)
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
