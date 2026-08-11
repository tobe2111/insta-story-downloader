"""단일 종목 실행 루프의 안전장치 — 실제로 한 사이클 돌려서 확인한다 (감사 79).

커버리지에서 `LiveTrader.step` **24줄이 미실행**이었다. 그 안에 세 가지
안전장치가 전부 들어 있다:

  ① 장 시간 가드 — 닫힌 시장에 주문을 내지 않는다
  ② 일일 손실 킬스위치 — 발동 시 청산하고 그날은 멈춘다
  ③ 서킷브레이커 — 발동 시 청산하고 멈춘다

기존 검사들은 이 장치들의 **부품**(KillSwitch·CircuitBreaker 클래스,
is_market_open 함수)을 각각 확인했다. 부품이 옳은 것과 **그 부품이 주문
경로에 꽂혀 있는 것은 다른 문제**다 — 오늘 감사에서 여러 번 확인한 간격이다.

여기서는 진짜로 `step()`을 돌려 **브로커에 주문이 갔는지 안 갔는지**로
판정한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.engine import LiveTrader          # noqa: E402


def _bars(n=60, start=100.0, drift=0.0):
    idx = pd.date_range("2026-01-01", periods=n, freq="h")
    px = [start * (1 + drift) ** i for i in range(n)]
    return pd.DataFrame({"open": px, "high": px, "low": px,
                         "close": px, "volume": [1000.0] * n}, index=idx)


class _Data:
    def __init__(self, df):
        self.df = df

    def get_ohlcv(self, *_a, **_k):
        return self.df


class _Strat:
    name = "fixed"
    allow_short = False

    def __init__(self, w=1.0):
        self.w = w

    def generate_signals(self, df):
        return pd.Series(self.w, index=df.index)


class _Risk:
    def size_positions(self, df, target):
        return target


class _Broker:
    """주문을 받기만 하고 기록한다 — '주문이 갔는가'가 판정 기준이다."""

    def __init__(self, equity=10_000.0):
        self.orders: list[tuple[str, float]] = []
        self._equity = equity

    def equity(self, _prices):
        return self._equity

    def target_weight(self, symbol, weight, *_a, **_k):
        self.orders.append((symbol, float(weight)))

    def get_cash(self):
        return self._equity

    def get_position(self, _s):
        class P:
            quantity = 0.0
        return P()


def _trader(broker, **kw):
    return LiveTrader(data=_Data(_bars()), strategy=_Strat(), broker=broker,
                      risk=_Risk(), symbol="BTC/USDT", **kw)


# ── ① 장 시간 가드 ──────────────────────────────────────────────

def test_closed_market_places_no_order(monkeypatch):
    """닫힌 시장에는 주문을 내지 않는다.

    가드가 빠지면 거래소가 거부하거나(운이 좋으면) 다음 개장에 엉뚱한
    가격으로 체결된다.
    """
    import quant.live.market_hours as mh
    monkeypatch.setattr(mh, "is_market_open", lambda *_a, **_k: False)
    monkeypatch.setattr(mh, "market_status", lambda *_a, **_k: "장 마감")

    b = _Broker()
    _trader(b, market="kr_stock").step()
    assert b.orders == [], "닫힌 시장에 주문이 나갔다"


def test_open_market_does_place_an_order(monkeypatch):
    """반대로 열린 시장까지 막으면 그것도 결함이다(과잉 차단 방지)."""
    import quant.live.market_hours as mh
    monkeypatch.setattr(mh, "is_market_open", lambda *_a, **_k: True)
    monkeypatch.setattr(mh, "market_status", lambda *_a, **_k: "정규장")

    b = _Broker()
    _trader(b, market="kr_stock").step()
    assert b.orders, "열린 시장인데 주문이 안 나갔다"


def test_market_none_is_treated_as_24h():
    """코인·미지정은 장 시간 가드를 적용하지 않는다."""
    b = _Broker()
    _trader(b).step()
    assert b.orders


# ── ② 일일 손실 킬스위치 ────────────────────────────────────────

def test_killswitch_liquidates_and_then_stays_halted():
    """발동한 사이클엔 청산하고, **다음 사이클엔 아예 매매하지 않는다.**

    두 번째가 핵심이다. 발동 순간만 막고 다음 봉부터 다시 매매하면
    '그날은 중단'이라는 약속이 지켜지지 않는다.
    """
    b = _Broker(equity=10_000.0)
    t = _trader(b, daily_max_loss=0.05)
    t.step()                                   # 기준선 등록
    assert b.orders, "첫 사이클에 주문이 없다 — 이후 판정이 무의미하다"

    b.orders.clear()
    b._equity = 9_000.0                        # -10% → 한도(5%) 초과
    t.step()
    assert b.orders == [("BTC/USDT", 0.0)], f"청산 주문이 아니다: {b.orders}"

    b.orders.clear()
    b._equity = 9_500.0                        # 조금 회복해도 그날은 멈춤
    t.step()
    assert b.orders == [], "킬스위치 발동 후에도 매매를 재개했다"


def test_killswitch_records_the_flat_position():
    """청산했으면 장부에도 비중 0이 남아야 한다 — 사이트가 진실을 말하도록."""
    b = _Broker(equity=10_000.0)
    t = _trader(b, daily_max_loss=0.05)
    t.step()
    b._equity = 8_000.0
    t.step()
    assert t.history and t.history[-1]["weight"] == 0.0, t.history[-1:]


def test_killswitch_halt_survives_a_failed_liquidation():
    """청산 주문이 실패해도 중단 상태는 유지된다.

    실패했다고 계속 매매하면, 손실이 나는 중에 더 매매하는 정반대가 된다.
    """
    class _Failing(_Broker):
        def target_weight(self, symbol, weight, *_a, **_k):
            if weight == 0.0:
                raise RuntimeError("청산 실패(모의)")
            super().target_weight(symbol, weight, *_a, **_k)

    b = _Failing(equity=10_000.0)
    t = _trader(b, daily_max_loss=0.05)
    t.step()
    b.orders.clear()
    b._equity = 8_000.0
    t.step()                                   # 청산 실패해도 예외가 새면 안 된다
    b.orders.clear()
    b._equity = 9_000.0
    t.step()
    assert b.orders == [], "청산에 실패했다고 매매를 재개했다"


# ── ③ 서킷브레이커 ──────────────────────────────────────────────

def test_circuit_breaker_liquidates_and_stops():
    class _CB:
        reason = "낙폭 한도"

        def __init__(self):
            self.on = False

        def update(self, _eq, _day):
            return self.on

    cb = _CB()
    b = _Broker()
    t = _trader(b, circuit_breaker=cb)
    t.step()
    assert b.orders

    b.orders.clear()
    cb.on = True
    t.step()
    assert b.orders == [("BTC/USDT", 0.0)], f"청산하지 않았다: {b.orders}"
    assert t.history[-1]["weight"] == 0.0


# ── 데이터가 없을 때 ────────────────────────────────────────────

def test_empty_data_places_no_order():
    """데이터가 비면 '비중 0'으로 오해해 청산하면 안 된다 — 그냥 건너뛴다."""
    b = _Broker()
    t = LiveTrader(data=_Data(pd.DataFrame()), strategy=_Strat(), broker=b,
                   risk=_Risk(), symbol="BTC/USDT")
    t.step()
    assert b.orders == [], "데이터가 없는데 주문을 냈다"


# ── 사장님의 전역 스위치 (감사 83) ──────────────────────────────
#
# 문자열 검사(test_owner_gate_covers_all_paths)는 '읽는다'만 본다. 실제로
# 주문이 멈추는지는 여기서 돌려 본다.

def _paused(monkeypatch, paused=True, scale=1.0):
    import quant.utils.settings as st
    monkeypatch.setattr(st, "owner_gate", lambda *_a, **_k: (paused, scale))


def test_admin_pause_stops_new_orders(monkeypatch):
    """'일시정지' 중에는 연속 실행 루프도 신규 주문을 내지 않는다."""
    _paused(monkeypatch, True)
    b = _Broker()
    _trader(b).step()
    assert b.orders == [], "일시정지 중인데 quant live가 주문을 냈다"


def test_exposure_scale_shrinks_the_order(monkeypatch):
    _paused(monkeypatch, False, 0.25)
    b = _Broker()
    _trader(b).step()
    assert b.orders, "주문이 아예 안 나갔다"
    _sym, w = b.orders[-1]
    assert abs(w) <= 0.26, f"총노출 배수가 적용되지 않았다: {w}"


def test_pause_does_not_disable_the_killswitch(monkeypatch):
    """일시정지는 '신규 매매 중단'이지 '위험 통제 해제'가 아니다.

    멈춰 둔 사이에 손실이 커졌는데 청산까지 막히면 정반대 결과가 된다.
    """
    b = _Broker(equity=10_000.0)
    t = _trader(b, daily_max_loss=0.05)
    t.step()                                   # 기준선(정상)
    _paused(monkeypatch, True)
    b.orders.clear()
    b._equity = 8_000.0
    t.step()
    assert b.orders == [("BTC/USDT", 0.0)], (
        f"일시정지가 킬스위치 청산까지 막았다: {b.orders}")
