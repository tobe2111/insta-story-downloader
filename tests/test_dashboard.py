"""라이브 모니터링 대시보드 테스트 (순수 stdlib — pandas 불필요)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# pandas를 import하는 패키지 __init__을 우회하기 위해 모듈을 직접 로드
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "dashboard_mod",
    str(Path(__file__).resolve().parent.parent / "quant" / "reporting" / "dashboard.py"),
)
dashboard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dashboard)


def _sample_state():
    hist = [{"time": f"2026-01-{i+1:02d}", "price": 100 + i,
             "weight": 0.5, "equity": 10_000 + i * 30} for i in range(20)]
    return {
        "symbol": "BTC/USDT", "strategy": "ensemble", "mode": "paper",
        "history": hist,
        "position": {"symbol": "BTC/USDT", "quantity": 0.1, "avg_price": 105.0},
        "orders": [{"side": "buy", "symbol": "BTC/USDT", "quantity": 0.1,
                    "price": 105.0, "status": "filled"}],
    }


def test_dashboard_written(tmp_path):
    out = dashboard.generate_dashboard(_sample_state(), tmp_path / "d.html")
    assert out.exists()
    html = out.read_text(encoding="utf-8")
    assert "<svg" in html
    assert "BTC/USDT" in html
    assert "총자산" in html
    assert "손익" in html


def test_dashboard_empty_history(tmp_path):
    """기록이 없어도 크래시 없이 렌더링된다."""
    state = {"symbol": "AAPL", "strategy": "momentum", "history": [],
             "position": {}, "orders": []}
    out = dashboard.generate_dashboard(state, tmp_path / "empty.html")
    assert out.exists()
    assert "데이터 수집 중" in out.read_text(encoding="utf-8")


def test_dashboard_shows_accuracy(tmp_path):
    """자동학습 상태(정확도 포함)면 방향 정확도 KPI가 퍼센트로 표시된다."""
    hist = [{"time": "t", "price": 100, "weight": 1.0, "equity": 10_000,
             "hit_rate": 0.53, "recent_hit_rate": 0.55, "n": 40}]
    state = {"symbol": "X", "strategy": "ml", "mode": "paper-autolearn",
             "history": hist, "position": {}, "orders": []}
    out = dashboard.generate_dashboard(state, tmp_path / "acc.html")
    html = out.read_text(encoding="utf-8")
    assert "방향 정확도" in html and "55.0%" in html   # recent_hit_rate 우선


def test_dashboard_accuracy_na_when_absent(tmp_path):
    """정확도 정보가 없으면 N/A로 표시(크래시 없음)."""
    hist = [{"time": "t", "price": 100, "weight": 1.0, "equity": 10_000}]
    state = {"symbol": "X", "strategy": "ma_cross", "history": hist,
             "position": {}, "orders": []}
    out = dashboard.generate_dashboard(state, tmp_path / "na.html")
    assert "N/A" in out.read_text(encoding="utf-8")


def test_dashboard_pnl_sign(tmp_path):
    """손실 상태에서도 정상 렌더 (음수 손익)."""
    hist = [{"time": "t", "price": 100, "weight": 1.0, "equity": 10_000},
            {"time": "t2", "price": 90, "weight": 1.0, "equity": 9_000}]
    state = {"symbol": "X", "strategy": "s", "history": hist,
             "position": {}, "orders": []}
    out = dashboard.generate_dashboard(state, tmp_path / "loss.html")
    assert "-10.00%" in out.read_text(encoding="utf-8")
