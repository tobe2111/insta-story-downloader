"""월말·월초 효과 — 가설 우선 방침의 1호 후보 (2026-08-23).

방침이 바뀐 날이다. 후보를 심사할 때마다 다중검정 문턱이 올라가므로
(실측: 시행 238→373회에 필요 샤프 2.52→2.61), 이제 **경제적 가설이 있는
규칙만** 링에 세운다. 이 후보의 가설:

    연금·적립식 펀드는 월말에 들어온 적립금을 규정이 정한 비율로 사야
    한다 — 가격에 둔감한 매수 수요가 매달 같은 달력 자리에 몰린다.

지켜야 할 약속:
- 판단은 **그 봉의 날짜 하나만** 본다. 색인의 다른 봉을 보면(예: "이 달의
  마지막 거래일인가") 뒤에 봉을 붙였을 때 과거 판단이 바뀐다 — 선견 편향.
- 월말 창(entry_day~말일)과 월초 창(1~exit_day)에서만 보유, 그 밖은 관망.
- 롱 전용(수급 가설이 매수 쪽이다). allow_short는 받되 쓰지 않는다.
- 가설이 소스에 명시돼 있다 — 누가, 왜, 가격에 둔감한가까지.
- 링에 서고 특혜는 없다. 바깥 성적은 근거로 쓰지 않는다(생존 편향).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.strategies.turn_of_month import TurnOfMonth       # noqa: E402


def _df(idx):
    c = np.full(len(idx), 100.0)
    return pd.DataFrame({"open": c, "high": c + 1, "low": c - 1,
                         "close": c, "volume": np.full(len(idx), 1e6)},
                        index=idx)


def test_it_holds_the_turn_and_rests_the_middle():
    idx = pd.bdate_range("2026-01-05", "2026-02-27")
    s = TurnOfMonth().generate_signals(_df(idx))
    held = {str(d.date()) for d, v in s.items() if v > 0}
    assert "2026-01-26" in held and "2026-02-03" in held, held
    assert "2026-01-15" not in held, "월 중순인데 들고 있다"
    assert "2026-02-13" not in held
    # 창 경계가 정확한가 — 24일은 관망, 25일부터 보유, 3일까지 보유, 4일 관망
    assert "2026-02-24" not in held and "2026-02-25" in held
    assert "2026-02-04" not in held


def test_price_cannot_change_the_answer():
    """이 규칙은 달력만 본다 — 가격이 폭락해도 판단이 같아야 한다.

    가격이 스며들면 그건 다른 전략이고, 가설(수급은 가격에 둔감)과 어긋난다.
    """
    idx = pd.bdate_range("2026-01-05", "2026-02-27")
    calm = TurnOfMonth().generate_signals(_df(idx))
    crash = _df(idx)
    crash["close"] *= np.linspace(1.0, 0.3, len(idx))   # -70% 폭락
    crashed = TurnOfMonth().generate_signals(crash)
    assert list(calm) == list(crashed), "가격이 판단에 스며들었다"


def test_tomorrow_cannot_change_today():
    """뒤에 봉을 붙여도 과거 판단이 그대로다 — 선견 편향 0의 증명.

    ⚠️ '이 달의 마지막 **거래일**'로 정의하면 이 검사가 깨진다(마지막
       거래일인지는 다음 봉이 와야 안다). 그래서 달력일 창으로 정의했다.
    """
    idx = pd.bdate_range("2026-01-05", "2026-01-28")
    short = TurnOfMonth().generate_signals(_df(idx))
    longer = TurnOfMonth().generate_signals(
        _df(pd.bdate_range("2026-01-05", "2026-03-31")))
    assert list(short) == list(longer)[:len(idx)], "미래 봉이 과거를 바꿨다"


def test_it_never_goes_short_even_when_asked():
    s = TurnOfMonth(allow_short=True)
    assert s.allow_short is False, "수급 가설은 매수 쪽인데 숏을 켰다"
    idx = pd.bdate_range("2026-01-05", "2026-02-27")
    assert float(min(s.generate_signals(_df(idx)))) >= 0.0


def test_nonsense_windows_are_refused():
    for entry, exit_ in ((3, 25), (25, 0), (32, 3), (5, 5)):
        with pytest.raises(ValueError):
            TurnOfMonth(entry_day=entry, exit_day=exit_)


def test_the_hypothesis_is_written_where_the_rule_lives():
    """가설 없는 후보는 이제 링에 못 선다 — 이 파일이 그 방침의 1호다."""
    src = (ROOT / "quant" / "strategies" / "turn_of_month.py").read_text("utf-8")
    for word in ("가설", "연금", "가격에 둔감"):
        assert word in src, f"소스에 '{word}'가 없다 — 가설이 명시돼 있지 않다"
    assert "생존 편향" in src, "바깥 성적을 왜 안 쓰는지 적혀 있지 않다"
    import re
    claims = re.findall(r"(CAGR|승률|연평균|\d+\s*%\s*(수익|상승))", src)
    assert not claims, f"바깥 성적을 본문에 적었다: {claims}"


def test_it_stands_in_the_ring_with_no_special_treatment():
    from quant.live.retrain import build_challengers, build_strategy, champion_spec

    assert build_strategy({"strategy": "turn_of_month",
                           "params": {"entry_day": 25, "exit_day": 3}}) is not None
    ring = build_challengers(champion_spec("crypto", "BTC/USDT"),
                             seed="x", evolve=True)
    assert any(c.get("strategy") == "turn_of_month" for c in ring), (
        "링에 안 서 있다 — 구현만 하고 안 세우면 없는 것과 같다")
