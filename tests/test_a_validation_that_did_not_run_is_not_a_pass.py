"""돌지 못한 검증이 화면에서 조용하다 (감사 249).

과최적화 감시(PBO·DSR)는 장부에 남고 사이트가 읽어 경보합니다. 그런데
규칙 두 개가 모두 이렇게 시작합니다:

    if pbo is not None and float(pbo) > 0.5: ...
    if dsr is not None and float(dsr) < 0.95: ...

값이 **없는** 항목에 대해서는 아무 말도 하지 않습니다. 그리고 값이 없는
경우가 실제로 있습니다 — 표본이 모자라면 `walk_forward`가 `ValueError`를
내고, 그 종목의 DSR은 `null`로 남습니다(이유는 콘솔에만 찍혔습니다).

실측(2026-08-15 장부):

    crypto:BTC/USDT   bars 300 · dsr **null** · pbo 0.78
    us_stock:SPY      bars 800 · dsr 0.008    · pbo 0.008

사이트에는 BTC의 **PBO 경보만** 떴습니다. 읽는 사람은 나머지가 통과한
줄로 읽습니다 — 사실은 **재지 못한 것**입니다.

같은 판정을 리포트 페이지는 이미 하고 있었습니다(감사 52):

    "판정 불가 — 돌지 못한 검증이 있음"
    # 돌지 않은 검증은 통과도 실패도 아니다.

**같은 사실을 한 화면은 말하고 다른 화면은 침묵**하고 있었습니다.
㉞ 같은 판정을 두 곳에서 쓰면 언젠가 갈라집니다.

고친 것: ① 못 돈 이유를 장부에 남긴다(콘솔에만 찍히면 사이트가 왜 없는지
모른다) ② 사이트가 "판정 불가"라고 말한다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.flag_watch import _current_flags  # noqa: E402


def _flags(validation: dict) -> dict:
    return _current_flags({"validation": validation})


# ── 재지 못한 것을 통과로 두지 않는가 ─────────────────────────

def test_a_missing_dsr_raises_a_flag():
    """실측 그 장면 — DSR이 null인데 사이트가 조용했다."""
    f = _flags({"crypto:BTC/USDT": {"strategy": "ml", "bars": 300,
                                    "dsr": None, "pbo": 0.78}})
    keys = [k for k in f if k.startswith("validation_missing")]
    assert keys, f"판정 불가를 말하지 않는다: {list(f)}"
    assert "판정 불가" in f[keys[0]]


def test_the_flag_says_why_it_could_not_run():
    """'왜 없는지'가 없으면 운영자가 할 일을 모른다."""
    f = _flags({"crypto:BTC/USDT": {
        "strategy": "ml", "dsr": None, "pbo": 0.1,
        "skipped": {"dsr": "표본이 부족합니다(최소 600봉)"}}})
    msg = f["validation_missing:crypto:BTC/USDT"]
    assert "표본이 부족합니다" in msg, msg


def test_it_says_so_even_without_a_recorded_reason():
    """옛 장부에는 이유 칸이 없다 — 그래도 침묵하지 않는다."""
    f = _flags({"x:Y": {"strategy": "ml", "dsr": None, "pbo": 0.1}})
    assert "이유 미기록" in f["validation_missing:x:Y"]


def test_both_missing_are_counted():
    f = _flags({"x:Y": {"strategy": "ml", "dsr": None, "pbo": None}})
    assert "검증 2종이 돌지 못했습니다" in f["validation_missing:x:Y"]


def test_it_does_not_read_as_a_pass():
    """문구가 '통과'로 읽히면 고친 의미가 없다."""
    f = _flags({"x:Y": {"strategy": "ml", "dsr": None, "pbo": 0.1}})
    msg = f["validation_missing:x:Y"]
    assert "재지 못한 것" in msg and "아직 검증되지 않았" in msg, msg


# ── 대조군: 다 잰 종목은 조용한가 ─────────────────────────────

def test_a_fully_measured_symbol_raises_no_missing_flag():
    """매일 울리는 경보는 꺼진 경보와 같다(감사 99)."""
    f = _flags({"x:Y": {"strategy": "ml", "dsr": 0.99, "pbo": 0.05}})
    assert not [k for k in f if k.startswith("validation_missing")], f


def test_the_existing_rules_still_fire():
    """대조군 — 새 규칙이 옛 규칙을 가리면 안 된다."""
    f = _flags({"x:Y": {"strategy": "ml", "dsr": 0.1, "pbo": 0.9}})
    assert any(k.startswith("overfit") for k in f)
    assert any(k.startswith("dsr_low") for k in f)


def test_a_zero_is_measured_not_missing():
    """0.0은 '못 쟀다'가 아니다 — falsy를 None으로 읽으면 안 된다."""
    f = _flags({"x:Y": {"strategy": "ml", "dsr": 0.0, "pbo": 0.0}})
    assert not [k for k in f if k.startswith("validation_missing")], f


# ── 배치가 이유를 남기는가 ────────────────────────────────────

def test_the_validate_command_records_the_reason():
    """콘솔에만 찍히면 사이트는 왜 없는지 영영 모른다."""
    src = (ROOT / "quant" / "cli.py").read_text("utf-8")
    assert '"skipped": dict(skipped) or None,' in src, (
        "검증 장부에 '못 돈 이유'가 안 실린다")
    for key in ("dsr", "pbo", "cpcv"):
        assert f'skipped["{key}"] = str(exc)' in src, (
            f"{key} 건너뜀 사유를 안 모은다")


# ── 두 화면이 같은 말을 하는가 ────────────────────────────────

def test_the_report_page_already_refuses_to_pass_it():
    """리포트 쪽 계약이 사라지면 이 감사의 전제가 무너진다."""
    src = (ROOT / "quant" / "reporting"
           / "validation_report.py").read_text("utf-8")
    assert "판정 불가 — 돌지 못한 검증이 있음" in src


def test_the_real_ledger_is_covered():
    """진짜 장부에 못 잰 항목이 있으면 지금 경보가 떠야 한다."""
    path = ROOT / "docs" / "status.json"
    if not path.exists():
        pytest.skip("status.json 없음")
    st = json.loads(path.read_text("utf-8"))
    val = st.get("validation") or {}
    missing = [k for k, r in val.items()
               if r.get("dsr") is None or r.get("pbo") is None]
    if not missing:
        pytest.skip("지금은 전부 측정됐다 — 이 검사의 전제가 없다")
    flags = _current_flags(st)
    for key in missing:
        assert f"validation_missing:{key}" in flags, (
            f"{key}의 못 잰 검증이 화면에서 조용하다")
