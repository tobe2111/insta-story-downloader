"""페이퍼 브로커 회계 정합성 테스트 — 평단가(숏/플립/커버) + 수수료 현금 가드.

자금은 보존되지만 avg_price가 숏/플립/부분커버에서 틀리면 equity()의 미표시
마크로 쓰여 자산을 왜곡한다. (순수 stdlib — pandas 불필요)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.broker import PaperBroker


def test_long_add_weighted_avg_unchanged_regression():
    """롱 추가는 가중평단, 부분청산은 평단 유지(기존 정상 동작 회귀)."""
    b = PaperBroker(cash=100_000, fee=0.0)
    b.market_order("X", "buy", 10, 100)
    assert b.get_position("X").avg_price == 100.0
    b.market_order("X", "buy", 5, 120)
    assert abs(b.get_position("X").avg_price - (100 * 10 + 120 * 5) / 15) < 1e-9
    b.market_order("X", "sell", 8, 110)                 # 부분 청산
    assert abs(b.get_position("X").avg_price - 1600 / 15) < 1e-9   # 평단 불변
    assert b.get_position("X").quantity == 7.0


# ⚠️ 아래 숏 장부 검사들은 **숏이 허용된 계좌**로 세운다(감사 260).
#    2026-08-16부터 기본 계좌는 보유를 넘어서는 매도를 막는다 — 증거금 없는
#    무제한 공매도가 열려 있었기 때문이다. 여기서 검증하는 것은 그 관문이
#    아니라 **숏이 열렸을 때의 장부 계산**(진입가·플립·부분커버)이므로,
#    관문을 통과한 계좌로 같은 계약을 그대로 확인한다.
_SHORT_OK = dict(short_margin=0.5)


def test_fresh_short_records_entry_price():
    """관망 상태에서 매도 → 숏 진입가가 체결가로 기록된다(구버전은 0)."""
    b = PaperBroker(cash=100_000, fee=0.0, **_SHORT_OK)
    b.market_order("X", "sell", 5, 100)
    pos = b.get_position("X")
    assert pos.quantity == -5.0
    assert pos.avg_price == 100.0            # 구버전은 0.0 → equity 왜곡


def test_flip_long_to_short_resets_avg():
    """롱→숏 전환 시 평단이 새 숏 진입가로 리셋된다(구버전은 옛 롱 평단 유지)."""
    b = PaperBroker(cash=100_000, fee=0.0, **_SHORT_OK)
    b.market_order("X", "buy", 10, 100)
    b.market_order("X", "sell", 15, 110)     # 10 롱 청산 + 5 숏 진입
    pos = b.get_position("X")
    assert pos.quantity == -5.0
    assert pos.avg_price == 110.0            # 구버전은 100.0


def test_partial_cover_keeps_short_avg():
    """숏 부분 커버 시 평단이 유지된다(구버전은 (-500+330)/-2=85 같은 무의미값)."""
    b = PaperBroker(cash=100_000, fee=0.0, **_SHORT_OK)
    b.market_order("X", "sell", 5, 100)
    b.market_order("X", "buy", 3, 110)       # 부분 커버 → -2 남음
    pos = b.get_position("X")
    assert pos.quantity == -2.0
    assert pos.avg_price == 100.0            # 구버전은 85.0


def test_full_close_snaps_to_zero():
    """전량 청산 시 수량·평단이 0으로(부동소수 먼지 제거 포함)."""
    b = PaperBroker(cash=100_000, fee=0.0)
    b.market_order("X", "buy", 0.1, 100)
    b.market_order("X", "sell", 0.1, 100)    # 0.1-0.1이 1e-17로 남을 수 있음
    pos = b.get_position("X")
    assert pos.quantity == 0.0               # 먼지 스냅
    assert pos.avg_price == 0.0


def test_equity_values_short_liability():
    """미표시 숏 포지션이 진입가로 평가되어 부채가 사라지지 않는다."""
    b = PaperBroker(cash=10_000, fee=0.0)
    b.market_order("X", "sell", 5, 100)      # 숏 → 현금 +500, 부채 -5*마크
    # marks 비어 있음 → 진입가(100)로 마크 → equity = 10500 + (-5*100) = 10000
    assert abs(b.equity({}) - 10_000.0) < 1e-9   # 구버전: 평단 0 → 10500(부채 증발)


def test_target_weight_full_buy_no_negative_cash():
    """풀 비중 매수가 수수료까지 예산에 넣어 현금을 음수로 만들지 않는다."""
    b = PaperBroker(cash=10_000, fee=0.001)
    order = b.target_weight("X", 1.0, 100.0, b.get_cash())   # 전액 매수
    assert order is not None and order.side == "buy"
    assert b.get_cash() >= -1e-6             # 음수 현금 아님 (구버전 ≈ -10)
    assert b.get_position("X").quantity < 10_000 / 100       # 수수료만큼 덜 삼


def test_target_weight_short_not_fee_shrunk():
    """숏 목표는 (1+fee) 버퍼로 축소하지 않는다 — 숏은 현금이 부족해질 방향이
    아니므로 버퍼가 목표 비중만 왜곡한다(과소 진입 버그 수정)."""
    b = PaperBroker(cash=10_000, fee=0.001, **_SHORT_OK)
    order = b.target_weight("X", -0.5, 100.0, 10_000.0)
    assert order is not None and order.side == "sell"
    # 정확히 -0.5 * 10000 / 100 = 50주 (구버전: 50/1.001 ≈ 49.95주)
    assert abs(order.quantity - 50.0) < 1e-9


def test_target_weight_reduce_not_fee_inflated():
    """포지션 축소(매도)는 (1+fee) 버퍼 없이 정확한 수량만 판다(과다 축소 버그 수정)."""
    b = PaperBroker(cash=100_000, fee=0.001)
    b.market_order("Y", "buy", 100, 100.0)               # 100주 보유
    order = b.target_weight("Y", 0.05, 100.0, 100_000.0)  # 목표 50주 → 50주 매도
    assert order is not None and order.side == "sell"
    # 정확히 100 - 50 = 50주 매도 (구버전: 100 - 50/1.001 ≈ 50.05주 과다 매도)
    assert abs(order.quantity - 50.0) < 1e-9


def test_order_log_capped():
    """order_log가 무한 성장하지 않는다(장기 실행 메모리 누수 방지)."""
    from quant.broker.paper import _ORDER_LOG_CAP
    b = PaperBroker(cash=10**9, fee=0.0)
    for _ in range(_ORDER_LOG_CAP + 50):
        b.market_order("X", "buy", 1, 1)
    assert len(b.order_log) <= _ORDER_LOG_CAP
