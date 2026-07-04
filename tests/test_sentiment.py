"""공포탐욕지수(외부 거시 피처) 파서 테스트 — 네트워크 없이 검증."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.data.sentiment import _parse_fng


def test_parse_fng_basic():
    payload = {"data": [
        {"timestamp": "1609459200", "value": "30"},   # 2021-01-01
        {"timestamp": "1609545600", "value": "70"},   # 2021-01-02
    ]}
    s = _parse_fng(payload)
    assert len(s) == 2
    assert s.min() == 30.0 and s.max() == 70.0
    assert str(s.index[0].date()) == "2021-01-01"


def test_parse_fng_empty():
    assert _parse_fng({}).empty
    assert _parse_fng({"data": []}).empty


def test_parse_fng_skips_bad_rows():
    payload = {"data": [
        {"timestamp": "oops", "value": "y"},          # 깨진 행 → 스킵
        {"timestamp": "1609459200", "value": "50"},
    ]}
    s = _parse_fng(payload)
    assert len(s) == 1 and s.iloc[0] == 50.0
