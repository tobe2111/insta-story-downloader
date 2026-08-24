"""프로그램(조종석)의 실시간 자산 — "프로그램에서도 가능해야 해" (2026-08-23).

사이트 트랙 페이지에 실시간 평가를 단 날, 사장님이 배포 프로그램(조종석)
에도 같은 것을 요구했다. 조종석 감시 탭은 상태 파일의 확정 자산만 보여주고
있었다 — 이제 현금 + Σ수량×지금가를 같은 계산 파일(assets/track-live.js)로
낸다. 규칙을 두 곳에 두면 같은 날 사이트와 프로그램이 다른 값을 말하게
된다(FROZEN_IDEAS ①) — 파일은 한 개다.

지켜야 할 약속:
- 봇 스냅샷이 **현금**을 남긴다(없으면 실시간 자산이 원리적으로 불가).
  못 재면 None — 0으로 적으면 '모름'이 '빈 지갑'이 된다.
- 현금을 모르는 옛 상태 파일에서는 합계를 지어내지 않고 사유를 말한다.
- 확정 KPI(수익률·낙폭·판정)는 건드리지 않는다 — 실시간 줄만 산다.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_the_snapshot_records_cash_or_confesses():
    """스냅샷에 cash가 있고, 못 재면 None이다(0이 아니라)."""
    src = (ROOT / "quant" / "live" / "multi.py").read_text("utf-8")
    assert '"cash": cash,' in src, "스냅샷이 현금을 남기지 않는다"
    assert "cash = None" in src, "현금을 못 잴 때 None이 아니다"

    # 값으로도 확인 — 가짜 브로커로 snapshot()을 실제로 돌린다.
    from quant.live.multi import MultiTrader

    class _Pos:
        def __init__(self):
            self.symbol, self.quantity, self.avg_price = "BTC/USDT", 0.5, 100.0

    class _Broker:
        order_log = []

        def get_cash(self):
            return 77.5

        def get_position(self, s):
            return _Pos()

    t = MultiTrader.__new__(MultiTrader)          # 네트워크 없이 최소 구성
    t.symbols = ["BTC/USDT"]
    t.broker = _Broker()
    t.strategy = None
    t.mode = "paper"
    t.history, t.history_summary = [], None
    t._avg_corr = None
    t._last_error = None
    t._last_summary_date = None
    t.kill_switch = None
    t._kill_unflattened, t._failed_orders, t._skipped_data = [], [], {}
    snap = t.snapshot()
    assert snap["cash"] == 77.5
    assert snap["positions"][0]["symbol"] == "BTC/USDT"

    class _NoCash(_Broker):
        def get_cash(self):
            raise AttributeError("없음")

    t.broker = _NoCash()
    assert t.snapshot()["cash"] is None, "현금을 못 재는데 0으로 적었다"


def test_the_monitor_wires_the_same_live_module():
    src = (ROOT / "quant" / "web" / "app.py").read_text("utf-8")
    assert '_inline_asset("track-live.js")' in src, (
        "조종석이 사이트와 같은 계산 파일을 싣지 않는다 — 규칙이 두 곳이 된다")
    assert 'id="tl-line"' in src, "실시간 줄이 들어갈 자리가 없다"
    assert "TrackLive.equityFromCash" in src, "현금 기반 계산을 부르지 않는다"
    assert "수익률·판정은 확정 기록만 씁니다" in src, (
        "실시간 값이 참고라는 말이 없다 — 확정 기록과 섞여 읽힌다")
    # 현금 모름 → 합계 대신 사유
    assert "실시간 합계는 표시하지 " in src and "재시작하면" in src


def test_the_cash_guard_is_a_contract_in_the_module():
    """Number(null)===0 — 이 가드가 사라지면 '모름'이 '0원'이 된다."""
    src = (ROOT / "docs" / "assets" / "track-live.js").read_text("utf-8")
    assert "cash == null || !isFinite(Number(cash))" in src
    assert '"현금 미기록"' in src.replace("'", '"')
