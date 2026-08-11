"""신호는 완성된 봉으로만 낸다 — 체결은 지금 가격으로 한다.

2026-08-11 감사 71. 주식 제공자에는 `_drop_unclosed`가 있어 장 마감 전의
'오늘' 봉을 버린다. 코인은 24시간 시장이라 UTC 일봉의 '오늘' 봉이 **항상**
진행 중인데 그 장치가 없었다. 저장된 스냅샷으로 실측한 결과:

    코인 : 결정에 쓴 봉 15개 중 **15개**가 확정 봉과 달랐다
           종가 차이   평균 66.8bp · 최대 150.8bp
           고저 레인지 평균 36% 축소 · 최대 88.6%
    주식 : 28개 중 0개

레인지가 짧게 잡히면 ATR·GK변동성이 낮게 읽히고, 변동성 타깃 사이징의
분모가 작아져 **목표보다 큰 비중**이 실린다. 그리고 오디션은 완성 봉으로만
평가하니 '선발되는 조건'과 '실전 조건'이 달랐다 — 오늘 하루 고쳐 온 격차와
같은 계열이다.

규칙: **완성된 정보로 판단하고, 지금 가격에 체결한다.** 실제 트레이더가
하는 것과 같다. 대가는 마지막 몇 시간의 가격 움직임을 신호가 못 본다는
것이고, 그건 오디션과 조건을 맞추기 위해 치르는 값이다.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.live import daily as dl  # noqa: E402


def _frame(n=300, end=None, seed=5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.02, n)))
    end = end or pd.Timestamp(dt.datetime.now(dt.timezone.utc).date())
    idx = pd.date_range(end=end, periods=n, freq="D")
    return pd.DataFrame({"open": close * 0.99, "high": close * 1.03,
                         "low": close * 0.97, "close": close,
                         "volume": 1e6}, index=idx)


# ── ① 진행 중인 봉만 골라서 뺀다 ──────────────────────────────


def test_drops_only_the_in_progress_bar_for_continuous_markets():
    df = _frame()                       # 마지막 봉 = 오늘(진행 중)
    assert len(dl._signal_frame("crypto", df)) == len(df) - 1
    # 주식은 제공자가 이미 완성 봉만 준다 — 건드리지 않는다
    for m in ("us_stock", "kr_stock", "synthetic"):
        assert len(dl._signal_frame(m, df)) == len(df), m


def test_leaves_the_frame_alone_when_the_last_bar_is_closed():
    """어제까지의 데이터라면 뺄 것이 없다."""
    df = _frame(end=pd.Timestamp(dt.date.today() - dt.timedelta(days=1)))
    assert len(dl._signal_frame("crypto", df)) == len(df)


def test_never_empties_a_tiny_frame():
    df = _frame(n=1)
    assert len(dl._signal_frame("crypto", df)) == 1


# ── ② 판단은 완성 봉, 체결은 지금 가격 ────────────────────────


class _P:
    def __init__(self, df):
        self._df = df

    def get_ohlcv(self, *a, **k):
        return self._df.copy()


class _Last:
    """마지막으로 본 프레임을 기록하는 전략 — 무엇을 보고 판단했는지 확인용."""

    name = "fixed"
    allow_short = False

    def __init__(self):
        self.seen: list[pd.DataFrame] = []

    def generate_signals(self, df):
        self.seen.append(df)
        return pd.Series(0.9, index=df.index)


def _run_portfolio(monkeypatch, tmp_path, df, market="crypto"):
    strat = _Last()
    monkeypatch.setattr("quant.data.get_provider", lambda m: _P(df))
    monkeypatch.setattr(dl, "champion_strategy", lambda *a, **k: strat)
    monkeypatch.setattr(dl, "champion_spec",
                        lambda *a, **k: {"strategy": "fixed", "params": {}})
    dl.run_daily_portfolio([(market, "AAA")], state_dir=str(tmp_path),
                           require_real_data=False)
    st = json.loads((tmp_path / "paper" / "portfolio_ALL.json")
                    .read_text(encoding="utf-8"))
    return strat, st["history"][-1]


def test_signal_sees_closed_bars_but_price_is_the_live_mark(monkeypatch,
                                                            tmp_path):
    """모델은 어제까지, 체결가는 지금 — 둘이 각자 옳은 값을 봐야 한다."""
    df = _frame()
    strat, rec = _run_portfolio(monkeypatch, tmp_path, df)

    assert strat.seen, "전략이 호출되지 않았다"
    seen = strat.seen[0]
    assert len(seen) == len(df) - 1, "모델이 진행 중인 봉을 봤다"
    assert seen.index[-1] == df.index[-2]

    # 체결·평가는 지금 값(진행 중 봉의 종가)이어야 한다 — 어제 종가가 아니라
    assert rec["fills"], "코인은 즉시 체결이어야 한다"
    assert rec["fills"][0]["price"] == round(float(df["close"].iloc[-1]), 6), (
        "체결가가 지금 가격이 아니다 — 어제 종가로 체결하면 실현 불가")


def test_stock_path_is_unchanged(monkeypatch, tmp_path):
    """주식은 이미 완성 봉만 오므로 이 변경의 영향을 받지 않는다."""
    df = _frame()
    strat, _ = _run_portfolio(monkeypatch, tmp_path, df, market="us_stock")
    assert len(strat.seen[0]) == len(df)


def test_partial_bar_is_still_disclosed_in_the_ledger(monkeypatch, tmp_path):
    """판단에서 뺐다고 사실을 숨기지는 않는다 — 완성도는 계속 기록한다."""
    df = _frame()
    _, rec = _run_portfolio(monkeypatch, tmp_path, df)
    assert rec.get("bar_partial"), "진행 중 봉이었다는 사실이 장부에서 사라졌다"


# ── ③ 오디션과 실전이 같은 조건을 본다 ────────────────────────


def test_live_and_audition_now_see_the_same_kind_of_bar():
    """오디션(백테스트)은 완성 봉으로 평가한다. 실전도 같아야 한다.

    이 검사가 지키는 것은 숫자가 아니라 **조건의 동일성**이다: 실전 신호를
    낸 프레임의 마지막 봉이 완성 봉이면, 오디션이 보던 것과 같은 종류다.
    """
    from quant.data.barclock import bar_status

    df = _frame()
    sig = dl._signal_frame("crypto", df)
    assert bar_status("crypto", sig.index[-1]) is None, (
        "신호 프레임의 마지막 봉이 아직 진행 중이다 — 오디션 조건과 다르다")
