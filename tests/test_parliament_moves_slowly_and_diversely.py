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


def _stub_backtester(monkeypatch, returns_by_name: dict,
                     idle: set | None = None) -> None:
    """의원별 홀드아웃 수익률을 손으로 정해 준다 — 점수를 결정적으로 만든다.

    idle에 든 이름은 '채점 구간 내내 무포지션'인 의원을 흉내 낸다 —
    전략이 아니라 현금인 의원(2026-08-14).
    """
    import quant.backtest as B

    idle = idle or set()

    class _Res:
        def __init__(self, r, flat: bool):
            self.returns = r
            # 실제 Backtester 결과에는 positions가 있다. 스텁에 없어서
            # '무포지션 의원' 가드를 검사할 수 없었다.
            self.positions = pd.Series(
                0.0 if flat else 1.0, index=r.index)

    class _Fake:
        def __init__(self, strat, **kw):
            self._name = getattr(strat, "name", "?")

        def run(self, df):
            return _Res(returns_by_name[self._name], self._name in idle)

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
    # ⚠️ 완전한 상수 계열을 쓰지 않는다(2026-08-14). 상수끼리는 상관이
    #    **NaN**이고, 다양성 게이트는 NaN을 '중복'으로 본다(감사 53의 규칙).
    #    즉 상수 픽스처는 이 검사의 주제(EMA 감쇠)와 무관한 이유로 의석을
    #    잃게 만든다. 매매 전략의 일별 수익이 소수점까지 똑같은 일은 없으므로,
    #    아주 작은 독립 잡음을 얹어 **픽스처를 현실에 맞춘다**(둘의 상관은
    #    여전히 0 근처라 다양성 판정에는 영향이 없다).
    _n = np.random.default_rng(11).normal(0, 1e-4, len(IDX))
    _m = np.random.default_rng(12).normal(0, 1e-4, len(IDX))
    win = pd.Series(0.01 + _n, index=IDX)      # 꾸준히 +1%/일
    lose = pd.Series(-0.005 + _m, index=IDX)   # 꾸준히 -0.5%/일
    assert abs(float(win.corr(lose))) < 0.5, "전제가 깨졌다 — 두 계열이 닮았다"
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
    # 상수 계열은 상관이 NaN이라 다양성 게이트에 걸린다 — 위 검사와 같은
    # 이유로 아주 작은 독립 잡음을 얹는다(주제는 EMA 한 걸음의 크기다).
    _n = np.random.default_rng(11).normal(0, 1e-4, len(IDX))
    _m = np.random.default_rng(12).normal(0, 1e-4, len(IDX))
    win = pd.Series(0.01 + _n, index=IDX)
    lose = pd.Series(-0.005 + _m, index=IDX)
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


# ── ㉕ 주석이 막겠다던 그 경로가 실제로 열려 있었다 (2026-08-14) ──────

"""감사 53은 "상관을 못 재면 무상관(0)이 아니라 중복(1)으로 본다"고 적고
`except` 분기를 뒀다. 그런데 **pandas의 corr는 한쪽이 상수여도 예외를 던지지
않고 조용히 NaN을 돌려준다.** 판정이 `c == c and c > CORR_CAP`이라 NaN은
`c == c`에서 False가 되어 '중복 아님'으로 통과했다 — 주석이 막겠다고 적어 둔
바로 그 방향으로 열려 있었던 셈이다.

기존 검사는 **예외를 던지는** 가짜 계열(_NoCorr)로만 확인해서 이 구멍을
보지 못했다. 예외는 드문 경로고, NaN이 흔한 경로다."""


def test_a_nan_correlation_is_treated_as_duplicate(monkeypatch):
    """예외가 아니라 NaN으로 오는 경로 — 실제로 일어나는 쪽."""
    # NaN이 나오는 모양: **한쪽의 분산이 정확히 0**이다(실측 2026-08-14,
    # 삼성전자 — 챔피언 std=0.0029 · 상대 std=0 → corr NaN).
    #
    # 실전에서 이 모양은 대개 '한 번도 매매하지 않은 의원'이고, 그건 아래
    # ㉖의 무포지션 가드가 먼저 잡는다. 여기서는 포지션은 있는데 수익이
    # 상수인 경우(가격이 안 움직인 구간 등)를 가정해 **NaN 판정 자체**만
    # 떼어 확인한다 — 두 겹으로 막는다.
    rng = np.random.default_rng(9)
    a = pd.Series(rng.normal(0.001, 0.01, len(IDX)), index=IDX)
    b = pd.Series(0.0, index=IDX)
    assert pd.isna(a.corr(b)), "전제가 깨졌다 — pandas가 NaN을 안 준다"
    _stub_backtester(monkeypatch, {"A": a, "B": b})   # idle 아님(포지션 있음)

    out = update_parliament(_entry(("A", 0.5), ("B", 0.5)), _df(),
                            build=_build, confirm_window=120)
    assert len(out) == 1, (
        f"상관이 NaN인데 두 의원이 다 남았다: {[m['strategy'] for m in out]} — "
        "다양성 강제가 '측정 실패 = 통과'로 열려 있다")


