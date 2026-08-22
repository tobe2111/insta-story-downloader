"""내부 봉 강도(IBS) — 링의 다른 후보가 못 보는 것 (2026-08-22 수집 라운드).

규칙은 한 줄이다:

    IBS = (종가 − 저가) / (고가 − 저가)
    진입 IBS < 0.2 (바닥 마감에 산다) · 청산 IBS > 0.8 (꼭대기 마감에 판다)

왜 링에 새로 세우는가: 이 저장소의 도전자 대부분은 **종가만** 본다
(이평·RSI·MACD·볼린저). 터틀·일목·파라볼릭은 고저가를 보지만 **여러 봉에
걸친 극단**을 본다. IBS가 보는 것은 **하루 안에서 종가가 앉은 위치**다 —
같은 종가로 끝나도 종일 밀리다 버틴 날과 오르다 꺾인 날은 정반대가 된다.

지켜야 할 약속:
- 규칙을 자료 그대로 옮긴다(바닥에 사고 꼭대기에 판다).
- 고가=저가인 봉에서는 IBS를 정의할 수 없다 — **직전 판단을 유지**하고
  0.5로 채우지 않는다. 0.5로 채우면 '모른다'가 '중립이라 판단했다'가 된다.
- 롱 전용이다(원문도 롱 편향). 교차 계약이 넘기는 allow_short는 받되 안 쓴다.
- 미래를 보지 않는다 — 오늘 판단에 오늘 봉까지만 쓴다.
- 링에 서고 특혜는 없다. 바깥에서 회자되는 성적은 근거로 쓰지 않는다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.strategies.ibs import IBSStrategy, internal_bar_strength  # noqa: E402


def _df(closes, high=110.0, low=90.0):
    c = np.asarray([float(x) for x in closes])
    n = len(c)
    return pd.DataFrame(
        {"open": c, "close": c,
         "high": np.full(n, float(high)), "low": np.full(n, float(low)),
         "volume": np.full(n, 1e6)},
        index=pd.date_range("2026-01-01", periods=n, freq="D"))


def test_the_indicator_says_where_in_the_bar_the_close_sat():
    got = internal_bar_strength(_df([90, 95, 100, 105, 110]))
    assert list(np.round(got.to_numpy(), 3)) == [0.0, 0.25, 0.5, 0.75, 1.0]


def test_it_buys_the_bottom_close_and_sells_the_top_close():
    # IBS  .10  .25  .90  .05  .95
    s = IBSStrategy().generate_signals(_df([92, 95, 108, 91, 109]))
    assert list(s) == [1.0, 1.0, 0.0, 1.0, 0.0], list(s)


def test_it_holds_between_the_thresholds():
    """중간값에서는 진입도 청산도 아니다 — 들고 있으면 유지, 없으면 관망."""
    s = IBSStrategy().generate_signals(_df([100, 100, 100]))
    assert list(s) == [0.0, 0.0, 0.0], "중립 구간에서 샀다"
    s2 = IBSStrategy().generate_signals(_df([92, 100, 100]))
    assert list(s2) == [1.0, 1.0, 1.0], "중립 구간에서 이유 없이 팔았다"


def test_a_bar_with_no_range_keeps_the_last_judgement():
    """고가=저가면 IBS를 정의할 수 없다 — 0.5로 채우면 '모른다'가 판단이 된다."""
    df = _df([92, 95, 108, 91, 109])
    df.loc[df.index[1], ["high", "low", "close", "open"]] = 100.0
    ibs = internal_bar_strength(df)
    assert pd.isna(ibs.iloc[1]), "정의할 수 없는 값을 숫자로 지어냈다"
    s = IBSStrategy().generate_signals(df)
    assert s.iloc[1] == s.iloc[0], "정의 불가 봉에서 판단이 흔들렸다"


def test_it_never_goes_short_even_when_asked():
    s = IBSStrategy(allow_short=True)
    assert s.allow_short is False, (
        "롱 전용 규칙인데 숏을 켰다 — 원문에 없는 반쪽을 지어낸 것이다")
    sig = s.generate_signals(_df([109, 109, 109]))
    assert float(min(sig)) >= 0.0, "숏 포지션이 나왔다"


def test_nonsense_thresholds_are_refused():
    for entry, exit_ in ((0.8, 0.2), (0.0, 0.8), (0.2, 1.0), (0.5, 0.5)):
        with pytest.raises(ValueError):
            IBSStrategy(entry=entry, exit=exit_)


def test_today_is_judged_without_tomorrow():
    """뒤에 봉을 더 붙여도 이미 내린 판단은 바뀌지 않는다(룩어헤드 없음)."""
    base = [92, 95, 108, 91, 109]
    short = IBSStrategy().generate_signals(_df(base))
    long = IBSStrategy().generate_signals(_df(base + [90, 110, 95]))
    assert list(short) == list(long)[:len(base)], (
        "미래 봉이 과거 판단을 바꿨다 — 룩어헤드다")


def test_it_stands_in_the_ring_with_no_special_treatment():
    from quant.live.retrain import build_challengers, champion_spec
    from quant.live.retrain import build_strategy

    assert build_strategy({"strategy": "ibs",
                           "params": {"entry": 0.2, "exit": 0.8}}) is not None
    ring = build_challengers(champion_spec("crypto", "BTC/USDT"),
                             seed="x", evolve=True)
    assert any(c.get("strategy") == "ibs" for c in ring), (
        "링에 안 서 있다 — 구현만 하고 안 붙이면 없는 것과 같다")


def test_the_module_does_not_quote_outside_performance():
    """바깥 성적을 근거로 적으면 생존 편향을 그대로 들여오는 것이다."""
    src = (ROOT / "quant" / "strategies" / "ibs.py").read_text("utf-8")
    assert "생존 편향" in src, "회자되는 성적을 왜 안 쓰는지 적혀 있지 않다"
    import re
    claims = re.findall(r"(CAGR|승률|연평균|\d+\s*%\s*(수익|상승))", src)
    assert not claims, f"바깥 성적을 본문에 적었다: {claims}"
