"""데이터 누수(look-ahead) 자동 탐지 테스트.

원리: 룩어헤드가 없는 전략이라면 시점 t의 신호는 '그 이전' 데이터에만
의존한다. 따라서 데이터를 뒤에서 잘라(미래를 없애) 다시 계산해도, 겹치는
과거 구간의 신호는 '완전히 동일'해야 한다. 만약 미래 정보가 지표·라벨 계산에
새어들면, 미래를 잘라냈을 때 과거 신호가 바뀌므로 이 테스트가 잡아낸다.

이 테스트는 새 전략/피처를 추가할 때 미래 참조 버그를 CI에서 자동으로
막아주는 안전망이다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.data import SyntheticDataProvider
from quant.strategies import (
    adaptive_ensemble,
    default_ensemble,
    get_strategy,
    list_strategies,
)

_DF = SyntheticDataProvider(seed=17).get_ohlcv("LEAK", "1d", limit=420)

# ⚠️ 절단점은 **여럿**이어야 한다(2026-08-12 감사 108).
#    1봉 룩어헤드는 절단 계열의 **경계 봉 하나만** 바꾼다. 그런데 신호는
#    대개 0/±1로 뭉툭해서, 그 한 봉이 우연히 같으면 차이가 0이 되어
#    통과한다. 절단점이 하나뿐이면 그 우연이 한 번만 맞으면 되지만,
#    여럿이면 매번 맞아야 하므로 확률이 급격히 떨어진다.
#
#    ⚠️ 정직한 한계: 이 방법으로도 **못 잡는 누수**가 있다. breakout의
#    `upper`에 `shift(-1)`을 심어 실측했더니 신호가 420봉 전부 0이 됐다
#    (미래 고가를 보면 종가가 그 위로 못 올라가 진입 조건이 영영 성립하지
#    않는다). 신호가 상수가 되면 절단해도 달라질 것이 없어 어떤 절단점도
#    차이를 못 만든다. 다만 그 방향의 누수는 **거래를 못 하게 만들 뿐
#    성적을 부풀리지 않아** 위험하지 않다.
#
#    ⚠️ 그런데 **성적을 부풀리는 종류도 못 잡았다.** `close.shift(-1)`을
#    심어 돌렸더니 절단점 9개에서 전부 통과했다(2026-08-12 실측).
#    이유는 같다 — 전체를 한 칸 당기면 절단 계열과 원본이 **경계 봉
#    하나에서만** 달라지고, 그 한 봉의 신호가 우연히 같으면 끝이다.
#    절단점을 늘려도 매번 같은 이유로 숨는다.
#
#    즉 이 탐지기는 **여러 봉을 한꺼번에 바꾸는 누수**(피처 전체가 미래
#    구간 통계를 쓰는 등)에는 강하지만, **1봉 시프트**에는 약하다.
#    파일 첫머리의 "새 전략을 추가할 때 미래 참조 버그를 자동으로
#    막아준다"는 설명은 그만큼 넓지 않다 — 미해결로 남기고 사장님께
#    보고했다. 고치려면 신호 비교가 아니라 '미래 구간을 무작위로 바꿔도
#    과거 신호가 불변인가'를 봐야 한다(다음 감사 과제).
_CUTS = (200, 240, 280, 300, 320, 340, 360, 380, 400)


def _assert_no_lookahead(make_strategy, name: str):
    """인과성 검사 — **절단**과 **교란** 두 가지로 본다.

    ① 절단: 미래를 잘라도 과거 신호가 같아야 한다.
    ② 교란: 미래 구간의 값을 **크게 바꿔도** 과거 신호가 같아야 한다.

    ②가 2026-08-12(감사 108)에 추가됐다. ①만으로는 **1봉 시프트를 놓친다** —
    전체를 한 칸 당기는 누수는 절단 계열과 원본이 경계 봉 하나에서만
    달라지고, 그 한 봉의 신호가 우연히 같으면 차이가 0이 된다. 실측에서
    `close.shift(-1)`(성적을 부풀리는 종류)이 절단점 9개를 전부 통과했다.

    ②는 미래 구간 전체를 1.5배로 옮긴다. 인과적 전략이라면 과거 신호가
    한 봉도 바뀌지 않아야 하고, 미래를 한 칸이라도 당겨 보면 경계 봉의
    입력이 **실제로 달라져** 신호가 흔들린다. OHLC를 같은 배수로 곱하므로
    고가≥종가 같은 정합성은 그대로 유지된다.
    """
    full = make_strategy().generate_signals(_DF)
    for cut in _CUTS:
        _compare_at(full, make_strategy, name, cut)
        _compare_perturbed(full, make_strategy, name, cut)


def _diff(a, b, cut: int) -> int:
    a, b = a.iloc[:cut].to_numpy(), b.iloc[:cut].to_numpy()
    assert len(a) == len(b) == cut
    return int(np.sum(~np.isclose(a, b, atol=1e-9, equal_nan=True)))


def _compare_at(full, make_strategy, name: str, cut: int):
    """① 미래를 잘라낸다."""
    trunc = make_strategy().generate_signals(_DF.iloc[:cut])
    bad = _diff(full, trunc, cut)
    assert bad == 0, (
        f"'{name}' 미래 참조 의심(절단 {cut}): "
        f"{bad}개 봉의 과거 신호가 미래 절단 시 바뀜")


def _compare_perturbed(full, make_strategy, name: str, cut: int):
    """② 미래 구간의 값을 크게 바꾼다 — 과거 신호는 불변이어야 한다."""
    pert = _DF.copy()
    tail = pert.index[cut:]
    for col in ("open", "high", "low", "close"):
        if col in pert.columns:
            pert.loc[tail, col] = pert.loc[tail, col].to_numpy() * 1.5
    got = make_strategy().generate_signals(pert)
    bad = _diff(full, got, cut)
    assert bad == 0, (
        f"'{name}' 미래 참조 확인(교란 {cut}): 미래 구간만 바꿨는데 "
        f"과거 신호 {bad}개 봉이 달라졌다 — 그 봉들이 미래를 보고 있다")


def test_no_lookahead_registered_strategies():
    """등록된 모든 단일 전략(ml 포함)이 미래를 참조하지 않는다."""
    for name in list_strategies():
        _assert_no_lookahead(lambda n=name: get_strategy(n), name)


def test_no_lookahead_ensembles():
    """고정/적응형 앙상블도 미래를 참조하지 않는다."""
    _assert_no_lookahead(default_ensemble, "default_ensemble")
    _assert_no_lookahead(lambda: adaptive_ensemble(lookback=40), "adaptive_ensemble")


def test_no_lookahead_ensemble_hrp_and_rebalance():
    """HRP(상관 인지) 가중과 가중 갱신 캐던스(rebalance>1)도 미래를 참조하지 않는다.

    rebalance 격자는 시계열 '시작'에서부터의 위치로 정해지므로 미래를 잘라도
    과거의 갱신 시점·가중치가 변하면 안 된다. HRP 가중은 [t-lookback, t-1]
    구간 PnL만 쓴다.
    """
    from quant.strategies import (
        AdaptiveEnsemble,
        MeanReversion,
        MovingAverageCross,
        RSIReversion,
        StrategyEnsemble,
    )

    strats = lambda: [MovingAverageCross(), RSIReversion(), MeanReversion()]  # noqa: E731
    _assert_no_lookahead(
        lambda: StrategyEnsemble(strats(), weighting="hrp",
                                 vol_lookback=60, rebalance=5),
        "ensemble_hrp")
    _assert_no_lookahead(
        lambda: StrategyEnsemble(strats(), weighting="inverse_vol", rebalance=7),
        "ensemble_inverse_vol_rebalance")
    _assert_no_lookahead(
        lambda: AdaptiveEnsemble(strats(), lookback=40,
                                 weighting="hrp", rebalance=5),
        "adaptive_ensemble_hrp_rebalance")


def test_no_lookahead_ml_with_extra_features():
    """외부 피처를 붙인 ML도 미래를 참조하지 않는다(reindex+ffill 병합 경로 커버).

    기본 leakage 테스트는 extra_features=None 경로만 돌아, 외부 피처 병합의
    미래 누수를 못 잡던 사각지대를 메운다.
    """
    import pandas as pd

    from quant.strategies import MLStrategy

    ext = pd.DataFrame({"macro": np.linspace(-1.0, 1.0, len(_DF))}, index=_DF.index)
    _assert_no_lookahead(
        lambda: MLStrategy(model="logreg", train_window=200, extra_features=ext),
        "ml+extra")
