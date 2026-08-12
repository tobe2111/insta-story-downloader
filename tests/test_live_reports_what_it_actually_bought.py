"""실거래 보고가 **실제로 산 것**을 말하는가 (감사 138).

국내주식은 정수 주만 산다. 브로커 어댑터는 그걸 알고 있다.

    # quant/broker/kr_live.py
    qty = int(quantity)          # 국내주식은 정수 수량
    if qty <= 0:
        return Order(symbol, side, 0.0, price, status="skipped")

문제는 그 다음이다. 집행 요약이 이렇게 세고 있었다.

    print(f"… 결정 {len(decisions)}종목 · 주문 {len(orders)}건")

`orders`에는 **0주로 잘린 주문도 한 줄씩** 들어간다. 그래서 한 주도 사지
못한 날에도 "주문 5건"으로 보고된다 — 접수와 체결을 한 숫자로 합쳐
말하는, 이 저장소가 반복해서 겪은 계열이다(감사 91 '배분 예산을 매수라
불렀다', 감사 119 '종목 수를 회전율이라 불렀다').

그리고 이건 가정이 아니다. 2026-08-12 페이퍼 계좌 기준 국내주식 5종목의
배정금액은 18~690원인데 1주 값은 10만~144만원이다 — **실전으로 켜면
다섯 종목 전부 0주로 잘린다.**
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.broker.base import Broker, Order, Position  # noqa: E402
from quant.broker.specs import MarketSpec  # noqa: E402


class _TinyAccountBroker(Broker):
    """8만원짜리 계좌 — 국내주식 1주 값에 한참 못 미친다.

    ⚠️ 처음 판은 `target_weight`를 통째로 흉내 냈다. 감사 148에서 실거래
       배치가 RobustBroker를 거치게 되자 그 지름길이 깨졌다 — 래퍼는
       `market_order`를 부르는데 이 가짜에는 그게 없었다.

       깨진 게 오히려 다행이다. 지름길로 흉내 낸 검사는 **실제 주문 경로를
       한 번도 지나가지 않는다.** 이제 진짜 브로커와 같은 모양(잔고·포지션·
       시장가주문·주문규격)만 구현하고, 비중→수량 계산과 규격 반올림은
       운영 코드가 하게 둔다.
    """

    def __init__(self, price: float = 100_800.0, cash: float = 80_000.0):
        self.price = price
        self.cash = cash
        self.qty = 0.0

    def get_cash(self) -> float:
        return self.cash

    def get_position(self, symbol: str) -> Position:
        return Position(symbol, self.qty, 0.0)

    def market_spec(self, symbol: str) -> MarketSpec:
        return MarketSpec(min_qty=1.0, qty_step=1.0)   # 국내주식 = 정수 주

    def market_order(self, symbol, side, quantity, price) -> Order:
        qty = int(quantity)
        if qty <= 0:
            return Order(symbol, side, 0.0, price, status="skipped")
        self.qty += qty if side == "buy" else -qty
        return Order(symbol, side, float(qty), price, status="accepted")


def _frame(price: float):
    """네트워크 없이 도는 깨끗한 일봉 — 합성 폴백 표식이 없어야 매매가 열린다."""
    import numpy as np
    import pandas as pd
    idx = pd.date_range("2025-01-01", periods=300, freq="D")
    rng = np.random.default_rng(5)
    close = price * np.cumprod(1 + rng.normal(0.001, 0.01, len(idx)))
    return pd.DataFrame({"open": close, "high": close * 1.01,
                         "low": close * 0.99, "close": close,
                         "volume": 1_000.0}, index=idx)


def _run(tmp_path, monkeypatch, broker, price: float = 100_800.0):
    """⚠️ 데이터·부착기를 전부 주입한다.

    처음 쓴 판은 진짜 제공자를 불렀다. 이 환경에는 네트워크가 없어 수신이
    실패했고, 그러면 그 종목은 통째로 스킵돼 **주문이 하나도 안 생긴다.**
    그런데 검사에는 `if not out.get("orders"): return` 가드가 있어서
    네 검사가 전부 '아무것도 확인하지 않고' 초록이었다 — 오늘 하루 잡아온
    바로 그 결함(검사가 헛돈다)을 내가 만들 뻔했다.
    """
    import quant.data as qd
    import quant.data.crossasset as ca
    import quant.data.krx as krx
    import quant.live.daily_live as L
    import quant.utils.settings as us

    df = _frame(price)

    class _P:
        def get_ohlcv(self, *a, **k):
            return df.copy()

    monkeypatch.setattr(qd, "get_provider", lambda *a, **k: _P())
    monkeypatch.setattr(krx, "attach_krx_flows", lambda d, s: d)
    monkeypatch.setattr(ca, "attach_cross_asset", lambda d, m, s, **k: d)

    # 사이징도 고정한다 — 챔피언이 관망(0)을 내면 예산이 0이 되어 어느
    # 가격이든 0주가 나온다. 그러면 '가격 때문에 못 샀다'와 '신호가 없어서
    # 안 샀다'가 구별되지 않아 대조군이 성립하지 않는다.
    import pandas as pd

    import quant.live.daily as D

    class _FullSize:
        def size_positions(self, df, signals):
            return pd.Series(1.0, index=df.index)

    monkeypatch.setattr(D, "_risk_for", lambda market: _FullSize())
    monkeypatch.setattr(us, "load_settings",
                        lambda path=us.SETTINGS_PATH: {
                            "trading_paused": False, "exposure_scale": 1.0,
                            "social_post": True, "note": "",
                            "portfolio_target_vol": None})
    # 가짜 시계 — 체결확인 90초를 실시간으로 기다리지 않는다(감사 148).
    _t = [0.0]

    def _sleep(s):
        _t[0] += float(s)

    out = L.run_daily_live([("kr_stock", "069500.KS")], paper=True,
                           state_dir=str(tmp_path), broker=broker,
                           _clock={"sleep": _sleep, "now": lambda: _t[0]})
    assert not out.get("skipped"), (
        f"종목이 스킵됐다 — 이 검사는 아무것도 확인하지 못한다: {out}")
    assert out.get("orders"), (
        f"주문이 하나도 안 생겼다 — 검사가 헛돈다: {out}")
    return out


def test_zero_share_orders_are_not_counted_as_purchases(tmp_path, monkeypatch,
                                                        capsys):
    """0주로 잘린 주문을 '주문 N건'에 넣지 않는다."""
    out = _run(tmp_path, monkeypatch, _TinyAccountBroker())
    assert out["zero_qty"], (
        "1주 값이 계좌 전액을 넘는데 0주 기록이 없다 — 왜 안 샀는지 알 수 없다")
    printed = capsys.readouterr().out
    # 감사 148에서 '주문 N건'을 '접수 N건 · 체결 N건'으로 나눴다 —
    # 주식은 접수와 체결이 별개라 한 숫자로는 말할 수 없다.
    assert "접수 0건" in printed and "체결 0건" in printed, (
        f"한 주도 안 샀는데 건수를 0으로 말하지 않는다:\n{printed}")
    assert "미집행" in printed, "0주로 잘린 사실을 사람이 읽을 수 없다"


def test_the_reason_is_recorded_not_just_the_fact(tmp_path, monkeypatch):
    """'못 샀다'만으로는 부족하다 — 얼마를 사려 했고 1주가 얼마인지."""
    out = _run(tmp_path, monkeypatch, _TinyAccountBroker())
    row = out["zero_qty"][0]
    for field in ("symbol", "budget", "price", "shares"):
        assert field in row, f"{field}가 없다 — 유니버스 판단의 근거가 안 된다"
    assert row["shares"] < 1.0
    assert row["price"] > row["budget"], (
        "1주 값이 배정금액보다 크지 않은데 0주가 됐다 — 전제가 깨졌다")


def test_a_normal_purchase_is_still_counted(tmp_path, monkeypatch, capsys):
    """대조군 — 살 수 있는 날까지 0건으로 말하면 그건 다른 거짓말이다."""
    out = _run(tmp_path, monkeypatch,
               _TinyAccountBroker(price=1_000.0, cash=80_000.0), price=1_000.0)
    assert not out.get("zero_qty"), f"살 수 있는데 0주로 셌다: {out['zero_qty']}"
    printed = capsys.readouterr().out
    assert "접수 1건" in printed, printed
    # 체결까지 확인돼야 한다 — 접수만 세면 감사 148 이전으로 되돌아간다.
    assert "체결 1건" in printed, printed
    assert not out.get("unfilled"), f"실제로 샀는데 미체결로 잡혔다: {out['unfilled']}"
    assert any(float(o["filled"]) > 0 for o in out["orders"]), out["orders"]


def test_the_broker_adapter_really_floors_to_whole_shares():
    """전제 고정 — 어댑터가 정수 절사를 그만두면 위 검사가 무의미해진다."""
    for name in ("kr_live", "kiwoom_live"):
        src = (ROOT / "quant" / "broker" / f"{name}.py").read_text("utf-8")
        assert "qty = int(quantity)" in src, (
            f"{name}: 국내주식 정수 주 절사가 사라졌다")
        assert 'status="skipped"' in src, (
            f"{name}: 0주가 됐을 때의 표식이 사라졌다")
