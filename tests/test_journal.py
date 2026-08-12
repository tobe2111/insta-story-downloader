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


# ── 복기 도구가 실제 장부를 본다 (감사 67) ────────────────────


def test_journal_defaults_to_the_real_account_ledger(tmp_path, monkeypatch):
    """`quant journal`의 기본 대상이 실제로 돈을 굴리는 장부인가.

    기본값이 results/state.json이었다. 그 파일은 개발용 `learn` 봇이 쓰는
    것이고, 8마일 통합 계좌는 state/paper/portfolio_ALL.json에 쌓인다.
    즉 사장님이 `quant journal`을 치면 매일 매매가 도는데도 "아직 완결된
    거래가 없습니다"만 나왔다 — 복기 도구가 빈 파일을 보고 있었다.
    """
    import json as _json

    from quant.cli import _default_journal_state

    monkeypatch.chdir(tmp_path)
    # 통합 계좌 장부가 없으면 예전 경로로 폴백(하위 호환)
    assert _default_journal_state().endswith("state.json")

    pf = tmp_path / "state" / "paper"
    pf.mkdir(parents=True)
    (pf / "portfolio_ALL.json").write_text(_json.dumps({"history": []}), "utf-8")
    got = _default_journal_state()
    assert got.endswith("portfolio_ALL.json"), (
        "통합 계좌 장부가 있는데도 개발용 파일을 기본으로 삼는다")


def test_journal_can_actually_read_the_portfolio_ledger():
    """통합 계좌의 기록 형식(history: equity·weight)으로 복기가 되는가."""
    from quant.live.journal import build_review

    hist = [{"equity": 80000.0, "weight": 0.0},
            {"equity": 80500.0, "weight": 0.4},
            {"equity": 81000.0, "weight": 0.4},
            {"equity": 80900.0, "weight": 0.0}]
    rev = build_review(hist)   # periods_per_year는 죽은 인자라 제거됐다(감사 174)
    assert rev["num_trades"] >= 1, "통합 계좌 형식에서 라운드트립을 못 뽑는다"
    assert rev["n_points"] == len(hist)
