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
    CALENDAR_END,
    CALENDAR_MIN_RUNWAY_DAYS,
    FOMC_DATES,
    calendar_is_stale,
    calendar_runway_days,
    is_event_day,
    minor_event_dates,
)
from quant.strategies import get_strategy  # noqa: E402
from quant.strategies.event_guard import EventGuard  # noqa: E402


# ── ① 만료 전에 미리 빨개지는 알람 ────────────────────────────


def test_the_calendar_still_has_runway():
    """⏰ **이 검사가 실패하면 코드가 아니라 달력을 고쳐야 한다.**

    할 일: 연준 공개 일정에서 다음 해 FOMC 발표일을 `quant/events.py`의
    `FOMC_DATES`에 추가한다(연준은 보통 1년 이상 앞서 공지한다).
    `CALENDAR_END`는 목록에서 자동으로 계산되므로 따로 고칠 것이 없다.

    이 검사는 **일부러 시간에 의존한다.** 만료 6개월 전에 스스로 빨개져서
    사람에게 알리는 것이 존재 이유다.
    """
    left = calendar_runway_days()
    assert not calendar_is_stale(), (
        f"이벤트 달력이 {CALENDAR_END}까지뿐이다 — 남은 {left}일 "
        f"(문턱 {CALENDAR_MIN_RUNWAY_DAYS}일). FOMC_DATES에 다음 해 일정을 "
        "추가할 것. 이대로 지나면 FOMC 가드가 조용히 꺼진다")


def test_the_end_is_derived_from_the_list_not_typed_by_hand():
    """손으로 적으면 목록과 어긋난다 — 실제로 어긋나 있었다(12/31 vs 12/08)."""
    assert CALENDAR_END == dt.date.fromisoformat(max(FOMC_DATES))


def test_the_minor_calendar_follows_the_major_one():
    """마이너 달력만 뒤처지면 옵션만기 가드가 먼저 꺼진다."""
    assert max(minor_event_dates()).year >= CALENDAR_END.year


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


def test_after_the_calendar_ends_the_verdict_says_unknown():
    far = (CALENDAR_END + dt.timedelta(days=90)).isoformat()
    gate = _gate_on(far)
    assert gate.get("stale_calendar"), (
        f"달력이 끝난 뒤인데 판단문이 평시와 같다: {gate}")
    assert "모름" in gate["reason"], gate["reason"]
    # ⚠️ 여기서 `"이벤트 없음" not in reason`으로 쓰면 안 된다 — **경고문
    #    자체가** "'이벤트 없음'이 아니라 모름이다"라고 말하므로 그 문구가
    #    들어 있다. 오늘 같은 실수를 두 번째로 했다(감사 136의 검사도
    #    자기 설명문에 걸렸다). 문구를 부정하지 말고 **평시 문장에만 있는
    #    표식**을 쓴다.
    assert "매매 허용" not in gate["reason"], (
        "달력이 끝났는데 평시와 같은 '매매 허용' 판정을 낸다 — "
        f"모르는 걸 안다고 말한다: {gate['reason']}")


def test_within_the_calendar_the_verdict_is_normal():
    """대조군 — 평시에 경고가 뜨면 매일 울려서 아무도 안 본다."""
    safe = (CALENDAR_END - dt.timedelta(days=CALENDAR_MIN_RUNWAY_DAYS + 60))
    # 이벤트 창이 아닌 날을 고른다(창이면 open=False라 분기가 다르다)
    while is_event_day(safe):
        safe -= dt.timedelta(days=1)
    gate = _gate_on(safe.isoformat())
    assert not gate.get("stale_calendar"), gate
    assert "이벤트 없음" in gate["reason"], gate["reason"]


def test_the_guard_still_guards_inside_the_calendar():
    """대조군 — 만료 처리를 붙이느라 가드 자체를 망가뜨리지 않았는가."""
    day = next(d for d in sorted(
        dt.date.fromisoformat(s) for s in FOMC_DATES) if d.year == 2026)
    gate = _gate_on(day.isoformat())
    assert gate["open"] is False, f"FOMC 발표일인데 매매를 열어 뒀다: {gate}"
    assert "이벤트" in gate["reason"]
