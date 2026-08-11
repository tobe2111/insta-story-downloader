"""다종목 킬스위치가 정말 '전 종목'을 청산하는가 (감사 80).

로그와 알림은 이렇게 말한다:

    🛑 일일 손실 킬스위치 발동 — **전 종목 청산** 후 다음 UTC 일까지 매매 중단

그런데 청산 루프는 `prices.items()`를 돈다. `prices`는 `_target_weights()`가
만드는데, 거기서 **데이터가 빈 종목은 `continue`로 건너뛴다.** 즉 그 사이클에
시세를 못 받은 종목은 **청산 시도조차 되지 않는다.**

그리고 킬스위치는 그날 매매를 멈추므로, 그 포지션은 **다음 날까지 열린 채로
남는다** — 손실이 커져서 멈춘 그 상황에서.

가장 나쁜 건 **아무도 모른다는 것**이다. 사장님은 "전 종목 청산"을 읽고
평평하다고 믿는다. 오늘 내내 고친 계열(말과 행동이 다르다)의 실물이고,
하필 손실 국면에서 발생한다.

고칠 것은 '시세 없이 주문을 내는 것'이 아니다(불가능하다). **확인한 사실만
말하는 것**이다 — 못 비운 종목을 장부와 알림에 남긴다.
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
    """변동이 있는 봉 — 값이 전부 같으면 변동성 0이라 목표 비중이 0이 되고,
    그러면 기준선 사이클에서 이미 청산돼 이 검사가 무의미해진다."""
    import numpy as np
    rng = np.random.default_rng(seed)
    close = px * np.cumprod(1 + rng.normal(0.0005, 0.01, n))
    idx = pd.date_range("2026-01-01", periods=n, freq="h")
    return pd.DataFrame({"open": close, "high": close * 1.001,
                         "low": close * 0.999, "close": close,
                         "volume": [1000.0] * n}, index=idx)


class _Data:
    """심볼별로 데이터를 주거나(정상) 빈 프레임을 준다(조회 실패)."""

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
    def __init__(self, held, equity=10_000.0):
        self.held = dict(held)             # symbol -> quantity
        self._equity = equity
        self.flattened: list[str] = []
        self.order_log: list = []

    def equity(self, _prices):
        return self._equity

    def get_cash(self):
        return self._equity

    def get_position(self, s):
        return _Pos(s, self.held.get(s, 0.0))

    def target_weight(self, symbol, weight, *_a, **_k):
        if float(weight) == 0.0:
            self.flattened.append(symbol)
            self.held[symbol] = 0.0
        return None


class _Notifier:
    def __init__(self):
        self.msgs: list[str] = []

    def send(self, msg, level="info"):
        self.msgs.append(str(msg))


SYMS = ["BTC/USDT", "ETH/USDT"]


def _trader(data, broker, notifier, tmp_path):
    return MultiTrader(
        data=data, strategy=_Strat(), broker=broker, symbols=SYMS,
        state_path=str(tmp_path / "s.json"), notifier=notifier,
        daily_max_loss=0.05)


@pytest.fixture
def setup(tmp_path):
    data = _Data()
    broker = _Broker({s: 10.0 for s in SYMS})
    notif = _Notifier()
    return data, broker, notif, _trader(data, broker, notif, tmp_path)


# ── 기준선 ──────────────────────────────────────────────────────

def test_all_symbols_are_flattened_when_all_have_prices(setup):
    data, broker, _n, t = setup
    t.step()                                    # 기준선 등록
    broker.flattened.clear()
    broker._equity = 8_000.0                    # -20% → 발동
    t.step()
    assert set(broker.flattened) == set(SYMS), broker.flattened


# ── 본체 ────────────────────────────────────────────────────────

def test_a_symbol_without_a_price_is_not_silently_left_open(setup):
    """시세를 못 받은 종목이 조용히 열린 채 남으면 안 된다.

    비울 수 없다면 최소한 **비우지 못했다고 말해야** 한다.
    """
    data, broker, notif, t = setup
    t.step()
    broker.flattened.clear()
    notif.msgs.clear()

    data.blackout.add("ETH/USDT")               # 이 사이클에 ETH 시세 실패
    broker._equity = 8_000.0
    t.step()

    assert broker.held["ETH/USDT"] != 0.0, (
        "이 검사가 성립하려면 ETH가 청산되지 않은 상태여야 한다")

    snap = t.snapshot()
    unflat = snap.get("kill_switch_unflattened")
    told = " ".join(notif.msgs)
    assert (unflat and "ETH/USDT" in " ".join(unflat)) or "ETH/USDT" in told, (
        "킬스위치가 '전 종목 청산'이라 해놓고 ETH/USDT를 비우지 못했는데 "
        f"장부에도 알림에도 그 사실이 없다 (장부={unflat!r}, 알림={told!r})")


def test_a_failed_liquidation_order_is_reported(setup, tmp_path):
    """주문이 거부돼도 마찬가지다 — 실패를 삼키면 안 된다."""
    data = _Data()
    notif = _Notifier()

    class _Refusing(_Broker):
        refuse = False        # 킬스위치 청산에서만 거부하도록 켠다

        def target_weight(self, symbol, weight, *_a, **_k):
            if self.refuse and float(weight) == 0.0 and symbol == "ETH/USDT":
                raise RuntimeError("거래소 거부(모의)")
            return super().target_weight(symbol, weight, *_a, **_k)

    broker = _Refusing({s: 10.0 for s in SYMS})
    t = _trader(data, broker, notif, tmp_path)
    t.step()
    notif.msgs.clear()
    broker.refuse = True
    broker._equity = 8_000.0
    t.step()

    assert broker.held["ETH/USDT"] != 0.0
    snap = t.snapshot()
    unflat = snap.get("kill_switch_unflattened")
    told = " ".join(notif.msgs)
    assert (unflat and "ETH/USDT" in " ".join(unflat)) or "ETH/USDT" in told, (
        f"청산 주문이 거부됐는데 아무도 모른다 (장부={unflat!r}, 알림={told!r})")


def test_a_flat_symbol_without_price_is_not_a_false_alarm(setup):
    """보유가 없는 종목은 시세가 없어도 '못 비웠다'가 아니다.

    거짓 경보를 만들면 진짜 경보를 무시하게 된다.
    """
    data, broker, notif, t = setup
    broker.held["ETH/USDT"] = 0.0               # 애초에 안 들고 있다
    t.step()
    notif.msgs.clear()
    data.blackout.add("ETH/USDT")
    broker._equity = 8_000.0
    t.step()

    unflat = t.snapshot().get("kill_switch_unflattened") or []
    assert "ETH/USDT" not in " ".join(unflat), (
        f"보유하지도 않은 종목을 '못 비웠다'고 보고했다: {unflat}")


def test_circuit_breaker_uses_the_same_liquidation_path(setup, tmp_path):
    """서킷브레이커도 같은 함수를 쓴다 — 두 곳에 적으면 한쪽만 고쳐진다.

    실제로 그럴 뻔했다: 감사 80을 킬스위치 분기에서만 고치고 서킷브레이커
    분기에 같은 버그를 남겨 둘 뻔했다. 오늘 1번 교훈의 재발이다.
    """
    data = _Data()
    broker = _Broker({s: 10.0 for s in SYMS})
    notif = _Notifier()

    class _CB:
        reason = "낙폭 한도"
        on = False

        def update(self, _eq, _day):
            return self.on

    cb = _CB()
    t = MultiTrader(data=data, strategy=_Strat(), broker=broker, symbols=SYMS,
                    state_path=str(tmp_path / "cb.json"), notifier=notif,
                    circuit_breaker=cb)
    t.step()
    notif.msgs.clear()

    data.blackout.add("ETH/USDT")               # 시세 실패
    cb.on = True
    t.step()

    unflat = t.snapshot().get("kill_switch_unflattened") or []
    told = " ".join(notif.msgs)
    assert "ETH/USDT" in " ".join(unflat) or "ETH/USDT" in told, (
        "서킷브레이커가 '전 종목 청산'이라 해놓고 못 비운 종목을 "
        f"알리지 않았다 (장부={unflat!r}, 알림={told!r})")


def test_one_rejected_order_does_not_cancel_the_others(setup, tmp_path):
    """한 종목 주문이 거부돼도 나머지는 나가야 한다 (감사 81).

    예전에는 try가 없어서 예외가 step() 밖으로 나갔다 — 나머지 종목 주문이
    아예 안 나가고 **그 사이클 기록조차 장부에 남지 않았다.** 매매는 일부
    일어났는데 장부에는 그날이 없는 상태다.
    """
    data = _Data()
    notif = _Notifier()

    class _RefuseOne(_Broker):
        def __init__(self, held):
            super().__init__(held)
            self.accepted: list[str] = []

        def target_weight(self, symbol, weight, *_a, **_k):
            if symbol == "BTC/USDT":
                raise RuntimeError("거래소 거부(모의)")
            self.accepted.append(symbol)
            return None

    broker = _RefuseOne({s: 10.0 for s in SYMS})
    t = _trader(data, broker, notif, tmp_path)
    t.step()                                    # 예외가 새어나오면 여기서 실패

    assert "ETH/USDT" in broker.accepted, (
        "BTC 주문이 거부되자 ETH 주문까지 나가지 않았다")
    assert t.history, "주문이 일부 나갔는데 그 사이클이 장부에 없다"
    failed = t.snapshot().get("failed_orders") or []
    told = " ".join(notif.msgs)
    assert "BTC/USDT" in " ".join(failed) or "BTC/USDT" in told, (
        f"주문 실패를 아무도 모른다 (장부={failed!r}, 알림={told!r})")


def test_a_clean_cycle_reports_no_failures(setup):
    """정상 사이클은 실패 목록을 남기지 않는다(거짓 경보 방지)."""
    _data, _broker, _n, t = setup
    t.step()
    assert t.snapshot().get("failed_orders") is None


def test_halt_still_holds_after_a_partial_liquidation(setup):
    """일부만 비웠어도 그날 매매는 멈춘다 — 재개하면 손실 중에 더 매매한다."""
    data, broker, _n, t = setup
    t.step()
    data.blackout.add("ETH/USDT")
    broker._equity = 8_000.0
    t.step()

    broker.flattened.clear()
    data.blackout.clear()
    broker._equity = 9_000.0
    t.step()
    assert broker.order_log == [] and not broker.flattened, \
        "부분 청산 후 매매를 재개했다"
