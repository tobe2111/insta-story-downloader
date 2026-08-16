"""실제로 돈이 나가는 경로에 **페이퍼와 같은 브레이크**가 걸려 있는가 (감사 263).

페이퍼 계좌(`run_daily_portfolio`)에는 자동 브레이크가 둘 있다.

    킬스위치      낙폭이 커지면 노출을 단계적으로 줄인다
    검증 게이트    과최적화 지표(PBO·DSR)를 그 종목 비중에 곱한다

**실거래 경로(`run_daily_live`)에는 둘 다 없었다.** 있던 것은 어드민이
손으로 돌리는 노출 배수와 일시정지뿐이었다. 문서와 사이트는
"킬스위치가 하루 손실 -3%에서 매매를 멈춘다"고 말하고 있었고, 그 말은
페이퍼에서만 사실이었다.

낼 재료조차 없었다는 점이 더 나쁘다 — 실거래 장부는 주문 한 줄마다
'현금 + 그 종목' 값만 남겼고 **계좌 전체 자산은 어디에도 없었다.**
낙폭을 재려면 계좌 자산이 있어야 하는데, 그 숫자가 기록된 적이 없다.

이 파일은 같은 병을 이미 한 번 앓았다. 2026-08-11에 재조정 밴드를
페이퍼만 고치고 실거래 경로는 옛 코드로 남겨 뒀고, 그때 이렇게 적었다 —
*"실제 수수료를 내는 쪽이 더 오래 방치돼 있던 셈이다."*

⚠️ 정직한 한계: 실거래는 아직 한 번도 켜진 적이 없다(키 미발급 · 이중
   잠금). 그래서 이 결함으로 잃은 돈은 없다. 하지만 로드맵상 남은 유일한
   개발 외 절차가 '키 발급'이므로, 키가 생기는 날 브레이크 없이 돌 뻔했다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live import daily_live as DL  # noqa: E402


# ── 가짜 브로커 — 주문이 얼마나 나갔는지만 본다 ─────────────────

class _Broker:
    """실제 경로가 부르는 그 자리(`market_order`)에서 받는다.

    ⚠️ `target_weight`를 가로채면 안 된다 — 실거래 경로는 브로커를
    RobustBroker로 감싸므로, 비중을 수량으로 바꾸는 계산이 통째로
    건너뛰어진다. 그러면 "비중이 줄었다"만 보고 **주문이 실제로 줄었는지**는
    못 본다.
    """

    def __init__(self, cash=1_000_000.0, held=0.0):
        self.cash = cash
        self.held = held
        self.orders: list = []

    def get_cash(self):
        return self.cash

    def get_position(self, symbol):
        return type("P", (), {"quantity": self.held, "avg_price": 0.0})()

    def market_order(self, symbol, side, quantity, price):
        from quant.broker.base import Order
        self.orders.append({"symbol": symbol, "side": side,
                            "quantity": float(quantity),
                            "notional": float(quantity) * float(price)})
        return Order(symbol, side, float(quantity), float(price),
                     status="filled", filled_quantity=float(quantity))


def _frame(n=400, drift=0.0004):
    """⚠️ 변동성이 **0이 아니어야** 한다.

    처음엔 매끈한 지수 곡선을 썼는데, 변동성 타깃 사이징이 0을 돌려줘
    비중이 0이 됐다 — 브레이크를 시험하려는데 애초에 주문이 없었다.
    실제 시세를 닮은 잡음을 넣는다(시드 고정 — 재현 가능).
    """
    rng = np.random.default_rng(7)
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(drift, 0.012, n))),
                      index=idx)
    return pd.DataFrame({"open": close, "high": close * 1.01,
                         "low": close * 0.99, "close": close,
                         "volume": 1e6}, index=idx)


class _Strat:
    name = "fixed"
    allow_short = False

    def generate_signals(self, df):
        return pd.Series(1.0, index=df.index)


def _run(monkeypatch, tmp_path, *, history=None, cash=1_000_000.0, held=0.0):
    """실거래 사이클을 값으로 돌리고 (요약, 브로커)를 돌려준다."""
    if history is not None:
        live = tmp_path / "live"
        live.mkdir(parents=True, exist_ok=True)
        (live / "kr.json").write_text(
            json.dumps({"history": history}), encoding="utf-8")

    df = _frame()
    monkeypatch.setattr("quant.data.get_provider",
                        lambda m: type("P", (), {
                            "get_ohlcv": lambda self, *a, **k: df.copy()})())
    monkeypatch.setattr(DL, "champion_strategy", lambda *a, **k: _Strat())
    monkeypatch.setattr("quant.data.krx.attach_krx_flows",
                        lambda d, s: d)
    monkeypatch.setattr("quant.data.crossasset.attach_cross_asset",
                        lambda d, m, s: d)
    broker = _Broker(cash=cash, held=held)
    summary = DL.run_daily_live([("kr_stock", "005930.KS")], paper=True,
                                state_dir=str(tmp_path), broker=broker)
    return summary, broker


# ── ① 계좌 자산을 재는가 (낙폭의 전제) ──────────────────────────

def test_the_live_ledger_records_account_equity(monkeypatch, tmp_path):
    """이게 없으면 낙폭을 **잴 수조차 없다** — 킬스위치의 재료다."""
    summary, _ = _run(monkeypatch, tmp_path, cash=1_000_000.0, held=0.0)
    assert summary.get("equity"), (
        "실거래 장부에 계좌 자산이 없다 — 낙폭을 잴 재료가 없으니 "
        "킬스위치는 배선해도 판단할 것이 없다")
    assert summary["equity"] == pytest.approx(1_000_000.0, rel=1e-6)


def test_equity_counts_holdings_not_just_cash(monkeypatch, tmp_path):
    """현금만 세면 보유 종목이 오른 날 낙폭이 가짜로 커진다."""
    s_cash, _ = _run(monkeypatch, tmp_path / "a", cash=500_000.0, held=0.0)
    s_held, _ = _run(monkeypatch, tmp_path / "b", cash=500_000.0, held=100.0)
    assert s_held["equity"] > s_cash["equity"], (
        "보유 수량이 자산에 안 잡힌다 — 현금만 세고 있다")


# ── ② 킬스위치가 실제로 노출을 줄이는가 ────────────────────────

def _falling(peak: float, now: float) -> list[dict]:
    """고점 peak에서 now까지 떨어진 계좌 기록."""
    return [{"date": "2026-08-01", "equity": peak},
            {"date": "2026-08-02", "equity": now}]


def test_a_deep_drawdown_shrinks_the_live_order(monkeypatch, tmp_path):
    """낙폭이 크면 실거래 주문 금액이 **실제로** 줄어야 한다.

    ⚠️ 두 경우의 **현금을 같게** 둔다. 처음엔 낙폭 쪽 현금을 줄여서 비교
    했는데, 그러면 킬스위치를 통째로 떼어내도 검사가 통과한다 — 돈이 적어
    주문이 작아진 것을 브레이크가 걸린 것으로 착각하기 때문이다.
    바꾸는 것은 **낙폭 하나**여야 한다.
    """
    cash = 1_000_000.0
    flat, b_flat = _run(monkeypatch, tmp_path / "flat", cash=cash,
                        history=_falling(cash, cash))          # 고점 = 현재
    deep, b_deep = _run(monkeypatch, tmp_path / "deep", cash=cash,
                        history=_falling(cash / 0.7, cash))    # 고점 대비 -30%

    assert flat["risk_scale"] == 1.0, f"낙폭이 없는데 줄었다: {flat['risk_scale']}"
    assert deep["risk_scale"] < 1.0, (
        f"고점 대비 30% 깨졌는데 노출이 그대로다(risk_scale="
        f"{deep['risk_scale']}) — 킬스위치가 실거래에 안 걸린다")
    assert b_flat.orders, "정상인 날에 주문이 아예 안 나갔다 — 검사가 낡았다"
    deep_notional = sum(o["notional"] for o in b_deep.orders)
    flat_notional = sum(o["notional"] for o in b_flat.orders)
    assert deep_notional < flat_notional, (
        f"risk_scale은 기록되는데 **실제 주문 금액**은 그대로다 "
        f"(낙폭 {deep_notional:,.0f}원 vs 정상 {flat_notional:,.0f}원) — "
        "숫자만 남고 실제로는 안 막는, 이 저장소가 가장 싫어하는 상태다")


def test_the_drawdown_is_recorded_so_a_human_can_check(monkeypatch, tmp_path):
    deep, _ = _run(monkeypatch, tmp_path, history=_falling(1e6, 7e5), cash=7e5)
    assert deep["drawdown_pct"] < -20, (
        f"30% 낙폭이 장부에 안 남거나 값이 이상하다: {deep['drawdown_pct']}")


def test_the_live_path_does_not_restate_the_killswitch_thresholds():
    """문턱을 여기 다시 적으면 언젠가 페이퍼와 갈라진다(FROZEN_IDEAS ①)."""
    src = (ROOT / "quant" / "live" / "daily_live.py").read_text("utf-8")
    # 주석은 뺀다 — 옛 사고를 설명하는 문장에 숫자가 들어 있는 것은
    # 결함이 아니라 기록이다. 지켜야 할 것은 **실행되는 코드**에 문턱이
    # 다시 나타나지 않는 것이다.
    import re
    code = "\n".join(ln.split("#", 1)[0] for ln in src.splitlines())
    code = code.split('"""', 2)[-1]
    for lit in ("0.03", "0.15", "0.25", "0.75"):
        assert not re.search(rf"(?<![\w.]){re.escape(lit)}(?![\w])", code), (
            f"실거래 경로가 킬스위치 문턱({lit})을 자기가 적고 있다 — "
            "페이퍼와 갈라질 자리다")
    assert "_kill_switch_scale" in src, "페이퍼와 같은 판정 함수를 안 쓴다"


