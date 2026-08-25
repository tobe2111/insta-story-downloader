"""펀딩 과열 회피 — 가설 우선 후보 5호 (2026-08-25 수집 라운드).

가설: 무기한 선물 펀딩비가 극단으로 오른 구간은 레버리지 롱 쏠림이고,
그 구간은 강제 청산(**정의상 가격에 둔감한 매도**) 연쇄에 취약하다.
과열 구간을 비켜서면 낙폭에서 이긴다 — 참인지는 오디션이 답한다.

지켜야 할 약속:
- 과열(과거 window봉 분위수 초과)이면 관망, 정상이면 보유. 롱 전용.
- funding 컬럼이 없으면(주식·수집 실패) **전부 관망** — "정상 펀딩"과
  "몰랐다"는 다르다.
- 문턱은 **자기 봉을 제외한 과거만**으로 계산 — 자기 값을 포함하면
  극단값이 자기 문턱을 끌어올려 과열이 자기를 감춘다.
- 문턱을 잴 과거가 모자라면 관망(모름은 보수 쪽).
- 미래 봉이 과거 판단을 못 바꾼다. 가격은 판단에 안 들어간다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.strategies.funding_guard import FundingGuard  # noqa: E402

W = 30                                   # 검사용 최소 창


def _df(n, funding=None, closes=None):
    c = np.asarray(closes if closes is not None else [100.0] * n, dtype=float)
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    df = pd.DataFrame({"open": c, "high": c + 1, "low": c - 1, "close": c,
                       "volume": np.full(n, 1e6)}, index=idx)
    if funding is not None:
        df["funding"] = np.asarray(funding, dtype=float)
    return df


def test_overheat_steps_aside_and_normal_holds():
    n = W + 20
    fnd = [0.0001] * n
    for i in range(W + 5, W + 10):
        fnd[i] = 0.01                     # 과열 구간
    s = FundingGuard(window=W, quantile=0.9).generate_signals(_df(n, fnd))
    assert float(s.iloc[W + 2]) == 1.0, "정상 펀딩인데 관망한다"
    assert float(s.iloc[W + 6]) == 0.0, "과열인데 들고 있다"
    assert float(s.iloc[-1]) == 1.0, "과열이 끝났는데 복귀하지 않았다"


def test_no_funding_column_means_flat_not_invented():
    s = FundingGuard(window=W).generate_signals(_df(W + 20))
    assert float(s.abs().max()) == 0.0, "펀딩을 모르는데 포지션을 지어냈다"


def test_insufficient_history_is_flat():
    n = W + 10
    s = FundingGuard(window=W, quantile=0.9).generate_signals(
        _df(n, [0.0001] * n))
    assert float(s.iloc[:W].abs().max()) == 0.0, (
        "문턱을 잴 과거가 없는데 보유한다 — 모름이 판단으로 둔갑")


def test_the_threshold_excludes_the_bar_itself():
    """극단값 하나가 자기 문턱을 끌어올려 자기를 감추면 안 된다."""
    n = W + 3
    fnd = [0.0001] * n
    fnd[-1] = 0.05                        # 마지막 봉이 사상 최대 과열
    s = FundingGuard(window=W, quantile=0.9).generate_signals(_df(n, fnd))
    assert float(s.iloc[-1]) == 0.0, (
        "자기 값을 문턱에 포함해 과열이 자기를 감췄다")


def test_tomorrow_cannot_change_today_and_price_is_ignored():
    n = W + 15
    fnd = [0.0001] * n
    fnd[-1] = 0.05
    short = FundingGuard(window=W).generate_signals(_df(n - 5, fnd[:n - 5]))
    longer = FundingGuard(window=W).generate_signals(_df(n, fnd))
    assert list(short) == list(longer)[:n - 5], "미래 봉이 과거 판단을 바꿨다"
    up = FundingGuard(window=W).generate_signals(
        _df(n, fnd, closes=np.linspace(100, 200, n)))
    dn = FundingGuard(window=W).generate_signals(
        _df(n, fnd, closes=np.linspace(200, 100, n)))
    assert list(up) == list(dn), "가격이 펀딩 판단을 바꿨다"


def test_never_short_and_refuses_nonsense():
    assert FundingGuard(allow_short=True).allow_short is False
    for w, q in ((10, 0.9), (5000, 0.9), (180, 0.4), (180, 1.0)):
        with pytest.raises(ValueError):
            FundingGuard(window=w, quantile=q)


def test_the_hypothesis_is_written_where_the_rule_lives():
    src = (ROOT / "quant" / "strategies" / "funding_guard.py").read_text("utf-8")
    for word in ("가설", "강제 청산", "가격에 둔감", "생존 편향"):
        assert word in src, f"소스에 '{word}'가 없다"
    claims = re.findall(r"(CAGR|승률|연평균|\d+\s*%\s*(수익|상승))", src)
    assert not claims, f"바깥 성적을 본문에 적었다: {claims}"


def test_it_is_wired_into_the_ring():
    from quant.live.retrain import build_challengers, champion_spec
    ring = build_challengers(champion_spec("crypto", "BTC/USDT"),
                             seed="x", evolve=True)
    assert any(c.get("strategy") == "funding_guard" for c in ring), (
        "링에 안 서 있다")
    from quant.strategies import get_strategy
    assert get_strategy("funding_guard").window == 180
