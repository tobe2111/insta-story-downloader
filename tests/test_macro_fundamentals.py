"""FRED(거시) + FMP(펀더멘탈·팩터랭킹) 테스트 — 네트워크 없이 파서/로직 검증."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.data.fundamentals import _parse_fmp_ratios, rank_factors
from quant.data.macro import _parse_fred


# ── FRED ───────────────────────────────────────────────────────────────
def test_parse_fred_basic_and_skips_missing():
    payload = {"observations": [
        {"date": "2020-01-01", "value": "1.88"},
        {"date": "2020-01-02", "value": "."},      # 결측 → 제외
        {"date": "2020-01-03", "value": "1.90"},
    ]}
    s = _parse_fred(payload)
    assert len(s) == 2
    assert s.iloc[0] == 1.88 and s.iloc[-1] == 1.90
    assert str(s.index[0].date()) == "2020-01-01"


def test_parse_fred_empty():
    assert _parse_fred({}).empty
    assert _parse_fred({"observations": []}).empty


# ── FMP 파싱 ───────────────────────────────────────────────────────────
def test_parse_fmp_ratios_maps_fields():
    payload = [{"peRatioTTM": 30.0, "priceToBookRatioTTM": 5.0,
                "returnOnEquityTTM": 1.2, "debtEquityRatioTTM": 0.4}]
    d = _parse_fmp_ratios(payload)
    assert d["pe"] == 30.0 and d["pb"] == 5.0 and d["roe"] == 1.2
    assert d["debt_equity"] == 0.4


def test_parse_fmp_ratios_empty():
    assert _parse_fmp_ratios([]) == {}
    assert _parse_fmp_ratios({}) == {}


# ── 멀티팩터 랭킹 ──────────────────────────────────────────────────────
def test_rank_factors_value_and_quality():
    """PER 낮고 ROE 높은 종목이 상위 → 비중을 받는다."""
    data = {
        "GOOD": {"pe": 8.0, "roe": 0.30},    # 싸고 고수익 → 최상
        "MID":  {"pe": 15.0, "roe": 0.15},
        "BAD":  {"pe": 40.0, "roe": 0.02},   # 비싸고 저수익 → 최하
    }
    factors = {"pe": -1.0, "roe": +1.0}       # PER 낮을수록/ROE 높을수록 좋음
    w = rank_factors(data, factors, top_n=2)
    assert "GOOD" in w and "BAD" not in w
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert all(v > 0 for v in w.values())


def test_rank_factors_positive_only_default():
    data = {"A": {"roe": 0.3}, "B": {"roe": 0.1}, "C": {"roe": 0.05}}
    w = rank_factors(data, {"roe": +1.0})     # top_n 없음 → 점수 양수만
    assert set(w) <= {"A", "B", "C"}
    assert abs(sum(w.values()) - 1.0) < 1e-9


def test_rank_factors_empty_or_no_usable_factor():
    assert rank_factors({}, {"pe": -1}) == {}
    # 모든 종목이 같은 값이면 표준편차 0 → 무의미 → 빈 dict
    same = {"A": {"pe": 10.0}, "B": {"pe": 10.0}}
    assert rank_factors(same, {"pe": -1.0}) == {}
