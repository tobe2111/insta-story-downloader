"""전략별 기여도 분석(attribution) 테스트 — pandas 필요(CI 전용)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.data import SyntheticDataProvider
from quant.reporting import (
    attribution_report,
    ensemble_weight_report,
    strategy_attribution,
)
from quant.strategies import MovingAverageCross, RSIReversion, default_ensemble


def _df(limit=300):
    return SyntheticDataProvider().get_ohlcv("X", "1d", limit=limit)


def test_strategy_attribution_shape_and_hints():
    out = strategy_attribution(
        _df(), {"ma": MovingAverageCross(), "rsi": RSIReversion()},
        periods_per_year=365)
    assert set(out) == {"ma", "rsi"}
    for row in out.values():
        assert {"sharpe", "total_return", "contribution_hint"} <= set(row)
        assert isinstance(row["sharpe"], float)
    hints = [r["contribution_hint"] for r in out.values()
             if r["contribution_hint"] is not None]
    if hints:                                   # 양의 샤프가 하나라도 있으면 합=1
        assert abs(sum(hints) - 1.0) < 1e-9
        assert all(0.0 <= h <= 1.0 for h in hints)


def test_strategy_attribution_all_negative_gives_none_hints():
    """모든 전략의 샤프가 0 이하이면 억지 기여도를 만들지 않는다(전부 None)."""
    import pandas as pd

    # 단조 하락 시장 — 롱 전용 전략은 손실(샤프<0)일 수밖에 없다
    idx = pd.date_range("2024-01-01", periods=250, freq="D")
    close = pd.Series(100.0, index=idx) * (0.99 ** pd.Series(range(250), index=idx))
    df = pd.DataFrame({"open": close, "high": close * 1.001,
                       "low": close * 0.999, "close": close, "volume": 1.0})
    out = strategy_attribution(df, {"ma": MovingAverageCross()},
                               periods_per_year=365)
    sharpe = out["ma"]["sharpe"]
    if sharpe is not None and sharpe <= 0:
        assert out["ma"]["contribution_hint"] is None


def test_attribution_report_korean_and_honest():
    out = strategy_attribution(
        _df(), {"ma": MovingAverageCross(), "rsi": RSIReversion()},
        periods_per_year=365)
    rep = attribution_report(out)
    assert "전략별 단독 성과" in rep and "샤프" in rep
    assert "보장하지 않습니다" in rep            # 정직성 푸터


def test_ensemble_weight_report_before_run():
    ens = default_ensemble(weighting="inverse_vol")
    msg = ensemble_weight_report(ens)
    assert "generate_signals" in msg             # 아직 실행 전 → 안내


def test_ensemble_weight_report_after_run():
    ens = default_ensemble(weighting="inverse_vol")
    ens.generate_signals(_df())
    rep = ensemble_weight_report(ens)
    assert "현재 앙상블 가중치" in rep and "%" in rep
    # 하위 전략 이름 + 순번(#i)이 표시된다
    assert "ma_cross#0" in rep
    assert "보장되지 않습니다" in rep or "보장하지" in rep   # 정직성 푸터