# ── ③ 검증 게이트가 실거래 비중에 곱해지는가 ────────────────────

def test_an_unmeasured_symbol_is_halved_not_trusted(monkeypatch, tmp_path):
    """'안 재봤다'와 '괜찮다'를 같게 두면 검증이 고장난 날 가장 공격적이 된다."""
    # 검증 기록이 없는 상태이므로 게이트가 절반을 물려야 한다.
    damp = DL._validation_damping([("kr_stock", "005930.KS")], str(tmp_path))
    assert damp["kr_stock:005930.KS"] == 0.5, (
        f"측정된 적 없는 종목이 감쇠 없이 통과한다: {damp}")


def test_the_gate_actually_shrinks_the_order_not_just_the_log(monkeypatch,
                                                             tmp_path):
    """⚠️ 변이 시험이 이 구멍을 잡았다.

    앞 검사는 게이트가 **0.5를 돌려주는지**만 봤다. 그래서 그 0.5를 비중에
    곱하는 줄을 통째로 지워도 통과했다 — 경고는 찍히는데 주문은 그대로인,
    이 저장소가 가장 싫어하는 상태를 못 잡는 검사였다.
    """
    import quant.live.validation_gate as VG

    def _grades(keys, **kw):
        return {k: {"grade": "통과", "scale": 1.0, "why": ""} for k in keys}

    monkeypatch.setattr(VG, "validation_grades", _grades)
    _, b_full = _run(monkeypatch, tmp_path / "full")

    def _halved(keys, **kw):
        return {k: {"grade": "경고", "scale": 0.5, "why": "시험"} for k in keys}

    monkeypatch.setattr(VG, "validation_grades", _halved)
    _, b_half = _run(monkeypatch, tmp_path / "half")

    full = sum(o["notional"] for o in b_full.orders)
    half = sum(o["notional"] for o in b_half.orders)
    assert full > 0, "정상 등급인데 주문이 안 나갔다 — 검사가 낡았다"
    assert half < full * 0.75, (
        f"게이트가 ×0.5인데 주문 금액이 그대로다(감쇠 {half:,.0f} vs "
        f"통과 {full:,.0f}) — 판정만 하고 곱하지 않는다")


