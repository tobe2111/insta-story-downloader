"""사장님의 전역 스위치가 웹훅 주문 경로에도 걸리는가 (감사 82).

`trading_paused`는 설정 문서에 이렇게 적혀 있다:

    trading_paused : true면 **신규 매매 중단** — 보유 포지션은 유지

그런데 이 설정을 읽는 곳은 새벽 배치(`daily.py`)뿐이었다. 웹훅
주문 경로(`WebhookExecutor.execute`)는 읽지 않았다 — 즉 사장님이 대시보드에서
'일시정지'를 눌러 두어도 **트레이딩뷰 알림 하나가 실계좌에 주문을 낸다.**
`quant webhook --live`는 진짜 돈이 나가는 경로다.

오늘 반복해서 나온 계열이다: **안전장치가 주문을 내는 모든 경로를 덮지
않는다.** 스위치를 누른 사람은 멈췄다고 믿는다.

⚠️ 아직 남은 구멍: 일일 손실 킬스위치도 웹훅 경로에는 걸리지 않는다.
   그건 계정별 상태 파일에 묶여 있어 '웹훅이 어느 계좌를 쓰는가'를 정해야
   배선할 수 있다 — 임의로 정하지 않고 사장님 판단을 기다린다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.webhook import WebhookExecutor          # noqa: E402


class _Broker:
    def __init__(self):
        self.orders: list[tuple[str, float]] = []

    def get_cash(self):
        return 10_000.0

    def get_position(self, _s):
        class P:
            quantity = 0.0
            avg_price = 0.0
        return P()

    def equity(self, _prices=None):
        return 10_000.0

    def target_weight(self, symbol, weight, *_a, **_k):
        self.orders.append((symbol, float(weight)))
        return None


ALERT = {"symbol": "BTC/USDT", "action": "buy", "weight": 1.0, "price": 100.0}


@pytest.fixture
def run(monkeypatch):
    def _go(settings):
        broker = _Broker()
        monkeypatch.setattr("quant.utils.settings.load_settings",
                            lambda *_a, **_k: settings)
        ex = WebhookExecutor(broker, price_fn=lambda _s: 100.0)
        return broker, ex.execute(dict(ALERT))
    return _go


def _defaults(**over):
    from quant.utils.settings import DEFAULTS
    d = dict(DEFAULTS)
    d.update(over)
    return d


# ── 본체 ────────────────────────────────────────────────────────

def test_admin_pause_blocks_the_webhook_order(run):
    """'일시정지'를 눌러 두면 외부 신호로도 주문이 나가면 안 된다."""
    broker, res = run(_defaults(trading_paused=True))
    assert broker.orders == [], (
        "어드민 '일시정지' 중인데 웹훅 알림이 주문을 냈다 — 스위치를 누른 "
        "사람은 멈췄다고 믿는다")
    assert res.get("ok") is False and res.get("skipped") is True, res


def test_normal_settings_still_place_the_order(run):
    """반대로 평시까지 막으면 기능이 죽는다(과잉 차단 방지)."""
    broker, res = run(_defaults())
    assert broker.orders, res
    assert res.get("ok") is True


def test_exposure_scale_shrinks_the_webhook_weight(run):
    """총노출 배수도 같은 손잡이다 — 배치만 줄고 웹훅은 안 줄면 어긋난다."""
    broker, _res = run(_defaults(exposure_scale=0.25))
    assert broker.orders, "주문이 아예 안 나갔다"
    _sym, w = broker.orders[-1]
    assert w == pytest.approx(0.25), f"총노출 배수가 웹훅에 적용되지 않았다: {w}"


def test_missing_settings_do_not_break_the_webhook(monkeypatch):
    """설정을 못 읽으면 매매를 막지도, 무시하지도 않고 기본값으로 간다."""
    broker = _Broker()

    def boom(*_a, **_k):
        raise RuntimeError("설정 파일 손상")

    monkeypatch.setattr("quant.utils.settings.load_settings", boom)
    ex = WebhookExecutor(broker, price_fn=lambda _s: 100.0)
    res = ex.execute(dict(ALERT))
    assert res.get("ok") is True and broker.orders


def test_pause_is_checked_before_any_order_side_effect(run):
    """막기 전에 주문을 이미 내버리면 막은 게 아니다."""
    broker, _res = run(_defaults(trading_paused=True))
    assert broker.orders == []


# ── 장 시간 가드(같은 함수의 미실행 구간) ──────────────────────

def test_closed_market_blocks_the_webhook_order(monkeypatch):
    """닫힌 시장에는 웹훅으로도 주문을 내지 않는다."""
    import quant.live.market_hours as mh
    monkeypatch.setattr(mh, "is_market_open", lambda *_a, **_k: False)
    monkeypatch.setattr(mh, "market_status", lambda *_a, **_k: "장 마감")

    broker = _Broker()
    ex = WebhookExecutor(broker, market="kr_stock", price_fn=lambda _s: 100.0)
    res = ex.execute({"symbol": "005930", "action": "buy", "weight": 1.0,
                      "price": 70000.0})
    assert broker.orders == [], "닫힌 시장에 웹훅 주문이 나갔다"
    assert res.get("skipped") is True and "마감" in str(res.get("reason"))


def test_open_market_lets_the_webhook_order_through(monkeypatch):
    import quant.live.market_hours as mh
    monkeypatch.setattr(mh, "is_market_open", lambda *_a, **_k: True)
    monkeypatch.setattr(mh, "market_status", lambda *_a, **_k: "정규장")

    broker = _Broker()
    ex = WebhookExecutor(broker, market="kr_stock", price_fn=lambda _s: 100.0)
    ex.execute({"symbol": "005930", "action": "buy", "weight": 1.0,
                "price": 70000.0})
    assert broker.orders, "열린 시장인데 웹훅 주문이 막혔다"
