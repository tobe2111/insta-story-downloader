"""일일 요약이 **막 시작한 날**을 요약하고 있었다 (감사 193).

`maybe_daily_summary`는 UTC 날짜가 바뀐 **직후** 불린다. 그런데 요약 대상으로
`today`(= 새 날짜)를 넘겼다.

    return t, build_daily_summary(state, today=t)      # t = 방금 시작한 날

새 날에는 기록이 0~1건뿐이다. 실측 — 08-12에 3사이클을 돌고 롤오버했더니:

    예전:  "일일 요약(2026-08-13 UTC): 오늘 사이클 1회 · 자산 111.00"
    실제:  08-12은 3사이클 · 그 날 마지막 자산 110.00

하루를 마감하는 보고인데 **아직 시작도 안 한 날**을 보고했다. 어제가 아무리
바빴어도 늘 0~1회로 찍히므로, 이 알림을 받는 사람은 "봇이 거의 안 돌았다"고
읽는다. 게다가 자산·적중률은 `history[-1]`(= 전체에서 가장 최근)에서 가져와
**다음 날 값**을 어제 요약에 실었다.

기존 검사는 롤오버에서 "'일일 요약'이라는 글자가 있는가"만 봤다 — **어느 날을
요약했는지는 아무도 안 봤다.**

배선: `live/multi.py` · `live/engine.py` · `live/autolearn.py` 세 러너가
매 사이클 부른다.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.summary import (  # noqa: E402
    build_daily_summary, maybe_daily_summary,
)

STATE = {
    "symbol": "BTC/USDT", "strategy": "ma_cross", "mode": "paper",
    "history": [
        {"time": "2026-08-12T01:00:00", "equity": 100.0, "recent_hit_rate": 0.60, "recent_n": 25},
        {"time": "2026-08-12T09:00:00", "equity": 105.0, "recent_hit_rate": 0.70, "recent_n": 25},
        {"time": "2026-08-12T17:00:00", "equity": 110.0, "recent_hit_rate": 0.80, "recent_n": 25},
        {"time": "2026-08-13T00:05:00", "equity": 111.0, "recent_hit_rate": 0.10, "recent_n": 10},
    ],
}


# ── 어느 날을 요약하는가 ──────────────────────────────────────


def test_the_rollover_summary_covers_the_day_that_just_ended():
    day, text = maybe_daily_summary(STATE, last_date="2026-08-12",
                                    today="2026-08-13")
    assert day == "2026-08-13", "다음 요약 기준 날짜는 오늘이어야 한다"
    assert "2026-08-12" in text, f"끝난 날이 아니라 시작한 날을 요약했다: {text}"
    assert "2026-08-13" not in text, text


def test_it_counts_the_whole_ended_day_not_the_new_one():
    _, text = maybe_daily_summary(STATE, last_date="2026-08-12",
                                  today="2026-08-13")
    assert "사이클 3회" in text, (
        f"08-12은 3사이클이었는데 새 날의 기록 수를 셌다: {text}")


def test_it_reads_the_last_record_of_that_day_not_the_newest_overall():
    """자산·적중률을 `history[-1]`에서 가져오면 **다음 날 값**이 실린다."""
    _, text = maybe_daily_summary(STATE, last_date="2026-08-12",
                                  today="2026-08-13")
    assert "110.00" in text and "111.00" not in text, (
        f"어제 요약에 오늘 자산이 실렸다: {text}")
    # 적중률도 그 날 마지막 기록의 것이어야 한다. 서식은 2026-08-14부터
    # 구간을 함께 낸다 — 80%(n=25)는 판정되고, 다음 날의 10%는 안 나온다.
    assert "80% (61~91% · n=25)" in text and "10%" not in text, text


# ── 대조군: 롤오버 판정 자체는 그대로인가 ─────────────────────


def test_no_summary_on_the_same_day():
    assert maybe_daily_summary(STATE, "2026-08-13", today="2026-08-13")[1] is None


def test_no_summary_on_the_very_first_cycle():
    """재시작할 때마다 요약이 중복 전송되면 안 된다."""
    day, text = maybe_daily_summary(STATE, None, today="2026-08-13")
    assert day == "2026-08-13" and text is None


def test_a_day_with_no_records_still_produces_a_summary():
    """대조군 — 조용한 날이라고 알림이 사라지면 '봇이 죽었나'와 구별이 안 된다."""
    _, text = maybe_daily_summary(STATE, last_date="2026-08-11",
                                  today="2026-08-12")
    assert text and "2026-08-11" in text and "사이클 0회" in text


def test_a_direct_call_still_summarises_the_day_it_was_given():
    assert "사이클 3회" in build_daily_summary(STATE, today="2026-08-12")
    assert "사이클 1회" in build_daily_summary(STATE, today="2026-08-13")


# ── 누락·손상에 안전한가 ──────────────────────────────────────


def test_missing_keys_do_not_raise():
    for bad in ({}, {"history": "리스트가 아님"}, {"history": [None, 3]},
                {"history": [{"time": None}]}):
        text = build_daily_summary(bad, today="2026-08-12")
        assert "일일 요약" in text and "N/A" in text


def test_a_non_dict_state_is_survivable():
    assert "일일 요약" in build_daily_summary(None, today="2026-08-12")
    assert "일일 요약" in build_daily_summary("문자열", today="2026-08-12")
