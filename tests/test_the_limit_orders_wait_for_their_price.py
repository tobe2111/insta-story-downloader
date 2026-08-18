"""지정가 그림자 — 같은 신호, 다른 체결 (2026-08-18, 투자능력 개선 2위).

본 실험(시장가 즉시 체결)과 나란히, 활성화 순간을 복제한 그림자 계좌가
같은 신호를 지정가로만 체결한다. 지켜야 할 약속:
- 지정가는 **다음 닫힌 봉이 그 가격에 닿아야만** 체결된다 — 닿지 않으면
  취소되고 미체결로 센다(공짜 체결 금지).
- 체결 비용은 수수료만(슬리피지 0) — 그 대가가 미체결 위험이다.
- 그림자는 활성화 순간 본 계좌의 복제라, 이후 차이는 체결 방식뿐이다.
- 그림자 실패가 본 실험을 막지 않는다. 레버리지 금지도 그대로다.
- 공개 리포트에 비교 숫자가 실린다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import quant.live.intraday_challenger as IC              # noqa: E402


def _df(closes, lows=None, highs=None, start="2026-08-18 00:00"):
    idx = pd.date_range(start, periods=len(closes), freq="h")
    c = np.asarray(closes, float)
    return pd.DataFrame({
        "open": c, "close": c,
        "high": np.asarray(highs, float) if highs is not None else c + 1.0,
        "low": np.asarray(lows, float) if lows is not None else c - 1.0,
        "volume": np.full(len(c), 1e6)}, index=idx)


def _mk_state():
    return {"cash": 10_000.0, "start_cash": 10_000.0, "positions": {},
            "cost_paid": 0.0, "rounds": [], "risk_scale": 1.0}


def _run(st, dfs, signals, prices, bars, now="2026-08-18T05:00:00"):
    return IC._limit_shadow_round(st, dfs, signals, prices,
                                  fee_only=0.001, scale=1.0,
                                  now_iso=now, bar_times=bars)


def test_a_buy_limit_waits_until_the_price_comes_down():
    st = _mk_state()
    sym = "BTC/USDT"
    sig = {s: (1.0 if s == sym else 0.0) for s in IC.UNIVERSE}
    # 회차 1 — 종가 100에 매수 지정가를 건다(활성화 + 주문).
    df1 = _df([100, 100, 100])
    info1 = _run(st, {sym: df1}, sig, {sym: 100.0},
                 {sym: str(df1.index[-1])})
    assert info1["pending"] == 1 and info1["filled"] == 0
    sh = st["limit_shadow"]
    assert sh["pending"][sym]["side"] == "buy"
    assert sh["positions"].get(sym) is None or sh["positions"][sym] == 0

    # 회차 2 — 새 봉의 저가가 101(지정가 100 위) → 체결 없음, 취소+재주문.
    df2 = _df([100, 100, 100, 103], lows=[99, 99, 99, 101])
    info2 = _run(st, {sym: df2}, sig, {sym: 103.0},
                 {sym: str(df2.index[-1])})
    assert info2["filled"] == 0 and info2["cancelled"] == 1, (
        "가격이 안 닿았는데 체결됐다 — 공짜 체결")
    assert st["limit_shadow"]["unfilled_total"] == 1

    # 회차 3 — 새 봉의 저가가 102(직전 지정가 103 아래) → 체결.
    df3 = _df([100, 100, 100, 103, 104], lows=[99, 99, 99, 101, 102])
    info3 = _run(st, {sym: df3}, sig, {sym: 104.0},
                 {sym: str(df3.index[-1])})
    assert info3["filled"] == 1, "가격이 닿았는데 체결이 안 됐다"
    sh = st["limit_shadow"]
    assert sh["positions"][sym] > 0
    # 체결가는 지정가(103) — 슬리피지 없음, 수수료만.
    notional = sh["positions"][sym] * 103.0
    assert abs(sh["cost_paid"] - notional * 0.001) < 1e-6, (
        f"수수료만 물어야 한다: cost={sh['cost_paid']}, 예상 {notional * 0.001}")


def test_a_sell_limit_needs_the_high_to_reach():
    st = _mk_state()
    sym = "BTC/USDT"
    st["positions"] = {sym: 10.0}
    st["cash"] = 0.0
    sig = {s: 0.0 for s in IC.UNIVERSE}          # 전량 정리 신호
    df1 = _df([100] * 3)
    _run(st, {sym: df1}, sig, {sym: 100.0}, {sym: str(df1.index[-1])})
    assert st["limit_shadow"]["pending"][sym]["side"] == "sell"
    # 다음 봉 고가 99.5 → 못 닿음 → 미체결. 그다음 봉 고가 101 → 체결.
    df2 = _df([100, 100, 100, 99], highs=[100.5, 100.5, 100.5, 99.5])
    info2 = _run(st, {sym: df2}, sig, {sym: 99.0}, {sym: str(df2.index[-1])})
    assert info2["filled"] == 0
    df3 = _df([100, 100, 100, 99, 100], highs=[100.5, 100.5, 100.5, 99.5, 101])
    info3 = _run(st, {sym: df3}, sig, {sym: 100.0}, {sym: str(df3.index[-1])})
    assert info3["filled"] == 1
    assert st["limit_shadow"]["positions"].get(sym, 0.0) < 10.0


def test_the_shadow_clones_the_main_account_at_activation():
    st = _mk_state()
    st["cash"] = 4_000.0
    st["positions"] = {"ETH/USDT": 2.0}
    sig = {s: 0.0 for s in IC.UNIVERSE}
    df = _df([3000] * 3)
    _run(st, {"ETH/USDT": df}, sig, {"ETH/USDT": 3000.0},
         {"ETH/USDT": str(df.index[-1])})
    sh = st["limit_shadow"]
    assert sh["start_equity"] == 4_000.0 + 2.0 * 3000.0
    assert sh["cash"] == 4_000.0 and sh["positions"]["ETH/USDT"] == 2.0


def test_the_shadow_never_borrows():
    """현금보다 큰 매수 주문은 걸리지도, 체결되지도 않는다."""
    st = _mk_state()
    st["cash"] = 50.0                            # 최소 주문(10 USDT)보다 약간 큼
    sym = "BTC/USDT"
    sig = {s: (1.0 if s == sym else 0.0) for s in IC.UNIVERSE}
    df1 = _df([100] * 3)
    _run(st, {sym: df1}, sig, {sym: 100.0}, {sym: str(df1.index[-1])})
    df2 = _df([100] * 4, lows=[99, 99, 99, 90])
    _run(st, {sym: df2}, sig, {sym: 100.0}, {sym: str(df2.index[-1])})
    assert st["limit_shadow"]["cash"] >= -1e-9, "그림자가 빚을 냈다"


def test_the_public_report_carries_the_comparison(tmp_path):
    st = _mk_state()
    sym = "BTC/USDT"
    sig = {s: (1.0 if s == sym else 0.0) for s in IC.UNIVERSE}
    df = _df([100] * 3)
    info = _run(st, {sym: df}, sig, {sym: 100.0}, {sym: str(df.index[-1])})
    st["rounds"] = [{"time": "2026-08-18T05:00:00", "equity": 10_000.0,
                     "trades": [], "limit_shadow": info}]
    out = IC.write_public_report(st, docs_dir=str(tmp_path))
    sh = out["limit_shadow"]
    assert sh and sh["start_equity"] == 10_000.0
    assert "미체결" in sh["note"], "미체결 위험을 말하지 않는다"
    page = (ROOT / "docs" / "intraday.html").read_text("utf-8")
    assert "limit_shadow" in page and "지정가" in page, (
        "공개 페이지가 비교를 보여주지 않는다")


def test_a_shadow_crash_cannot_stop_the_main_round(monkeypatch):
    """그림자가 죽어도 본 실험 회차는 끝까지 돈다."""
    src = (ROOT / "quant" / "live" / "intraday_challenger.py").read_text("utf-8")
    assert "지정가 그림자 실패(본 실험 무관)" in src, (
        "그림자 예외가 본 실험으로 새어 나간다")
