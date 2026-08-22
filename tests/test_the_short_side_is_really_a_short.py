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
    FUNDING_RATE_PER_8H, MAX_GROSS_EXPOSURE, SHORT_STOP_PCT,
    apply_funding, can_short, execute_targets, funding_cost,
    gross_exposure, load_state, mark_equity, stopped_out,
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
def _short_then_adverse_move(uni, entry=100.0, later=150.0):
    """숏을 열어 두고 가격이 크게 올라간 상태의 장부를 만든다."""
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
    assert gross_exposure(st, px) > eq * 2, (
        "전제가 안 만들어졌다 — 손실 뒤에 노출이 자산을 넘어야 한다")
    execute_targets(st, {s: -1.0 for s in uni}, px, eq, FEE, uni)
    gross = gross_exposure(st, px)
    assert gross <= eq * MAX_GROSS_EXPOSURE + 1.0, (
        f"총 노출 {gross:,.2f}가 자산 {eq:,.2f}의 {MAX_GROSS_EXPOSURE}배를 "
        "넘은 채로 남았다 — 배율이 저절로 걸렸다")


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
    # BTC만 크게 숏 → 그 뒤 가격이 두 배가 되면 노출이 자산을 크게 넘는다.
    execute_targets(st, {"BTC/USDT": -1.0, "ETH/USDT": 0.0},
                    {"BTC/USDT": 100.0, "ETH/USDT": 50.0},
                    10_000.0, FEE, uni)
    px = {"BTC/USDT": 200.0, "ETH/USDT": 50.0}
    eq = mark_equity(st, px)
    assert gross_exposure(st, px) > eq, "전제가 안 만들어졌다"
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
    execute_targets(st, {s: -3.0 for s in uni}, px, 10_000.0, FEE, uni)
    gross = gross_exposure(st, px)
    eq = mark_equity(st, px)
    assert gross <= 10_000.0 * MAX_GROSS_EXPOSURE + 1.0, (
        f"신호가 1을 넘자 총 노출 {gross:,.2f}가 한도(자산 {eq:,.2f}의 "
        f"{MAX_GROSS_EXPOSURE}배)를 넘었다 — 배율이 걸렸다")
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
    assert gross > 9_000.0, (
        f"신호가 정상 범위인데 한도가 주문을 깎았다 — 총 노출 {gross:,.2f}")


def test_room_freed_earlier_in_the_round_is_usable():
    """대조군 — 앞 종목을 줄여 생긴 자리를 뒤 종목이 쓸 수 있어야 한다.

    남은 한도를 회차 시작에 한 번만 계산해 들고 다니면, 앞에서 줄인 만큼이
    반영되지 않아 뒤 종목이 이유 없이 막힌다(감사 304에서 실제로 그랬다).
    """
    uni = ["BTC/USDT", "ETH/USDT"]
    st = _fresh()
    # BTC만 크게 숏 → 가격이 두 배가 되어 노출이 자산을 넘는다.
    execute_targets(st, {"BTC/USDT": -1.0, "ETH/USDT": 0.0},
                    {"BTC/USDT": 100.0, "ETH/USDT": 50.0},
                    10_000.0, FEE, uni)
    px = {"BTC/USDT": 200.0, "ETH/USDT": 50.0}
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


def test_the_page_shows_both_directions(tmp_path):
    v = _render(tmp_path, _SAMPLE)
    assert "숏" in v["보유"] and "롱" in v["보유"], (
        f"양방향 페이지인데 방향이 안 보인다:\n{v['보유']}")
    assert "0.021" in v["보유"], (
        f"숏 수량이 절댓값으로 안 나온다:\n{v['보유']}")
    assert "-0.021" not in v["보유"] and "−0.021" not in v["보유"], (
        "수량을 음수로 그대로 적었다 — '−0.021개를 들고 있다'는 읽는 사람에게 "
        f"아무 뜻이 없다:\n{v['보유']}")


def test_the_page_says_there_is_no_leverage(tmp_path):
    """**가장 중요한 문장.** 선물이라는 말은 배율을 떠올리게 한다.

    이 트랙이 배율을 안 쓴다는 사실이 화면에 없으면, 읽는 사람은 있다고
    가정한다 — 그리고 그 가정 위에서 위험을 잘못 읽는다.
    """
    v = _render(tmp_path, _SAMPLE)
    # ⚠️ **'제한' 블록 안에서** 찾는다. 처음엔 페이지 전체에서 '레버리지'를
    #    찾았는데, 그 단어는 머리말과 한계 목록에도 있어서 정작 제한 항목을
    #    통째로 지워도 통과했다 — 변이 시험이 알려 줬다(감사 304).
    assert "레버리지" in v["제한"], (
        f"제한 항목에 배율 이야기가 없다:\n{v['제한']}")
    assert "레버리지를 쓰지 않습니다" in v["제한"], (
        f"배율을 안 쓴다는 말이 제한 항목에 없다 — '선물'이라는 말은 배율을 "
        f"떠올리게 하므로, 없으면 있다고 가정된다:\n{v['제한']}")


def test_the_page_admits_the_funding_rate_is_an_assumption(tmp_path):
    """가정을 실측인 것처럼 적으면 그 페이지는 증거가 아니다."""
    v = _render(tmp_path, _SAMPLE)
    assert "가정" in v["제한"], (
        f"자금조달 요율이 가정치라는 말이 없다:\n{v['제한']}")


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
