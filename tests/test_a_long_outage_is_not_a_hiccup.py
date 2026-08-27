"""피처 유실 경보가 **하루 장애와 끊긴 소스를 구별한다** (2026-08-27).

■ 이건 결함이 아니라 개선이다 (정직하게)

장치 자체는 이미 잘 돌고 있었다. 장부에 빠진 피처 이름·어느 소스 탓인지·
왜 그런지·어느 종목인지까지 남기고(``feature_health``), 경보도 한 번 울렸다
(``flag_state``에 ``features_missing:x_frgn5,x_inst5``가 저장돼 있다).

빠져 있던 것은 **기간**뿐이다. 경보 문장이 "오늘 빠졌다"만 말해서, 읽는
쪽이 **기다리면 되는 일**과 **사람이 고쳐야 하는 일**을 구별할 수 없었다.

    실측(장부 2026-08-20~): 한국 수급 피처 두 개가 42밤 내내 0/42.
    원인은 KRX 로그인 설정 — 기다린다고 저절로 낫지 않는다.

■ ⚠️ 열쇠에 날짜를 넣지 않는다

경보는 **새로 켜진 열쇠만** 알림을 보낸다(이미 켜진 것은 다시 안 보낸다).
열쇠에 "42일째"를 넣으면 매일 새 열쇠가 되어 **매일 알림이 간다** — 그건
고치는 게 아니라 늑대소년을 하나 더 만드는 것이다(감사 99: 매일 울리는
경보는 꺼진 경보와 같다). 기간은 열쇠가 아니라 **문장**에 들어간다.
"""
from __future__ import annotations

from quant.live.flag_watch import (LONG_OUTAGE_DAYS, _current_flags,
                                   _missing_streak)


def _paper(days_missing: int, gone=("x_frgn5", "x_inst5"), why=None) -> dict:
    """전 종목에서 gone이 days_missing일 연속 빠진 페이퍼 장부."""
    hist = []
    for _ in range(10 - days_missing):
        hist.append({"feature_health": {"missing_everywhere": []}})
    for _ in range(days_missing):
        rec = {"feature_health": {"missing_everywhere": list(gone)}}
        if why:
            rec["feature_health"]["why_missing"] = why
        hist.append(rec)
    return {"paper": {"portfolio:ALL": {"history": hist}}}


def _feature_flags(status: dict) -> dict:
    return {k: v for k, v in _current_flags(status).items()
            if k.startswith("features_missing:")}


def test_a_one_day_gap_reads_as_a_hiccup():
    """하루 빠진 것은 **기다리면 되는 일**로 읽힌다."""
    flags = _feature_flags(_paper(1))
    assert flags, "피처가 빠졌는데 경보가 없다"
    msg = next(iter(flags.values()))
    assert "일시 장애" in msg, f"하루짜리를 장기 결손처럼 말한다: {msg}"


def test_a_long_outage_says_a_person_must_fix_it():
    """오래 빠진 것은 **사람이 고쳐야 하는 일**로 읽힌다.

    기다린다고 저절로 낫지 않는 종류(설정 누락·끊긴 계약)를 '일시 장애'라고
    말하면, 읽는 쪽은 아무것도 안 하고 몇 주가 지난다. 실제로 그랬다.
    """
    flags = _feature_flags(_paper(LONG_OUTAGE_DAYS + 5))
    msg = next(iter(flags.values()))
    assert f"{LONG_OUTAGE_DAYS + 5}일째" in msg, (
        f"며칠째인지 안 적는다: {msg}")
    assert "일시 장애가 아닙니다" in msg, (
        f"오래된 결손을 여전히 일시 장애처럼 말한다: {msg}")


def test_the_alarm_key_does_not_carry_the_day_count():
    """⚠️ 열쇠는 **날짜가 바뀌어도 그대로**다 — 안 그러면 매일 알림이 간다.

    경보는 새로 켜진 열쇠만 보낸다. 열쇠에 기간이 들어가면 매일 새 열쇠가
    되고, 매일 울리는 경보는 꺼진 경보와 같다.
    """
    a = set(_feature_flags(_paper(1)))
    b = set(_feature_flags(_paper(9)))
    assert a == b and a, f"기간이 열쇠를 바꾼다: {a} vs {b}"


def test_the_recorded_reason_rides_along():
    """장부가 아는 **사유**를 경보가 함께 싣는다.

    사유는 이미 장부에 있었다(어느 소스가, 왜). 경보에 안 실으면 읽는 쪽이
    장부를 열어야 하고, 그러면 대개 안 연다.
    """
    why = {"krx_flows": {"reason": "KRX 로그인 설정이 빠졌을 수 있다"}}
    msg = next(iter(_feature_flags(_paper(7, why=why)).values()))
    assert "KRX 로그인 설정" in msg, f"사유를 안 싣는다: {msg}"


def test_nothing_missing_means_no_alarm():
    """대조군 — 다 붙어 있으면 **아무 말도 안 한다**.

    ⚠️ 이게 없으면 "언제나 경보"도 위 검사들을 통과한다. 늘 켜져 있는
       경고등은 꺼진 것과 같다.
    """
    assert not _feature_flags(_paper(0))


def test_the_streak_stops_at_a_day_that_recovered():
    """중간에 한 번이라도 붙었으면 **거기서 끊는다**.

    "연속"이라고 적어 놓고 전체 결손 일수를 세면, 어제 회복된 소스도
    '42일째'라고 말하게 된다.
    """
    hist = ([{"feature_health": {"missing_everywhere": ["a"]}}] * 3
            + [{"feature_health": {"missing_everywhere": []}}]
            + [{"feature_health": {"missing_everywhere": ["a"]}}] * 2)
    assert _missing_streak(hist, ["a"]) == 2


def test_a_partial_overlap_is_not_the_same_outage():
    """빠진 **조합이 달라지면** 같은 결손이 아니다.

    어제는 하나만 빠졌는데 오늘 둘이 빠졌다면, 그건 이어진 사건이 아니라
    더 나빠진 사건이다. 이어 세면 '오래됐으니 아는 일'로 잘못 읽힌다.
    """
    hist = ([{"feature_health": {"missing_everywhere": ["a"]}}] * 4
            + [{"feature_health": {"missing_everywhere": ["a", "b"]}}])
    assert _missing_streak(hist, ["a", "b"]) == 1
    assert _missing_streak(hist, ["a"]) == 5      # a만 보면 5일째가 맞다


def test_an_empty_ledger_does_not_crash():
    """장부가 비어도(첫날·새 설치) 조용히 0을 돌려준다."""
    assert _missing_streak([], ["a"]) == 0
    assert _missing_streak([{"feature_health": {}}], ["a"]) == 0
    assert _missing_streak([{}], ["a"]) == 0
    assert _missing_streak([{"feature_health": {"missing_everywhere": ["a"]}}],
                           []) == 0
