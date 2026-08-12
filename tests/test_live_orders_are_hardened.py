"""무인 실거래 경로가 **견고화 래퍼를 거치는가** (감사 148).

사람이 지켜보는 경로에는 재시도·체결확인·규격검사가 다 있었고,
**아무도 안 보는 경로에만 없었다.**

    cli `trade`  (사람이 '실전' 두 글자 입력)      → RobustBroker ✅
    cli `webhook`(사람이 'yes' 입력)               → RobustBroker ✅
    `live-daily` (kr-live.yml이 매일 무인 실행)    → 생 KISBroker ❌

빠진 셋이 각각 무슨 일을 하는가.

    ① 재시도       HTTP 오류 한 번에 그 종목은 그날 통째로 건너뛴다.
    ② 체결 확인    KIS 시장가 접수 응답은 status='accepted', filled=0이다.
                   kr_live.py는 "실제 체결은 RobustBroker의 confirm_fills가
                   측정한다"고 **적어 두었는데 그 래퍼가 없었다.**
                   → 한 주도 안 체결된 날에도 장부는 '주문 N건'.
    ③ 규격         min_qty·qty_step이 0이라 1주 미만도 그대로 내려간다.
                   감사 139가 `_spec_for()`를 고쳤지만 **답할 줄 아는
                   브로커가 코인 하나뿐**이었다(주식 둘은 메서드가 없었다).

부품 검사와 배선 검사는 다른 것이다(FROZEN_IDEAS ㉑). RobustBroker 자체는
잘 검사돼 있었다 — 아무도 그걸 **거쳐 가는지**를 보지 않았을 뿐이다.
그래서 이 파일은 가짜 브로커를 주입해 **실제 배치를 돌리고** 결과를 읽는다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.broker import RobustBroker  # noqa: E402
from quant.broker.base import Broker, Order, Position  # noqa: E402
from quant.broker.kiwoom_live import KiwoomBroker  # noqa: E402
from quant.broker.kr_live import KISBroker  # noqa: E402
from quant.broker.us_live import AlpacaBroker  # noqa: E402
from quant.live.daily_live import _harden, run_daily_live  # noqa: E402


class FakeKR(Broker):
    """정수 주만 받는 국내주식 브로커 흉내 — 접수는 되고 체결은 비동기."""

    def __init__(self, cash: float = 1_000_000.0, flaky: int = 0,
                 fills: bool = True):
        self._cash = cash
        self._qty: dict[str, float] = {}
        self.flaky = flaky              # 앞의 N번은 예외를 던진다
        self.fills = fills              # False면 접수만 되고 체결이 안 된다
        self.sent: list[tuple] = []

    def get_cash(self) -> float:
        return self._cash

    def get_position(self, symbol: str) -> Position:
        return Position(symbol, self._qty.get(symbol, 0.0), 0.0)

    def market_order(self, symbol, side, quantity, price) -> Order:
        if self.flaky > 0:
            self.flaky -= 1
            raise RuntimeError("일시적 네트워크 오류")
        qty = int(quantity)
        self.sent.append((symbol, side, qty))
        if qty <= 0:
            return Order(symbol, side, 0.0, price, status="skipped")
        if self.fills:                  # 체결되면 포지션이 변한다
            self._qty[symbol] = self._qty.get(symbol, 0.0) + (
                qty if side == "buy" else -qty)
        # 실제 KIS와 같이 '접수'만 보고한다 — 체결 수량은 모른다
        return Order(symbol, side, float(qty), price, status="accepted",
                     filled_quantity=0.0, order_id="X1")


# ── 브로커가 자기 규격을 말할 줄 아는가 ───────────────────────


def test_stock_brokers_declare_their_order_spec():
    """감사 139는 물음만 고쳤다 — 답할 줄 아는 브로커가 하나뿐이었다."""
    for cls in (KISBroker, KiwoomBroker, AlpacaBroker):
        assert hasattr(cls, "market_spec"), (
            f"{cls.__name__}에 market_spec이 없다 — RobustBroker가 물어도 "
            "기본 규격(전부 0)으로 떨어져 규격 검사가 꺼진다")


def test_korean_stocks_are_whole_lots_and_us_stocks_are_not():
    kr = KISBroker.market_spec(object(), "005930")
    assert kr.min_qty == 1.0 and kr.qty_step == 1.0
    assert kr.round_qty(0.9) == 0.0, "1주 미만은 0으로 잘려야 한다"
    assert kr.round_qty(3.7) == 3.0, "정수 주로 내림해야 한다"

    us = AlpacaBroker.market_spec(object(), "SPY")
    assert us.round_qty(0.37) == pytest.approx(0.37), (
        "미국주식은 소수점 주가 되는데 정수로 잘리면 예산이 통째로 사라진다")
    assert not us.is_tradeable(0.001, 100.0) or us.min_notional == 0.0


# ── 배치가 그 래퍼를 실제로 거치는가 ──────────────────────────


def test_the_unattended_batch_wraps_its_broker():
    inner = FakeKR()
    assert isinstance(_harden(inner), RobustBroker), (
        "무인 실거래 배치가 생 브로커로 주문을 낸다 — 재시도·체결확인·규격이 "
        "전부 빠진다")


def test_hardening_is_not_applied_twice():
    once = _harden(FakeKR())
    assert _harden(once) is once, "이중 래핑은 재시도 횟수를 제곱시킨다"


def test_confirm_fills_is_on_for_stocks():
    """주식은 접수와 체결이 별개다 — 확인을 켜지 않으면 측정할 방법이 없다."""
    r = _harden(FakeKR())
    assert r.confirm_fills is True
    assert r.fill_timeout > 0, "확인을 켜고 시간을 0으로 두면 켜지 않은 것과 같다"
    assert r.retries >= 2, "무인 경로에서 재시도가 없으면 오류 한 번에 하루가 날아간다"


# ── 배치를 실제로 돌려 본다 ───────────────────────────────────


class _Clock:
    """가짜 시계 — 체결확인 90초·재시도 백오프를 실시간으로 기다리지 않는다."""

    def __init__(self):
        self.t = 0.0

    def sleep(self, s):
        self.t += float(s)

    def now(self):
        return self.t


def _run(monkeypatch, tmp_path, broker):
    """실데이터·설정을 갈아끼우고 실거래 배치를 한 번 돌린다."""
    import numpy as np
    import pandas as pd

    import quant.live.daily_live as dl

    idx = pd.date_range("2025-01-01", periods=400, freq="D")
    rng = np.random.default_rng(0)
    # 꾸준한 상승 추세 — 어떤 챔피언이 뽑히든 롱 비중이 나오게 한다.
    # (잡음만 있는 계열은 비중 0이 나와 주문 자체가 없고, 그러면 이 파일의
    #  검사가 전부 공짜로 통과한다 — 대조군이 필요한 이유와 같다.)
    close = 40_000.0 * np.exp(np.cumsum(
        rng.normal(0.0015, 0.008, 400)))
    df = pd.DataFrame({"open": close, "high": close * 1.01,
                       "low": close * 0.99, "close": close,
                       "volume": 1e6}, index=idx)

    class _P:
        def get_ohlcv(self, *a, **k):
            return df.copy()

    monkeypatch.setattr("quant.data.get_provider", lambda m: _P())
    monkeypatch.setattr("quant.data.krx.attach_krx_flows", lambda d, s: d)
    monkeypatch.setattr("quant.data.crossasset.attach_cross_asset",
                        lambda d, m, s: d)
    monkeypatch.setattr("quant.utils.settings.load_settings",
                        lambda: {"trading_paused": False, "exposure_scale": 1.0})
    # 기본 챔피언은 ML(logreg)이라 짧은 합성 계열에서는 신호가 늘 0이다 —
    # 그러면 주문 자체가 없어 이 파일의 검사가 전부 공짜로 통과한다.
    # 추세를 그대로 따라가는 단순 챔피언을 박아 넣어 실제로 주문이 나가게 한다.
    from quant.live.retrain import save_champions
    save_champions({"kr_stock:069500.KS": {
        "strategy": "ma_cross",
        "params": {"fast": 10, "slow": 40}}}, str(tmp_path))
    clk = _Clock()
    return run_daily_live(targets=[("kr_stock", "069500.KS")],
                          paper=True, state_dir=str(tmp_path), broker=broker,
                          _clock={"sleep": clk.sleep, "now": clk.now})


def test_a_transient_error_is_retried_not_dropped(monkeypatch, tmp_path):
    """오류 두 번 뒤 성공 — 재시도가 없으면 이 종목은 그날 통째로 빠진다."""
    broker = FakeKR(flaky=2)
    out = _run(monkeypatch, tmp_path, broker)
    assert out.get("orders"), (
        f"재시도가 없어 주문이 하나도 안 나갔다 — skipped={out.get('skipped')}")
    assert len(broker.sent) >= 1


def test_an_accepted_but_unfilled_order_is_not_counted_as_bought(
        monkeypatch, tmp_path):
    """접수만 되고 체결이 0이면 장부가 그렇게 말해야 한다.

    감사 138은 '0주로 잘림'을 고쳤다. 그런데 **접수됐는데 체결 0**인
    경우는 그대로 '주문 1건'으로 세고 있었다 — 같은 병의 다음 단계다.
    """
    out = _run(monkeypatch, tmp_path, FakeKR(fills=False))
    if not out.get("orders"):
        pytest.skip("이 시세에서는 밴드에 걸려 주문 자체가 안 나갔다")
    assert out.get("unfilled"), (
        "체결이 0인데 미체결 목록이 비어 있다 — 장부가 '샀다'고 말한다")
    for row in out["orders"]:
        assert "filled" in row, "장부에 실제 체결 수량 칸이 없다"
        assert float(row["filled"]) == 0.0


def test_a_real_fill_is_recorded_as_filled(monkeypatch, tmp_path):
    """대조군 — 정상 체결되면 filled가 0이 아니어야 한다.

    이 검사가 없으면 위 검사는 '항상 미체결'인 코드로도 통과한다.
    """
    out = _run(monkeypatch, tmp_path, FakeKR(fills=True))
    if not out.get("orders"):
        pytest.skip("이 시세에서는 밴드에 걸려 주문 자체가 안 나갔다")
    assert not out.get("unfilled"), (
        f"정상 체결인데 미체결로 잡혔다 — {out['unfilled']}")
    assert any(float(o["filled"]) > 0 for o in out["orders"]), (
        "포지션이 실제로 늘었는데 체결 수량이 0으로 기록된다 — "
        "confirm_fills가 배선되지 않았다")


# ── 주문 감사 로그가 실제로 쌓이는가 (감사 150) ───────────────


def test_every_order_lands_in_the_append_only_log(monkeypatch, tmp_path):
    """`journal.record_order`는 모듈 설명의 '두 가지' 중 첫 번째인데
    **운영 코드에서 부르는 곳이 한 곳도 없었다** — 검사에서만 불렸다.

    kr.json은 하루 한 줄 요약이고 400일치만 남긴다. 이 JSONL은 append-only라
    증권사 체결 내역과 order_id로 대사할 수 있는 유일한 기록이다.
    """
    from quant.live.journal import load_orders

    out = _run(monkeypatch, tmp_path, FakeKR(fills=True))
    if not out.get("orders"):
        pytest.skip("이 시세에서는 밴드에 걸려 주문 자체가 안 나갔다")

    rows = load_orders(tmp_path / "live" / "orders.jsonl")
    assert rows, "주문이 나갔는데 감사 로그가 비어 있다"
    for field in ("symbol", "side", "quantity", "filled", "status",
                  "order_id", "ts", "mode", "broker", "weight", "equity"):
        assert field in rows[0], f"감사 로그에 {field}가 없다 — 대사에 못 쓴다"
    assert rows[0]["mode"] == "paper"
    assert float(rows[0]["filled"]) > 0


def test_the_log_only_appends(monkeypatch, tmp_path):
    """두 번 돌리면 두 줄 — 덮어쓰면 감사 추적이 아니다."""
    from quant.live.journal import load_orders

    b = FakeKR(fills=True)
    if not _run(monkeypatch, tmp_path, b).get("orders"):
        pytest.skip("주문이 안 나갔다")
    first = len(load_orders(tmp_path / "live" / "orders.jsonl"))
    _run(monkeypatch, tmp_path, FakeKR(fills=True))
    second = len(load_orders(tmp_path / "live" / "orders.jsonl"))
    assert second > first, f"{first} → {second}: 로그가 덮어써지고 있다"
