"""의회의 두 안전장치가 **아무도 안 지키고 있었다** (감사 123·124).

의회(parliament)는 실제로 돈을 굴리는 혼합 전략이다. 어제의 챔피언 하나가
전액을 굴리지 않도록 최대 3명에게 의석을 나눠 주고, 매일 밤 홀드아웃
성과로 그 비중을 조정한다. 두 개의 브레이크가 달려 있다.

    ㉓ EMA 감쇠   — 하루에 목표 비중 쪽으로 EMA_STEP(25%)만 이동한다.
                    없으면 어제 잘한 전략이 **하룻밤에 전액**을 가져간다.
                    그러면 의회를 만든 이유(교체 순간의 급변 방지)가 사라지고,
                    회전율이 폭발하며, 하루짜리 우연이 곧 전 재산이 된다.

    ㉔ 상관 실패 = 중복 — 두 의원의 홀드아웃 수익률 상관을 못 재면 '무상관'이
                    아니라 '중복'으로 본다(감사 53에서 고친 규칙). 0으로 치면
                    **계산 실패가 곧 통과**가 되어, 다양성 강제 장치가
                    하필 흔들리는 날에 정반대로 동작한다.

변이 시험 결과 둘 다 무방비였다.

    w = (1 - EMA_STEP) * prev + EMA_STEP * target   →   w = target      ❌
    c = 1.0  (상관 계산 실패 시)                    →   c = 0.0         ❌

기존 `test_parliament.py`는 신입 의석 상한을 `ENTRY_WEIGHT + 0.35`(=0.60)로
느슨하게 봤다 — EMA를 꺼도 목표 비중이 0.60 아래면 그냥 통과한다. 그리고
상관 실패 경로는 **한 번도 실행된 적이 없다**(예외를 일으키는 검사가 없다).

감사 120·121·122와 같은 계열이다: 규칙은 옳게 적혀 있고, 그 규칙이 지켜지는지
확인하는 사람이 없었다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.live.parliament import (  # noqa: E402
    EMA_STEP,
    MIN_WEIGHT,
    update_parliament,
)

IDX = pd.date_range("2025-01-01", periods=200, freq="D")


def _df() -> pd.DataFrame:
    close = pd.Series(np.linspace(100, 130, len(IDX)), index=IDX)
    return pd.DataFrame({"open": close, "high": close, "low": close,
                         "close": close, "volume": 1.0}, index=IDX)


def _stub_backtester(monkeypatch, returns_by_name: dict) -> None:
    """의원별 홀드아웃 수익률을 손으로 정해 준다 — 점수를 결정적으로 만든다."""
    import quant.backtest as B

    class _Res:
        def __init__(self, r):
            self.returns = r

    class _Fake:
        def __init__(self, strat, **kw):
            self._name = getattr(strat, "name", "?")

        def run(self, df):
            return _Res(returns_by_name[self._name])

    monkeypatch.setattr(B, "Backtester", _Fake)


def _build(spec):
    class _S:
        name = spec["strategy"]
    return _S()


def _entry(*pairs) -> dict:
    ms = [{"strategy": n, "params": {}, "weight": w} for n, w in pairs]
    return {"strategy": ms[0]["strategy"], "params": {}, "parliament": ms}


# ── ㉓ 하룻밤에 전액이 옮겨 가지 않는다 ─────────────────────────


def test_one_good_night_does_not_hand_over_the_whole_book(monkeypatch):
    """A가 압도적으로 잘해도, 하루 만에 B의 의석을 다 뺏을 수는 없다."""
    win = pd.Series(0.01, index=IDX)          # 꾸준히 +1%/일
    lose = pd.Series(-0.005, index=IDX)       # 꾸준히 -0.5%/일
    _stub_backtester(monkeypatch, {"A": win, "B": lose})

    out = update_parliament(_entry(("A", 0.5), ("B", 0.5)), _df(),
                            build=_build, confirm_window=120)
    got = {m["strategy"]: m["weight"] for m in out}

    assert set(got) == {"A", "B"}, (
        f"하룻밤 만에 의석이 사라졌다: {got} — EMA 감쇠가 없으면 목표 비중이 "
        f"0이 된 의원은 곧바로 MIN_WEIGHT({MIN_WEIGHT}) 아래로 떨어진다")
    assert got["A"] > 0.5, "이겼는데 비중이 안 늘었다 — 조정이 아예 안 된다"
    assert got["A"] <= 0.85, (
        f"하룻밤에 {got['A']:.0%}까지 갔다 — 급변 방지가 동작하지 않는다")


def test_the_step_is_a_fraction_of_the_gap_not_the_whole_gap(monkeypatch):
    """이동 폭이 '목표까지의 거리 × EMA_STEP' 언저리인가 (정규화 전 기준).

    부등식만 걸면 EMA_STEP을 0.9로 키워도 통과한다. 감쇠가 **실제로
    얼마나** 잡아 주는지를 못 박는다.
    """
    win = pd.Series(0.01, index=IDX)
    lose = pd.Series(-0.005, index=IDX)
    _stub_backtester(monkeypatch, {"A": win, "B": lose})

    out = update_parliament(_entry(("A", 0.5), ("B", 0.5)), _df(),
                            build=_build, confirm_window=120)
    got = {m["strategy"]: m["weight"] for m in out}
    # 정규화 전: A = 0.5 + EMA_STEP*(1-0.5), B = 0.5 - EMA_STEP*0.5
    raw_a = 0.5 + EMA_STEP * 0.5
    raw_b = 0.5 * (1 - EMA_STEP)
    expect = raw_a / (raw_a + raw_b)
    assert abs(got["A"] - expect) < 0.02, (
        f"한 걸음의 크기가 EMA_STEP({EMA_STEP})과 맞지 않는다: "
        f"{got['A']:.4f} vs 기대 {expect:.4f}")


# ── ㉔ 상관을 못 재면 '중복'으로 본다 ───────────────────────────


class _NoCorr(pd.Series):
    """상관 계산이 실패하는 수익률 계열 — 실제로 일어나는 일이다.

    (표본이 어긋나거나, 한쪽이 전부 결측이거나, 인덱스가 겹치지 않을 때.)
    """

    @property
    def _constructor(self):
        return _NoCorr

    def corr(self, *a, **k):
        raise RuntimeError("상관 계산 실패")


def test_an_unmeasurable_correlation_is_treated_as_duplicate(monkeypatch):
    """실패가 곧 통과가 되면 안 된다 — 같은 베팅에 두 자리를 주게 된다."""
    a = _NoCorr(np.linspace(0.01, 0.02, len(IDX)), index=IDX)
    b = _NoCorr(np.linspace(-0.01, 0.03, len(IDX)), index=IDX)
    _stub_backtester(monkeypatch, {"A": a, "B": b})

    out = update_parliament(_entry(("A", 0.5), ("B", 0.5)), _df(),
                            build=_build, confirm_window=120)
    assert len(out) == 1, (
        f"상관을 못 쟀는데 두 의원이 다 남았다: {[m['strategy'] for m in out]} — "
        "계산 실패가 다양성 강제를 통과시킨다")


def test_a_measurable_low_correlation_keeps_both_seats(monkeypatch):
    """반대 방향도 확인 — 안전장치가 덫이 되면 안 된다(FROZEN_IDEAS ④)."""
    rng = np.random.default_rng(7)
    a = pd.Series(rng.normal(0.001, 0.01, len(IDX)), index=IDX)
    b = pd.Series(rng.normal(0.001, 0.01, len(IDX)), index=IDX)
    assert abs(float(a.corr(b))) < 0.5, "전제가 깨졌다 — 두 계열이 닮았다"
    _stub_backtester(monkeypatch, {"A": a, "B": b})

    out = update_parliament(_entry(("A", 0.5), ("B", 0.5)), _df(),
                            build=_build, confirm_window=120)
    assert len(out) == 2, "상관이 낮은데도 의석을 뺏는다 — 다양성 강제가 덫이 됐다"
