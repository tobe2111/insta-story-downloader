"""거래 저널 & 성과 복기 테스트.

주문 감사 로그(JSONL)와 정직한 판정 문구는 순수 stdlib라 로컬 실행 가능.
history→거래통계(build_review)는 pandas(trades 재사용)라 CI.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# journal 모듈을 패키지 __init__(pandas) 없이 파일에서 직접 로드 → stdlib 부분 실행
_spec = importlib.util.spec_from_file_location(
    "jn", str(Path(__file__).resolve().parent.parent / "quant" / "live" / "journal.py"))
jn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(jn)


# ── 감사 로그 (stdlib) ───────────────────────────────────────────────────────

def test_record_and_load_orders(tmp_path):
    p = tmp_path / "orders.jsonl"
    jn.record_order(p, {"symbol": "BTC/USDT", "side": "buy", "quantity": 0.1,
                        "status": "filled"}, {"time": "2026-01-01", "equity": 10000})
    jn.record_order(p, {"symbol": "BTC/USDT", "side": "sell", "quantity": 0.1,
                        "status": "filled"}, {"time": "2026-01-02", "equity": 10200})
    rows = jn.load_orders(p)
    assert len(rows) == 2
    assert rows[0]["symbol"] == "BTC/USDT" and rows[0]["equity"] == 10000
    assert rows[1]["side"] == "sell"


def test_load_missing_returns_empty(tmp_path):
    assert jn.load_orders(tmp_path / "none.jsonl") == []


def test_record_never_raises_on_bad_dir():
    # 존재할 수 없는 경로여도 예외를 삼킨다(운용 루프를 죽이지 않게)
    jn.record_order("/proc/nonexistent/x.jsonl", {"a": 1})   # 예외 없이 통과


# ── 리뷰 판정 문구 (stdlib — build_review 결과 dict를 직접 넣어 검증) ─────────

def test_review_report_flags_small_sample():
    text = jn.review_report({
        "num_trades": 5, "win_rate": 0.6, "avg_win": 0.02, "avg_loss": -0.01,
        "expectancy": 0.004, "profit_factor": 2.0, "avg_bars_held": 3.0,
        "total_return": 0.05})
    assert "노이즈" in text and "5건" in text
    assert "기대손익" in text and "보장하지 않습니다" in text


def test_review_report_flags_negative_expectancy():
    text = jn.review_report({
        "num_trades": 50, "win_rate": 0.7, "avg_win": 0.01, "avg_loss": -0.03,
        "expectancy": -0.002, "profit_factor": 0.8, "avg_bars_held": 4.0,
        "total_return": -0.1})
    # 승률 70%여도 기대손익 음수면 '돈을 잃고 있다'고 경고
    assert "🚨" in text and "돈을 잃고" in text


def test_review_report_no_trades():
    assert "완결된 거래" in jn.review_report({"num_trades": 0})


def test_review_report_infinite_profit_factor():
    text = jn.review_report({
        "num_trades": 40, "win_rate": 1.0, "avg_win": 0.01, "avg_loss": 0.0,
        "expectancy": 0.01, "profit_factor": float("inf"), "avg_bars_held": 2.0,
        "total_return": 0.4})
    assert "∞" in text


# ── history → 거래통계 (pandas — CI) ─────────────────────────────────────────

def test_build_review_from_history():
    """자본·목표비중 시계열에서 라운드트립 거래를 뽑아 통계를 낸다."""
    history = [
        {"equity": 10000, "weight": 0.0},
        {"equity": 10000, "weight": 1.0},   # 진입
        {"equity": 10300, "weight": 1.0},
        {"equity": 10500, "weight": 0.0},   # 청산(+이익)
        {"equity": 10500, "weight": 1.0},   # 재진입
        {"equity": 10200, "weight": 0.0},   # 청산(-손실)
    ]
    r = jn.build_review(history)
    assert r["num_trades"] >= 1
    assert "expectancy" in r and "total_return" in r


def test_build_review_short_history_no_crash():
    assert jn.build_review([{"equity": 100}])["num_trades"] == 0


def test_review_state_file(tmp_path):
    import json
    p = tmp_path / "state.json"
    p.write_text(json.dumps({"history": [
        {"equity": 10000, "weight": 0.0}, {"equity": 10000, "weight": 1.0},
        {"equity": 10400, "weight": 0.0}]}), encoding="utf-8")
    r = jn.review_state_file(p)
    assert "num_trades" in r


def test_journal_cli_parses():
    import quant.cli as cli
    ns = cli.build_parser().parse_args(["journal", "--state", "results/x.json"])
    assert ns.command == "journal" and callable(ns.func)
