"""선물 트랙 — 숏이 정말 숏인가, 그리고 배율이 정말 없는가 (감사 304).

사장님 지시(2026-08-22): *"선물 거래 페이지를 별도로 만들어 진행하자.
매수/매도 포지션 모두 가지면 머신러닝에 도움되지 않나?"*

맞는 직관이었다. 머신러닝 챔피언이 내놓는 것은 **상승 확률**인데, 지금까지
시스템은 그것을 "산다 / 안 산다" 둘로만 썼다. 확률 0.20인 봉 — 모델이
"내린다"고 꽤 확신하는 봉 — 이 확률 0.50인 봉(모른다)과 **같은 취급**을
받고 버려졌다.

실측(2026-08-21 스냅샷 · BTC/USDT 800봉 · logreg 챔피언):

    숏 금지:  롱 216봉 · 관망 584봉 · 숏   0봉
    숏 허용:  롱 216봉 · 관망 402봉 · 숏 182봉

롱 판단은 하나도 안 바뀌고(216 그대로), 관망의 31%가 숏이 됐다.

■ 이 파일이 지키는 것

이 트랙은 **돈의 성격이 다른 트랙**이다. 그래서 검사도 그 지점에 건다.

  · 숏이 정말 숏인가 — 가격이 내리면 벌고 오르면 잃는가
  · 배율이 정말 없는가 — 숏을 열면 현금이 늘어나므로, 롱 트랙의 현금
    한도만으로는 노출이 무한히 커진다
  · 자금조달을 정말 무는가 — 안 물면 이 트랙만 유리한 자로 재게 된다
  · 숏에 바닥이 있는가 — 롱은 −100%에서 멈추지만 숏은 안 멈춘다
  · 못 하는 종목에 하는 척하지 않는가
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.futures_challenger import (          # noqa: E402
    FUNDING_RATE_PER_8H, MAINTENANCE_MARGIN_RATE, MAX_GROSS_EXPOSURE,
    SHORT_STOP_PCT, apply_funding, can_short, execute_targets, funding_cost,
    gross_exposure, leverage_for, liquidation_check, load_state,
    margin_ratio, mark_equity, stopped_out,
)

FEE = 0.0015                    # 편도 비용률(코인) — 실전 모델과 같은 값
ONE = ["BTC/USDT"]


def _fresh(cash=10_000.0):
    return {"cash": cash, "start_cash": cash, "positions": {},
            "avg_cost": {}, "cost_paid": 0.0, "funding_paid": 0.0}


# ── ① 숏이 정말 숏인가 ─────────────────────────────────────────

def test_a_short_makes_money_when_the_price_falls():
    """**이 트랙의 존재 이유.** 내릴 때 버는 자리가 정말 있는가."""
    st = _fresh()
    execute_targets(st, {"BTC/USDT": -1.0}, {"BTC/USDT": 100.0},
                    10_000.0, FEE, ONE)
    assert st["positions"]["BTC/USDT"] < 0, (
        f"숏을 냈는데 수량이 음수가 아니다: {st['positions']}")
    down = mark_equity(st, {"BTC/USDT": 80.0})
    assert down > 10_000.0 * 0.99, (
        f"20% 내렸는데 숏이 못 벌었다 — 자산 {down:,.2f}")


def test_a_short_loses_money_when_the_price_rises():
    """대조군 — 오르면 잃어야 한다.

    없으면 "숏이 언제나 번다"도 위 검사를 통과하고, 그건 계산이 아니라
    소원이다.
    """
    st = _fresh()
    execute_targets(st, {"BTC/USDT": -1.0}, {"BTC/USDT": 100.0},
                    10_000.0, FEE, ONE)
    up = mark_equity(st, {"BTC/USDT": 120.0})
    assert up < 10_000.0, f"20% 올랐는데 숏이 안 잃었다 — 자산 {up:,.2f}"


def test_a_long_still_behaves_like_a_long():
    """숏을 붙이면서 롱이 망가지지 않았는가."""
    st = _fresh()
    execute_targets(st, {"BTC/USDT": 1.0}, {"BTC/USDT": 100.0},
                    10_000.0, FEE, ONE)
    assert st["positions"]["BTC/USDT"] > 0
    assert mark_equity(st, {"BTC/USDT": 120.0}) > 10_000.0
    assert mark_equity(st, {"BTC/USDT": 80.0}) < 10_000.0


def test_closing_a_short_reports_the_profit_after_cost():
    st = _fresh()
    execute_targets(st, {"BTC/USDT": -1.0}, {"BTC/USDT": 100.0},
                    10_000.0, FEE, ONE)
    tr = execute_targets(st, {"BTC/USDT": 0.0}, {"BTC/USDT": 80.0},
                         10_000.0, FEE, ONE)
    assert tr and tr[0].get("realized_pnl") is not None, tr
    assert tr[0]["realized_pnl"] > 0, (
        f"20% 내린 뒤 숏을 덮었는데 손실로 적혔다: {tr[0]}")


def test_closing_a_short_at_a_higher_price_is_a_loss():
    """대조군 — 숏 손익의 부호가 롱과 반대인지 실제로 확인한다."""
    st = _fresh()
    execute_targets(st, {"BTC/USDT": -1.0}, {"BTC/USDT": 100.0},
                    10_000.0, FEE, ONE)
    tr = execute_targets(st, {"BTC/USDT": 0.0}, {"BTC/USDT": 120.0},
                         10_000.0, FEE, ONE)
    assert tr[0]["realized_pnl"] < 0, (
        f"20% 오른 뒤 숏을 덮었는데 이익으로 적혔다 — 부호가 뒤집혔다: {tr[0]}")


# ── ② 배율이 정말 없는가 ───────────────────────────────────────

# ⚠️ 한도를 시험하려면 **한도가 실제로 무는 상황**을 만들어야 한다.
#    처음에 쓴 검사들은 슬라이스가 자산/종목수라 노출이 애초에 1배를 못
#    넘는 상황을 재고 있었다 — 한도를 통째로 걷어내도 그대로 통과했다.
#    변이 시험이 그것을 알려 줬다(감사 304). 한도가 안 무는 자리에서
#    한도를 재는 검사는 장식이다.
#
#    한도가 무는 진짜 상황은 **손실이 난 뒤**다. 숏을 열어 둔 채 가격이
#    오르면 자산은 줄고 노출은 늘어난다 — 그때가 배율이 저절로 생기는
#    순간이고, 여기서 브레이크가 밟혀야 한다.
def _short_then_adverse_move(uni, entry=100.0, later=115.0):
    """숏을 열어 두고 가격이 올라간 상태의 장부를 만든다.

    ⚠️ 예전에는 50% 상승을 썼다. 배율이 1배일 때는 그래도 계좌가 살아
       있었지만, 3배에서는 **청산선을 지나쳐** 계좌가 통째로 날아간다
       (감사 308). 한도 검사를 하려는데 계좌가 없어지면 잴 것이 없다.
       그래서 청산 전이면서 노출이 자산을 크게 넘는 자리(15%)를 쓴다:
       실측으로 자산 5,455 · 노출 34,500 · 증거금률 0.158(유지선 0.05).
    """
    st = _fresh()
    px = {s: entry for s in uni}
    execute_targets(st, {s: -1.0 for s in uni}, px, 10_000.0, FEE, uni)
    px2 = {s: later for s in uni}
    return st, px2, mark_equity(st, px2)


def test_a_short_cannot_grow_the_book_without_limit():
    """**가장 중요한 안전장치.** 숏은 열면 현금이 늘어난다.

    롱 트랙의 한도는 "현금이 모자라면 못 산다"였다. 숏에는 그 브레이크가
    아예 안 걸린다 — 팔수록 현금이 늘기 때문이다. 총 노출로 재야 한다.

    실측: 진입 시 노출 10,000 / 자산 9,985(1.0배). 가격이 50% 오르면
    자산 4,985 · 노출 15,000 — **저절로 3배**가 된다. 한도가 없으면 그
    상태에서 숏을 더 얹는다.
    """
    uni = ["BTC/USDT", "ETH/USDT"]
    st, px, eq = _short_then_adverse_move(uni)
    assert gross_exposure(st, px) > eq * MAX_GROSS_EXPOSURE, (
        "전제가 안 만들어졌다 — 손실 뒤에 노출이 상한을 넘어야 한다")
    execute_targets(st, {s: -1.0 for s in uni}, px, eq, FEE, uni)
    gross = gross_exposure(st, px)
    assert gross <= eq * MAX_GROSS_EXPOSURE + 1.0, (
        f"총 노출 {gross:,.2f}가 자산 {eq:,.2f}의 {MAX_GROSS_EXPOSURE}배를 "
        "넘은 채로 남았다 — 상한 위로 배율이 더 걸렸다")


def test_long_and_short_together_do_not_cancel_the_limit():
    """롱과 숏은 서로를 상쇄하지 않는다 — 합쳐서 두 배로 걸려 있는 것이다.

    순노출(롱−숏)로 재면 0으로 보인다. 그건 위험이 없다는 뜻이 아니다.
    """
    uni = ["BTC/USDT", "ETH/USDT"]
    st = _fresh()
    px = {s: 100.0 for s in uni}
    execute_targets(st, {"BTC/USDT": 1.0, "ETH/USDT": -1.0}, px,
                    10_000.0, FEE, uni)
    # 롱 +5,000 · 숏 −5,000 → 순노출은 0이지만 총 노출은 10,000이다.
    net = sum(q * px[k] for k, q in st["positions"].items())
    assert abs(net) < 500.0, f"전제가 안 만들어졌다 — 순노출 {net:,.2f}"
    assert gross_exposure(st, px) > 9_000.0, (
        f"롱과 숏이 서로를 상쇄해 노출이 0으로 보인다: "
        f"{gross_exposure(st, px):,.2f} (순노출 {net:,.2f})")


def test_reducing_risk_is_never_blocked_and_never_flips_the_side():
    """대조군 — 한도가 **줄이는 거래**까지 물면 스톱이 동작 못 한다.

    손실이 난 뒤에는 남은 한도가 음수다. 그때 줄이는 주문에까지 한도를
    적용하면 목표가 **부호째 뒤집힌다** — 숏을 덮으려던 주문이 롱을 여는
    주문이 된다. 위험을 줄이려던 동작이 정반대 위험을 만드는 것이다.
    """
    uni = ["BTC/USDT", "ETH/USDT"]
    st, px, eq = _short_then_adverse_move(uni)
    before = dict(st["positions"])
    execute_targets(st, {s: -1.0 for s in uni}, px, eq, FEE, uni)
    for sym in uni:
        now = st["positions"].get(sym, 0.0)
        assert now < 0, (
            f"{sym}: 숏을 줄이려던 주문이 방향을 뒤집었다 "
            f"({before[sym]:.3f} → {now:.3f})")
        assert abs(now) < abs(before[sym]), (
            f"{sym}: 위험을 줄이는 주문이 한도에 막혔다 "
            f"({before[sym]:.3f} → {now:.3f})")


def test_a_new_position_cannot_be_opened_while_already_over_the_limit():
    """이미 한도를 넘긴 상태에서 **새 종목**을 열려 하면 막혀야 한다.

    ⚠️ 이 자리를 찾는 데 변이 시험이 필요했다(감사 304). 앞의 검사들은
       전부 '이미 들고 있는 것을 줄이는' 길만 지나갔고, 그 길에서는 한도
       계산이 아예 실행되지 않는다 — 한도를 통째로 걷어내도 초록이었다.

    그리고 이 검사를 쓰다가 **진짜 결함**이 나왔다. 남은 한도가 음수일 때
    (손실로 이미 넘긴 상태) 목표를 한도로 자르면 부호가 뒤집혀, 숏을
    열려던 주문이 **롱을 여는 주문**이 됐다. 브레이크가 정반대 위험을
    만드는 것이다. 0에서 바닥을 치도록 고쳤다.
    """
    uni = ["BTC/USDT", "ETH/USDT"]
    st = _fresh()
    # BTC만 숏 → 그 뒤 값이 오르면 노출이 상한을 넘는다.
    execute_targets(st, {"BTC/USDT": -1.0, "ETH/USDT": 0.0},
                    {"BTC/USDT": 100.0, "ETH/USDT": 50.0},
                    10_000.0, FEE, uni)
    px = {"BTC/USDT": 140.0, "ETH/USDT": 50.0}
    eq = mark_equity(st, px)
    assert gross_exposure(st, px) > eq * MAX_GROSS_EXPOSURE, (
        f"전제가 안 만들어졌다 — 노출 {gross_exposure(st, px):,.0f} vs "
        f"상한 {eq * MAX_GROSS_EXPOSURE:,.0f}")
    assert "ETH/USDT" not in st["positions"]
    execute_targets(st, {"BTC/USDT": -1.0, "ETH/USDT": -1.0}, px, eq,
                    FEE, uni)
    eth = st["positions"].get("ETH/USDT", 0.0)
    assert eth <= 0, (
        f"숏을 열려던 주문이 롱이 됐다 — 한도가 부호를 뒤집었다: {eth:.4f}")
    gross = gross_exposure(st, px)
    assert gross <= eq * MAX_GROSS_EXPOSURE + 1.0, (
        f"한도를 넘긴 상태에서 노출을 더 키웠다: {gross:,.2f} > 자산 {eq:,.2f}")


def test_an_oversized_signal_cannot_buy_leverage():
    """신호가 1을 넘어오면 한도가 **실제로 문다.**

    ⚠️ 이 검사를 찾는 데 손 추적이 필요했다(감사 304). 지금의 크기 계산은
       종목당 자산/종목수를 최대로 태우므로, 신호가 [-1, 1] 안에 있는 한
       총 노출은 자연히 자산을 못 넘는다 — 즉 **한도가 닿지 않는 자리**에
       있었고, 통째로 걷어내도 아무 검사가 안 깨졌다.

       그래서 한도를 지우는 대신, 한도가 정말 필요한 길을 검사가 지나가게
       했다. 이 체결기는 공개 함수이고 신호를 스스로 자르지 않는다 —
       크기 계산이 바뀌거나 부르는 쪽이 큰 신호를 넘기는 날, 여기가
       유일한 브레이크다. 그 날을 위해 두는 안전장치이므로, 그 날을
       검사가 미리 살아 본다.
    """
    uni = ["BTC/USDT", "ETH/USDT"]
    st = _fresh()
    px = {s: 100.0 for s in uni}
    # 신호 3.0 — 크기 계산이 바뀌면 이런 값이 들어올 수 있다. 한도가
    # 없으면 자산의 세 배가 걸린다.
    execute_targets(st, {s: -9.0 for s in uni}, px, 10_000.0, FEE, uni)
    gross = gross_exposure(st, px)
    eq = mark_equity(st, px)
    assert gross <= 10_000.0 * MAX_GROSS_EXPOSURE + 1.0, (
        f"신호가 1을 넘자 총 노출 {gross:,.2f}가 상한(자산 {eq:,.2f}의 "
        f"{MAX_GROSS_EXPOSURE}배)을 넘었다 — 상한 위로 배율이 더 걸렸다")
    for sym in uni:
        assert st["positions"].get(sym, 0.0) <= 0, (
            f"{sym}: 한도가 숏을 롱으로 뒤집었다")


def test_a_normal_signal_is_not_clipped_by_the_limit():
    """대조군 — 한도가 **평상시 주문까지** 깎으면 안 된다.

    없으면 "언제나 0으로 자른다"도 위 검사를 통과하고, 그러면 이 트랙은
    아무것도 사지 못한다.
    """
    uni = ["BTC/USDT", "ETH/USDT"]
    st = _fresh()
    px = {s: 100.0 for s in uni}
    execute_targets(st, {s: -1.0 for s in uni}, px, 10_000.0, FEE, uni)
    gross = gross_exposure(st, px)
    assert gross > 10_000.0 * MAX_GROSS_EXPOSURE * 0.9, (
        f"신호가 정상 범위인데 상한이 주문을 깎았다 — 총 노출 {gross:,.2f}")


def test_room_freed_earlier_in_the_round_is_usable():
    """대조군 — 앞 종목을 줄여 생긴 자리를 뒤 종목이 쓸 수 있어야 한다.

    남은 한도를 회차 시작에 한 번만 계산해 들고 다니면, 앞에서 줄인 만큼이
    반영되지 않아 뒤 종목이 이유 없이 막힌다(감사 304에서 실제로 그랬다).
    """
    uni = ["BTC/USDT", "ETH/USDT"]
    st = _fresh()
    # BTC만 숏 → 값이 올라 노출이 상한을 넘는다.
    execute_targets(st, {"BTC/USDT": -1.0, "ETH/USDT": 0.0},
                    {"BTC/USDT": 100.0, "ETH/USDT": 50.0},
                    10_000.0, FEE, uni)
    px = {"BTC/USDT": 120.0, "ETH/USDT": 50.0}
    eq = mark_equity(st, px)
    # 이번 회차에 BTC는 크게 줄고(목표 = 자산/2), 그만큼 자리가 생긴다.
    execute_targets(st, {"BTC/USDT": -1.0, "ETH/USDT": -1.0}, px, eq,
                    FEE, uni)
    assert st["positions"].get("ETH/USDT", 0.0) < 0, (
        "앞 종목을 줄여 자리가 생겼는데 뒤 종목이 못 들어갔다 — 남은 한도를 "
        f"묵은 값으로 재고 있다: {st['positions']}")


def test_a_full_close_is_never_blocked():
    """전량 청산은 언제나 통과해야 한다 — 스톱이 이 길을 쓴다."""
    uni = ["BTC/USDT", "ETH/USDT"]
    st, px, eq = _short_then_adverse_move(uni)
    execute_targets(st, {s: 0.0 for s in uni}, px, eq, FEE, uni)
    assert not st["positions"], (
        f"전량 청산이 막혔다 — 남은 포지션 {st['positions']}")


# ── ③ 자금조달 — 안 물면 이 트랙만 유리한 자로 잰다 ────────────

def test_a_long_pays_funding_and_a_short_receives_it():
    st = _fresh()
    execute_targets(st, {"BTC/USDT": 1.0}, {"BTC/USDT": 100.0},
                    10_000.0, FEE, ONE)
    paid_long = funding_cost(st, {"BTC/USDT": 100.0}, 8.0)
    st2 = _fresh()
    execute_targets(st2, {"BTC/USDT": -1.0}, {"BTC/USDT": 100.0},
                    10_000.0, FEE, ONE)
    paid_short = funding_cost(st2, {"BTC/USDT": 100.0}, 8.0)
    assert paid_long > 0, f"롱이 자금조달을 안 냈다: {paid_long}"
    assert paid_short < 0, (
        f"숏이 자금조달을 받지 않았다 — 부호가 같으면 숏 성적이 조용히 "
        f"부풀려진다: {paid_short}")


def test_funding_scales_with_time_not_with_rounds():
    """8시간에 한 번 정산이다 — 회차를 많이 돌린다고 더 물지 않는다."""
    st = _fresh()
    execute_targets(st, {"BTC/USDT": 1.0}, {"BTC/USDT": 100.0},
                    10_000.0, FEE, ONE)
    px = {"BTC/USDT": 100.0}
    assert funding_cost(st, px, 16.0) == pytest.approx(
        2 * funding_cost(st, px, 8.0), rel=1e-9)
    assert funding_cost(st, px, 0.0) == 0.0


def test_funding_actually_leaves_the_account():
    """부품을 만들어 놓고 안 붙이면 없는 것과 같다."""
    st = _fresh()
    execute_targets(st, {"BTC/USDT": 1.0}, {"BTC/USDT": 100.0},
                    10_000.0, FEE, ONE)
    cash_before = st["cash"]
    paid = apply_funding(st, {"BTC/USDT": 100.0}, 8.0)
    assert st["cash"] == pytest.approx(cash_before - paid)
    assert st["funding_paid"] == pytest.approx(paid)
    assert paid > 0


def test_an_empty_book_pays_no_funding():
    """대조군 — 포지션이 없으면 낼 것도 없다."""
    assert funding_cost(_fresh(), {"BTC/USDT": 100.0}, 8.0) == 0.0


# ── ④ 숏에는 바닥이 있어야 한다 ────────────────────────────────

def test_a_runaway_short_hits_the_stop():
    st = _fresh()
    execute_targets(st, {"BTC/USDT": -1.0}, {"BTC/USDT": 100.0},
                    10_000.0, FEE, ONE)
    hit = 100.0 * (1.0 + SHORT_STOP_PCT + 0.01)
    assert stopped_out(st, {"BTC/USDT": hit}) == ["BTC/USDT"], (
        "숏이 한도를 넘게 밀렸는데 스톱이 안 걸렸다 — 숏에는 파산이라는 "
        "자연 바닥이 없다")


def test_a_short_within_the_limit_is_left_alone():
    """대조군 — 조금 밀렸다고 털면 그건 스톱이 아니라 잡음이다."""
    st = _fresh()
    execute_targets(st, {"BTC/USDT": -1.0}, {"BTC/USDT": 100.0},
                    10_000.0, FEE, ONE)
    ok = 100.0 * (1.0 + SHORT_STOP_PCT - 0.05)
    assert stopped_out(st, {"BTC/USDT": ok}) == []


def test_a_long_is_not_stopped_by_the_short_stop():
    """롱에는 파산이라는 자연 바닥이 있다 — 이 스톱의 대상이 아니다.

    ⚠️ **오르는 롱**으로 잰다. 처음엔 내린 롱(−90%)으로 쟀는데, 그러면
       스톱이 롱까지 보게 만들어도 조건식이 안 걸려서 통과했다 — 변이
       시험이 알려 줬다(감사 304). 이 스톱의 조건은 "진입가보다 25% 위"
       이므로, 그 조건에 실제로 닿는 것은 **오른** 롱이다. 크게 번 롱이
       이유 없이 청산되는 것이 여기서 막아야 할 사고다.
    """
    st = _fresh()
    execute_targets(st, {"BTC/USDT": 1.0}, {"BTC/USDT": 100.0},
                    10_000.0, FEE, ONE)
    risen = 100.0 * (1.0 + SHORT_STOP_PCT + 0.20)      # 45% 상승 — 큰 이익
    assert stopped_out(st, {"BTC/USDT": risen}) == [], (
        "45% 오른 롱이 숏 스톱에 걸려 청산됐다 — 이익 난 보유를 털어 버린다")
    assert stopped_out(st, {"BTC/USDT": 10.0}) == [], (
        "90% 내린 롱이 숏 스톱에 걸렸다")


# ── ⑤ 못 하는 것을 하는 척하지 않는다 ──────────────────────────

def test_only_a_model_champion_may_short():
    assert can_short({"strategy": "ml"}) is True
    for rule in ("ma_cross", "macd", "bollinger", "buy_hold", "momentum"):
        assert can_short({"strategy": rule}) is False, (
            f"{rule}에 숏을 허용했다 — 규칙 전략은 음수 신호를 내지 않는다. "
            "억지로 만들면 '같은 규칙을 양방향으로'라는 전제가 깨진다")
    assert can_short(None) is False
    assert can_short({}) is False


def test_the_rule_strategies_really_do_not_short():
    """전제 고정 — **실측으로** 확인한다.

    can_short의 판단은 "규칙 전략은 음수를 안 낸다"는 사실 위에 서 있다.
    그 사실이 바뀌면(어떤 전략이 숏 신호를 내게 되면) 이 트랙의 설계가
    통째로 달라진다. 그래서 믿지 않고 잰다.
    """
    import glob

    import numpy as np
    import pandas as pd
    from quant.strategies import _REGISTRY
    snaps = sorted(glob.glob(str(ROOT / "state" / "snapshots" / "*" /
                                 "crypto_ETH_USDT.csv.gz")))
    if not snaps:
        pytest.skip("스냅샷 없음 — 잴 것이 없다")
    df = pd.read_csv(snaps[-1])
    for name, params in [("ma_cross", dict(fast=20, slow=60)), ("macd", {}),
                         ("bollinger", {}), ("momentum", {})]:
        s = np.asarray(_REGISTRY[name](**params).generate_signals(df),
                       dtype=float)
        s = s[~np.isnan(s)]
        if not len(s):
            continue
        assert s.min() >= 0.0, (
            f"{name}이 음수 신호를 낸다({s.min():+.3f}) — 이 트랙의 전제가 "
            "바뀌었다. can_short를 다시 볼 것")


def test_the_model_champion_really_does_short():
    """대조군 — 머신러닝 쪽은 **정말로** 숏을 낸다.

    이게 없으면 "아무도 숏을 못 한다"도 위 검사들을 통과하고, 그러면 이
    트랙은 롱 전용 트랙을 하나 더 만든 것에 지나지 않는다.
    """
    import glob

    import numpy as np
    import pandas as pd
    from quant.strategies.ml import MLStrategy
    snaps = sorted(glob.glob(str(ROOT / "state" / "snapshots" / "*" /
                                 "crypto_BTC_USDT.csv.gz")))
    if not snaps:
        pytest.skip("스냅샷 없음 — 잴 것이 없다")
    df = pd.read_csv(snaps[-1])
    base = dict(model="logreg", threshold=0.55, train_window=250,
                retrain_every=20)
    off = np.asarray(MLStrategy(**base).generate_signals(df), dtype=float)
    on = np.asarray(MLStrategy(**base, allow_short=True).generate_signals(df),
                    dtype=float)
    off, on = off[~np.isnan(off)], on[~np.isnan(on)]
    assert (on < 0).sum() > 0, (
        "숏을 켰는데 숏 신호가 하나도 안 나온다 — 이 트랙은 롱 전용 트랙을 "
        "하나 더 만든 것에 불과하다")
    # 롱 판단은 **한 개도 바뀌면 안 된다.** 바뀌면 이 트랙은 '버려지던
    # 절반을 쓰는 실험'이 아니라 '다른 전략'이 된다.
    assert (off > 0).sum() == (on > 0).sum(), (
        f"숏을 켰더니 롱 판단까지 바뀌었다 — {(off > 0).sum()} → "
        f"{(on > 0).sum()}. 그러면 비교가 방향 비교가 아니다")


# ── ⑥ 장부가 따로 서 있는가 ────────────────────────────────────

def _offline_round(monkeypatch, tmp_path, closes, signal, *, now=None):
    """시세를 넣어 주고 회차를 **진짜로** 한 번 돌린다.

    ⚠️ 이 컨테이너는 거래소로 못 나간다(그리고 나가서도 안 된다 — 검사가
       바깥 사정에 흔들리면 그건 검사가 아니다). 그래서 시세를 받아 오는
       입구와 전략만 갈아 끼우고, **나머지 길은 실제 코드를 그대로**
       지나가게 한다. 부품만 따로 부르면 "리포트에 안 실린다"는 결함이
       그대로 살아남는다(감사 306에서 실제로 그랬다).
    """
    import pandas as pd
    import quant.live.futures_challenger as F

    idx = pd.date_range("2026-01-01", periods=len(closes), freq="h")
    df = pd.DataFrame({"open": closes, "high": closes, "low": closes,
                       "close": closes, "volume": [1.0] * len(closes)},
                      index=idx)

    class _Strat:
        def generate_signals(self, frame):
            return pd.Series([signal] * len(frame), index=frame.index)

    monkeypatch.setattr(F, "_fetch_real", lambda sym, timeframe=None: df)
    monkeypatch.setattr(F, "build_two_sided",
                        lambda sym, state_dir: (_Strat(), True))
    monkeypatch.setattr(F, "MIN_BARS", 5)
    # ⚠️ 배율 상한은 2026-08-25부터 **이 트랙의 기록이** 정한다(감사 314).
    #    빈 장부로 시작하는 검사는 당연히 1배를 받고, 1배에서는 값이 30%
    #    빠져도 청산되지 않는다 — 그건 옳은 동작이지만, 그러면 청산·배율
    #    경로를 **아무도 안 지나간다.** 여기서는 "배율을 이미 번 트랙"을
    #    전제로 두어 그 경로가 실제로 돌게 한다. 배율을 어떻게 버는지는
    #    tests/test_the_leverage_is_earned_not_chosen.py가 따로 지킨다.
    monkeypatch.setattr(
        "quant.live.leverage.adaptive_max_leverage",
        lambda curve, hard_cap, **k: {"max_leverage": float(hard_cap),
                                      "proven": True,
                                      "why": "검사용 — 배율을 번 트랙 전제"})
    return F.run_futures_round(now or "2026-06-01T00:00:00+09:00",
                               state_dir=str(tmp_path),
                               universe=["BTC/USDT"], per_side=0.0015)


def test_a_round_remembers_the_prices_it_saw(monkeypatch, tmp_path):
    """회차가 **마지막 시세를 장부에 남긴다.**

    안 남기면 종목별 손익을 영영 못 그린다 — 지금 값을 모르니까. 계산이
    아무리 맞아도 재료가 없으면 화면은 빈칸이다(감사 306).
    """
    closes = [100.0] * 40
    _offline_round(monkeypatch, tmp_path, closes, -1.0)
    st = load_state(str(tmp_path))
    assert st.get("last_prices", {}).get("BTC/USDT") == pytest.approx(100.0), (
        f"회차가 돌았는데 장부에 시세가 안 남았다: {st.get('last_prices')}")


def test_a_round_actually_opens_the_short(monkeypatch, tmp_path):
    """대조군 — 회차가 정말 포지션을 연다.

    없으면 "아무것도 안 하는 회차"도 위 검사를 통과한다.
    """
    _offline_round(monkeypatch, tmp_path, [100.0] * 40, -1.0)
    st = load_state(str(tmp_path))
    assert st["positions"].get("BTC/USDT", 0.0) < 0, (
        f"숏 신호였는데 포지션이 안 생겼다: {st['positions']}")


def test_a_stale_price_is_not_erased_when_a_symbol_is_skipped(monkeypatch,
                                                              tmp_path):
    """시세를 못 받은 종목의 **이전 값을 지우지 않는다.**

    지우면 화면이 "모른다"로 바뀌는데, 실제로는 조금 낡았을 뿐이다.
    """
    import quant.live.futures_challenger as F
    _offline_round(monkeypatch, tmp_path, [100.0] * 40, -1.0)
    monkeypatch.setattr(F, "_fetch_real", lambda sym, timeframe=None: None)
    F.run_futures_round("2026-06-01T01:00:00+09:00", state_dir=str(tmp_path),
                        universe=["BTC/USDT"], per_side=0.0015)
    st = load_state(str(tmp_path))
    assert st.get("last_prices", {}).get("BTC/USDT") == pytest.approx(100.0), (
        "시세를 못 받자 이전 값까지 지웠다 — 낡은 것과 모르는 것은 다르다")


def test_the_futures_report_draws_on_those_prices(tmp_path):
    """**배선** — 남긴 시세로 종목별 손익이 실제로 나온다.

    부품(계산)과 재료(시세)가 다 있어도 리포트가 안 부르면 없는 것과 같다.
    """
    from quant.live.futures_challenger import public_report
    st = load_state(str(tmp_path))
    st["positions"] = {"BTC/USDT": -1.0}
    st["last_prices"] = {"BTC/USDT": 80.0}
    st["rounds"] = [{"at": "2026-08-22T00:00:00+09:00",
                     "trades": [{"symbol": "BTC/USDT", "notional": -100.0,
                                 "price": 100.0}]}]
    rows = public_report(st).get("holdings") or []
    assert rows, "시세를 남겼는데 종목별 줄이 안 나온다"
    assert rows[0]["last_price"] == pytest.approx(80.0), rows
    assert rows[0]["pnl"] == pytest.approx(20.0), (
        f"숏이 20% 내렸는데 손익이 이상하다: {rows[0]}")


def test_the_futures_ledger_is_its_own(tmp_path):
    """본 계좌·장중 트랙과 한 글자도 안 섞인다."""
    st = load_state(str(tmp_path))
    assert st["start_cash"] == 10_000.0
    assert st["positions"] == {} and st["cash"] == 10_000.0
    assert st.get("funding_paid") == 0.0
    from quant.live.futures_challenger import _path
    assert "futures" in _path(str(tmp_path))


# ── ⑦ 화면이 그 말을 실제로 하는가 (진짜 브라우저) ─────────────

_SAMPLE = {
    "kind": "futures-experiment", "updated": "2026-08-22T21:05:00+09:00",
    "start_cash": 10000.0, "equity": 10241.5, "return_pct": 2.415,
    "cost_paid": 31.2, "funding_paid": -4.25, "funding_rate_per_8h": 0.0001,
    "max_gross_exposure": 1.0, "short_stop_pct": 0.25,
    "gross_exposure": 9800.0, "long_positions": 2, "short_positions": 2,
    "long_only_symbols": ["ETH/USDT"], "stopped": ["XRP/USDT"], "skipped": [],
    "rounds": 37, "observed_gap_minutes": 11.4,
    "curve": [{"at": "a", "equity": 10000.0}, {"at": "b", "equity": 10120.0},
              {"at": "c", "equity": 10241.5}],
    "positions": {"BTC/USDT": -0.021, "ETH/USDT": 0.35},
    "recent_trades": [
        {"at": "2026-08-22T20:00:00+09:00", "symbol": "BTC/USDT",
         "side": "sell", "direction": "숏", "notional": -2000.0,
         "price": 100.0, "cost": 3.0, "signal": -0.82},
        {"at": "2026-08-22T21:00:00+09:00", "symbol": "SOL/USDT",
         "side": "buy", "direction": "청산", "notional": 1500.0,
         "price": 80.0, "cost": 2.25, "signal": 0.0,
         "realized_pnl": 312.75, "avg_cost": 100.0}],
    "limits": ["가상 자금입니다", "레버리지를 쓰지 않습니다"],
}


def _render(tmp_path, data):
    import functools
    import http.server
    import json
    import shutil
    import socketserver
    import threading
    pytest.importorskip("playwright.sync_api",
                        reason="playwright 없음 — 화면 검사 생략")
    sys.path.insert(0, str(ROOT / "tests"))
    from _browser import block_external, chromium_or_skip
    from playwright.sync_api import sync_playwright

    site = tmp_path / "site"
    shutil.copytree(ROOT / "docs", site, dirs_exist_ok=True)
    (site / "futures.json").write_text(
        json.dumps(data, ensure_ascii=False), "utf-8")

    class _Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    srv = socketserver.TCPServer(
        ("127.0.0.1", 0), functools.partial(_Quiet, directory=str(site)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    out = {}
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=chromium_or_skip())
            pg = b.new_page(viewport={"width": 1200, "height": 1400})
            block_external(pg)
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{srv.server_address[1]}/futures.html")
            pg.wait_for_timeout(1800)
            for k, sel in (("요약", "#sum"), ("제한", "#rules"),
                           ("보유", "#pos"), ("체결", "#tr"),
                           ("한계", "#limits")):
                out[k] = pg.inner_text(sel)
            out["전체"] = pg.inner_text("body")
            b.close()
        assert not errs, f"페이지 오류 {errs[:2]}"
    finally:
        srv.shutdown()
    return out


def _rule_items(v) -> list:
    """'제한' 블록의 **항목별** 글자.

    ⚠️ 블록 전체에서 낱말을 찾으면 **이웃 항목의 같은 낱말**에 걸린다.
       실제로 그랬다(감사 308) — 배율 항목을 통째로 지우는 변이가 청산
       항목의 '배율'·'확신' 덕에 살아남았고, 자금조달 항목을 지우는 변이가
       청산 항목의 '가정치' 덕에 살아남았다. 이웃이 대신 말해 주는 검사는
       그 항목을 하나도 안 지킨다. 그래서 항목마다 따로 본다.
    """
    return [line.strip() for line in v["제한"].split("\n") if line.strip()]


def _rule_saying(v, *words):
    """그 낱말들을 **한 항목 안에서 전부** 말하는 줄. 없으면 None."""
    for item in _rule_items(v):
        if all(w in item for w in words):
            return item
    return None


def test_the_page_shows_both_directions(tmp_path):
    v = _render(tmp_path, _SAMPLE)
    assert "숏" in v["보유"] and "롱" in v["보유"], (
        f"양방향 페이지인데 방향이 안 보인다:\n{v['보유']}")
    assert "0.021" in v["보유"], (
        f"숏 수량이 절댓값으로 안 나온다:\n{v['보유']}")
    assert "-0.021" not in v["보유"] and "−0.021" not in v["보유"], (
        "수량을 음수로 그대로 적었다 — '−0.021개를 들고 있다'는 읽는 사람에게 "
        f"아무 뜻이 없다:\n{v['보유']}")


def test_the_page_says_how_the_leverage_is_decided(tmp_path):
    """배율을 **누가 정하는지** 화면이 말한다 (감사 308).

    사장님 지시(2026-08-22): *"선물은 레버리지를 써도 되게끔 해. 그만큼
    수익 실현에 확신이 있으면 하는거잖아."*

    핵심은 '배율을 쓴다'가 아니라 **'확신이 있으면'**이다. 그래서 배율을
    사람이 고르지 않고 신호의 크기가 정한다 — 확신이 없는 날은 1배다.
    화면이 그 규칙을 말하지 않으면, 읽는 사람은 매일 최대치를 태우는
    계좌로 읽는다.

    ⚠️ **'제한' 블록 안에서** 찾는다. 처음엔 페이지 전체에서 찾았는데
       머리말·한계 목록에도 같은 말이 있어서 정작 제한 항목을 통째로
       지워도 통과했다 — 변이 시험이 알려 줬다(감사 304).
    """
    v = _render(tmp_path, _SAMPLE)
    item = _rule_saying(v, "배율", "확신", "1배")
    assert item, (
        "배율·확신·1배를 **한 항목 안에서** 말하는 줄이 없다 — 배율을 "
        f"무엇이 정하는지 말하지 않으면 매일 최대치를 태우는 계좌로 "
        f"읽힌다:\n{v['제한']}")


def test_the_page_admits_the_conviction_is_unproven(tmp_path):
    """대조군 — 배율을 자랑으로 적으면 안 된다.

    "확신에 비례한다"만 적으면 그 확신이 검증된 것처럼 읽힌다. 이 트랙은
    모델의 확률이 잘 보정돼 있는지 **아직 재지 않았다.** 확신이 클수록
    크게 태우는데 그 확신이 틀리면 손실도 그만큼 커진다.
    """
    v = _render(tmp_path, _SAMPLE)
    assert _rule_saying(v, "확신", "증명"), (
        f"확신이 아직 증명되지 않았다는 말이 배율 항목에 없다 — 배율을 "
        f"우위처럼 적으면 그 페이지는 증거가 아니라 광고다:\n{v['제한']}")


def test_the_page_warns_that_leverage_brings_liquidation(tmp_path):
    """**배율을 켠 순간 생긴, 1배에는 없던 위험.**

    화면이 청산을 말하지 않으면 읽는 사람은 "많이 잃어도 계좌는 남는다"고
    가정한다. 선물에서 그 가정은 틀렸고, 틀린 가정 위에서 위험을 잘못
    읽는다.
    """
    v = _render(tmp_path, _SAMPLE)
    item = _rule_saying(v, "청산", "회복할 것이 없")
    assert item, (
        "청산과 '회복할 것이 없다'를 **한 항목 안에서** 말하는 줄이 없다 — "
        f"그냥 손실과 같은 것으로 읽힌다:\n{v['제한']}")
    assert "%" in item, (
        f"어느 지점에서 청산되는지 숫자가 없다: {item}")


def test_the_page_shows_how_much_margin_is_left(tmp_path):
    """지금 얼마나 여유가 있는지 — 안 보이면 청산이 갑자기 온 것처럼 읽힌다."""
    data = dict(_SAMPLE, margin_ratio=0.184,
                maintenance_margin_rate=0.05)
    v = _render(tmp_path, data)
    assert "증거금률" in v["요약"], f"증거금률 칸이 없다:\n{v['요약']}"
    assert "18.4" in v["요약"], f"증거금률 값이 안 나온다:\n{v['요약']}"
    assert "유지선" in v["요약"], (
        f"유지선이 어디인지 안 보인다 — 숫자만으로는 위험한지 알 수 없다:"
        f"\n{v['요약']}")


def test_the_page_says_nothing_when_there_is_no_margin_to_measure(tmp_path):
    """대조군 — 포지션이 없으면 증거금률은 '—'다.

    0%로 그리면 '청산 직전'으로 읽히는데, 실제로는 걸린 것이 없다는 뜻이다.
    """
    data = dict(_SAMPLE, margin_ratio=None, maintenance_margin_rate=0.05)
    v = _render(tmp_path, data)
    # ⚠️ 요약 전체에서 '—'를 찾으면 다른 칸의 '—'에 걸린다. **증거금률 줄**을
    #    골라 본다(감사 308 — 변이 시험이 그 헐거움을 알려 줬다).
    line = next((ln for ln in v["요약"].split("\n") if "유지선" in ln), "")
    assert line, f"증거금률 줄이 아예 없다:\n{v['요약']}"
    assert "—" in line, f"잴 것이 없는데 숫자를 그렸다: {line!r}"
    assert "0.0%" not in line.split("/")[0], (
        f"잴 것이 없는 증거금률을 0%로 그렸다 — '청산 직전'으로 읽힌다: "
        f"{line!r}")


def test_a_liquidation_is_announced_loudly(tmp_path):
    """청산은 조용히 지나가면 안 된다."""
    data = dict(_SAMPLE, liquidations=1, liquidated={
        "at_ratio": 0.0455, "closed": ["BTC/USDT", "ETH/USDT"],
        "equity": 955.0, "maintenance_rate": 0.05})
    v = _render(tmp_path, data)
    assert "강제 청산" in v["요약"], (
        f"청산이 일어났는데 요약이 조용하다:\n{v['요약']}")
    assert "4.55" in v["요약"], f"어느 지점에서 털렸는지 안 말한다:\n{v['요약']}"
    assert "1번 청산" in v["제한"], (
        f"청산 횟수를 제한 항목이 말하지 않는다:\n{v['제한']}")


def test_the_page_says_when_the_rule_changed(tmp_path):
    """규칙이 바뀐 날을 화면이 말한다 (감사 308).

    이 트랙은 **1배로 24회차를 돌고 나서** 배율이 켜졌다. 그 사실을 안
    적으면 자산 곡선의 한 지점부터 성격이 달라지는데 보는 사람은 이유를
    모른다 — 그건 조용한 골대 이동이고, 이 저장소가 판정 시계에서 가장
    엄격하게 막는 것이다.

    ⚠️ 과거 회차는 고치지 않는다. 그때는 정말 1배였다.
    """
    from quant.live.futures_challenger import LEVERAGE_ENABLED_ON, RULE_CHANGES
    data = dict(_SAMPLE, rule_changes=list(RULE_CHANGES))
    v = _render(tmp_path, data)
    item = _rule_saying(v, LEVERAGE_ENABLED_ON, "규칙이 바뀌었습니다")
    assert item, (
        f"배율을 켠 날을 화면이 말하지 않는다 — 곡선이 왜 달라졌는지 "
        f"읽는 사람이 알 수 없다:\n{v['제한']}")
    assert "1배" in item, (
        f"그 전에는 1배였다는 사실을 말하지 않는다: {item}")


def test_the_report_carries_the_rule_change(tmp_path):
    """**배선** — 화면이 그릴 재료가 리포트에 실린다."""
    from quant.live.futures_challenger import public_report
    out = public_report(load_state(str(tmp_path)))
    changes = out.get("rule_changes") or []
    assert changes, f"규칙 변경 이력이 리포트에 없다: {sorted(out)}"
    assert changes[0].get("on") and changes[0].get("what")


def test_a_track_without_rule_changes_says_nothing(tmp_path):
    """대조군 — 바뀐 게 없으면 그런 줄이 없어야 한다."""
    data = dict(_SAMPLE, rule_changes=[])
    v = _render(tmp_path, data)
    assert not _rule_saying(v, "규칙이 바뀌었습니다"), (
        f"바뀐 게 없는데 바뀌었다고 말한다:\n{v['제한']}")


def test_a_healthy_account_is_not_told_it_was_liquidated(tmp_path):
    """대조군 — 청산이 없었으면 그런 말이 없어야 한다."""
    v = _render(tmp_path, _SAMPLE)
    assert "강제 청산" not in v["요약"], (
        f"청산이 없었는데 청산됐다고 말한다:\n{v['요약']}")


def test_the_page_admits_the_funding_rate_is_an_assumption(tmp_path):
    """가정을 실측인 것처럼 적으면 그 페이지는 증거가 아니다."""
    v = _render(tmp_path, _SAMPLE)
    assert "가정" in v["제한"], (
        f"자금조달 요율이 가정치라는 말이 없다:\n{v['제한']}")


def test_the_page_says_it_pays_funding(tmp_path):
    """자금조달을 **문다**는 사실이 제 항목에서 살아 있어야 한다.

    ⚠️ 예전에는 '가정'이라는 낱말을 제한 블록 전체에서 찾았다. 그런데
       청산 항목에도 "유지증거금률은 가정치"가 있어서, 자금조달 항목을
       통째로 지워도 통과했다(감사 308). 이웃이 대신 말해 주는 검사는
       그 항목을 하나도 안 지킨다.
    """
    v = _render(tmp_path, _SAMPLE)
    item = _rule_saying(v, "자금조달", "가정")
    assert item, (
        f"자금조달을 문다는 항목이 없다 — 안 무는 트랙으로 읽힌다:"
        f"\n{v['제한']}")
    assert "8시간" in item, f"정산 주기를 말하지 않는다: {item}"


def test_the_page_says_which_symbols_cannot_short(tmp_path):
    v = _render(tmp_path, _SAMPLE)
    assert "ETH/USDT" in v["제한"], (
        f"숏을 못 하는 종목을 말하지 않는다 — 못 하는 것을 하는 척하게 된다:"
        f"\n{v['제한']}")


def test_the_page_reports_a_hard_stop(tmp_path):
    v = _render(tmp_path, _SAMPLE)
    assert "XRP/USDT" in v["요약"], (
        f"하드 스톱으로 청산된 종목을 말하지 않는다:\n{v['요약']}")


def test_received_funding_is_not_drawn_as_paid(tmp_path):
    """숏은 자금조달을 **받는다**. 절댓값만 적으면 낸 것처럼 읽힌다."""
    v = _render(tmp_path, _SAMPLE)      # funding_paid = -4.25 (받음)
    assert "+4.25" in v["요약"], (
        f"받은 자금조달이 낸 것처럼 그려졌다:\n{v['요약']}")


def test_a_paid_funding_is_drawn_as_paid(tmp_path):
    """대조군 — 낸 날은 낸 것으로 그린다."""
    data = dict(_SAMPLE, funding_paid=4.25)
    v = _render(tmp_path, data)
    assert "−4.25" in v["요약"] or "-4.25" in v["요약"], (
        f"낸 자금조달이 받은 것처럼 그려졌다:\n{v['요약']}")


def test_an_opening_order_has_no_realized_number(tmp_path):
    """대조군 — 새로 여는 주문에는 확정된 것이 없다."""
    v = _render(tmp_path, _SAMPLE)
    assert "312.75" in v["체결"], f"청산 손익이 안 나온다:\n{v['체결']}"
    assert "—" in v["체결"], (
        f"여는 주문 자리를 안 비웠다 — 0으로 적으면 본전이라는 뜻이 된다:"
        f"\n{v['체결']}")


def test_the_page_keeps_its_honest_limits(tmp_path):
    v = _render(tmp_path, _SAMPLE)
    assert "가상 자금" in v["한계"], f"한계를 안 싣는다:\n{v['한계']}"
    assert "수익을 보장하지 않습니다" in v["전체"]


def test_the_page_says_nothing_rather_than_guessing(tmp_path):
    """대조군 — 기록이 없으면 없다고 한다(0으로 채우지 않는다)."""
    import functools
    import http.server
    import shutil
    import socketserver
    import threading
    pytest.importorskip("playwright.sync_api",
                        reason="playwright 없음 — 화면 검사 생략")
    sys.path.insert(0, str(ROOT / "tests"))
    from _browser import block_external, chromium_or_skip
    from playwright.sync_api import sync_playwright
    site = tmp_path / "empty"
    shutil.copytree(ROOT / "docs", site, dirs_exist_ok=True)
    (site / "futures.json").unlink(missing_ok=True)

    class _Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    srv = socketserver.TCPServer(
        ("127.0.0.1", 0), functools.partial(_Quiet, directory=str(site)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=chromium_or_skip())
            pg = b.new_page()
            block_external(pg)
            pg.goto(f"http://127.0.0.1:{srv.server_address[1]}/futures.html")
            pg.wait_for_timeout(1500)
            txt = pg.inner_text("#sum")
            b.close()
    finally:
        srv.shutdown()
    assert "없" in txt or "못" in txt, (
        f"기록이 없는데 숫자를 지어냈다: {txt}")


# ── ⑧ 배율은 확신이 정한다 (2026-08-22 사장님 지시) ───────────

def test_no_conviction_means_no_leverage():
    """**이 규칙의 핵심.** 확신이 없는 날은 1배다.

    사장님 지시: *"그만큼 수익 실현에 확신이 있으면 하는거잖아."*
    매일 똑같이 최대치를 태우는 것은 확신이 아니라 습관이다.
    """
    assert leverage_for(0.0) == pytest.approx(1.0)
    assert leverage_for(1.0) == pytest.approx(MAX_GROSS_EXPOSURE)
    assert leverage_for(0.5) == pytest.approx(
        1.0 + (MAX_GROSS_EXPOSURE - 1.0) * 0.5)


def test_leverage_grows_with_conviction():
    prev = 0.0
    for c in (0.0, 0.2, 0.5, 0.8, 1.0):
        lev = leverage_for(c)
        assert lev >= prev, f"확신이 커졌는데 배율이 안 커진다: {c} → {lev}"
        prev = lev
    assert leverage_for(1.0) > leverage_for(0.0), "배율이 아예 안 움직인다"


def test_a_short_uses_the_same_leverage_as_a_long():
    """방향이 배율을 바꾸면 안 된다 — 확신의 크기만 본다."""
    assert leverage_for(-0.8) == pytest.approx(leverage_for(0.8))


def test_an_unknown_signal_falls_back_to_one():
    """모르는 날에 크게 태우는 것이 이 트랙이 할 수 있는 가장 나쁜 일이다."""
    for bad in (None, float("nan"), "", "abc"):
        assert leverage_for(bad) == pytest.approx(1.0), bad


def test_leverage_never_exceeds_the_cap():
    """신호가 1을 넘어와도 배율은 상한에서 멈춘다."""
    assert leverage_for(5.0) == pytest.approx(MAX_GROSS_EXPOSURE)


def test_conviction_actually_changes_the_position_size():
    """**배선** — 규칙이 맞아도 체결에 안 붙으면 없는 것과 같다."""
    px = {"BTC/USDT": 100.0}
    weak, strong = _fresh(), _fresh()
    execute_targets(weak, {"BTC/USDT": 0.3}, px, 10_000.0, FEE, ONE)
    execute_targets(strong, {"BTC/USDT": 1.0}, px, 10_000.0, FEE, ONE)
    w, t = gross_exposure(weak, px), gross_exposure(strong, px)
    assert t > w * 2, (
        f"확신이 세 배 이상 차이 나는데 크기가 비슷하다 — 배율이 안 붙었다: "
        f"약한 신호 {w:,.0f} vs 센 신호 {t:,.0f}")


# ── ⑨ 배율을 쓰면 청산이 생긴다 ───────────────────────────────

def test_a_leveraged_position_can_be_liquidated():
    """**1배에는 없던 위험.**

    실측: 자산 10,000을 확신 최대(3배)로 태운 롱이 30% 하락하면 자산
    955 · 증거금률 0.046 → 유지선(0.05) 밑 → 전량 강제 청산.
    """
    st = _fresh()
    execute_targets(st, {"BTC/USDT": 1.0}, {"BTC/USDT": 100.0},
                    10_000.0, FEE, ONE)
    crashed = {"BTC/USDT": 70.0}
    ratio = margin_ratio(st, crashed)
    assert ratio is not None and ratio <= MAINTENANCE_MARGIN_RATE, (
        f"전제가 안 만들어졌다 — 증거금률 {ratio}")
    liq = liquidation_check(st, crashed)
    assert liq, "증거금이 바닥났는데 청산이 안 일어났다"
    assert st["positions"] == {}, f"청산했는데 포지션이 남았다: {st['positions']}"
    assert st["liquidations"] == 1
    assert liq["closed"] == ["BTC/USDT"]


def test_a_healthy_account_is_not_liquidated():
    """대조군 — 조금 잃었다고 터는 것은 청산이 아니라 고장이다."""
    st = _fresh()
    execute_targets(st, {"BTC/USDT": 1.0}, {"BTC/USDT": 100.0},
                    10_000.0, FEE, ONE)
    assert liquidation_check(st, {"BTC/USDT": 95.0}) is None, (
        "5% 하락에 청산됐다")
    assert st["positions"], "청산이 안 일어났는데 포지션이 사라졌다"


def test_the_margin_is_measured_on_gross_not_net():
    """롱과 숏이 서로를 상쇄하면 **위험이 안 보인다.**

    ⚠️ 이 자리를 찾는 데 변이 시험이 필요했다(감사 308). 앞선 검사들은
       전부 한 종목만 들고 있어서 |합| 과 합|·| 이 같았다 — 순노출로
       재도 결과가 같으니 그 결함이 통과했다.

    롱 1억·숏 1억이면 순노출은 0이다. 그건 위험이 없다는 뜻이 아니라
    **두 배로 걸려 있다**는 뜻이고, 어느 한쪽이 크게 밀리면 계좌가 죽는다.
    순노출로 재면 증거금률이 무한대로 보여 **청산이 영영 안 걸린다.**
    """
    st = _fresh()
    px = {"BTC/USDT": 100.0, "ETH/USDT": 100.0}
    # 손으로 만든 장부 — 롱 5,000 · 숏 5,000. 순노출 0, 총 노출 10,000.
    st["positions"] = {"BTC/USDT": 50.0, "ETH/USDT": -50.0}
    net = sum(q * px[k] for k, q in st["positions"].items())
    assert abs(net) < 1e-9, f"전제가 안 만들어졌다 — 순노출 {net}"
    assert gross_exposure(st, px) == pytest.approx(10_000.0)
    st["cash"] = 400.0        # 자산 400 → 총 노출 기준 증거금률 0.04
    ratio = margin_ratio(st, px)
    assert ratio == pytest.approx(0.04), (
        f"증거금률을 순노출로 쟀다 — 롱과 숏이 상쇄돼 위험이 사라졌다: {ratio}")
    assert liquidation_check(st, px), (
        "증거금이 바닥났는데(0.04 < 0.05) 청산이 안 걸렸다 — 순노출로 재면 "
        "이 계좌는 영영 안 털린다")


def test_an_empty_account_has_no_margin_to_measure():
    """포지션이 없으면 증거금률은 **0이 아니라 없음**이다.

    0으로 두면 '청산 직전'으로 읽히는데, 실제로는 걸린 것이 없다는 뜻이다.
    """
    st = _fresh()
    assert margin_ratio(st, {"BTC/USDT": 100.0}) is None
    assert liquidation_check(st, {"BTC/USDT": 100.0}) is None


def test_liquidation_leaves_what_was_actually_left():
    """청산은 값을 고르지 않는다 — 그 시점 자산이 그대로 현금이 된다."""
    st = _fresh()
    execute_targets(st, {"BTC/USDT": 1.0}, {"BTC/USDT": 100.0},
                    10_000.0, FEE, ONE)
    crashed = {"BTC/USDT": 70.0}
    before = mark_equity(st, crashed)
    liquidation_check(st, crashed)
    assert st["cash"] == pytest.approx(before), (
        f"청산 뒤 현금이 그 시점 자산과 다르다: {st['cash']} vs {before}")


def test_a_round_liquidates_before_it_decides(monkeypatch, tmp_path):
    """**순서가 중요하다** — 청산이 새 판단보다 먼저다.

    순서를 바꾸면 이미 털렸어야 할 계좌가 한 회차를 더 버티며 새 포지션을
    여는, 현실에 없는 장부가 된다.
    """
    import quant.live.futures_challenger as F
    _offline_round(monkeypatch, tmp_path, [100.0] * 40, 1.0)
    st = load_state(str(tmp_path))
    assert st["positions"], "전제가 안 만들어졌다 — 첫 회차가 포지션을 안 열었다"
    # 값이 30% 무너진 봉으로 다음 회차를 돌린다.
    r = _offline_round(monkeypatch, tmp_path, [70.0] * 40, 1.0,
                       now="2026-06-01T01:00:00+09:00")
    assert r.get("liquidated"), (
        f"증거금이 바닥났는데 회차 기록에 청산이 없다: {sorted(r)}")
    assert load_state(str(tmp_path))["liquidations"] >= 1


def test_the_report_carries_the_margin_and_liquidations(tmp_path):
    """**배선** — 화면이 그릴 재료가 리포트에 실린다."""
    from quant.live.futures_challenger import public_report
    st = load_state(str(tmp_path))
    st["positions"] = {"BTC/USDT": 100.0}
    st["last_prices"] = {"BTC/USDT": 100.0}
    st["liquidations"] = 2
    st["rounds"] = [{"at": "2026-08-22T00:00:00+09:00", "trades": [],
                     "margin_ratio": 0.184,
                     "liquidated": {"at_ratio": 0.04, "closed": ["ETH/USDT"]}}]
    out = public_report(st)
    assert out["margin_ratio"] == pytest.approx(0.184), out.get("margin_ratio")
    assert out["maintenance_margin_rate"] == pytest.approx(
        MAINTENANCE_MARGIN_RATE)
    assert out["liquidations"] == 2
    assert (out.get("liquidated") or {}).get("closed") == ["ETH/USDT"]
