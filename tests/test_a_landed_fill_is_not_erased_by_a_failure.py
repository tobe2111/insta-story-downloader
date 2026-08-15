"""이미 체결된 것이 '주문 실패'에 묻힌다 (감사 242).

`RobustBroker`는 응답이 끊긴 주문에 대해 **잔고를 읽어 얼마가 체결됐는지
직접 잽니다.** 그 값을 세 번이나 재고도, 재시도가 다 실패하면 예외를
던지면서 그 숫자를 **버렸습니다.**

실측(1.0 매수 요청 · 첫 주문에서 0.6 체결 후 응답 끊김 · 이후 계속 실패):

    로그      "부분 체결 감지(0.600000/1.000000)"  ← 세 번 찍힘
    반환      RuntimeError("❌ 주문 최종 실패")
    거래소    0.6 보유
    우리 장부  없음

위층 실거래 루프(`run_daily_live`)는 이 예외를 잡아 그 종목을 `skipped`로
적습니다. 그러면 **거래소에는 있는데 우리 장부에는 없는 포지션**이 생깁니다.
증권사 체결 내역과 대사하려고 만든 유일한 기록(`orders.jsonl`)에도 한 줄이
안 남습니다 — 대사하면 우리 쪽만 비어 있습니다.

결과가 실패로만 끝나지 않습니다. 다음 날 배치는 그 종목을 '보유 0'으로
알고 목표 비중을 다시 계산해 **또 삽니다.** 킬스위치가 전량 청산을 걸어도
모르는 포지션은 팔지 않습니다 — 안전장치가 닿지 않는 자산이 생깁니다.

고친 방향: **'더 못 산다'와 '아무것도 안 샀다'는 다른 말이다.** 잔고로
확인한 체결은 그대로 돌려주고(status="partial"), 실패는 알림으로 크게
말합니다. 아무것도 안 됐을 때만 예외로 올립니다.

함께 고친 것: 남은 수량이 거래소 최소 주문금액 미만이면 **보낼 수 없는
주문**입니다. 그대로 보내면 거절 → 재시도 → 같은 거절을 반복하다 "최종
실패"로 마감돼, 역시 체결분이 묻혔습니다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.broker.base import Order, Position  # noqa: E402
from quant.broker.retry import RobustBroker  # noqa: E402
from quant.broker.specs import MarketSpec  # noqa: E402


class _DiesAfterLanding:
    """첫 주문에서 `landed_frac`만 체결시키고 응답이 끊긴다. 이후 계속 실패.

    실거래에서 흔한 모양이다 — 시장가는 접수되면 거래소에서 체결이 진행되고,
    끊기는 것은 **응답**이지 주문이 아니다.
    """

    def __init__(self, landed_frac: float = 0.6, blind_after: int | None = None,
                 spec: MarketSpec | None = None):
        self.landed_frac = landed_frac
        self.blind_after = blind_after      # N번째 잔고 조회부터 실패
        self.spec = spec
        self.qty = 0.0
        self.submitted: list[float] = []
        self.pos_calls = 0

    def get_cash(self):
        return 1_000_000.0

    def get_position(self, symbol):
        self.pos_calls += 1
        if self.blind_after is not None and self.pos_calls > self.blind_after:
            raise RuntimeError("잔고 조회 실패")
        return Position(symbol, self.qty, 100.0)

    def market_spec(self, symbol):
        if self.spec is None:
            raise AttributeError
        return self.spec

    def market_order(self, symbol, side, quantity, price):
        self.submitted.append(round(quantity, 8))
        if len(self.submitted) == 1:
            self.qty += quantity * self.landed_frac    # 거래소에는 체결됐다
        raise TimeoutError("응답 없음")


def _robust(inner, **kw):
    kw.setdefault("spec", MarketSpec(min_qty=0.0, qty_step=0.0,
                                     min_notional=0.0))
    return RobustBroker(inner, retries=3, backoff=0.0,
                        sleep=lambda s: None, **kw)


# ── 체결된 것이 살아남는가 ────────────────────────────────────

def test_a_partial_fill_survives_the_final_failure():
    """실측 그 장면 — 예외가 아니라 '0.6 체결'이 나와야 한다."""
    inner = _DiesAfterLanding(0.6)
    out = _robust(inner).market_order("BTC/USDT", "buy", 1.0, 100.0)
    assert out.status == "partial", f"실패로 마감했다: {out.status}"
    assert out.filled_quantity == pytest.approx(0.6)


def test_the_report_matches_what_the_exchange_actually_holds():
    """장부와 거래소가 갈리면 그 뒤의 모든 계산이 틀린다."""
    inner = _DiesAfterLanding(0.6)
    out = _robust(inner).market_order("BTC/USDT", "buy", 1.0, 100.0)
    assert out.filled_quantity == pytest.approx(inner.qty)


def test_a_sell_that_partly_went_through_is_reported_too():
    """매도도 같다 — 절반 팔린 것을 '못 팔았다'로 적으면 이중 매도가 된다."""
    inner = _DiesAfterLanding(0.6)
    inner.qty = 1.0

    def _order(symbol, side, quantity, price):
        inner.submitted.append(round(quantity, 8))
        if len(inner.submitted) == 1:
            inner.qty -= quantity * 0.6
        raise TimeoutError("응답 없음")

    inner.market_order = _order
    out = _robust(inner).market_order("BTC/USDT", "sell", 1.0, 100.0)
    assert out.status == "partial"
    assert out.filled_quantity == pytest.approx(0.6)


def test_the_notifier_says_it_out_loud():
    """조용히 반쪽만 사고 넘어가면 안 된다 — 사람이 알아야 한다.

    그리고 **마지막에 남는 말**이 사실이어야 한다. 알림이 "주문 최종 실패"로
    끝나면 사람은 산 것이 없는 줄로 읽는다 — 거래소에는 0.6이 있는데.
    """
    sent = []

    class _N:
        def send(self, msg, level="info"):
            sent.append((msg, level))

    inner = _DiesAfterLanding(0.6)
    _robust(inner, notifier=_N()).market_order("BTC/USDT", "buy", 1.0, 100.0)
    errs = [m for m, lv in sent if lv == "error"]
    assert errs, f"실패 알림이 없다: {sent}"
    assert any("0.6" in m and "체결" in m for m in errs), errs
    assert "0.6" in errs[-1], f"끝맺음이 '아무것도 못 샀다'로 읽힌다: {errs[-1]}"


# ── 대조군: 아무것도 안 됐으면 여전히 실패다 ──────────────────

def test_nothing_landed_still_raises():
    """'더 못 산다'와 '아무것도 안 샀다'를 구분하는 반대쪽."""
    inner = _DiesAfterLanding(0.0)
    with pytest.raises(RuntimeError, match="최종 실패"):
        _robust(inner).market_order("X", "buy", 1.0, 100.0)


def test_a_healthy_order_is_still_just_filled():
    """대조군 — 멀쩡한 주문이 partial로 강등되면 안 된다."""

    class _Fine:
        qty = 0.0

        def get_cash(self):
            return 1_000.0

        def get_position(self, symbol):
            return Position(symbol, self.qty, 100.0)

        def market_order(self, symbol, side, quantity, price):
            self.qty += quantity
            return Order(symbol, side, quantity, price, status="filled",
                         filled_quantity=quantity)

    out = _robust(_Fine()).market_order("X", "buy", 1.0, 100.0)
    assert out.status == "filled" and out.filled_quantity == pytest.approx(1.0)


# ── 확인이 불가능할 때는 여전히 크게 실패한다 ─────────────────

def test_an_unverifiable_state_still_raises_but_says_what_it_last_saw():
    """잔고를 못 읽으면 재주문하지 않고 실패한다(감사 55) — 다만 마지막으로
    확인한 체결량은 알려준다. 그 숫자가 있어야 계좌를 어디서부터 볼지 안다.
    """
    # 제출 전 1회 + 1차 실패 후 1회까지는 읽히고, 그 뒤로는 안 읽힌다.
    inner = _DiesAfterLanding(0.6, blind_after=2)
    with pytest.raises(RuntimeError) as err:
        _robust(inner).market_order("X", "buy", 1.0, 100.0)
    msg = str(err.value)
    assert "직접 확인" in msg, msg
    assert "마지막 확인" in msg and "0.6" in msg, (
        f"확인했던 체결량을 안 알려준다:\n{msg}")


# ── 보낼 수 없는 잔량은 잔량이 아니다 ─────────────────────────

def test_a_remainder_below_the_exchange_minimum_ends_the_order():
    """최소 주문금액 미만의 잔량을 계속 보내면 거절만 쌓인다."""
    spec = MarketSpec(min_qty=0.0, qty_step=0.0, min_notional=10.0)
    inner = _DiesAfterLanding(0.98, spec=spec)
    out = _robust(inner, spec=spec).market_order("X", "buy", 1.0, 100.0)
    # 잔량 0.02 × 100원 = 2원 < 최소 10원 → 보내지 않는다
    assert inner.submitted == [1.0], f"못 보낼 주문을 보냈다: {inner.submitted}"
    assert out.status == "partial"
    assert out.filled_quantity == pytest.approx(0.98)


def test_a_remainder_above_the_minimum_is_still_retried():
    """대조군 — 보낼 수 있는 잔량은 그대로 재주문해야 한다."""
    spec = MarketSpec(min_qty=0.0, qty_step=0.0, min_notional=10.0)
    inner = _DiesAfterLanding(0.5, spec=spec)
    _robust(inner, spec=spec).market_order("X", "buy", 1.0, 100.0)
    assert len(inner.submitted) > 1, "잔량 50원어치를 포기했다"


# ── 위층 실거래 루프까지 살아 오는가 ──────────────────────────

class _KrDiesAfterLanding:
    """국내주식 모양(정수 주)으로, 첫 주문의 60%만 체결되고 응답이 끊긴다."""

    def __init__(self, price: float = 10_000.0, cash: float = 10_000_000.0):
        self.price = price
        self.cash = cash
        self.qty = 0.0
        self.submitted: list[float] = []

    def get_cash(self):
        return self.cash

    def get_position(self, symbol):
        return Position(symbol, self.qty, self.price)

    def market_spec(self, symbol):
        return MarketSpec(min_qty=1.0, qty_step=1.0)

    def market_order(self, symbol, side, quantity, price):
        self.submitted.append(quantity)
        if len(self.submitted) == 1:
            self.qty += float(int(quantity * 0.6))
        raise TimeoutError("응답 없음")


def _frame(price: float):
    import numpy as np
    import pandas as pd
    idx = pd.date_range("2025-01-01", periods=300, freq="D")
    rng = np.random.default_rng(5)
    close = price * np.cumprod(1 + rng.normal(0.001, 0.01, len(idx)))
    return pd.DataFrame({"open": close, "high": close * 1.01,
                         "low": close * 0.99, "close": close,
                         "volume": 1_000.0}, index=idx)


def _run_live(tmp_path, monkeypatch, broker, price=10_000.0):
    """실거래 배치를 네트워크 없이 한 바퀴 돌린다(감사 138 검사와 같은 판)."""
    import pandas as pd

    import quant.data as qd
    import quant.data.crossasset as ca
    import quant.data.krx as krx
    import quant.live.daily as D
    import quant.live.daily_live as L
    import quant.utils.settings as us

    df = _frame(price)

    class _P:
        def get_ohlcv(self, *a, **k):
            return df.copy()

    monkeypatch.setattr(qd, "get_provider", lambda *a, **k: _P())
    monkeypatch.setattr(krx, "attach_krx_flows", lambda d, s: d)
    monkeypatch.setattr(ca, "attach_cross_asset", lambda d, m, s, **k: d)

    class _FullSize:
        def size_positions(self, df, signals):
            return pd.Series(1.0, index=df.index)

    monkeypatch.setattr(D, "_risk_for", lambda market: _FullSize())
    monkeypatch.setattr(us, "load_settings",
                        lambda path=us.SETTINGS_PATH: {
                            "trading_paused": False, "exposure_scale": 1.0,
                            "social_post": True, "note": "",
                            "portfolio_target_vol": None})
    _t = [0.0]
    return L.run_daily_live([("kr_stock", "069500.KS")], paper=True,
                            state_dir=str(tmp_path), broker=broker,
                            _clock={"sleep": lambda s: _t.__setitem__(
                                0, _t[0] + float(s)), "now": lambda: _t[0]})


def test_the_live_batch_does_not_call_it_a_skip(tmp_path, monkeypatch):
    """예외가 위로 올라가면 그 종목은 `skipped` — 산 것이 통째로 사라진다."""
    broker = _KrDiesAfterLanding()
    out = _run_live(tmp_path, monkeypatch, broker)
    assert broker.qty > 0, "이 검사의 전제(체결이 실제로 일어남)가 깨졌다"
    assert "069500.KS" not in (out.get("skipped") or []), (
        f"산 종목이 스킵으로 적혔다: {out}")


def test_the_order_journal_keeps_the_row(tmp_path, monkeypatch):
    """증권사 체결 내역과 대사할 유일한 기록에 한 줄이 남아야 한다."""
    broker = _KrDiesAfterLanding()
    _run_live(tmp_path, monkeypatch, broker)
    path = tmp_path / "live" / "orders.jsonl"
    assert path.exists(), "주문 기록 파일이 아예 없다 — 대사할 것이 없다"
    rows = [json.loads(ln) for ln in path.read_text("utf-8").splitlines() if ln]
    filled = [r for r in rows if float(r.get("filled") or 0) > 0]
    assert filled, f"체결이 있었는데 기록에는 0뿐이다: {rows}"
    assert filled[0]["filled"] == pytest.approx(broker.qty), (
        f"기록({filled[0]['filled']})과 거래소({broker.qty})가 갈렸다")
