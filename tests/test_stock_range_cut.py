"""주식 시세의 범위 절단 — 룩어헤드 차단막 (감사 84).

`_cut_range`는 `end`를 강제해 **그 시점 이후의 봉을 보지 못하게** 막는다.
`quant verify --date X`가 과거 결정을 재현할 때 기대는 바로 그 장치다.
여기가 조용히 실패하면 **검증이 미래 데이터로 통과한다** — 이 프로젝트가
하루 종일 싸운 그 결함 계열의 가장 나쁜 형태다.

실패가 조용한 이유가 하나 더 있다. intraday 인덱스는 tz-aware(거래소 tz)이고
일봉 인덱스는 tz-naive다. 둘을 그냥 비교하면 pandas가 TypeError를 내고,
호출부는 그것을 '시세 조회 실패'로 받아 **합성 데이터로 폴백**한다. 즉
룩어헤드 차단이 깨진 자리가 "데이터를 못 받았다"로 보인다.

커버리지에서 `_cut_range` 7줄·`_align_ts` 7줄이 미실행이었다. 네트워크가
필요 없는 순수 함수인데도 아무도 돌려 보지 않았다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.data.stock import _align_ts, _cut_range          # noqa: E402


def _daily(n=10, start="2026-01-01"):
    """tz-naive 일봉."""
    idx = pd.date_range(start, periods=n, freq="D")
    return pd.DataFrame({"close": range(n)}, index=idx)


def _intraday(n=10, tz="America/New_York"):
    """tz-aware 분봉."""
    idx = pd.date_range("2026-01-05 09:30", periods=n, freq="30min", tz=tz)
    return pd.DataFrame({"close": range(n)}, index=idx)


# ── 룩어헤드 차단 ───────────────────────────────────────────────

def test_end_cuts_future_bars_on_a_naive_index():
    df = _cut_range(_daily(10), None, "2026-01-05", limit=999)
    assert df.index.max() <= pd.Timestamp("2026-01-05")
    assert len(df) == 5


def test_the_bar_exactly_at_end_is_kept():
    """경계 봉은 미래가 아니다 — 버리면 그날 결정을 재현할 수 없다."""
    df = _cut_range(_daily(10), None, "2026-01-05", limit=999)
    assert pd.Timestamp("2026-01-05") in df.index


def test_naive_end_against_an_aware_index_does_not_explode():
    """분봉(tz-aware)에 naive end가 와도 TypeError가 나면 안 된다.

    예전에는 여기서 예외가 나면 호출부가 '시세 조회 실패'로 받아 **합성
    데이터로 폴백**했다 — 룩어헤드 차단이 깨진 자리가 '데이터 없음'으로
    보였다.
    """
    src = _intraday(10)
    cutoff = src.index[4].tz_localize(None)          # naive로 만든 같은 시각
    df = _cut_range(src, None, cutoff, limit=999)
    assert len(df) == 5, df.index
    assert df.index.max() <= src.index[4]


def test_aware_end_against_a_naive_index_does_not_explode():
    src = _daily(10)
    cutoff = pd.Timestamp("2026-01-05", tz="UTC")
    df = _cut_range(src, None, cutoff, limit=999)
    assert len(df) == 5, df.index


def test_start_filters_the_beginning():
    df = _cut_range(_daily(10), "2026-01-06", None, limit=999)
    assert df.index.min() >= pd.Timestamp("2026-01-06")
    assert len(df) == 5


def test_start_and_end_together_bound_both_sides():
    df = _cut_range(_daily(10), "2026-01-03", "2026-01-06", limit=999)
    assert len(df) == 4
    assert df.index.min() == pd.Timestamp("2026-01-03")
    assert df.index.max() == pd.Timestamp("2026-01-06")


def test_limit_applies_only_when_no_range_is_given():
    """범위를 줬는데 limit이 또 자르면 요청한 구간이 잘려 나간다."""
    full = _cut_range(_daily(10), "2026-01-01", "2026-01-10", limit=3)
    assert len(full) == 10, "범위 지정인데 limit이 끼어들어 구간을 잘랐다"

    tail = _cut_range(_daily(10), None, None, limit=3)
    assert len(tail) == 3 and tail.index.max() == pd.Timestamp("2026-01-10")


def test_an_end_before_all_data_yields_nothing_not_everything():
    """자를 게 전부여도 조용히 전체를 돌려주면 안 된다."""
    df = _cut_range(_daily(10), None, "2025-12-01", limit=999)
    assert len(df) == 0, "end보다 뒤인 봉이 남았다 — 룩어헤드"


# ── _align_ts 자체 ──────────────────────────────────────────────

def test_align_localizes_a_naive_ts_to_the_index_tz():
    idx = _intraday(3).index
    out = _align_ts(pd.Timestamp("2026-01-05 10:00"), idx)
    assert out.tzinfo is not None and str(out.tz) == str(idx.tz)


def test_align_converts_an_aware_ts_to_naive_utc():
    idx = _daily(3).index
    out = _align_ts(pd.Timestamp("2026-01-02 05:00", tz="Asia/Seoul"), idx)
    assert out.tzinfo is None
    # 05:00 KST = 전날 20:00 UTC — 시각을 버리지 않고 변환해야 한다
    assert out == pd.Timestamp("2026-01-01 20:00")


def test_align_leaves_a_matching_pair_alone():
    idx = _daily(3).index
    ts = pd.Timestamp("2026-01-02")
    assert _align_ts(ts, idx) == ts


@pytest.mark.parametrize("tz", ["UTC", "Asia/Seoul", "America/New_York"])
def test_alignment_never_moves_a_bar_across_the_cutoff(tz):
    """어느 시간대에서든 '같은 시각'은 같은 쪽에 남아야 한다.

    변환이 틀리면 경계 근처 봉이 잘리거나(재현 불가) 남는다(룩어헤드).
    """
    src = _intraday(20, tz=tz)
    cutoff_aware = src.index[9]
    a = _cut_range(src, None, cutoff_aware, limit=999)
    b = _cut_range(src, None, cutoff_aware.tz_localize(None), limit=999)
    assert len(a) == len(b) == 10, (len(a), len(b))
