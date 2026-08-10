"""알파 14차 ③ — 체결 가정 검증(실측 개장 갭 vs 백테스트 슬리피지 가정).

핵심 계약:
  ① 갭 = 체결가(다음 시가)/결정 종가 − 1, 불리 방향(+)은 매매 방향 기준
  ② 비중 변화가 없는 기록(밴드로 주문 안 나감)은 표본에서 제외
  ③ 시장별 집계에 백테스트 가정(bp)을 병기하고, 실측 불리 평균이 가정을
     넘으면 optimistic=True(백테스트 낙관 의심)를 스스로 단다
  ④ status.json(fill_check)과 사이트 카드에 배선된다
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.reporting.fill_gap import _iter_fill_gaps, fill_gap_report  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

HIST = [
    {"date": "2026-08-01", "price": 100.0, "weight": 0.5},   # 매수 결정 0→0.5
    {"date": "2026-08-04", "price": 102.0, "weight": 0.2,    # 매도 결정 0.5→0.2
     "fill": {"price": 101.0, "decided_bar": "2026-08-01", "weight": 0.5}},
    {"date": "2026-08-05", "price": 99.0, "weight": 0.2,
     "fill": {"price": 100.0, "decided_bar": "2026-08-04", "weight": 0.2}},
]


def test_gap_signs_follow_trade_direction():
    gaps = _iter_fill_gaps(HIST)
    assert len(gaps) == 2
    # 매수(0→0.5): 결정가 100 → 체결 101 = 비싸게 삼 → 불리 +100bp
    assert gaps[0][2] == pytest.approx(100.0, abs=0.1)
    # 매도(0.5→0.2): 결정가 102 → 체결 100 = 싸게 팜 → 불리 +196bp
    assert gaps[1][2] == pytest.approx(196.1, abs=0.2)


def test_no_trade_records_are_skipped():
    hist = [
        {"date": "2026-08-01", "price": 100.0, "weight": 0.3},
        {"date": "2026-08-04", "price": 101.0, "weight": 0.3,   # 비중 변화 없음
         "fill": {"price": 102.0, "decided_bar": "2026-08-01", "weight": 0.3}},
    ]
    # 첫 기록(j=0)은 prev=0→0.3 매수로 취급되므로, 변화 없음 검사는 둘째 결정으로
    hist2 = [{"date": "2026-07-31", "price": 100.0, "weight": 0.3}] + hist
    assert _iter_fill_gaps(hist2) == []


def test_report_aggregates_and_flags_optimism(tmp_path):
    paper = tmp_path / "paper"
    paper.mkdir()
    (paper / "kr.json").write_text(json.dumps(
        {"market": "kr_stock", "symbol": "005930", "history": HIST}), "utf-8")
    (paper / "pf.json").write_text(json.dumps(
        {"market": "portfolio", "symbol": "ALL", "history": HIST}), "utf-8")
    rep = fill_gap_report(str(tmp_path))
    assert rep["total_fills"] == 2
    assert list(rep["markets"]) == ["kr_stock"]      # 통합 계좌는 중복이라 제외
    m = rep["markets"]["kr_stock"]
    assert m["n"] == 2
    assert m["mean_adverse_bp"] == pytest.approx(148.0, abs=0.2)
    assert m["assumed_bp"] == pytest.approx(14.0, abs=0.1)   # 수수료+슬리피지
    assert m["optimistic"] is True                   # 실측 불리 > 가정 → 자기 고발


def test_report_none_without_samples(tmp_path):
    assert fill_gap_report(str(tmp_path)) is None


def test_wired_into_status_and_site():
    dl = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert "fill_gap_report" in dl and '"fill_check"' in dl
    p = (ROOT / "docs" / "paper.html").read_text("utf-8")
    assert "체결 가정 검증" in p and "st.fill_check" in p
    assert "백테스트 낙관" in p                      # 자기 고발 문구
