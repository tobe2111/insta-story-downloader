"""조회 실패를 '오늘 받아온 사실'로 도장 찍고 있었다 (감사 191).

`quant/data/earnings.py`는 실적 발표일 ±1일에 비중을 절반으로 줄인다. 발표일은
갭이 가장 큰 날이라 이 저장소가 명시적으로 두기로 한 보호다.

발표일 목록은 야후에서 받아 `state/earnings.json`에 7일 캐시한다. 그런데
**조회가 실패해도 `fetched`에 오늘을 적었다.**

    except Exception:
        dates = (entry or {}).get("dates", [])      # 옛 캐시라도 쓴다
    entry = {"dates": dates, "fetched": today.isoformat()}   # ← 실패인데 '오늘'

다음 실행에서 `fresh`가 참이 되어 **7일 동안 재시도를 안 한다.** 첫 조회가
실패했다면 `dates`는 빈 목록이므로, 그 일주일은 "이 종목엔 실적 발표가 없다"로
굳는다. 실측:

    08-12  조회 실패            → 캐시 {dates: [], fetched: "08-12"}
    08-13  **실제 발표일**       → 조회가 정상인데 부르지도 않음 → 가드 1.0

**가드가 지키려는 바로 그 날에 꺼져 있다.** 코드 주석은 이 경로를
"조회 실패 = 가드 미발동(무해)"이라 적어 뒀는데, 하루 미발동이 아니라
일주일이고 그 안에 발표일이 들어 있으면 무해하지 않다.

'못 받았다'와 '없다'는 다르다 — 감사 163·182와 같은 계열이다.

형제 확인: 같은 모양의 갱신 캐시는 `web/app.py`의 `_PRICE_CACHE` 하나인데,
거기는 `if prices:`로 **성공했을 때만** 도장을 찍는다(이미 옳다).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.data.earnings import (  # noqa: E402
    GUARD_FACTOR, PAD_DAYS, earnings_guard_factor, nearest_earnings_date,
    next_earnings_date,
)

TODAY = dt.date(2026, 8, 12)
ANNOUNCE = "2026-08-13"


def _boom(_symbol):
    raise RuntimeError("yfinance 일시 장애")


def _dates(*iso):
    return lambda _symbol: list(iso)


# ── 실패가 사실로 굳지 않는가 ─────────────────────────────────


def test_a_failed_lookup_is_retried_tomorrow(tmp_path):
    """실패한 날을 '받아온 날'로 적으면 일주일간 재시도를 안 한다."""
    d = str(tmp_path)
    earnings_guard_factor("AAPL", TODAY, d, fetch=_boom)

    calls: list[str] = []

    def counted(sym):
        calls.append(sym)
        return [ANNOUNCE]

    factor, why = earnings_guard_factor(
        "AAPL", dt.date.fromisoformat(ANNOUNCE), d, fetch=counted)
    assert calls, "조회 실패 다음 날 재시도조차 하지 않았다"
    assert factor == GUARD_FACTOR, (
        f"실제 발표일인데 가드가 {factor}다 — 실패가 '발표 없음'으로 굳었다")
    assert why == ANNOUNCE


def test_a_failure_does_not_stamp_the_cache_as_fresh(tmp_path):
    d = str(tmp_path)
    earnings_guard_factor("AAPL", TODAY, d, fetch=_boom)
    cache = json.loads((tmp_path / "earnings.json").read_text("utf-8"))
    assert cache["AAPL"]["fetched"] != TODAY.isoformat(), (
        f"실패했는데 오늘 받아온 것으로 적혔다: {cache}")


def test_an_old_calendar_survives_a_failure(tmp_path):
    """실패해도 예전에 받아 둔 발표일은 계속 쓴다 — 지우는 건 더 나쁘다."""
    d = str(tmp_path)
    earnings_guard_factor("AAPL", dt.date(2026, 8, 5), d,
                          fetch=_dates(ANNOUNCE))
    factor, why = earnings_guard_factor(
        "AAPL", dt.date.fromisoformat(ANNOUNCE), d, fetch=_boom)
    assert factor == GUARD_FACTOR and why == ANNOUNCE, (
        "조회가 실패했다고 이미 알던 발표일까지 버렸다")


def test_a_successful_lookup_is_still_cached_for_a_week(tmp_path):
    """대조군 — 매번 다시 받으면 20종목 순회가 야후를 두들긴다."""
    d = str(tmp_path)
    calls: list[str] = []

    def counted(sym):
        calls.append(sym)
        return [ANNOUNCE]

    for k in (0, 1, 3, 6):
        earnings_guard_factor("AAPL", TODAY + dt.timedelta(days=k), d,
                              fetch=counted)
    assert len(calls) == 1, f"캐시가 안 먹는다 — {len(calls)}회 조회했다"


# ── 가드 창의 계약 ────────────────────────────────────────────


def test_the_guard_covers_the_day_after_not_just_before(tmp_path):
    """발표 다음 날이 갭이 가장 크다 — 예전에는 발표 전만 막았다."""
    d = str(tmp_path)
    after = dt.date.fromisoformat(ANNOUNCE) + dt.timedelta(days=PAD_DAYS)
    factor, why = earnings_guard_factor("AAPL", after, d,
                                        fetch=_dates(ANNOUNCE))
    assert factor == GUARD_FACTOR and why == ANNOUNCE


def test_outside_the_window_the_guard_is_off(tmp_path):
    """대조군 — 늘 켜져 있으면 그건 가드가 아니라 상시 축소다."""
    d = str(tmp_path)
    far = dt.date.fromisoformat(ANNOUNCE) + dt.timedelta(days=PAD_DAYS + 1)
    assert earnings_guard_factor("AAPL", far, d,
                                 fetch=_dates(ANNOUNCE)) == (1.0, None)


def test_no_calendar_means_no_guard_not_a_crash(tmp_path):
    d = str(tmp_path)
    assert earnings_guard_factor("AAPL", TODAY, d, fetch=_dates()) == (1.0, None)
    assert earnings_guard_factor("AAPL", TODAY, d, fetch=_boom) == (1.0, None)


def test_broken_dates_in_the_cache_are_skipped(tmp_path):
    d = str(tmp_path)
    (tmp_path / "earnings.json").write_text(json.dumps(
        {"AAPL": {"dates": ["나쁜값", ANNOUNCE], "fetched": TODAY.isoformat()}}),
        encoding="utf-8")
    factor, why = earnings_guard_factor("AAPL", TODAY, d, fetch=_boom)
    assert factor == GUARD_FACTOR and why == ANNOUNCE


def test_next_looks_forward_and_nearest_looks_both_ways(tmp_path):
    d = str(tmp_path)
    past, future = "2026-08-11", "2026-09-30"
    assert next_earnings_date("AAPL", TODAY, d,
                              fetch=_dates(past, future)).isoformat() == future
    assert nearest_earnings_date("AAPL", TODAY, d,
                                 fetch=_dates(past, future)).isoformat() == past


def test_a_corrupt_cache_file_does_not_stop_the_batch(tmp_path):
    d = str(tmp_path)
    (tmp_path / "earnings.json").write_text("{망가진", encoding="utf-8")
    factor, why = earnings_guard_factor("AAPL", TODAY, d,
                                        fetch=_dates(ANNOUNCE))
    assert factor == GUARD_FACTOR and why == ANNOUNCE
