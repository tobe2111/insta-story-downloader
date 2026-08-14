"""낙폭이 원금을 고점으로 안 친다 — 브레이크가 한 단계 덜 걸린다 (감사 239).

`twr_index`의 첫 줄은 "입금 효과를 제거한 누적 성장 지수(**시작 1.0**)"라고
적혀 있다. 그런데 그 1.0은 시계열에 없다 — 첫 값이 이미 `첫 기록 자산 / 원금`
이다. 그리고 낙폭을 재는 두 함수는 배열 안의 값만 고점 후보로 봤다.

그래서 **계좌가 원금을 한 번도 넘지 못한 구간에서는 첫 기록의 손실이 그대로
기준선이 된다.** 실측(원금 100,000원 → 90,000 → 85,000 → 80,000 → 72,000):

    보고된 낙폭  -20.00%   ← 90,000을 고점으로 쟀다
    진짜 낙폭    -28.00%   ← 원금 100,000 대비

그리고 그 차이가 킬스위치 단계를 가른다:

    낙폭 -28% → 노출 배수 0.00  (전량 정지)
    낙폭 -20% → 노출 배수 0.50  (절반만 축소)

**브레이크가 가장 필요한 국면에서 항상 한 단계 덜 걸린다.** 감사 198(안전장치가
NaN에 조용히 꺼진다)·233(브로커가 자기 현금을 안 본다)과 같은 계열이다.

⚠️ 고치는 방법을 두 번 골랐다. 처음에는 `twr_index`가 1.0을 실제로 내보내게
   했는데, 검사가 그 자리에서 잡았다 — **사이트·방송의 낙폭 차트가 이 배열을
   기록 날짜와 나란히 그린다.** 한 점을 더하면 그래프가 하루씩 밀린다. 그래서
   배열은 그대로 두고 낙폭을 재는 쪽이 원점을 고점 후보로 보게 했다.
   ("고치는 방향이 여러 개일 때, 그중 하나만 다른 것을 안 깨뜨린다.")

실제로 이 결함은 지금 장부에도 남아 있다 — SPY 종목 계좌의 최대낙폭이
사이트에 -0.10%로 적혀 있는데 원금(10,000) 대비로는 -0.14%다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.live.ledger_basics import (  # noqa: E402
    INDEX_ORIGIN,
    drawdown_from_index,
    max_drawdown_from_index,
    time_weighted_return,
    twr_index,
)

ROOT = Path(__file__).resolve().parent.parent


def _hist(*equities):
    return [{"date": f"2026-01-{i:02d}", "equity": float(e)}
            for i, e in enumerate(equities, start=1)]


# ── 원금 아래로만 다닌 계좌 ───────────────────────────────────

SINKING = _hist(90_000, 85_000, 80_000, 72_000)


def test_the_drawdown_is_measured_from_the_principal():
    """실측 그 장면 — -20%가 아니라 -28%가 나와야 한다."""
    idx = twr_index(SINKING, [], start_cash=100_000)
    assert drawdown_from_index(idx) == pytest.approx(-0.28)
    assert max_drawdown_from_index(idx) == pytest.approx(-0.28)


def test_the_killswitch_now_reaches_the_right_step():
    """숫자가 아니라 **브레이크 단계**가 달라진다 — 그것이 이 결함의 무게다."""
    from quant.live.daily import _kill_switch_scale

    idx = twr_index(SINKING, [], start_cash=100_000)
    dd = drawdown_from_index(idx)
    assert _kill_switch_scale(1.0, dd) < _kill_switch_scale(1.0, -0.20), (
        "고친 낙폭이 예전 낙폭과 같은 단계에 머문다 — 고쳐진 게 없다")


def test_a_first_day_loss_is_not_the_new_baseline():
    """첫 기록이 이미 손실인 계좌 — 그 손실도 낙폭이다."""
    idx = twr_index(_hist(95_000), [], start_cash=100_000)
    assert max_drawdown_from_index(idx) == pytest.approx(-0.05)


# ── 대조군: 이익 구간은 건드리지 않는다 ────────────────────────

def test_an_account_above_water_is_unchanged():
    """원금 위로 올라간 계좌의 낙폭은 **그 고점** 대비다."""
    idx = twr_index(_hist(110_000, 105_000, 120_000), [], start_cash=100_000)
    assert max_drawdown_from_index(idx) == pytest.approx(105 / 110 - 1)
    assert drawdown_from_index(idx) == pytest.approx(0.0)


def test_a_new_high_resets_the_current_drawdown():
    idx = twr_index(_hist(90_000, 130_000), [], start_cash=100_000)
    assert drawdown_from_index(idx) == pytest.approx(0.0)
    assert max_drawdown_from_index(idx) == pytest.approx(-0.10)


def test_the_return_itself_did_not_move():
    """수익률은 원래 맞았다 — 낙폭만 고친다."""
    assert time_weighted_return(SINKING, [], start_cash=100_000) == -28.0
    assert time_weighted_return(_hist(110_000, 105_000, 120_000), [],
                                start_cash=100_000) == 20.0


# ── 차트 정렬을 깨지 않았는가 ─────────────────────────────────

def test_the_index_still_has_one_point_per_record():
    """사이트·방송의 낙폭 차트가 이 배열을 기록 날짜와 나란히 그린다.

    한 점을 더하면 그래프가 하루씩 밀린다 — 처음 고칠 때 실제로 그랬고
    검사 넷이 그 자리에서 잡았다.
    """
    for n in (1, 2, 5):
        hist = _hist(*[100_000 - i * 1000 for i in range(n)])
        assert len(twr_index(hist, [], start_cash=100_000)) == n


def test_an_empty_history_is_still_empty():
    assert twr_index([], [], start_cash=100_000) == []
    assert drawdown_from_index([]) == 0.0
    assert max_drawdown_from_index([]) == 0.0


# ── 입금이 낙폭을 지우지 않는가 (감사 197의 계약 유지) ─────────

def test_a_deposit_still_does_not_erase_the_drawdown():
    """입금이 고점을 끌어올려 낙폭이 0이 되면 안 된다 — 그 계약은 그대로다."""
    hist = _hist(90_000, 1_000_000)
    deps = [{"date": "2026-01-02", "amount": 920_000,
             "settled_bar": "2026-01-02"}]
    idx = twr_index(hist, deps, start_cash=100_000)
    assert drawdown_from_index(idx) < -0.09, (
        f"입금이 낙폭을 지웠다 — 지수 {idx}")


# ── 원점 상수가 실제로 쓰이는가 ───────────────────────────────

def test_the_origin_is_one():
    assert INDEX_ORIGIN == 1.0


def test_both_drawdown_functions_use_the_origin():
    """둘 중 하나만 고치면 현재 낙폭과 최대 낙폭이 서로 다른 말을 한다."""
    idx = twr_index(SINKING, [], start_cash=100_000)
    assert drawdown_from_index(idx) == pytest.approx(
        max_drawdown_from_index(idx)), "두 함수가 다른 기준선을 쓴다"


# ── 지금 장부에 남아 있는 흔적 ────────────────────────────────

def test_the_live_ledger_shows_the_old_understatement():
    """SPY 계좌가 이 결함의 증거다 — 사이트 -0.10% vs 원금 대비 -0.14%.

    ⚠️ **과거 기록은 고치지 않는다.** 이 검사는 그 값을 바꾸라는 것이 아니라,
       결함이 실재했음을 못박아 둔다. 다음 배치부터 새 계산으로 기록된다.
    """
    import json

    path = ROOT / "state" / "paper" / "us_stock_SPY.json"
    if not path.exists():
        pytest.skip("SPY 장부 없음")
    d = json.loads(path.read_text("utf-8"))
    hist = d.get("history") or []
    start = float(d.get("start_cash") or 0)
    if len(hist) < 3 or start <= 0:
        pytest.skip("표본 부족")
    idx = twr_index(hist, d.get("deposits") or [], start_cash=start)
    fixed = max_drawdown_from_index(idx)
    # 옛 계산: 배열 안의 값만 고점 후보로 봤다
    peak, old = 0.0, 0.0
    for v in idx:
        peak = max(peak, v)
        if peak > 0:
            old = min(old, v / peak - 1)
    assert fixed <= old, "고친 값이 옛 값보다 얕다 — 방향이 반대다"
