"""터틀 트레이딩이 **규칙대로** 움직이고, 심사대에 실제로 오르는가.

사장님 제안(2026-08-18)으로 들어온 전략 — 규칙이 공개돼 있으니 검사도
규칙 그대로 한다: ① 20일 돌파 진입 ② 10일 최저 이탈 청산 ③ 2N 손절.
그리고 전설이라도 특혜는 없다 — 도전자 링에 있는지까지 확인한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.strategies import get_strategy                    # noqa: E402
from quant.strategies.turtle import TurtleStrategy           # noqa: E402

SRC = (ROOT / "quant" / "strategies" / "turtle.py").read_text("utf-8")


def _df(closes, spread=0.5):
    # ⚠️ pd.Series를 그대로 넣으면 새 날짜 인덱스와 정렬돼 전부 NaN이 된다
    #    — 반드시 ndarray로 위치 배치한다(실제로 그렇게 한 번 당했다).
    c = np.asarray([float(x) for x in closes])
    return pd.DataFrame({"open": c, "high": c + spread,
                         "low": c - spread, "close": c, "volume": 1.0},
                        index=pd.date_range("2025-01-01",
                                            periods=len(c), freq="D"))


# ── ① 20일 돌파 진입 ───────────────────────────────────────────

def test_a_breakout_enters_and_quiet_tape_does_not():
    flat = [100.0] * 60
    s = TurtleStrategy().generate_signals(_df(flat))
    assert float(s.iloc[-1]) == 0.0, "돌파가 없는데 들어갔다"
    breakout = [100.0] * 60 + [105.0, 106.0]
    s = TurtleStrategy().generate_signals(_df(breakout))
    assert float(s.iloc[-1]) == 1.0, "20일 최고가 돌파인데 안 들어갔다"


def test_the_channel_excludes_the_current_bar():
    """돌파 판정에 자기 봉이 들어가면(룩어헤드) 종가가 자기 고가를 못 넘어
    영원히 진입하지 못한다 — shift(1)가 빠지는 순간 전략이 죽는다."""
    assert ".shift(1)" in SRC, "채널·ATR 계산이 현재 봉을 제외하지 않는다"


# ── ② 10일 최저 이탈 청산 ──────────────────────────────────────

def test_the_ten_day_low_exit_lets_go():
    path = ([100.0] * 60 + [105.0] + [106.0] * 12          # 진입 후 보합
            + [98.0])                                      # 10일 최저 이탈
    s = TurtleStrategy().generate_signals(_df(path))
    assert float(s.iloc[-2]) == 1.0
    assert float(s.iloc[-1]) == 0.0, "10일 최저를 깼는데 들고 있다"


# ── ③ 2N 손절 — 터틀의 '영혼' ─────────────────────────────────

def test_the_two_atr_stop_fires_before_the_channel():
    """채널(10일 최저)이 멀어도, 진입가−2×ATR이 깨지면 나와야 한다."""
    # 좁은 박스(ATR≈1) → 105 돌파 진입(손절≈103) → 102.5: 10일 최저(99.5)
    # 위지만 손절선 아래.
    path = [100.0] * 60 + [105.0, 102.5]
    s = TurtleStrategy().generate_signals(_df(path))
    assert float(s.iloc[-2]) == 1.0, "진입 자체가 안 됐다 — 픽스처 문제"
    assert float(s.iloc[-1]) == 0.0, (
        "손절선(진입가-2N)이 깨졌는데 들고 있다 — 터틀의 영혼이 빠졌다")


def test_a_shallow_dip_above_the_stop_holds():
    """대조군 — 손절선 위의 얕은 되돌림에는 버텨야 한다.
    이게 없으면 '아무 하락에나 판다'도 위 검사를 통과한다."""
    path = [100.0] * 60 + [105.0, 104.0, 103.5]
    s = TurtleStrategy().generate_signals(_df(path))
    assert float(s.iloc[-1]) == 1.0, "손절선 위인데 팔았다 — 손절이 아니라 겁이다"


def test_the_atr_is_borrowed_not_rewritten():
    assert "from quant.strategies.keltner import average_true_range" in SRC, (
        "ATR을 다시 적었다 — 같은 계산이 두 곳이면 언젠가 갈라진다")


# ── 심사대 — 전설이라도 특혜는 없다 ────────────────────────────

def test_the_turtle_is_registered_and_buildable():
    s = get_strategy("turtle", entry_window=20, exit_window=10)
    assert isinstance(s, TurtleStrategy)
    from quant.live.retrain import build_strategy
    s2 = build_strategy({"strategy": "turtle",
                         "params": {"entry_window": 55, "exit_window": 20}})
    assert isinstance(s2, TurtleStrategy) and s2.entry_window == 55


def test_both_turtle_systems_stand_in_the_challenger_ring():
    from quant.live.retrain import build_challengers
    ring = build_challengers({"strategy": "ml",
                              "params": {"model": "logreg"}}, seed="t")
    turtles = [c for c in ring if c.get("strategy") == "turtle"]
    wins = sorted(t["params"]["entry_window"] for t in turtles)
    assert wins == [20, 55], (
        f"터틀 시스템1(20/10)·시스템2(55/20)가 링에 없다: {turtles} — "
        "만들어 두고 심사에 안 세우면 없는 전략이다")


def test_no_position_sizing_inside_the_strategy():
    """크기 결정(1% 리스크·피라미딩)은 위험 계층의 일이다 — 전략이 크기까지
    정하면 킬스위치와 싸운다. 신호는 [0,1] 방향·강도만 낸다."""
    body = SRC.split('"""', 2)[-1]
    for banned in ("equity", "riskMoney", "lots", "0.01"):
        assert banned not in body, f"전략 안에 크기 결정({banned})이 들어 있다"
