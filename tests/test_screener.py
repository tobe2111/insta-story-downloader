"""종목 선별기(스크리너) 테스트 — 재무데이터 주입으로 네트워크 없이 검증."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.portfolio import screen_symbols

# 가짜 재무데이터 (FMP 대체)
_FAKE = {
    "AAA": {"pe": 8.0, "pb": 1.0, "roe": 0.30},   # 싸고 우량 → 최상
    "BBB": {"pe": 15.0, "pb": 2.0, "roe": 0.15},
    "CCC": {"pe": 40.0, "pb": 6.0, "roe": 0.02},   # 비싸고 저수익 → 최하
}


def _fake_ratios(sym: str) -> dict:
    return _FAKE.get(sym, {})


def test_screener_selects_top():
    res = screen_symbols(["AAA", "BBB", "CCC"], top_n=2, ratios_fn=_fake_ratios)
    assert "AAA" in res["selected"] and "CCC" not in res["selected"]
    assert abs(sum(res["weights"].values()) - 1.0) < 1e-9
    assert set(res["ratios"]) == {"AAA", "BBB", "CCC"}


def test_screener_skips_unknown_symbols():
    """재무데이터 없는 종목은 자동 제외된다."""
    res = screen_symbols(["AAA", "ZZZ"], ratios_fn=_fake_ratios)
    assert "ZZZ" not in res["ratios"]


def test_screener_empty_when_no_data():
    res = screen_symbols(["ZZZ"], ratios_fn=lambda s: {})
    assert res["weights"] == {} and res["selected"] == []


def test_screener_quality_only_factor():
    res = screen_symbols(["AAA", "BBB", "CCC"], factors={"roe": 1.0},
                         top_n=1, ratios_fn=_fake_ratios)
    assert res["selected"] == ["AAA"]   # ROE 최고
