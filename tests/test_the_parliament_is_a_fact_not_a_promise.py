"""의회 의석 — 사이트가 약속한 구조가 실제로 켜져 있는가 (감사 225).

배경:
  trust.html은 "통과자 최대 3개가 의석을 나눠 갖고 … 단일 전략 붕괴가 계좌
  붕괴가 되는 구조를 **없앤 것**"이라고 현재형으로 적고 있었다. 그런데 실제
  장부는 20계좌 전부가 **1석**이었다 — 한 번도 2석이 된 적이 없다.

  의석은 2단계 오디션을 통과한 승격자만 얻는데 승격은 139회 중 1회였고,
  그 1회조차 챔피언의 파라미터 변형이라 상관 게이트가 곧바로 한 석으로
  합쳤다. 설계가 틀린 게 아니라 **잠든 구조를 작동 중이라 말한 문장**이
  틀렸다.

  그리고 하필 `parliament_summary`는 2석 이상일 때만 문장을 내놓는다 —
  이 장치는 작동할 때만 자기를 알리고 잠들어 있을 땐 침묵한다. 침묵은
  "정상"으로 읽힌다. 그래서 잠든 상태 자체를 숫자로 내보낸다.

핵심 계약:
  · 의석 수를 세는 자리는 하나다(seat_census) — 사이트는 읽기만 한다
  · 1석이면 diversified=False, 2석 이상이면 True (대조군 포함)
  · write_docs_status가 그 숫자를 status.json에 싣는다
  · trust.html의 '현재 상태' 문장은 그 숫자에서 만들어진다(하드코딩 금지)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.live.parliament import (  # noqa: E402
    PARLIAMENT_K, members_of, parliament_summary, seat_census,
)

ROOT = Path(__file__).resolve().parent.parent

_ML = {"strategy": "ml", "params": {"model": "logreg", "threshold": 0.55}}
_MA = {"strategy": "ma_cross", "params": {"fast": 20, "slow": 60}}


def _entry(*members):
    """champions.json 한 항목 — 리더가 strategy/params 자리를 유지한다."""
    lead = members[0]
    return {"strategy": lead["strategy"], "params": lead["params"],
            "parliament": [dict(m) for m in members]}


# ── ① 의석을 세는 자리는 하나다 ───────────────────────────────


def test_a_single_member_ledger_is_one_seat():
    """지금 실제 장부의 모습 — 의원 1명이면 1석이다."""
    census = seat_census({"crypto:BTC/USDT": _entry({**_ML, "weight": 1.0})})
    assert census["accounts"] == 1
    assert census["single_seat"] == 1
    assert census["multi_seat"] == 0
    assert census["max_seats"] == 1
    assert census["diversified"] is False
    assert census["cap"] == PARLIAMENT_K


def test_a_ledger_with_no_parliament_field_still_counts_one_seat():
    """의회 도입 이전 항목도 '단독 의회'로 세어야 한다(members_of와 같은 규칙)."""
    entry = {"strategy": "ml", "params": {"model": "logreg"}}
    assert len(members_of(entry)) == 1
    assert seat_census({"us_stock:SPY": entry})["max_seats"] == 1


def test_two_seats_are_reported_as_diversified():
    """대조군 — 구조가 켜지면 숫자가 그렇게 말해야 한다.

    ⚠️ 이 대조군이 없으면 seat_census가 무조건 1을 돌려줘도 위 검사는
       통과한다. '줄었다'는 검사에는 항상 '평소엔 안 줄어든다'가 붙는다.
    """
    census = seat_census({
        "kr_stock:005930.KS": _entry({**_ML, "weight": 0.6},
                                     {**_MA, "weight": 0.4}),
        "us_stock:SPY": _entry({**_ML, "weight": 1.0}),
    })
    assert census["accounts"] == 2
    assert census["multi_seat"] == 1
    assert census["single_seat"] == 1
    assert census["max_seats"] == 2
    assert census["diversified"] is True


def test_a_broken_entry_is_not_counted_as_a_seat():
    """셀 수 없는 항목은 세지 않는다 — 손상 기록이 의석 수를 부풀리면 안 된다."""
    census = seat_census({"bad": {"no": "strategy"}, "x": None,
                          "ok": _entry({**_ML, "weight": 1.0})})
    assert census["accounts"] == 1
    assert census["max_seats"] == 1


def test_empty_ledger_says_nothing_rather_than_claiming_diversity():
    census = seat_census({})
    assert census["accounts"] == 0 and census["diversified"] is False


# ── ② 침묵의 비대칭 — 켜졌을 때만 말한다 ─────────────────────


def test_the_summary_line_is_silent_while_the_structure_sleeps():
    """이것이 결함의 정체다 — parliament_summary는 1석에서 None을 준다.

    그래서 매일의 설명문에는 아무 말도 안 붙고, 사장님이 보시기엔
    '문제 없음'으로 읽힌다. seat_census는 그 침묵을 숫자로 깬다.
    """
    single = _entry({**_ML, "weight": 1.0})
    assert parliament_summary(single) is None
    assert seat_census({"k": single})["diversified"] is False   # 침묵 ≠ 정상

    multi = _entry({**_ML, "weight": 0.6}, {**_MA, "weight": 0.4})
    assert parliament_summary(multi) is not None


# ── ③ 사이트가 그 숫자를 읽는다 ───────────────────────────────


def test_write_docs_status_publishes_the_seat_census(tmp_path):
    from quant.live.daily import write_docs_status

    paper = tmp_path / "paper"
    paper.mkdir()
    (paper / "portfolio_ALL.json").write_text(json.dumps({
        "market": "portfolio", "symbol": "ALL", "currency": "KRW",
        "start_cash": 1_000_000.0, "cash": 1_000_000.0, "positions": {},
        "history": [{"date": "2026-08-13", "equity": 1_000_000.0,
                     "return_pct": 0.0}]}), "utf-8")
    (tmp_path / "champions.json").write_text(json.dumps({
        "crypto:BTC/USDT": _entry({**_ML, "weight": 1.0}),
        "us_stock:SPY": _entry({**_ML, "weight": 1.0}),
    }), "utf-8")

    out = tmp_path / "status.json"
    status = write_docs_status(str(tmp_path), docs_path=str(out))
    p = status["parliament"]
    assert p["accounts"] == 2
    assert p["single_seat"] == 2
    assert p["diversified"] is False
    assert json.loads(out.read_text("utf-8"))["parliament"] == p


def test_the_site_reads_the_census_instead_of_asserting_it():
    """'지금 몇 석인가'는 장부에서 와야 한다 — 문장에 박아 두면 안 된다.

    문장에 상태를 박으면 구조가 잠들어 있는 동안에도 계속 '분산 운용 중'
    으로 읽힌다. 그게 이번에 고친 결함 자체다.
    """
    html = (ROOT / "docs" / "trust.html").read_text("utf-8")
    assert 'id="seat-now"' in html, "현재 의석을 채울 자리가 없다"
    assert "st.parliament" in html, "사이트가 장부의 의석 수를 읽지 않는다"
    # 두 갈래(잠듦/켜짐)를 모두 렌더할 수 있어야 한다 — 한쪽만 있으면
    # 나중에 구조가 켜져도 문장은 영영 '잠들어 있다'고 말한다.
    assert "diversified" in html
