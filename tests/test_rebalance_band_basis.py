"""재조정 밴드가 **말없이 바뀌지 않는지** 확인한다 (감사 74).

밴드는 왕복 체결 비용에 비례하고, 실측 표본이 문턱(MEASURED_COST_MIN_SAMPLES)
을 넘는 순간 가정 → 실측으로 갈아탄다. 한국주식은 그 전환에서

    0.150 (하한 클립)  →  0.400 (상한 클립)      2.67배

로 뛴다. 회전율이 크게 줄어드는 날인데, 예전에는 이 값이 계산되어 쓰이고
**어디에도 기록되지 않았다** — 사장님이 보시기엔 이유 없이 매매가 멎은 날이
된다. 설계는 옳으므로(비싼 시장에서 덜 매매한다) 로직이 아니라 흔적을
검사한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.live import daily as D          # noqa: E402


@pytest.fixture
def gap(monkeypatch):
    """fill_gap_report를 대신해 원하는 표본 수·실측 갭을 만들어 준다."""

    def _set(market="kr_stock", n=0, assumed_bp=14.0, adverse_bp=62.1):
        rep = {"markets": {market: {"n": n, "assumed_bp": assumed_bp,
                                    "mean_adverse_bp": adverse_bp}}}
        import quant.reporting.fill_gap as fg
        monkeypatch.setattr(fg, "fill_gap_report", lambda *_a, **_k: rep)
        return rep

    return _set


# ── 근거가 남는가 ───────────────────────────────────────────────────

def test_basis_says_assumed_while_samples_are_thin(gap):
    gap(n=D.MEASURED_COST_MIN_SAMPLES - 1)
    b = D.rebalance_band_basis("kr_stock")
    assert b["source"] == "가정"
    assert b["n"] == D.MEASURED_COST_MIN_SAMPLES - 1
    assert b["min_samples"] == D.MEASURED_COST_MIN_SAMPLES


def test_basis_says_measured_once_the_threshold_is_reached(gap):
    gap(n=D.MEASURED_COST_MIN_SAMPLES)
    b = D.rebalance_band_basis("kr_stock")
    assert b["source"] == "실측"
    assert b["n"] == D.MEASURED_COST_MIN_SAMPLES


def test_the_switch_is_a_real_jump_and_is_visible(gap):
    """전환 전후가 실제로 크게 다르고, 그 차이가 근거에 드러나야 한다."""
    gap(n=D.MEASURED_COST_MIN_SAMPLES - 1)
    before = D.rebalance_band_basis("kr_stock")
    gap(n=D.MEASURED_COST_MIN_SAMPLES)
    after = D.rebalance_band_basis("kr_stock")

    assert after["band"] > before["band"], "실측이 훨씬 비싼데 밴드가 안 넓어졌다"
    assert after["band"] / before["band"] > 2.0, (before, after)
    # 근거만 보고도 '왜 오늘부터 달라졌는지' 알 수 있어야 한다
    assert before["source"] != after["source"]
    assert after["roundtrip_bp"] > before["roundtrip_bp"]


def test_band_stays_within_its_clips(gap):
    for n, adverse in ((0, 0.0), (50, 0.0), (50, 5000.0)):
        gap(n=n, adverse_bp=adverse)
        b = D.rebalance_band_basis("kr_stock")
        assert D.REBALANCE_BAND_REL_MIN <= b["band"] <= D.REBALANCE_BAND_REL_MAX


def test_clip_is_named_so_a_pinned_band_is_not_mistaken_for_a_measurement(gap):
    """상·하한에 걸린 밴드는 '비용이 그렇다'가 아니라 '클립이 그렇다'이다."""
    gap(n=0)
    assert D.rebalance_band_basis("kr_stock")["clipped"] == "하한"
    gap(n=D.MEASURED_COST_MIN_SAMPLES, adverse_bp=5000.0)
    assert D.rebalance_band_basis("kr_stock")["clipped"] == "상한"


def test_favorable_measurement_does_not_narrow_the_band_below_assumption(gap):
    """실측이 유리했다고 밴드를 좁히지 않는다 — 소표본 낙관은 금물."""
    gap(n=D.MEASURED_COST_MIN_SAMPLES, adverse_bp=-30.0)
    b = D.rebalance_band_basis("kr_stock")
    assert b["roundtrip_bp"] == pytest.approx(2 * 14.0, abs=0.5), b


def test_basis_survives_a_broken_report(monkeypatch):
    """실측 리포트가 깨져도 매매를 막지 않는다(근거만 '가정'으로 물러난다)."""
    import quant.reporting.fill_gap as fg

    def boom(*_a, **_k):
        raise RuntimeError("장부 손상")

    monkeypatch.setattr(fg, "fill_gap_report", boom)
    b = D.rebalance_band_basis("kr_stock")
    assert b["source"] == "가정" and b["n"] == 0
    assert D.REBALANCE_BAND_REL_MIN <= b["band"] <= D.REBALANCE_BAND_REL_MAX


def test_the_real_daily_record_carries_the_band(monkeypatch, tmp_path):
    """말이 아니라 **진짜 하루를 돌려** 장부에 근거가 남는지 본다.

    통합 계좌(8만원)를 실제로 하루 굴리고 그날 기록을 읽는다 — 함수 단위로만
    확인하면 기록 지점을 빼먹어도 초록이다.
    """
    from tests.test_guards_actually_bind import _Provider, _bars, _run

    rec = _run(monkeypatch, tmp_path, _Provider(default=_bars(seed=7)))["record"]
    bands = rec.get("rebalance_band")
    assert bands, "오늘 쓴 재조정 밴드가 장부에 없다"
    for market, b in bands.items():
        assert set(b) >= {"band", "source", "roundtrip_bp", "n", "min_samples"}, b
        assert b["source"] in ("가정", "실측")
        assert D.REBALANCE_BAND_REL_MIN <= b["band"] <= D.REBALANCE_BAND_REL_MAX
        assert b["band"] == D._rebalance_band_rel(market, str(tmp_path)), \
            "장부에 적힌 밴드와 실제로 쓰인 밴드가 다르다"


def test_the_number_actually_used_equals_the_number_recorded(gap):
    """기록된 밴드와 주문에 쓰이는 밴드가 같은 값이어야 한다.

    같은 규칙을 두 곳에 적으면 반드시 어긋난다 — 오늘 세 번 당한 패턴이다.
    """
    for n in (0, D.MEASURED_COST_MIN_SAMPLES):
        gap(n=n)
        assert D._rebalance_band_rel("kr_stock") == \
            D.rebalance_band_basis("kr_stock")["band"]
