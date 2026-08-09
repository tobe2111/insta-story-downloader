"""실거래 전환 준비 계약 검사 — live-daily 집행·2중 잠금·진단·워크플로.

핵심 계약:
  ① 실전(paper=False)은 QUANT_LIVE_REAL=1 없이는 예외 — 2중 잠금
  ② 어드민 trading_paused → 주문 0(스킵 사유 반환)
  ③ 결정→주문: 켈리 상한·노출 배수·롱온리 클립·1/n 슬라이스가 적용된다
  ④ 진단(check_readiness): 키 없으면 주문·네트워크 없이 누락 항목 보고
  ⑤ 워크플로: 수동 실행 전용(schedule 주석), real은 vars 2중 잠금, CLI 등록
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.broker.base import Broker, Order, Position  # noqa: E402
from quant.live.daily_live import check_readiness, run_daily_live  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


class FakeBroker(Broker):
    def __init__(self, cash: float = 1_000_000.0):
        self.cash = cash
        self.orders: list[Order] = []

    def get_cash(self) -> float:
        return self.cash

    def get_position(self, symbol: str) -> Position:
        return Position(symbol, 0.0, 0.0)

    def market_order(self, symbol, side, quantity, price) -> Order:
        o = Order(symbol, side, quantity, price, status="accepted")
        self.orders.append(o)
        return o


def _seed_champion(tmp_path, symbol="005930.KS"):
    from quant.live.retrain import save_champions
    save_champions({f"kr_stock:{symbol}": {
        "strategy": "ma_cross", "params": {"fast": 5, "slow": 20},
        "promotions": 0}}, str(tmp_path))


def _fake_provider(monkeypatch):
    """kr_stock 프로바이더를 상승 추세 합성 데이터로 대체(실데이터 플래그)."""
    import quant.live.daily_live as dl

    class P:
        def get_ohlcv(self, symbol, tf, limit=400):
            idx = pd.date_range("2025-01-01", periods=300, freq="D")
            v = 100.0 * np.cumprod(1 + np.full(300, 0.003))
            return pd.DataFrame({"open": v, "high": v * 1.01, "low": v * 0.99,
                                 "close": v, "volume": 1000.0}, index=idx)

    import quant.data as qd
    monkeypatch.setattr(qd, "get_provider", lambda m: P())
    return dl


# ── ① 2중 잠금 ─────────────────────────────────────────────────


def test_real_mode_requires_env_gate(monkeypatch, tmp_path):
    monkeypatch.delenv("QUANT_LIVE_REAL", raising=False)
    with pytest.raises(RuntimeError, match="QUANT_LIVE_REAL"):
        run_daily_live(targets=[("kr_stock", "005930.KS")], paper=False,
                       state_dir=str(tmp_path), broker=FakeBroker())


# ── ② 어드민 일시정지 ──────────────────────────────────────────


def test_admin_pause_blocks_orders(monkeypatch, tmp_path):
    import quant.utils.settings as st
    monkeypatch.setattr(st, "load_settings", lambda *a, **k: {
        "trading_paused": True, "exposure_scale": 1.0, "social_post": True})
    out = run_daily_live(targets=[("kr_stock", "005930.KS")],
                         state_dir=str(tmp_path), broker=FakeBroker())
    assert out.get("skipped") == "어드민 일시정지"


# ── ③ 결정→주문 사슬 ───────────────────────────────────────────


def test_decision_places_long_only_sliced_order(monkeypatch, tmp_path):
    _seed_champion(tmp_path)
    _fake_provider(monkeypatch)
    import quant.utils.settings as st
    monkeypatch.setattr(st, "load_settings", lambda *a, **k: {
        "trading_paused": False, "exposure_scale": 0.5, "social_post": True})
    b = FakeBroker(cash=1_000_000.0)
    out = run_daily_live(targets=[("kr_stock", "005930.KS")],
                         state_dir=str(tmp_path), broker=b)
    assert out["mode"] == "모의투자"
    w = out["decisions"]["005930.KS"]
    assert 0.0 <= w <= 0.5                    # 롱온리 + 노출 배수 0.5 상한
    if b.orders:                               # 상승 추세 → 매수 주문
        o = b.orders[0]
        assert o.symbol == "005930" and o.side == "buy"
        # 1/n 슬라이스(단일 종목 n=1) 예산 내 수량
        assert o.quantity * o.price <= 1_000_000.0 * w + 1e-6
    # 집행 기록이 state/live/kr.json에 남는다
    assert (tmp_path / "live" / "kr.json").exists()


# ── ④ 진단 ─────────────────────────────────────────────────────


def test_readiness_reports_missing_keys(monkeypatch):
    for k in ("KIS_APP_KEY", "KIS_APP_SECRET", "KIS_CANO",
              "KIWOOM_APP_KEY", "KIWOOM_SECRET", "KIWOOM_ACCOUNT"):
        monkeypatch.delenv(k, raising=False)
    rows = check_readiness()                   # 기본 = kis
    assert rows[0][1] is False and "누락" in rows[0][2]
    assert all(not ok for _, ok, _ in rows)    # 네트워크 호출 없이 실패 보고
    rows_kw = check_readiness(broker_name="kiwoom")
    assert "키움" in rows_kw[0][0] and "KIWOOM_APP_KEY" in rows_kw[0][2]
    rows_bad = check_readiness(broker_name="toss")
    assert rows_bad[0][1] is False and "미지원" in rows_bad[0][2]


def test_broker_factory_selects_and_rejects(monkeypatch):
    from quant.live.daily_live import make_kr_broker
    # 키가 없으면 어댑터 생성 자체가 명확한 한국어 오류 — 어느 키인지 알려준다
    for k in ("KIS_APP_KEY", "KIS_APP_SECRET", "KIS_CANO",
              "KIWOOM_APP_KEY", "KIWOOM_SECRET", "KIWOOM_ACCOUNT"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(RuntimeError, match="KIS_APP_KEY"):
        make_kr_broker("kis")
    with pytest.raises(RuntimeError, match="KIWOOM"):
        make_kr_broker("kiwoom")
    with pytest.raises(RuntimeError, match="지원하지 않는 증권사"):
        make_kr_broker("toss")
    # 환경변수로도 선택된다
    monkeypatch.setenv("QUANT_KR_BROKER", "kiwoom")
    with pytest.raises(RuntimeError, match="KIWOOM"):
        make_kr_broker(None)


# ── ⑤ 워크플로·CLI 배선 ────────────────────────────────────────


def test_workflow_manual_only_with_double_lock():
    y = (ROOT / ".github" / "workflows" / "kr-live.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch" in y
    assert "# schedule:" in y                  # 자동 실행은 주석(수동 결정 후 해제)
    assert "QUANT_LIVE_REAL" in y and "vars.QUANT_LIVE_REAL" in y
    assert "KIS_APP_KEY" in y


def test_cli_has_live_daily_and_check():
    c = (ROOT / "quant" / "cli.py").read_text(encoding="utf-8")
    assert '"live-daily"' in c and '"live-check"' in c
    r = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "live-daily" in r and "QUANT_LIVE_REAL" in r
