"""캡션이 '목표'를 '실제'처럼 말한다 (2026-08-14 감사 238).

같은 계좌를 두고 사이트와 SNS가 다른 숫자를 말하고 있었다.

    사이트  "투자 중 271,475원(27.2%) · 현금 728,372원(72.8%)"
            "오늘 목표 노출은 45.6% — 차이는 아직 정리되지 않은 기존 보유"
    캡션    "💰 999,847원 … · **노출 46%**"

캡션의 46%는 그날의 **목표**다. 실제로 시장에 나가 있던 돈은 27.2%였다.
차이는 주식의 다음 시가 대기(13.9%p)와, 밴드·쿨다운으로 아직 목표까지 채우지
못한 기존 보유다. 캡션만 읽는 사람은 자기 돈의 절반이 시장에 있다고 읽는다.

같은 뿌리의 결함이 둘 더 있었다:

    "🎯 배분 상위: 솔라나 · **아마존** · 리플"  ← 아마존은 한 주도 없었다
    "오늘 **7종목** 보유"                        ← 실제 보유는 5종목

**이 실수의 세 번째 거울이다.** 감사 218에서 시작금이 그랬고(사이트 산문은
고쳤는데 캡션은 "8만원"이 그대로), 감사 113·114에서 카드와 캡션이 서로
번갈아 빠졌다. 사이트는 2026-08-13에 이미 고쳤는데 캡션만 남아 있었다.

방송에 나가는 글이라 사이트보다 오히려 더 위험하다 — 사이트는 옆에 설명이
붙지만 캡션은 숫자 하나만 읽히기 때문이다.

지키는 계약:
  · 캡션은 **실제 투자 비율을 앞에** 쓰고, 목표는 괄호로 덧붙인다
  · 잔고를 모르는 옛 기록에서는 목표를 실제인 것처럼 말하지 않는다
  · 아직 안 산 종목에는 **(대기)**라고 적는다
  · 종목 수는 실제 보유 수다
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.reporting.social import build_captions  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _status(invested_value=271_474.89, equity=999_847.15, target=0.4562,
            pending=None, holdings_n=5):
    """실측(2026-08-14)을 본뜬 최소 status."""
    pending = {"us_stock:AMZN": 0.0878, "us_stock:META": 0.0515} \
        if pending is None else pending
    holdings = [{"key": f"crypto:C{i}/USDT", "value": invested_value / holdings_n}
                for i in range(holdings_n)] if holdings_n else []
    return {
        "updated": "2026-08-14",
        "symbols": {"crypto:SOL/USDT": {"name": "솔라나"},
                    "us_stock:AMZN": {"name": "아마존"},
                    "crypto:XRP/USDT": {"name": "리플"}},
        "paper": {"portfolio:ALL": {
            "equity": equity, "cash": equity - invested_value,
            "holdings": holdings,
            "principal": 1_000_000.0, "start_cash": 1_000_000.0,
            "history": [{
                "date": "2026-08-14", "equity": equity,
                "return_pct": -0.02, "day_pct": 0.02, "twr_pct": -0.02,
                "weight": target, "risk_scale": 1.0, "exposure_scale": 1.0,
                "applied": {"crypto:SOL/USDT": 0.15, "us_stock:AMZN": 0.0878,
                            "crypto:XRP/USDT": 0.0747},
                "pending_next_open": pending,
            }],
        }},
    }


def _caps(**kw):
    return build_captions(_status(**kw), "https://example.test")


# ── 실제가 앞에 온다 ──────────────────────────────────────────

def test_the_caption_leads_with_what_is_actually_invested():
    c = _caps()
    assert "투자 중 27%" in c["instagram"], c["instagram"]
    assert "현금 73%" in c["instagram"]


def test_the_target_is_still_shown_but_named_as_a_target():
    """목표를 지우는 것이 답이 아니다 — 무엇인지 밝히고 함께 보여준다."""
    ig = _caps()["instagram"]
    assert "오늘 목표 46%" in ig
    assert "총노출" not in ig, "목표를 여전히 '총노출'이라 부른다"


def test_the_thread_version_keeps_the_same_rule():
    """스레드는 500자 제한이라 짧지만 순서는 같아야 한다."""
    th = _caps()["threads"]
    assert "투자 27%(목표 46%)" in th, th
    assert "노출 46%" not in th


def test_the_gap_is_explained():
    """왜 다른지 안 적으면 '숫자가 이상하다'로만 읽힌다."""
    assert "다음 시가 대기 14%p 포함" in _caps()["instagram"]


def test_no_gap_means_no_parenthetical():
    """대조군 — 목표와 실제가 같은 날까지 괄호를 달면 글이 지저분해진다."""
    ig = _caps(target=0.2715)["instagram"]
    assert "투자 중 27%" in ig
    assert "목표" not in ig.split("\n")[6], ig.split("\n")[6]


# ── 모르면 목표로 대신하지 않는다 ─────────────────────────────

def test_an_old_record_without_holdings_does_not_fake_it():
    """잔고가 없던 시절 기록 — 목표를 '투자 중'이라고 말하면 안 된다."""
    ig = _caps(holdings_n=0)["instagram"]
    assert "목표 노출 46%" in ig
    assert "투자 중" not in ig
    th = _caps(holdings_n=0)["threads"]
    assert "목표 노출 46%" in th


def test_a_broken_holdings_entry_does_not_take_the_caption_down():
    st = _status()
    st["paper"]["portfolio:ALL"]["holdings"][0]["value"] = None
    c = build_captions(st, "https://example.test")
    assert c["instagram"] and c["threads"]


# ── 안 산 종목은 그렇게 적는다 ────────────────────────────────

def test_a_pending_symbol_is_marked_as_pending():
    """"배분 상위: 솔라나 · 아마존 · 리플" — 아마존은 한 주도 없었다."""
    for text in _caps().values():
        if not isinstance(text, str) or "배분 상위" not in text:
            continue
        assert "아마존(대기)" in text, text


def test_a_held_symbol_is_not_marked():
    """대조군 — 들고 있는 종목에 (대기)를 붙이면 그 표시가 무의미해진다."""
    ig = _caps()["instagram"]
    assert "솔라나 ·" in ig and "솔라나(대기)" not in ig


def test_nothing_is_marked_when_nothing_is_pending():
    ig = _caps(pending={})["instagram"]
    assert "(대기)" not in ig


# ── 종목 수는 실제 보유 수 ────────────────────────────────────

def test_the_symbol_count_is_what_is_actually_held():
    """applied 키를 세면 대기 종목까지 '보유'가 된다(실측 5 vs 캡션 7)."""
    assert "5종목 보유" in _caps()["instagram"]
    assert "7종목 보유" not in _caps()["instagram"]


def test_the_count_follows_the_holdings_list():
    assert "3종목 보유" in _caps(holdings_n=3)["instagram"]


# ── 사이트와 같은 값을 말하는가 (실제 장부로) ──────────────────

def test_the_caption_and_the_site_read_the_same_ledger():
    """**진짜 status.json으로** 확인한다 — 두 화면이 갈라지면 안 된다."""
    path = ROOT / "docs" / "status.json"
    if not path.exists():
        pytest.skip("status.json 없음")
    st = json.loads(path.read_text("utf-8"))
    port = (st.get("paper") or {}).get("portfolio:ALL") or {}
    if not port.get("holdings"):
        pytest.skip("잔고가 없는 기록")
    eq = float(port["equity"])
    inv = sum(float(h["value"]) for h in port["holdings"]) / eq
    ig = build_captions(copy.deepcopy(st), "https://example.test")["instagram"]
    assert f"투자 중 {inv * 100:.0f}%" in ig, (
        f"캡션이 사이트와 다른 투자 비율을 말한다 (사이트 {inv * 100:.1f}%)")


def test_the_caption_never_calls_the_target_the_whole_exposure():
    """소스에서 옛 표현이 되살아나지 않게 못박는다."""
    src = (ROOT / "quant" / "reporting" / "social.py").read_text("utf-8")
    assert 'f"📈 총노출 {gross}' not in src
    assert 'f"💰 {eq} (누적 {ret}{day_line}) · 노출 {gross}' not in src
