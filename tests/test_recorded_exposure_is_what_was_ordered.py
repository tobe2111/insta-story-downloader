"""장부에 적는 노출이 **실제로 주문이 나간 만큼**인가 (감사 93).

91·92와 같은 계열이다. `MultiTrader.step()`은 이렇게 생겼다:

    for s, w in weights.items():
        if not price: continue              # ← 시세 없음: 주문 안 냄
        try:    order = broker.target_weight(...)
        except: failed.append(s); continue  # ← 주문 실패: 포지션 안 생김
    history.append({"weight": sum(abs(v) for v in weights.values())})  # ← 목표 전부

즉 **주문이 나가지 않은 종목까지 노출로 적었다.** 하필 데이터 소스나
브로커가 흔들리는 날에 장부가 실제보다 큰 노출을 말한다 — 그 숫자를 보고
"오늘은 위험을 많이 졌구나" 하고 판단하게 된다. 반대 방향이면 더 나쁘다:
포지션이 있다고 믿고 청산을 안 한다.

이 프로젝트의 규칙은 "확인한 사실만 말한다"이다. 여기서 고정한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.multi import MultiTrader          # noqa: E402


def _bars(n=60, px=100.0, seed=3):
    import numpy as np
    rng = np.random.default_rng(seed)
    close = px * np.cumprod(1 + rng.normal(0.0005, 0.01, n))
    idx = pd.date_range("2026-01-01", periods=n, freq="h")
    return pd.DataFrame({"open": close, "high": close * 1.001,
                         "low": close * 0.999, "close": close,
                         "volume": [1000.0] * n}, index=idx)


class _Data:
    def __init__(self):
        self.blackout: set[str] = set()

    def get_ohlcv(self, symbol, *_a, **_k):
        if symbol in self.blackout:
            return pd.DataFrame()
        return _bars(seed=abs(hash(symbol)) % 1000)


class _Strat:
    name = "fixed"
    allow_short = False

    def generate_signals(self, df):
        return pd.Series(0.5, index=df.index)


class _Pos:
    def __init__(self, symbol, qty):
        self.symbol, self.quantity, self.avg_price = symbol, qty, 100.0


class _Broker:
    """지정한 종목의 주문만 예외로 실패시키는 브로커."""

    def __init__(self, equity=10_000.0):
        self._equity = equity
        self.reject: set[str] = set()
        self.order_log: list = []
        self.orders: list[tuple[str, float]] = []

    def equity(self, _prices):
        return self._equity

    def get_cash(self):
        return self._equity

    def get_position(self, s):
        return _Pos(s, 0.0)

    def target_weight(self, symbol, weight, *_a, **_k):
        if symbol in self.reject:
            raise RuntimeError("브로커 거부")
        self.orders.append((symbol, float(weight)))
        return None


SYMS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]


@pytest.fixture
def trader(tmp_path):
    data, broker = _Data(), _Broker()
    t = MultiTrader(data=data, strategy=_Strat(), broker=broker, symbols=SYMS,
                    state_path=str(tmp_path / "s.json"))
    return data, broker, t


def _recorded(t) -> float:
    return float(t.history[-1]["weight"])


def test_baseline_records_the_full_target_when_everything_goes_through(trader):
    _d, broker, t = trader
    t.step()
    want = sum(abs(w) for _s, w in broker.orders)
    assert _recorded(t) == pytest.approx(want, abs=1e-9)
    assert _recorded(t) > 0, "기준선이 0이면 아래 검사가 무의미하다"


def test_a_rejected_order_is_not_counted_as_exposure(trader):
    """주문이 예외로 실패한 종목은 포지션이 없다 — 노출에 넣으면 안 된다."""
    _d, broker, t = trader
    t.step()
    full = _recorded(t)

    broker.reject = {"ETH/USDT"}
    broker.orders.clear()
    t.step()
    got = _recorded(t)
    want = sum(abs(w) for _s, w in broker.orders)      # 실제로 나간 주문만

    assert got == pytest.approx(want, abs=1e-9), (
        f"장부가 노출 {got}을 적었는데 실제로 나간 주문의 합은 {want}다 — "
        "브로커가 거부한 종목까지 들고 있다고 말한다")
    assert got < full, "실패가 있었는데 기록된 노출이 전량과 같다"
    assert t._failed_orders, "실패 흔적도 남지 않았다"


def test_a_symbol_without_a_price_is_not_counted_either(trader):
    """시세를 못 받아 건너뛴 종목도 마찬가지다."""
    data, broker, t = trader
    t.step()
    full = _recorded(t)

    data.blackout = {"SOL/USDT"}
    broker.orders.clear()
    t.step()
    got = _recorded(t)
    placed = sum(abs(w) for _s, w in broker.orders)
    assert got == pytest.approx(placed, abs=1e-9), (
        f"장부 노출 {got} vs 실제 주문 합 {placed}")
    # ⚠️ 여기서 `got < full`을 기대하면 안 된다 — 데이터가 빠진 종목은
    #    `_target_weights()`에서 이미 제외되고 나머지로 **재정규화**되므로
    #    총노출은 그대로다. 검사가 봐야 하는 건 '장부 = 실제 주문'뿐이다.
    assert full > 0 and got > 0
    assert ("SOL/USDT" not in [s for s, _w in broker.orders])


def test_an_unchanged_position_still_counts(trader):
    """밴드 안이라 주문을 안 낸 경우(order=None)는 노출이 **유지**된다.

    이건 빼면 안 된다 — 안 고쳐 잡았을 뿐 포지션은 그대로 있다.
    반대로 여기까지 빼면 재조정을 쉰 날마다 노출 0이라 보고하게 된다.
    """
    _d, broker, t = trader
    t.step()                       # _Broker.target_weight는 항상 None을 돌려준다
    assert _recorded(t) > 0, (
        "밴드 안(order=None)을 '주문 안 나감'으로 오해해 노출에서 뺐다")
