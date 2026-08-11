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
_CUT = 320   # 이 시점 이후(미래)를 잘라낸다


def _assert_no_lookahead(make_strategy, name: str):
    full = make_strategy().generate_signals(_DF)
    trunc = make_strategy().generate_signals(_DF.iloc[:_CUT])
    # 겹치는 과거 구간 전체 — **절단 경계 봉을 포함해서** 비교한다.
    #
    # ⚠️ 예전에는 `iloc[:_CUT - 1]`로 경계 봉을 빼고 봤다(감사 57). 그런데
    #    1봉 룩어헤드(`close.shift(-1)`)는 절단된 계열의 **마지막 한 봉만**
    #    바꾼다. 그 봉을 비교에서 빼면 차이가 0이 되어 검사가 초록으로
    #    통과한다 — 하필 가장 흔한 형태의 룩어헤드에 눈을 감는 탐지기였다.
    #    인과적 전략이라면 마지막 봉의 신호도 미래 유무와 무관해야 하므로,
    #    경계를 포함하는 것이 옳다(실측: 전 후보 24종 모두 포함해도 통과).
    a = full.iloc[:_CUT].to_numpy()
    b = trunc.iloc[:_CUT].to_numpy()
    assert len(a) == len(b) == _CUT
    bad = int(np.sum(~np.isclose(a, b, atol=1e-9)))
    assert bad == 0, f"'{name}' 미래 참조 의심: {bad}개 봉의 과거 신호가 미래 절단 시 바뀜"


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
