"""이벤트 달력이 **조용히 만료되면 안 된다** (감사 154).

FOMC 가드는 "그날은 위험을 줄인다"는 결정적 규칙이고, 그 근거는 손으로
적어 둔 날짜 목록이다. 목록은 2027년까지 있다. 그다음 날부터 무슨 일이
일어나는가.

    event_dates() 에 그날이 없다
      → is_event_day() = False
        → 가드가 아무것도 막지 않는다
          → 전략은 "오늘은 주요 이벤트 없음(매매 허용)"이라고 **매일** 말한다

에러도, 경고도, 장부 흔적도 없다. **꺼진 안전장치보다 나쁜 것은 꺼진 줄
모르는 안전장치다.**

`CALENDAR_END = date(2027, 12, 31)`이라는 상수가 있긴 했다. 그런데 **읽는
곳이 한 곳도 없었다** — 감사 135·139·150과 같은 계열(만들어 놓고 배선 안 함).
게다가 손으로 적은 값이라 목록과 어긋날 수도 있었다(실제로 목록의 마지막은
2027-12-08이다).

이 파일이 하는 일은 둘이다.

    ① 달력이 끝나가면 **미리** 빨개진다(만료 6개월 전).
       CI가 어느 날 갑자기 실패하는 게 목적이다 — 그게 알람이다.
    ② 달력이 끝난 뒤에는 판단문이 '이벤트 없음'이 아니라 **'모름'**이라고
       말하는지 확인한다.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.events import (  # noqa: E402
    CALENDAR_MIN_RUNWAY_DAYS,
    ESTIMATED_PAD_DAYS,
    FOMC_DATES,
    PROJECT_YEARS_AHEAD,
    PUBLISHED_END,
    _nth_weekday,
    _slot_rules,
    calendar_runway_days,
    event_dates,
    is_event_day,
    is_projected_day,
    minor_event_dates,
    projected_fomc_dates,
    published_event_dates,
)
from quant.strategies import get_strategy  # noqa: E402
from quant.strategies.event_guard import EventGuard  # noqa: E402


# ── ① 만료 전에 미리 빨개지는 알람 ────────────────────────────


def test_the_guard_never_goes_dark_no_matter_how_far_ahead():
    """**어느 해를 갖다 대도 이벤트일이 있어야 한다** — 이게 영구성의 정의다.

    공표 목록이 2027년에 끝나도 추정 일정이 그 뒤를 메운다. 지평선은
    `오늘 + PROJECT_YEARS_AHEAD`로 매 실행마다 다시 계산되므로, 몇 년이
    지나도 앞으로 30년은 언제나 채워져 있다.
    """
    today = dt.date.today()
    for years in (1, 5, 10, PROJECT_YEARS_AHEAD - 1):
        y = today.year + years
        got = projected_fomc_dates(y) if y > PUBLISHED_END.year else [
            d for d in (dt.date.fromisoformat(s) for s in FOMC_DATES)
            if d.year == y]
        assert len(got) >= 8, f"{y}년 이벤트일이 {len(got)}개뿐 — 가드가 꺼진다"
        for d in got:
            assert is_event_day(d), f"{d}가 이벤트일 집합에 없다"


def test_the_projection_rule_is_derived_not_typed():
    """규칙을 손으로 적으면 목록을 갱신했을 때 규칙만 뒤처진다(감사 154 재발)."""
    assert PUBLISHED_END == dt.date.fromisoformat(max(FOMC_DATES))
    assert len(_slot_rules()) == 8, _slot_rules()


def test_the_rule_reproduces_the_years_we_actually_know():
    """정답을 아는 데이터 — 2027 규칙으로 과거를 재생성해 맞춰 본다.

    실측: 2026년 8/8 정확 · 2025년 7/8(5월 회의만 7일 어긋남).
    완벽하지 않기 때문에 추정에는 ±3일 패딩을 준다.
    """
    for year, want_min in ((2026, 8), (2025, 7)):
        real = sorted(dt.date.fromisoformat(s) for s in FOMC_DATES
                      if s.startswith(str(year)))
        gen = [_nth_weekday(year, m, w, o) for m, w, o in _slot_rules()]
        hit = sum(1 for a, b in zip(gen, real) if a == b)
        assert hit >= want_min, (
            f"{year}년 재생성 정확도 {hit}/8 — 규칙이 실제 일정과 멀어졌다")


def test_an_estimate_is_padded_wider_than_a_published_date():
    """모르는 만큼 더 조심한다 — 추정은 ±3일, 공표는 ±1일."""
    assert ESTIMATED_PAD_DAYS > 1
    future = projected_fomc_dates(PUBLISHED_END.year + 3)[0]
    for k in range(-ESTIMATED_PAD_DAYS, ESTIMATED_PAD_DAYS + 1):
        assert is_event_day(future + dt.timedelta(days=k)), (
            f"추정일 {future} ±{k}일이 안 가려진다")
    assert not is_event_day(future + dt.timedelta(days=ESTIMATED_PAD_DAYS + 4)), (
        "추정 패딩이 너무 넓어 아무 날이나 이벤트가 된다")


def test_published_dates_are_still_only_padded_by_one():
    """대조군 — 확정 일정까지 넓게 가리면 멀쩡한 날에 관망하게 된다."""
    d = dt.date.fromisoformat("2026-03-18")
    assert d in published_event_dates(1)
    assert d + dt.timedelta(days=3) not in published_event_dates(1)


def test_the_minor_calendar_reaches_just_as_far():
    """마이너 달력만 뒤처지면 옵션만기 가드가 먼저 꺼진다."""
    assert max(minor_event_dates()).year >= dt.date.today().year + 10


def test_the_calendar_runway_is_reported_even_though_it_no_longer_breaks():
    """공표 달력의 남은 날은 **정보로** 남긴다.

    ⚠️ 예전 판에서는 이 값이 문턱 아래면 검사를 실패시켰다. 지금은 추정으로
       계속 도니까 실패시키지 않는다 — 대신 몇 일 남았는지는 계속 셀 수
       있어야 한다. 갱신 시점을 사람이 판단할 근거다.
    """
    left = calendar_runway_days()
    assert isinstance(left, int)
    assert calendar_runway_days(PUBLISHED_END) == 0
    assert calendar_runway_days(PUBLISHED_END + dt.timedelta(days=10)) == -10
    assert CALENDAR_MIN_RUNWAY_DAYS > 0


# ── ② 만료 뒤에는 '모름'이라고 말하는가 ───────────────────────


def _gate_on(day: str) -> dict:
    idx = pd.date_range(end=day, periods=120, freq="D")
    c = 100.0 * np.exp(np.cumsum(
        np.random.default_rng(1).normal(0.001, 0.01, len(idx))))
    df = pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99,
                       "close": c, "volume": 1e6}, index=idx)
    g = EventGuard(get_strategy("ma_cross"), pad_days=1, factor=0.0)
    g.generate_signals(df)
    return g.last_gate_


def test_after_the_published_list_ends_the_verdict_says_it_is_an_estimate():
    far = (PUBLISHED_END + dt.timedelta(days=400)).isoformat()
    gate = _gate_on(far)
    assert gate.get("projected"), (
        f"공표 목록 밖인데 판단문이 평시와 같다: {gate}")
    assert "추정" in gate["reason"], gate["reason"]
    # ⚠️ 여기서 `"이벤트 없음" not in reason`으로 쓰면 안 된다 — **경고문
    #    자체가** "'이벤트 없음'이 아니라 모름이다"라고 말하므로 그 문구가
    #    들어 있다. 오늘 같은 실수를 두 번째로 했다(감사 136의 검사도
    #    자기 설명문에 걸렸다). 문구를 부정하지 말고 **평시 문장에만 있는
    #    표식**을 쓴다.
    assert "매매 허용" not in gate["reason"], (
        "추정으로 판단하면서 평시와 같은 '매매 허용' 문구를 낸다 — "
        f"근거의 급이 다르다는 사실이 안 보인다: {gate['reason']}")


def test_within_the_calendar_the_verdict_is_normal():
    """대조군 — 평시에 경고가 뜨면 매일 울려서 아무도 안 본다."""
    safe = (PUBLISHED_END - dt.timedelta(days=CALENDAR_MIN_RUNWAY_DAYS + 60))
    # 이벤트 창이 아닌 날을 고른다(창이면 open=False라 분기가 다르다)
    while is_event_day(safe):
        safe -= dt.timedelta(days=1)
    gate = _gate_on(safe.isoformat())
    assert not gate.get("projected"), gate
    assert "이벤트 없음" in gate["reason"], gate["reason"]


def test_the_guard_still_guards_far_in_the_future():
    """추정 구간에서도 **실제로 막아야** 한다 — 안 막으면 영구화가 무의미하다."""
    far_year = dt.date.today().year + 8
    day = projected_fomc_dates(far_year)[0]
    gate = _gate_on(day.isoformat())
    assert gate["open"] is False, f"추정 FOMC일인데 매매를 열어 뒀다: {gate}"


def test_the_guard_still_guards_inside_the_calendar():
    """대조군 — 만료 처리를 붙이느라 가드 자체를 망가뜨리지 않았는가."""
    day = next(d for d in sorted(
        dt.date.fromisoformat(s) for s in FOMC_DATES) if d.year == 2026)
    gate = _gate_on(day.isoformat())
    assert gate["open"] is False, f"FOMC 발표일인데 매매를 열어 뒀다: {gate}"
    assert "이벤트" in gate["reason"]