def test_the_guard_is_not_a_trap_for_measurable_pairs(monkeypatch):
    """반대 방향 — 잴 수 있고 낮으면 두 자리를 준다(FROZEN_IDEAS ④)."""
    rng = np.random.default_rng(3)
    a = pd.Series(rng.normal(0.001, 0.01, len(IDX)), index=IDX)
    b = pd.Series(rng.normal(0.001, 0.01, len(IDX)), index=IDX)
    _stub_backtester(monkeypatch, {"A": a, "B": b})
    out = update_parliament(_entry(("A", 0.5), ("B", 0.5)), _df(),
                            build=_build, confirm_window=120)
    assert len(out) == 2


# ── ㉖ 아무 베팅도 안 한 의원은 전략이 아니라 현금이다 ────────────

"""의석은 '이 전략에 책의 몇 %를 맡긴다'는 뜻이다. 채점 구간 내내 포지션이
없던 의원에게 의석을 주면 그 비중만큼 책이 조용히 현금으로 가고, 장부에는
"의회가 그렇게 배분했다"고 적힌다. 오디션 링에서 뺀 '무효 후보'와 같은 부류다.

실측(2026-08-14, 삼성전자 800봉): 승격 후보가 채점 구간 120봉에서 한 번도
포지션을 갖지 않았는데 **34% 의석**을 받았다."""


def test_a_member_that_never_took_a_position_gets_no_seat(monkeypatch):
    rng = np.random.default_rng(5)
    live = pd.Series(rng.normal(0.001, 0.01, len(IDX)), index=IDX)
    flat = pd.Series(0.0, index=IDX)
    _stub_backtester(monkeypatch, {"A": live, "B": flat}, idle={"B"})

    out = update_parliament(_entry(("A", 0.5), ("B", 0.5)), _df(),
                            build=_build, confirm_window=120)
    names = [m["strategy"] for m in out]
    assert names == ["A"], (
        f"무포지션 의원이 의석을 가졌다: {names} — 그 비중만큼 책이 조용히 "
        "현금이 되고 장부에는 '의회 배분'이라 적힌다")
    assert out[0]["weight"] == 1.0


def test_an_all_idle_parliament_still_returns_something(monkeypatch):
    """전원이 무포지션이어도 의회가 빈 채로 돌아오면 안 된다(매매가 멈춘다)."""
    flat = pd.Series(0.0, index=IDX)
    _stub_backtester(monkeypatch, {"A": flat, "B": flat}, idle={"A", "B"})
    out = update_parliament(_entry(("A", 0.5), ("B", 0.5)), _df(),
                            build=_build, confirm_window=120)
    assert out, "의회가 통째로 비었다 — 다음 사이클에 배분할 대상이 없다"


def test_an_idle_member_cannot_outrank_and_evict_a_losing_one():
    """무포지션 의원이 **지고 있는 의원을 밀어내고** 책을 통째로 현금으로 만든다.

    이게 무포지션 가드가 따로 필요한 이유다. 점수는 구간 수익률이라
    무포지션 의원은 정확히 0점이다. 손실 중인 의원(-)보다 **높다.**
    그러면 순위 1등이 되어 먼저 의석을 잡고, 뒤이어 채점되는 진짜 의원은
    무포지션 의원과의 상관이 NaN이라 '중복'으로 탈락한다.

    결과: 그날 책 100%가 아무것도 하지 않는 의원에게 간다 = 전액 현금.
    장부에는 "의회가 그렇게 배분했다"고 적힌다. 하락장에서 정확히 이 조합이
    나온다(챔피언이 손실 중 + 신입이 아직 진입 안 함).
    """
    import quant.backtest as B

    live = pd.Series(-0.002, index=IDX)      # 지고 있는 진짜 의원
    flat = pd.Series(0.0, index=IDX)         # 아무것도 안 하는 의원

    class _Res:
        def __init__(self, r, f):
            self.returns = r
            self.positions = pd.Series(0.0 if f else 1.0, index=r.index)

    class _Fake:
        def __init__(self, strat, **kw):
            self._n = getattr(strat, "name", "?")

        def run(self, df):
            return (_Res(flat, True) if self._n == "IDLE"
                    else _Res(live, False))

    import pytest as _pt
    mp = _pt.MonkeyPatch()
    try:
        mp.setattr(B, "Backtester", _Fake)
        out = update_parliament(_entry(("LIVE", 0.5), ("IDLE", 0.5)), _df(),
                                build=_build, confirm_window=120)
    finally:
        mp.undo()

    names = [m["strategy"] for m in out]
    assert "IDLE" not in names, (
        f"무포지션 의원이 의석을 잡았다: {names} — 0점이 손실(-)보다 높아 "
        "1등이 되고, 진짜 의원은 NaN 상관으로 밀려난다. 책이 전액 현금이 된다")
    assert names == ["LIVE"], names
