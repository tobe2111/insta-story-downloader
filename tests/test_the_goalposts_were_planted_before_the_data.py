"""실험 판정 기준의 사전 등록 — 골대는 데이터보다 먼저 (2026-08-19).

결과를 보고 기준을 정하면 그 선택이 결과에 오염된다(골대 이동). 장중
실험 30→90일을 "첫날 고쳐야 정직한 수정"이라 했던 원칙의 일반화.

지켜야 할 약속:
- 돌고 있는 실험 7개(미국 장중·미국 지정가 그림자·2세대 집중 포함)가 전부 등록돼 있고, 필수
  항목(시작일·판정일·통계·유의수준·보정·미달 시 결과)이 빠짐없다.
- 판정일 = 시작일 + 선언한 기간(날짜 산수가 맞는다).
- 다(多)트랙 실험은 다중비교 보정을 선언한다.
- 공개 페이지(trust)에 같은 판정일이 실려 있다 — 코드에만 있는 등록은
  등록이 아니다.
- status.json에 등록 원문이 실린다.
- 수정 이력(AMENDMENTS)에 항목이 생기면 trust에도 정정이 있어야 한다.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live import prereg                            # noqa: E402

TRUST = (ROOT / "docs" / "trust.html").read_text("utf-8")

EXPECTED = {"intraday_1h": ("2026-08-18", 90),
            "cadence_ladder": ("2026-08-18", 90),
            "limit_shadow": ("2026-08-18", 90),
            "intraday_us": ("2026-08-19", 90),
            "us_limit_shadow": ("2026-08-19", 90),
            "gen2_concentration": ("2026-08-19", 120),
            "alloc_ladder": ("2026-08-19", 120),
            "sizing_ladder": ("2026-08-22", 120)}

REQUIRED = ("name", "question", "start", "judge_on", "statistic",
            "alpha", "correction", "on_fail")


def test_all_four_experiments_are_registered_completely():
    assert set(prereg.PREREGISTERED) == set(EXPECTED), (
        f"등록 목록이 실험 목록과 다르다: {sorted(prereg.PREREGISTERED)}")
    for key, exp in prereg.PREREGISTERED.items():
        missing = [k for k in REQUIRED if not exp.get(k)]
        assert not missing, f"{key}의 필수 항목이 빠졌다: {missing}"
        assert exp["alpha"] == 0.05


def test_the_date_arithmetic_is_honest():
    """판정일이 '시작 + 기간'과 다르면 이미 골대가 움직인 것이다."""
    for key, (start, days) in EXPECTED.items():
        exp = prereg.PREREGISTERED[key]
        assert exp["start"] == start, f"{key} 시작일이 실측과 다르다"
        want = (dt.date.fromisoformat(start)
                + dt.timedelta(days=days)).isoformat()
        assert exp["judge_on"] == want, (
            f"{key} 판정일 {exp['judge_on']} ≠ {start}+{days}일({want})")


def test_multi_track_experiments_declare_their_correction():
    for key in ("cadence_ladder", "alloc_ladder", "sizing_ladder"):
        assert "본페로니" in prereg.PREREGISTERED[key]["correction"], (
            f"{key}는 비교가 여러 쌍인데 다중비교 보정 선언이 없다")


def test_every_verdict_date_is_on_the_public_page():
    assert "사전 등록" in TRUST, "trust에 사전 등록 문단이 없다"
    for key, exp in prereg.PREREGISTERED.items():
        assert exp["judge_on"] in TRUST, (
            f"{key}의 판정일({exp['judge_on']})이 공개 페이지에 없다 — "
            "코드에만 있는 등록은 등록이 아니다")
    assert "미체결율 20%" in TRUST, "지정가 그림자의 추가 관문이 공개돼 있지 않다"


def test_the_registration_reaches_the_ledger():
    daily = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert 'status["prereg"]' in daily, "등록 원문이 status.json에 안 실린다"
    paper = (ROOT / "docs" / "paper.html").read_text("utf-8")
    assert "st.prereg" in paper, (
        "배분 카드가 판정일을 등록 원문에서 읽지 않는다")


def test_amendments_must_surface_on_the_public_page():
    """수정은 금지가 아니라 공개다 — 조용한 수정만 금지다."""
    for a in prereg.AMENDMENTS:
        assert a.get("on") and a.get("why"), "수정 이력에 날짜·이유가 없다"
        assert a["on"] in TRUST, (
            f"{a['on']} 수정이 공개 페이지에 없다 — 조용한 수정이다")


def test_failing_the_bar_never_moves_the_bar():
    for key, exp in prereg.PREREGISTERED.items():
        assert "현행" in exp["on_fail"] and "공개" in exp["on_fail"], (
            f"{key}의 미달 시 결과가 '현행 유지 + 공개'가 아니다")
