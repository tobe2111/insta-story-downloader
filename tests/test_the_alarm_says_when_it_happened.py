"""경보가 **며칠 전 사고를 오늘 일처럼** 말하고 있었다 (감사 264).

2026-08-16 밤, 디스코드로 이런 경보가 나갔습니다.

    🚨 현금 부족으로 거부된 주문 1건: us_stock:AMZN — 지금 구조에서는
       나올 수 없는 값입니다. …

그런데 그 일은 **이틀 전(2026-08-15)** 통화 사고(감사 254) 때 생긴 것이고,
그날 안에 이미 되돌렸습니다. 장부가 08-15에서 멈춰 있었기 때문에
`history[-1]`이 계속 그날 기록을 가리켰던 것입니다.

이 파일의 경보들은 전부 `history[-1]`을 읽으면서 **그 기록이 오늘 것인지
묻지 않았습니다.** 그래서 배치가 커밋을 못 하는 동안 같은 경고가 매일
현재형으로 나갑니다. 감사 243(정체 경보)과 같은 계열입니다.

고칠 때 **경보를 끄지는 않습니다** — 아직 안 고쳤을 수도 있습니다. 대신
① 언제 것인지 밝히고, ② 장부가 멈춘 것 **자체**를 따로 알립니다.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.flag_watch import (LEDGER_STALE_DAYS, _current_flags,  # noqa: E402
                                   _ledger_age)


def _status(day: str, **extra) -> dict:
    last = {"date": day, "equity": 1_000_000.0, "return_pct": 0.0}
    last.update(extra)
    return {"paper": {"portfolio:ALL": {"history": [last]}}}


_CASH = {"cash_short": [{"key": "us_stock:AMZN", "need": 1.0, "cash": 0.0}]}


# ── ① 나이를 잴 수 있는가 ────────────────────────────────────────

def test_the_age_is_measured_from_today():
    assert _ledger_age({"date": "2026-08-15"}, "2026-08-17") == ("2026-08-15", 2)
    assert _ledger_age({"date": "2026-08-17"}, "2026-08-17") == ("2026-08-17", 0)


def test_a_missing_or_broken_date_does_not_crash():
    """날짜를 못 재면 **경보를 끄지 않는다** — 모르는 것과 괜찮은 것은 다르다."""
    assert _ledger_age({}, "2026-08-17") == (None, None)
    assert _ledger_age({"date": "어제"}, "2026-08-17") == ("어제", None)
    flags = _current_flags(_status("어제", **_CASH), today="2026-08-17")
    assert [k for k in flags if k.startswith("cash_short:")], list(flags)


# ── ② 오래된 경보가 언제 것인지 밝히는가 ─────────────────────────

def test_a_stale_warning_says_when_it_happened():
    """실측 그 장면 — 08-15 기록이 08-16 밤에 현재형으로 나갔다."""
    flags = _current_flags(_status("2026-08-15", **_CASH), today="2026-08-17")
    msg = next(v for k, v in flags.items() if k.startswith("cash_short:"))
    assert msg.startswith("[2026-08-15 기록 · 2일 전]"), msg
    # 경보 자체는 **살아 있다** — 아직 안 고쳤을 수 있다.
    assert "us_stock:AMZN" in msg


def test_a_todays_warning_has_no_prefix():
    """대조군 — 오늘 기록에 날짜 딱지가 붙으면 모든 경보가 낡아 보인다."""
    flags = _current_flags(_status("2026-08-17", **_CASH), today="2026-08-17")
    msg = next(v for k, v in flags.items() if k.startswith("cash_short:"))
    assert not msg.startswith("["), msg
    assert msg.startswith("🚨"), msg


# ── ③ 장부가 멈춘 것 자체를 알리는가 ─────────────────────────────

def test_a_stalled_ledger_is_its_own_alarm():
    """배치 실패 경보는 워크플로가 보내지만, 그 채널이 죽으면(감사 263)
    아무도 모른다. 장부가 안 느는 것 **자체**가 사건이다."""
    flags = _current_flags(_status("2026-08-15", **_CASH), today="2026-08-17")
    keys = [k for k in flags if k.startswith("ledger_stalled:")]
    assert keys, list(flags)
    assert keys[0].endswith(":2"), keys           # 나이가 키에 들어간다
    assert "2026-08-15" in flags[keys[0]], flags[keys[0]]


def test_a_fresh_ledger_is_quiet():
    """대조군 — 어제 기록은 정상이다(주말·휴일 배치 시각 차이).

    문턱을 잘못 잡으면 매일 울려서 아무도 안 본다.
    """
    assert LEDGER_STALE_DAYS == 2
    for day in ("2026-08-17", "2026-08-16"):
        flags = _current_flags(_status(day), today="2026-08-17")
        assert not [k for k in flags if k.startswith("ledger_stalled:")], (day, list(flags))


def test_the_stall_alarm_repeats_when_it_gets_worse():
    """나이가 키에 들어가야 **하루 더 멈추면 다시 울린다.**

    키가 고정이면 첫날만 울리고 그 뒤로는 영원히 '이미 켜져 있던 플래그'로
    분류돼 조용해진다 — 그게 이 시스템에서 가장 위험한 침묵이다.
    """
    a = _current_flags(_status("2026-08-15"), today="2026-08-17")
    b = _current_flags(_status("2026-08-15"), today="2026-08-18")
    ka = {k for k in a if k.startswith("ledger_stalled:")}
    kb = {k for k in b if k.startswith("ledger_stalled:")}
    assert ka and kb and ka != kb, (ka, kb)
