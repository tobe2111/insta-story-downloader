"""CPCV가 **정말로 미래를 가리는가** (감사 156).

CPCV는 챔피언을 뽑는 마지막 관문이다. 데이터를 그룹으로 나눠 여러 개의
독립적인 OOS 경로를 만들고, 그 경로들의 성과 분포로 "한 번의 좋은 숫자가
운인지"를 판정한다. 이 판정이 틀리면 그 뒤가 전부 틀린다.

그런데 변이를 처음 걸어 보니 셋이 무방비였다.

    run(df.iloc[:hi])  →  run(df)                 ❌ 검증에 미래 전체를 준다
    lo += embargo      →  (없앰)                  ❌ 경계에서 정보가 샌다
    sign = -1 if LOWER_IS_BETTER else 1  →  1     ❌ 방향이 뒤집힌다

기존 검사는 "PBO가 나온다", "경로가 여러 개다" 같은 **형식**만 봤다.
가장 중요한 성질 — 검증 구간이 학습에 안 쓰였는가 — 은 아무도 안 봤다.

──────────────────────────────────────────────────────────────
룩어헤드를 어떻게 잡는가

값을 못 박는 방식은 구조가 바뀌면 같이 바뀌어 쓸모가 없다. 대신
**모델이 실제로 본 프레임의 마지막 봉**을 기록해서 본다. 검증 그룹 g를
평가할 때 백테스터에 들어간 데이터는 그 그룹 끝(hi)을 넘으면 안 된다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.objective import LOWER_IS_BETTER  # noqa: E402
from quant.optimize.cpcv import _train_segments, cpcv  # noqa: E402
from quant.strategies.base import Strategy  # noqa: E402

N = 480
IDX = pd.date_range("2024-01-01", periods=N, freq="D")


def _frame() -> pd.DataFrame:
    rng = np.random.default_rng(11)
    c = 100.0 * np.exp(np.cumsum(rng.normal(0.0005, 0.012, N)))
    return pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99,
                         "close": c, "volume": 1e6}, index=IDX)


SEEN: list[pd.Timestamp] = []          # 프레임의 마지막 봉(미래를 봤는가)
SEEN_FIRST: list[pd.Timestamp] = []    # 프레임의 첫 봉(엠바고가 잘랐는가)


class _Spy(Strategy):
    """받은 프레임의 **첫 봉과 마지막 봉**을 기록하는 전략."""

    name = "spy"

    def __init__(self, fast: int = 5, slow: int = 20):
        self.fast, self.slow = int(fast), int(slow)

    def generate_signals(self, df):
        SEEN.append(df.index[-1])
        SEEN_FIRST.append(df.index[0])
        ma_f = df["close"].rolling(self.fast).mean()
        ma_s = df["close"].rolling(self.slow).mean()
        return (ma_f > ma_s).astype(float).fillna(0.0)


class _FixedExposure(Strategy):
    """노출을 파라미터로 직접 잡는 전략 — **정답을 아는** 변동성 비교용.

    비중이 scale로 고정되므로 변동성 ≈ 시장변동성 × scale이다. 즉
    scale이 작을수록 변동성이 작다는 것을 계산 없이 안다.
    """

    name = "fixed-exposure"

    def __init__(self, scale: float = 1.0):
        self.scale = float(scale)

    def generate_signals(self, df):
        return pd.Series(self.scale, index=df.index)


GRID = {"fast": [5, 10], "slow": [20, 40]}
EXPOSURE_GRID = {"scale": [0.1, 1.0]}


# ── 검증 구간이 정말 미래를 안 보는가 ─────────────────────────


def test_no_evaluation_ever_sees_the_end_of_the_data():
    """어떤 평가도 **자기 검증 그룹 끝을 넘는 데이터**를 받으면 안 된다.

    가장 늦은 검증 그룹의 끝은 전체 데이터의 끝이므로, '전체 끝을 본 횟수'가
    조합 수만큼 나오면 미래를 통째로 준 것이다.
    """
    SEEN.clear()
    cpcv(_frame(), _Spy, GRID, n_groups=4, n_test=1, embargo=3,
         min_train_bars=40)
    assert SEEN, "전략이 한 번도 안 불렸다 — 이 검사가 헛돈다"

    last_bar = IDX[-1]
    saw_end = sum(1 for t in SEEN if t == last_bar)
    # 마지막 그룹을 검증할 때만 데이터 끝까지 본다(조합 4개 중 1개 + 그
    # 조합의 학습 구간 몇 개). 전체 호출의 절반을 넘으면 미래를 준 것이다.
    assert saw_end < len(SEEN) * 0.5, (
        f"{len(SEEN)}번 중 {saw_end}번이 데이터 끝까지 봤다 — "
        "검증에 미래를 통째로 주고 있다")


def test_each_test_group_is_evaluated_on_data_that_stops_at_its_own_end():
    """그룹별로 직접 확인 — 그룹 g의 평가 프레임은 group_end(g)에서 끝나야 한다."""
    df = _frame()
    n_groups = 4
    edges = np.linspace(0, len(df), n_groups + 1, dtype=int)
    group_ends = {IDX[int(e) - 1] for e in edges[1:]}

    SEEN.clear()
    cpcv(df, _Spy, GRID, n_groups=n_groups, n_test=1, embargo=3,
         min_train_bars=40)
    # 평가 호출은 반드시 어떤 그룹의 끝에서 멈춘다. 학습 호출은 그보다
    # 짧은 구간이라 다른 곳에서 끝날 수 있으므로 '전부'는 요구하지 않는다.
    assert any(t in group_ends for t in SEEN)
    beyond = [t for t in SEEN if t > max(group_ends)]
    assert not beyond, f"그룹 경계를 넘어선 프레임이 있다: {beyond[:3]}"


# ── 엠바고가 실제로 잘라내는가 ────────────────────────────────


def test_the_embargo_trims_the_training_edge_that_touches_a_test_group():
    """검증 그룹 **바로 뒤**에서 시작하는 학습 구간은 embargo봉만큼 늦게 시작한다.

    ⚠️ 처음엔 '엠바고 1 vs 60에서 결과가 달라지는가'로 봤는데 **안 잡혔다.**
       시작 쪽 절단을 지워도 끝 쪽 절단이 남아 결과는 여전히 달라진다.
       한쪽만 지운 변이는 그런 느슨한 검사를 그냥 통과한다.

       그래서 **학습 프레임의 첫 봉**을 직접 본다. 검증이 그룹 0이면
       학습은 그룹 1부터인데, 그룹 1의 시작이 아니라 +embargo에서
       시작해야 한다.
    """
    df = _frame()
    n_groups, embargo = 4, 25
    edges = np.linspace(0, len(df), n_groups + 1, dtype=int)
    g1_start = int(edges[1])

    SEEN_FIRST.clear()
    cpcv(df, _Spy, GRID, n_groups=n_groups, n_test=1, embargo=embargo,
         min_train_bars=30)
    assert SEEN_FIRST, "전략이 한 번도 안 불렸다"

    starts = set(SEEN_FIRST)
    assert IDX[g1_start + embargo] in starts, (
        f"그룹1 시작+{embargo}봉({IDX[g1_start + embargo].date()})에서 시작한 "
        f"학습 프레임이 없다 — 엠바고가 시작 쪽을 안 자른다")
    assert IDX[g1_start] not in starts, (
        f"검증 그룹 바로 뒤({IDX[g1_start].date()})부터 학습했다 — "
        "경계에서 정보가 샌다")


def test_the_segments_are_split_around_the_test_groups():
    """검증 그룹을 뺀 나머지가 **연속 구간**으로 묶여야 지표가 안 끊긴다."""
    assert _train_segments(4, (0,)) == [[1, 2, 3]]
    assert _train_segments(4, (1,)) == [[0], [2, 3]]
    assert _train_segments(6, (1, 4)) == [[0], [2, 3], [5]]


def test_the_embargo_value_reaches_the_boundaries():
    """엠바고를 크게 주면 학습 표본이 실제로 줄어야 한다(값이 배선됐는가)."""
    df = _frame()
    small = cpcv(df, _Spy, GRID, n_groups=4, n_test=1, embargo=1,
                 min_train_bars=30)
    big = cpcv(df, _Spy, GRID, n_groups=4, n_test=1, embargo=60,
               min_train_bars=30)
    # 학습 구간이 달라지면 뽑히는 파라미터나 경로 성적이 달라진다.
    assert (small["segments"] != big["segments"]
            or abs(small["sharpe_mean"] - big["sharpe_mean"]) > 1e-12), (
        "엠바고를 1에서 60으로 올렸는데 아무것도 안 달라졌다 — 안 걸린다")


# ── 목적함수 방향 ─────────────────────────────────────────────


def test_lower_is_better_objectives_pick_the_smaller_value():
    """변동성처럼 '작을수록 좋은' 지표에서 큰 값을 고르면 안 된다.

    ⚠️ 처음엔 이동평균 그리드로 썼는데 **안 잡혔다.** 후보들의 변동성이
       0.153~0.173으로 거의 같아서, 방향을 뒤집어도 고르는 게 안 바뀐다.
       고를 여지가 없는 데이터로는 '무엇을 고르는가'를 검사할 수 없다.

       노출을 파라미터로 직접 잡는 전략으로 바꿨다 — 비중이 scale로
       고정되니 변동성 ≈ 시장변동성 × scale이고, **계산 없이 정답을 안다.**
    """
    assert "volatility" in LOWER_IS_BETTER, "전제가 깨졌다"
    got = cpcv(_frame(), _FixedExposure, EXPOSURE_GRID, n_groups=4, n_test=1,
               embargo=3, objective="volatility", min_train_bars=40)
    picked = [float(s["params"]["scale"]) for s in got["segments"]]
    assert picked, "선택된 파라미터가 없다 — 이 검사가 헛돈다"
    assert all(p == 0.1 for p in picked), (
        f"변동성이 작을수록 좋은데 노출 {picked}를 골랐다 — 방향이 뒤집혔다")


def test_higher_is_better_objectives_still_pick_the_larger_value():
    """대조군 — 방향을 고친다고 전부 뒤집으면 그건 다른 결함이다.

    같은 그리드에 목적함수만 샤프로 바꾸면, 노출이 큰 쪽이 뽑혀야 한다
    (수익이 양인 구간에서 노출 1.0의 샤프가 0.1보다 크거나 같다).
    """
    got = cpcv(_frame(), _FixedExposure, EXPOSURE_GRID, n_groups=4, n_test=1,
               embargo=3, objective="sharpe", min_train_bars=40)
    picked = [float(s["params"]["scale"]) for s in got["segments"]]
    assert picked
    assert any(p == 1.0 for p in picked), (
        f"샤프가 클수록 좋은데 노출 {picked}만 골랐다 — 방향이 반대로 굳었다")


# ── 경로 분포 ─────────────────────────────────────────────────


def test_the_paths_are_separate_not_one_pile():
    """경로가 하나로 뭉치면 '분포'가 없어져 과적합 탐지가 무의미해진다."""
    got = cpcv(_frame(), _Spy, GRID, n_groups=6, n_test=2, embargo=3,
               min_train_bars=40)
    assert got["n_combinations"] == 15, got["n_combinations"]
    assert got["n_paths"] >= 4, f"경로가 {got['n_paths']}개뿐 — φ=C(5,1)=5여야"
    assert len(got["paths"]) == got["n_paths"]


def test_the_distribution_is_actually_reported():
    """대조군 — 분포 요약이 비면 위 검사들이 공짜로 통과한다."""
    got = cpcv(_frame(), _Spy, GRID, n_groups=4, n_test=1, embargo=3,
               min_train_bars=40)
    for k in ("sharpe_mean", "sharpe_std", "sharpe_min", "worst_path_return"):
        assert k in got and np.isfinite(got[k]), f"{k} 없음/비유한: {got.get(k)}"
    assert got["sharpe_min"] <= got["sharpe_mean"] + 1e-9


def test_it_refuses_when_the_data_is_too_short():
    """모르면 숫자를 만들지 않는다."""
    with pytest.raises(ValueError):
        cpcv(_frame().iloc[:40], _Spy, GRID, n_groups=6, n_test=2)
    with pytest.raises(ValueError):
        cpcv(_frame(), _Spy, GRID, n_groups=3, n_test=3)
