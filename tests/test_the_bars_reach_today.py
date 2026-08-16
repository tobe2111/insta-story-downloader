"""800봉을 다 받고도 **최신 165일을 못 받았다** — 실전 사고 (감사 261).

2026-08-16 야간 배치. 코인 5종목이 `bars=800`으로 **성공**했습니다. 봉 수는
목표대로였고 경보도 없었습니다. 그런데 마지막 봉이 **2026-03-04**였습니다.

    챔피언 결정에 쓴 데이터의 마지막 날   2026-03-04
    배치가 돈 날                         2026-08-16
    빈 구간                              **165일 (5개월 반)**

감사 243의 정체 경보가 정확히 `165`로 잡아냈습니다 — 그 장치가 없었다면
"800봉 받았고 실패 0건"만 보고 넘어갔을 것입니다.

## 원인

이어받기가 **개수로 멈췄습니다.**

    시작점 = 지금 − (limit × 1.2 + 5)봉      ← 800봉이면 965일 전
    루프    : 앞으로 받다가 `len(rows) >= limit`이면 중단

965일 전부터 앞으로 800개를 모으면 그 지점은 아직 **165일 전**입니다.
즉 **가장 오래된 800개**를 받고 최근 구간을 통째로 버렸습니다.

**"봉 수를 채웠다"와 "최신까지 받았다"는 다른 조건입니다.** 개수로 멈추면
남는 쪽은 언제나 **더 오래된 쪽** — 판단에 쓸 수 없는 쪽입니다.

고친 방법: 멈추는 기준을 개수가 아니라 **도달 시각**으로 바꾸고, 넘치면
뒤에서 자릅니다. 페이지 요청도 남은 개수로 조르지 않습니다(마지막 페이지가
잘려 최신 봉을 못 받습니다).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.data.crypto import _fetch_paged  # noqa: E402

DAY = 86_400_000


class Exchange:
    """`cap`봉까지만 주는 거래소(OKX는 300). 역사는 `history_days`만큼."""

    def __init__(self, cap: int = 300, history_days: int = 3000):
        self.cap = cap
        self.calls: list[tuple] = []
        now = int(pd.Timestamp.now("UTC").timestamp() * 1000)
        self.now = now - now % DAY
        self.first = self.now - history_days * DAY

    def fetch_ohlcv(self, symbol, timeframe="1d", since=None, limit=None):
        self.calls.append((since, limit))
        want = min(self.cap, limit or self.cap)
        t = max(since if since is not None else self.first, self.first)
        t -= t % DAY
        out = []
        while len(out) < want and t <= self.now:
            out.append([t, 1.0, 1.1, 0.9, 1.0, 10.0])
            t += DAY
        return out


def _last_day(rows) -> pd.Timestamp:
    return pd.Timestamp(rows[-1][0], unit="ms").normalize()


# ── 실전 사고 그 장면 ────────────────────────────────────────

def test_eight_hundred_bars_must_end_today_not_five_months_ago():
    """실측 그 장면 — bars=800인데 마지막 봉이 165일 전이었다."""
    ex = Exchange(cap=300)
    rows = _fetch_paged(ex, "BTC/USDT", "1d", None, 800)
    assert len(rows) == 800, f"{len(rows)}봉"
    gap = (pd.Timestamp.now("UTC").normalize().tz_localize(None)
           - _last_day(rows)).days
    assert gap <= 1, f"마지막 봉이 {gap}일 전이다 — 개수만 채우고 멈췄다"


def test_the_count_alone_is_not_the_stop_condition():
    """⚠️ 개수로 멈추면 남는 쪽은 언제나 **더 오래된 쪽**이다.

    상한이 작을수록(=페이지가 많이 필요할수록) 더 뒤처진다. 그 성질이
    사라졌는지 본다 — 상한 100짜리 거래소에서도 오늘까지 와야 한다.
    """
    rows = _fetch_paged(Exchange(cap=100), "BTC/USDT", "1d", None, 800)
    gap = (pd.Timestamp.now("UTC").normalize().tz_localize(None)
           - _last_day(rows)).days
    assert gap <= 1, f"상한 100 거래소에서 {gap}일 뒤처졌다"


def test_a_generous_exchange_still_ends_today():
    """대조군 — 한 번에 다 주는 거래소(바이낸스)에서도 같아야 한다."""
    ex = Exchange(cap=1000)
    rows = _fetch_paged(ex, "BTC/USDT", "1d", None, 800)
    assert len(rows) == 800
    gap = (pd.Timestamp.now("UTC").normalize().tz_localize(None)
           - _last_day(rows)).days
    assert gap <= 1


def test_the_page_request_is_not_shrunk_to_the_remainder():
    """'최신 limit봉'을 받는 중에는 남은 개수로 조르면 안 된다.

    마지막 페이지가 잘려 최신 봉을 못 받는다.
    """
    ex = Exchange(cap=300)
    _fetch_paged(ex, "BTC/USDT", "1d", None, 800)
    assert all(lim == 800 for _, lim in ex.calls), (
        f"페이지 요청이 줄어들었다: {[l for _, l in ex.calls]}")


def test_an_explicit_range_still_stops_at_the_count():
    """⚠️ 대조군 — 시작점을 **받은** 요청은 성격이 다르다.

    호출자가 구간을 아는 요청("이 지점부터 limit봉")은 개수를 채우면 끝이다.
    여기까지 '현재에 닿을 때까지'로 바꾸면 넉넉한 거래소에서도 불필요하게
    한 번 더 부른다(레이트리밋 낭비). 두 요청을 뭉뚱그린 것이 사고의 뿌리였다.
    """
    ex = Exchange(cap=1000)
    start = ex.now - 2000 * DAY
    rows = _fetch_paged(ex, "BTC/USDT", "1d", start, 800)
    assert len(rows) == 800
    assert len(ex.calls) == 1, f"한 번이면 될 것을 {len(ex.calls)}번 불렀다"


# ── 원래 지키던 성질이 남아 있는가 ───────────────────────────

def test_a_short_listing_returns_what_exists():
    """신규 상장이면 정말 없을 수 있다 — 없는 것을 지어내지 않는다."""
    rows = _fetch_paged(Exchange(cap=300, history_days=120),
                        "NEW/USDT", "1d", None, 800)
    assert 0 < len(rows) <= 130


def test_a_stuck_exchange_does_not_loop_forever():
    """같은 페이지를 반복해서 주는 고장 — 배치가 안 끝나면 그날 기록이 빈다."""
    class Stuck(Exchange):
        def fetch_ohlcv(self, symbol, timeframe="1d", since=None, limit=None):
            self.calls.append((since, limit))
            return [[self.first + i * DAY, 1.0, 1.1, 0.9, 1.0, 10.0]
                    for i in range(50)]

    ex = Stuck(cap=300)
    rows = _fetch_paged(ex, "BTC/USDT", "1d", None, 800)
    assert len(rows) == 50
    assert len(ex.calls) <= 20


def test_an_explicit_start_is_honoured():
    """시작점을 주면 그 지점부터 — 최신 쪽으로 밀어내면 안 된다."""
    ex = Exchange(cap=300)
    start = ex.now - 500 * DAY
    rows = _fetch_paged(ex, "BTC/USDT", "1d", start, 400)
    assert rows[0][0] >= start
    assert len(rows) == 400


def test_the_rows_are_sorted_and_unique():
    rows = _fetch_paged(Exchange(cap=300), "BTC/USDT", "1d", None, 800)
    ts = [r[0] for r in rows]
    assert ts == sorted(ts) and len(set(ts)) == len(ts)


# ── 정체 경보가 이 사고를 실제로 잡는가 ──────────────────────

def test_the_stall_alarm_would_catch_this_again():
    """감사 243이 없었다면 '800봉 성공'만 보고 넘어갔다.

    그 경보가 살아 있는지 여기서도 확인한다 — 두 장치가 같은 사고를
    각각 잡아야 한다(하나가 죽어도 다른 하나가 남는다).
    """
    from quant.data.market_calendar import missed_sessions

    n = missed_sessions("crypto", "2026-03-04", "2026-08-16")
    assert n == 165, f"정체 일수가 {n}일로 계산된다 — 실측은 165일이었다"