def test_a_broken_gate_is_conservative_not_permissive(monkeypatch, tmp_path):
    """게이트를 못 부르면 **절반**이어야 한다 — 못 재면 조심하는 쪽으로."""
    import quant.live.validation_gate as VG
    monkeypatch.setattr(VG, "validation_grades",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    damp = DL._validation_damping([("kr_stock", "005930.KS")], str(tmp_path))
    assert damp["kr_stock:005930.KS"] == 0.5, (
        "검증 게이트가 고장났는데 비중을 그대로 준다")


# ── ④ 모르는 상태에서 과하게 굴지 않는가 ────────────────────────

def test_a_fresh_account_is_neither_locked_nor_loosened(monkeypatch, tmp_path):
    """기록이 없으면 낙폭을 모른다 — 그때 0으로 잠그면 첫날이 영원히 온다."""
    scale, dd = DL._kill_switch_for_live(str(tmp_path), 1_000_000.0)
    assert scale == 1.0 and dd == 0.0, (scale, dd)


def test_a_failed_price_lookup_does_not_fake_a_crash(monkeypatch, tmp_path):
    """포지션 조회가 실패한 종목을 0으로 치면 없던 폭락이 생긴다."""
    class _Bad(_Broker):
        def get_position(self, symbol):
            raise RuntimeError("조회 실패")

    eq = DL._account_equity(_Bad(cash=1_000_000.0), {"005930.KS": 70_000.0})
    assert eq == pytest.approx(1_000_000.0), (
        f"조회 실패 종목을 0으로 세어 자산이 왜곡됐다: {eq}")
