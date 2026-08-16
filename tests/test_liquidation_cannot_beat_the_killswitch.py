"""레버리지를 열기 전에 — **청산이 감시보다 먼저 오면 안전장치가 아니다.**

⚠️ 왜 이 파일이 생겼나 (2026-08-14, 사장님이 선물 투자를 물어서).

    이 시스템의 안전장치는 전부 **자산이 0 아래로 안 간다**는 현물의 전제 위에
    서 있다. 킬스위치는 새벽 배치에서 하루 한 번 돌고, 그래도 되는 이유는
    최악이어도 내일 아침에 처리하면 되기 때문이다.

    레버리지 선물은 그 전제가 깨진다. 거래소는 실시간으로 청산하고, 우리는
    루프가 돌 때만 본다. 그 사이에 끝나면 "낙폭 -25%면 전량 관망합니다"는
    **선언만 남고 아무것도 안 막는다.**

이 파일은 그 관문이 실제로 막는지를 값으로 확인한다. 그리고 **지금 동작을
바꾸지 않는지**도 확인한다 — 관문이 먼저 서고 문은 나중에 열린다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.risk.liquidation import (                       # noqa: E402
    DEFAULT_JUMP_FLOOR,
    JUMP_FLOOR,
    SAFETY_FACTOR,
    check_headroom,
    interval_worst_move,
    liquidation_price,
    max_safe_leverage,
    move_to_liquidation,
)


# ── ① 청산가 계산이 맞는가 ──────────────────────────────────────

def test_no_leverage_cannot_be_liquidated():
    """1배 롱은 가격이 0이 돼야 청산이다 — **지금 이 시스템의 상태다.**

    이 성질이 깨지면 현물 계좌가 갑자기 청산 대상이 된다.
    """
    assert liquidation_price(100.0, 1.0) == 0.0
    assert move_to_liquidation(1.0) == pytest.approx(1.0)


@pytest.mark.parametrize("lev,expect", [(2, 0.497), (5, 0.196), (10, 0.095),
                                        (20, 0.045)])
def test_liquidation_distance_matches_the_textbook(lev, expect):
    """격리마진 표준식 — 10배면 대략 10%에서 청산된다는 상식과 맞아야 한다."""
    assert move_to_liquidation(lev) == pytest.approx(expect, abs=0.002)


def test_shorts_are_liquidated_upward():
    """숏은 **올라가면** 청산된다 — 방향을 뒤집으면 정반대로 계산한다."""
    assert liquidation_price(100.0, 5.0, side="short") > 100.0
    assert liquidation_price(100.0, 5.0, side="long") < 100.0


def test_higher_maintenance_margin_liquidates_sooner():
    """유지증거금률이 높을수록 청산가가 진입가에 가깝다(더 위험하다).

    거래소는 포지션이 커지면 이 값을 올린다 — 큰 포지션이 더 위험한 이유다.
    """
    assert move_to_liquidation(10, mmr=0.02) < move_to_liquidation(10, mmr=0.005)


def test_nonsense_inputs_are_refused_not_guessed():
    for bad in ({"entry": 0.0, "leverage": 5.0}, {"entry": 100.0, "leverage": 0.0},
                {"entry": 100.0, "leverage": 5.0, "mmr": 1.5}):
        with pytest.raises(ValueError):
            liquidation_price(**bad)
    with pytest.raises(ValueError):
        liquidation_price(100.0, 5.0, side="sideways")


# ── ② 관문이 실제로 막는가 ──────────────────────────────────────

def test_todays_system_passes_unchanged():
    """**레버리지가 없으면 관문은 언제나 통과한다.**

    이 파일을 넣는 것만으로 오늘 동작이 바뀌면 안 된다 — 관문이 먼저 서고
    문은 나중에 열린다. 여기가 깨지면 현물 계좌가 새 관문에 걸린다.
    """
    for market in ("crypto", "us_stock", "kr_stock", ""):
        h = check_headroom(1.0, daily_vol=0.03, market=market)
        assert h.ok, f"{market}: 레버리지 없는데 거부됐다 — {h.reason}"


def test_ten_times_on_a_daily_loop_is_refused():
    """하루 1회 감시에 10배는 **막혀야 한다.** 이 파일이 존재하는 이유다."""
    h = check_headroom(10.0, daily_vol=0.03, guard_minutes=1440, market="crypto")
    assert not h.ok
    assert "감시가 보기 전에 청산" in h.reason


def test_unknown_volatility_blocks_leverage_but_not_spot():
    """모르는 것을 '위험 없음'으로 읽지 않는다 — 미측정=절반 규칙과 같은 정신.

    다만 레버리지가 없으면 청산 자체가 불가능하므로 그때는 통과한다.
    """
    assert not check_headroom(3.0, daily_vol=0.0).ok
    assert check_headroom(1.0, daily_vol=0.0).ok


def test_measured_worst_move_beats_the_assumption():
    """실측이 있으면 가정 대신 실측을 쓴다 — 이 저장소의 기본 태도.

    그리고 실측인지 가정인지 **화면에 나온다** — 안 나오면 읽는 사람이
    가정을 실측으로 읽는다.
    """
    guess = check_headroom(3.0, daily_vol=0.03, market="crypto")
    meas = check_headroom(3.0, worst_move=0.05, market="crypto")
    assert not guess.measured and meas.measured
    assert "가정" in guess.describe() and "실측" in meas.describe()
    # 실측이 가정보다 작으면 통과할 수 있어야 한다(가정이 무조건 이기면 실측이 무의미).
    assert meas.ok and not guess.ok


# ── ③ 자주 본다고 다 피할 수 있는 게 아니다 ──────────────────────

def test_checking_more_often_does_not_unlock_unlimited_leverage():
    """**이 검사가 이 파일에서 제일 중요하다.**

    ⚠️ 점프 바닥을 안 넣었을 때 실측에서 이런 답이 나왔다: 1분마다 감시하면
       20배까지 안전하다. 틀렸다 — √시간 축소는 가격이 연속으로 움직인다고
       가정하는데, 실제로는 두 틱 사이에 통째로 뛴다(플래시 크래시·갭·
       거래소 장애). 자주 보는 것으로는 그걸 못 피한다.
    """
    fast = max_safe_leverage(daily_vol=0.03, guard_minutes=1, market="crypto")
    slow = max_safe_leverage(daily_vol=0.03, guard_minutes=1440, market="crypto")
    assert fast < 5.0, f"1분마다 보면 {fast}배까지 된다 — 점프 위험을 안 센다"
    assert fast >= slow, "자주 보는데 더 위험해질 수는 없다"


def test_the_jump_floor_binds_no_matter_the_interval():
    """감시 주기를 아무리 줄여도 최악 변동은 바닥 아래로 안 내려간다."""
    for mins in (1440, 60, 5, 1, 0.1):
        w = interval_worst_move(0.001, mins, market="crypto")
        assert w >= JUMP_FLOOR["crypto"], f"{mins}분에서 바닥을 뚫었다: {w}"


def test_unknown_markets_get_the_worst_floor():
    """모르는 시장은 **가장 나쁜 값**을 쓴다 — 모르면 나쁜 쪽으로."""
    assert DEFAULT_JUMP_FLOOR == max(JUMP_FLOOR.values())
    assert (interval_worst_move(0.01, 60, market="처음보는시장")
            == pytest.approx(DEFAULT_JUMP_FLOOR))


def test_crypto_is_capped_tighter_than_stocks():
    """24시간·서킷브레이커 없는 시장이 더 위험하다 — 그게 숫자에 나와야 한다."""
    coin = max_safe_leverage(daily_vol=0.03, guard_minutes=60, market="crypto")
    stock = max_safe_leverage(daily_vol=0.015, guard_minutes=60, market="kr_stock")
    assert coin < stock, f"코인 {coin}배가 주식 {stock}배보다 관대하다"


# ── ④ 상한 계산이 관문과 어긋나지 않는가 ────────────────────────

@pytest.mark.parametrize("market,vol", [("crypto", 0.03), ("us_stock", 0.02),
                                        ("kr_stock", 0.015)])
def test_max_safe_leverage_agrees_with_the_gate(market, vol):
    """상한이 관문과 갈라지면, 화면이 "5배까지 됩니다"라고 하고 실제로는 막힌다.

    같은 규칙을 두 곳에 적으면 반드시 어긋난다(FROZEN_IDEAS ①) — 여기서는
    상한을 관문으로 **찾아내므로** 갈라질 수 없다. 그 성질을 값으로 못 박는다.
    """
    L = max_safe_leverage(daily_vol=vol, guard_minutes=60, market=market)
    assert check_headroom(L, daily_vol=vol, guard_minutes=60, market=market).ok
    over = check_headroom(L * 1.05, daily_vol=vol, guard_minutes=60, market=market)
    assert not over.ok, f"{market}: 상한 {L}배를 넘겼는데 통과한다"


def test_the_safety_factor_is_actually_more_than_one():
    """1배 여유는 '이론상 아슬아슬하게 산다'는 뜻이고 실전에서 못 산다는 뜻이다."""
    assert SAFETY_FACTOR > 1.0
