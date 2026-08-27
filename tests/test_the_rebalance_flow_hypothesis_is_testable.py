"""가설 6호 — 목표비중 자금의 월말 강제 리밸런싱(2026-08-27 수집 라운드).

■ 이 검사가 지키는 것

후보를 하나 세울 때마다 **모든 후보의 합격선이 올라간다**(다중검정). 그러니
새 후보는 (a) 가설이 명시돼 있고 (b) 그 가설이 실제로 코드가 되어 있고
(c) 이미 있는 후보와 **다른 질문**을 해야 자격이 있다. 셋 다 검사한다.

그리고 무엇보다 **선견(룩어헤드)이 0**이어야 한다. "이 봉이 이 달의 마지막
거래일인가"는 미래를 봐야 아는 값이고, 그걸 쓰면 백테스트에서만 좋아 보이는
규칙이 오디션의 모든 관문을 정당하게 통과한다.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant.strategies import get_strategy
from quant.strategies.rebalance_flow import RebalanceFlow

ROOT = Path(__file__).resolve().parent.parent
SRC = (ROOT / "quant" / "strategies" / "rebalance_flow.py").read_text("utf-8")


def _frame(seed: int = 0, n: int = 1500) -> pd.DataFrame:
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    rng = np.random.default_rng(seed)
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.012, n))),
                      index=idx)
    return pd.DataFrame({"open": close, "high": close * 1.01,
                         "low": close * 0.99, "close": close,
                         "volume": 1_000.0}, index=idx)


# ── ① 선견이 0인가 — 이 파일에서 가장 중요한 검사 ──────────────────────

def test_the_rule_cannot_see_the_end_of_the_month_before_it_arrives():
    """미래 봉을 잘라내도 **과거 신호가 하나도 안 바뀐다**.

    "이 봉이 이 달의 마지막 거래일인가"는 다음 봉을 봐야 안다. 그걸 쓰면
    데이터 끝에 봉을 붙일 때마다 과거 판단이 바뀌고, 백테스트에서만 좋아
    보이는 규칙이 만들어진다. 그래서 이 규칙은 '이 달의 **첫** 봉인가'만
    보고(직전 봉과 비교 — 과거다), 창은 그 봉 자신의 달력일로 가른다.
    """
    df = _frame()
    strat = RebalanceFlow()
    full = strat.generate_signals(df)
    for cut in (900, 1200, 1400):
        part = strat.generate_signals(df.iloc[:cut])
        assert np.allclose(full.iloc[:cut].to_numpy(), part.to_numpy(),
                           equal_nan=True), (
            f"미래 {len(df) - cut}봉을 잘랐더니 과거 신호가 바뀌었다 — "
            "규칙이 미래를 본다")


def test_the_lookahead_check_is_not_vacuous():
    """대조군 — 신호가 **실제로 오르내리는가**.

    ⚠️ 위 검사는 신호가 늘 0이어도 초록이다(자르든 말든 0은 0이다).
       규칙이 조용히 죽어 있으면 룩어헤드 검사가 아무것도 안 지킨다.
    """
    sig = RebalanceFlow().generate_signals(_frame())
    assert set(np.unique(sig.to_numpy())) == {0.0, 1.0}, (
        f"신호가 켜지지도 꺼지지도 않는다: {np.unique(sig.to_numpy())}")
    share = float(sig.mean())
    assert 0.01 < share < 0.5, (
        f"노출 비율이 {share:.3f} — 늘 켜져 있거나 늘 꺼져 있으면 "
        "규칙이 아무 말도 안 하는 것이다")


# ── ② 가설이 실제로 코드가 되어 있는가 ─────────────────────────────────

def test_the_month_end_leg_avoids_the_winner_and_buys_the_loser():
    """압력 구간의 **부호**가 가설대로다 — 오른 자산은 피하고 내린 자산은 산다.

    가설: 비중이 넘친 자산은 "비싸서"가 아니라 **규정 때문에** 팔린다.
    그러니 그달 많이 오른 자산은 팔릴 차례이고, 많이 내린 자산은 사줄
    차례다. 부호가 반대면 그건 이 가설이 아니라 추세추종이다.
    """
    idx = pd.date_range("2026-01-01", periods=90, freq="D")
    strat = RebalanceFlow(entry_day=25, exit_day=3, band=0.03)

    def _sig(monthly_move: float) -> pd.Series:
        # 2월 한 달 동안 monthly_move 만큼 곧게 움직이는 가격.
        close = pd.Series(100.0, index=idx)
        feb = (idx.month == 2)
        steps = np.linspace(0, monthly_move, int(feb.sum()))
        close[feb] = 100.0 * (1.0 + steps)
        close[idx.month > 2] = float(close[feb].iloc[-1])
        df = pd.DataFrame({"open": close, "high": close, "low": close,
                           "close": close, "volume": 1_000.0}, index=idx)
        return strat.generate_signals(df)

    late_feb = (idx.month == 2) & (idx.day >= 25)
    up, down = _sig(+0.20), _sig(-0.20)
    assert float(down[late_feb].mean()) == 1.0, (
        "그달 많이 **내린** 자산을 월말에 안 산다 — 규정상 사줄 차례라는 "
        "가설이 코드에 없다")
    assert float(up[late_feb].mean()) == 0.0, (
        "그달 많이 **오른** 자산을 월말에 그대로 들고 간다 — 팔릴 차례를 "
        "피한다는 가설이 코드에 없다")


def test_the_unwind_leg_exists_too():
    """되돌림 구간이 **있다** — 없으면 이건 압력 가설이 아니다.

    ⚠️ 가설의 핵심은 "정보가 아니라 일시적 압력"이다. 압력이라면 다음 달
       초에 **되돌아와야** 한다. 월말 다리만 있고 되돌림 다리가 없으면
       그 규칙이 참일 때 나타날 패턴의 절반만 보는 것이고, 그러면 이겨도
       가설이 맞았다고 말할 수 없다.
    """
    idx = pd.date_range("2026-01-01", periods=90, freq="D")
    close = pd.Series(100.0, index=idx)
    feb = (idx.month == 2)
    close[feb] = 100.0 * (1.0 + np.linspace(0, 0.20, int(feb.sum())))
    close[idx.month > 2] = float(close[feb].iloc[-1])
    df = pd.DataFrame({"open": close, "high": close, "low": close,
                       "close": close, "volume": 1_000.0}, index=idx)

    sig = RebalanceFlow(entry_day=25, exit_day=3, band=0.03).generate_signals(df)
    early_mar = (idx.month == 3) & (idx.day <= 3)
    assert float(sig[early_mar].mean()) == 1.0, (
        "지난달 많이 올라 팔렸던 자산의 눌림을 다음 달 초에 안 탄다 — "
        "'일시적 압력'이라는 가설의 절반이 코드에 없다")


def test_a_flat_month_says_nothing():
    """대조군 — 그달 거의 안 움직였으면 **아무 말도 안 한다**.

    밴드가 없으면 잡음 한 톨에도 방향이 뒤집히고, 그러면 이 규칙은
    '리밸런싱 압력'이 아니라 그냥 매일 동전을 던지는 장치다.
    """
    idx = pd.date_range("2026-01-01", periods=90, freq="D")
    close = pd.Series(100.0, index=idx)                 # 완전히 평평
    df = pd.DataFrame({"open": close, "high": close, "low": close,
                       "close": close, "volume": 1_000.0}, index=idx)
    sig = RebalanceFlow(band=0.03).generate_signals(df)
    assert float(sig.sum()) == 0.0, (
        f"움직이지 않은 달에도 신호를 냈다: {float(sig.mean()):.3f}")

    with pytest.raises(ValueError):
        RebalanceFlow(band=0.0)     # 기준 없는 밴드는 아예 막는다


# ── ③ 이미 있는 후보와 다른 질문인가 ───────────────────────────────────

def test_it_asks_a_different_question_than_the_plain_turn_of_month_rule():
    """월말 후보(turn_of_month)와 **신호가 다르다**.

    똑같은 신호를 내는 후보를 하나 더 세우면 얻는 것은 없고 다중검정
    문턱만 올라간다. 달력이 겹치는 것은 괜찮다 — 겹쳐도 **부호가 있어서**
    종목마다 방향이 갈리는 것이 이 후보의 정체다.
    """
    df = _frame(seed=3)
    mine = RebalanceFlow().generate_signals(df)
    tom = get_strategy("turn_of_month").generate_signals(df)
    differ = float((mine != tom).mean())
    assert differ > 0.05, (
        f"월말 후보와 신호가 {100 * (1 - differ):.0f}% 같다 — 같은 질문을 "
        "두 번 하는 것이고, 그러면 문턱만 올라가고 남는 것이 없다")


def test_it_stands_in_the_nightly_ring():
    """밤 오디션의 고정 격자에 **실제로 올라가 있다**.

    전략 파일이 있는 것과 링에 서는 것은 다른 일이다 — 이 저장소가 이미
    여러 번 겪은 '설정에는 있는데 실제로는 안 도는' 병이다.
    """
    from quant.live.retrain import build_challengers, build_strategy

    champ = {"strategy": "ml", "params": {"model": "logreg"}}
    ring = build_challengers(champ, seed="2026-08-27:us_stock:SPY")
    entries = [c for c in ring if c.get("strategy") == "rebalance_flow"]
    assert entries, ("가설 6호가 그날 밤 링에 없다 — 전략 파일만 있고 "
                     "오디션이 그것을 안 부른다")
    for spec in entries:
        build_strategy(spec)        # 못 만들면 여기서 죽는다


# ── ④ 기록의 정직함 ────────────────────────────────────────────────────

def test_the_hypothesis_is_written_down_including_who_and_why():
    """가설이 **소스에 명시**돼 있다 — 누가·왜·참이면 나타날 패턴까지.

    (2026-08-23 방침) 숫자 규칙만 적고 가설을 안 적으면, 나중에 이 후보가
    지거나 이겼을 때 **무엇이 기각·확인된 것인지** 아무도 말할 수 없다.
    그러면 문턱 비용만 내고 배운 것이 없다.
    """
    for must in ("누가:", "왜:", "그래서:", "가설이 참이라면 나타날 패턴"):
        assert must in SRC, f"가설 기록에 '{must}'가 없다"
    assert "정직한 한계" in SRC, "한계를 안 적었다"
    assert "생존 편향" in SRC, (
        "바깥에서 회자되는 성적을 근거로 쓰지 않는다는 기록이 없다")


def test_the_record_does_not_promise_returns():
    """'수익 보장'류 표현이 없다 — 법적 레드라인이자 이 제품의 정체성."""
    for banned in ("수익 보장", "확실한 수익", "손실 없", "무조건 수익"):
        assert banned not in SRC, f"금지 표현이 들어갔다: {banned}"
