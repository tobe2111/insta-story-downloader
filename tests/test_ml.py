"""ML 전략 테스트 (scikit-learn 필요 — CI에서 설치)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.backtest import Backtester
from quant.data import SyntheticDataProvider
from quant.strategies import MLStrategy, get_strategy, list_strategies

_DF = SyntheticDataProvider(seed=6).get_ohlcv("ML", "1d", limit=500)


def test_ml_registered_and_bounded():
    assert "ml" in list_strategies()
    sig = get_strategy("ml").generate_signals(_DF)
    assert sig.index.equals(_DF.index)
    assert sig.max() <= 1.0 + 1e-9 and sig.min() >= -1.0 - 1e-9


def test_ml_no_signal_before_training():
    """학습 창(train_window) 이전에는 신호가 0 — 룩어헤드 없음의 방증."""
    sig = MLStrategy(train_window=250).generate_signals(_DF)
    assert (sig.iloc[:250] == 0).all()


def test_ml_backtest_runs():
    result = Backtester(MLStrategy(model="logreg", train_window=200)).run(_DF)
    assert (result.equity > 0).all()


def test_ml_random_forest():
    sig = MLStrategy(model="rf", train_window=200,
                     retrain_every=50).generate_signals(_DF)
    assert sig.abs().max() <= 1.0 + 1e-9


def test_ml_short_data_no_trade():
    """데이터가 train_window보다 짧으면 학습을 못 해 전부 관망(0)."""
    short = SyntheticDataProvider(seed=1).get_ohlcv("S", "1d", limit=100)
    sig = MLStrategy(train_window=250).generate_signals(short)
    assert (sig == 0).all()


def test_ml_gradient_boosting_and_vote():
    """추가 모델(gb·soft-voting 앙상블)도 경계 안에서 동작한다."""
    for kind in ("gb", "vote"):
        sig = MLStrategy(model=kind, train_window=200,
                         retrain_every=50).generate_signals(_DF)
        assert sig.abs().max() <= 1.0 + 1e-9
        assert sig.index.equals(_DF.index)


def test_ml_proba_sizing_is_graded():
    """확신도 사이징(proba)은 0/1 이분법이 아니라 중간값도 나온다."""
    sig = MLStrategy(model="rf", train_window=200, sizing="proba").generate_signals(_DF)
    traded = sig[sig != 0].abs()
    # 최소한 하나는 풀포지션(1.0)이 아닌 부분 포지션이어야 '그라데이션'이다
    assert (traded < 0.999).any()
    assert sig.max() <= 1.0 + 1e-9 and sig.min() >= 0.0 - 1e-9


def test_ml_binary_sizing_is_full_or_flat():
    """binary 모드는 풀포지션(1.0) 또는 관망(0)만 낸다."""
    sig = MLStrategy(train_window=200, sizing="binary").generate_signals(_DF)
    uniq = set(round(float(v), 6) for v in sig.unique())
    assert uniq <= {0.0, 1.0}


def test_ml_short_allows_negative():
    """allow_short=True면 하락 확신 시 음(-) 비중도 낸다."""
    sig = MLStrategy(model="logreg", train_window=200,
                     allow_short=True, threshold=0.52).generate_signals(_DF)
    assert sig.min() < 0.0            # 숏 포지션이 최소 한 번은 나와야 한다
    assert sig.abs().max() <= 1.0 + 1e-9


def test_ml_importances_recorded():
    """학습 후 피처 중요도(또는 계수)가 기록되어 해석 가능해야 한다."""
    from quant.strategies.ml import FEATURE_NAMES

    strat = MLStrategy(model="rf", train_window=200)
    strat.generate_signals(_DF)
    assert strat.last_importances_ is not None
    assert set(strat.last_importances_) == set(FEATURE_NAMES)


def test_ml_extra_features_used():
    """외부(거시) 피처를 넣으면 학습에 포함되고 중요도에도 나타난다."""
    import numpy as np
    import pandas as pd

    ext = pd.DataFrame({"fear_greed": np.linspace(0.0, 1.0, len(_DF))}, index=_DF.index)
    strat = MLStrategy(model="rf", train_window=200, extra_features=ext)
    sig = strat.generate_signals(_DF)
    assert sig.abs().max() <= 1.0 + 1e-9
    assert "x_fear_greed" in strat.feature_names_
    assert strat.last_importances_ is not None
    assert "x_fear_greed" in strat.last_importances_


def test_ml_sparse_extra_feature_does_not_disable_model():
    """외부 피처가 초반 구간에 NaN이어도(예: 공포탐욕지수 시작 전) 그 구간을
    통째로 무거래로 만들지 않는다 — valid는 기본 피처만 판정(버그 수정)."""
    import numpy as np
    import pandas as pd

    n = len(_DF)
    vals = np.concatenate([np.full(300, np.nan), np.linspace(0.0, 1.0, n - 300)])
    ext = pd.DataFrame({"fear_greed": vals}, index=_DF.index)
    sig = MLStrategy(model="logreg", train_window=200,
                     extra_features=ext).generate_signals(_DF)
    # 외부 피처가 NaN인 구간(200~300)에서도 기본 피처가 유효하면 거래가 나온다.
    # 구버전은 valid가 외부 피처까지 AND라 이 구간이 전부 0이었다.
    assert (sig.iloc[200:300] != 0).any()


def test_ml_extra_features_callable():
    """extra_features 를 callable(df)->DataFrame 로도 줄 수 있다."""
    import pandas as pd

    def make(df):
        return pd.DataFrame({"macro": 0.5}, index=df.index)

    strat = MLStrategy(train_window=200, extra_features=make)
    strat.generate_signals(_DF)
    assert "x_macro" in strat.feature_names_


def test_ml_no_extra_features_default_names():
    """외부 피처가 없으면 기본 15개 피처 이름만 쓴다(하위호환)."""
    from quant.strategies.ml import FEATURE_NAMES

    strat = MLStrategy(model="rf", train_window=200)
    strat.generate_signals(_DF)
    assert strat.feature_names_ == list(FEATURE_NAMES)


# ── 확률 보정(calibrate) + Δ비중 양자화(weight_step) ─────────────────────

def test_ml_calibrated_bounded_and_index_preserved():
    """보정(sigmoid·isotonic)을 켜도 신호는 경계 안이고 인덱스가 보존된다.

    보정은 엣지를 만들지 않는다 — 과대확신 확률로 사이징할 때의 기하 손실을
    줄일 뿐이므로, 여기서는 '수익'이 아니라 계약(경계·인덱스)만 검증한다.
    """
    for method in ("sigmoid", "isotonic"):
        sig = MLStrategy(model="logreg", train_window=200, retrain_every=50,
                         calibrate=method).generate_signals(_DF)
        assert sig.index.equals(_DF.index)
        assert sig.abs().max() <= 1.0 + 1e-9
        assert sig.min() >= 0.0 - 1e-9        # 롱온리 기본


def test_ml_calibrate_invalid_raises():
    with pytest.raises(ValueError):
        MLStrategy(calibrate="platt")


def test_ml_calibrated_truncation_invariance():
    """보정 변형도 미래 절단 불변(test_leakage 방식) — 보정기는 학습창 내부
    3-겹 CV로만 적합되므로 미래를 잘라도 과거 신호가 바뀌면 안 된다."""
    import numpy as np

    cut = 400
    make = lambda: MLStrategy(model="logreg", train_window=200,  # noqa: E731
                              retrain_every=50, calibrate="sigmoid")
    full = make().generate_signals(_DF)
    trunc = make().generate_signals(_DF.iloc[:cut])
    a = full.iloc[:cut - 1].to_numpy()
    b = trunc.iloc[:cut - 1].to_numpy()
    assert int(np.sum(~np.isclose(a, b, atol=1e-9))) == 0


def test_ml_weight_step_quantizes_to_grid():
    """weight_step=0.1이면 모든 신호가 0.1 격자 위에 있고 여전히 경계 안이다."""
    import numpy as np

    step = 0.1
    sig = MLStrategy(model="rf", train_window=200, sizing="proba",
                     weight_step=step).generate_signals(_DF)
    arr = sig.to_numpy()
    assert np.allclose(np.round(arr / step) * step, arr, atol=1e-9)
    assert sig.abs().max() <= 1.0 + 1e-9
    assert (sig != 0).any()                    # 양자화가 신호를 전멸시키지 않는다


def test_ml_weight_step_stays_near_unquantized():
    """양자화는 반올림이므로 비양자화 신호에서 step/2 이상 벗어나지 않는다."""
    import numpy as np

    base = MLStrategy(model="logreg", train_window=200,
                      retrain_every=50).generate_signals(_DF)
    quant = MLStrategy(model="logreg", train_window=200, retrain_every=50,
                       weight_step=0.1).generate_signals(_DF)
    assert float(np.abs(base - quant).max()) <= 0.05 + 1e-9


def test_ml_weight_step_zero_is_default_behavior():
    """weight_step=0.0(기본)은 기존 신호와 비트 단위로 같다."""
    a = MLStrategy(model="logreg", train_window=200,
                   retrain_every=50).generate_signals(_DF)
    b = MLStrategy(model="logreg", train_window=200, retrain_every=50,
                   weight_step=0.0).generate_signals(_DF)
    assert (a == b).all()
