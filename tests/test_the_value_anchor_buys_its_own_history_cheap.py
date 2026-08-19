"""가치 닻 — 자기 역사 대비 저평가 구간만 보유 (2026-08-19, KIS 사례 채택).

지켜야 할 약속:
- 재무 데이터(val_pbr)가 없는 시장(코인·미국)은 언제나 관망.
- 자기 역사 대비 싼 구간(하위 분위수)에서 보유하고, 비싼 구간은 관망.
- 분위수 창은 전부 과거(당일 제외) — 미래가 과거 판정을 못 바꾼다.
- 워밍업·결측('모름')은 보류 — 감사 206의 규칙.
- 부착은 도전자 전용 이름(val_*)이라 챔피언 피처 행렬에 안 들어간다.
- 링에 실제로 서 있고, 파이프라인 세 곳이 실제로 부착한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.data.krx import attach_krx_value              # noqa: E402
from quant.strategies.valueanchor import ValueAnchor     # noqa: E402


def _df(n=700, pbr=None):
    rng = np.random.RandomState(2)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    d = pd.DataFrame({"open": close, "close": close, "high": close + 1,
                      "low": close - 1, "volume": np.full(n, 1e6)}, index=idx)
    if pbr is not None:
        d["val_pbr"] = pbr
    return d


def test_no_value_data_means_no_opinion():
    sig = ValueAnchor().generate_signals(_df())
    assert float(sig.abs().max()) == 0.0, (
        "재무 데이터가 없는데 의견을 낸다 — 재료 없는 신호는 잡음이다")


def test_cheap_holds_and_expensive_waits():
    n = 700
    pbr = np.full(n, 2.0)
    pbr[400:550] = 0.8                                   # 자기 역사 대비 급락
    sig = ValueAnchor(min_obs=120).generate_signals(_df(n, pbr)).to_numpy()
    assert sig[430:550].mean() > 0.95, "싼 구간에서 사지 않는다"
    assert sig[200:400].mean() < 0.05, "평소 수준(비싼 구간)에서 산다"
    assert sig[600:].mean() < 0.05, (
        "다시 비싸졌는데 들고 있다 — 닻이 끌려갔다")


def test_the_future_cannot_change_the_past():
    n = 700
    pbr = np.full(n, 2.0)
    pbr[400:550] = 0.8
    base = ValueAnchor().generate_signals(_df(n, pbr)).iloc[:380]
    pbr2 = pbr.copy()
    pbr2[600:] = 0.1                                     # 미래를 뒤흔든다
    spiked = ValueAnchor().generate_signals(_df(n, pbr2)).iloc[:380]
    assert (base == spiked).all(), "미래 봉이 과거 판정을 바꿨다 — 룩어헤드"


def test_warmup_is_held_not_passed():
    n = 700
    pbr = np.full(n, 0.5)                                # 처음부터 싸 보여도
    sig = ValueAnchor(min_obs=120).generate_signals(_df(n, pbr))
    assert float(sig.iloc[:100].abs().max()) == 0.0, (
        "표본 미달인데 판정한다 — '모름'은 보류다(감사 206)")


def _price_df(idx):
    rng = np.random.RandomState(2)
    close = 100 + np.cumsum(rng.normal(0, 1, len(idx)))
    return pd.DataFrame({"open": close, "close": close, "high": close + 1,
                         "low": close - 1,
                         "volume": np.full(len(idx), 1e6)}, index=idx)


def test_attach_is_challenger_only_and_zero_div_is_real():
    idx = pd.date_range("2025-01-01", periods=100, freq="D")
    fund = pd.DataFrame({"per": np.linspace(5, 15, 100),
                         "pbr": np.linspace(0.5, 1.5, 100),
                         "div": np.zeros(100)}, index=idx)
    out = attach_krx_value(
        _price_df(pd.date_range("2025-01-01", periods=120, freq="D")),
        "005930.KS", fetch=lambda s: fund)
    assert "val_pbr" in out.columns and "val_per" in out.columns
    assert float(out["val_div"].dropna().max()) == 0.0, (
        "배당 0(무배당)이 결측으로 지워졌다 — 0은 진짜 값이다")
    from quant.strategies.ml import _features
    feats = _features(out)
    assert not any(str(c).startswith("val_") for c in feats.columns), (
        "가치 컬럼이 챔피언 피처 행렬에 들어갔다 — 구조 동결 위반")


def test_negative_per_is_unknown_not_cheap():
    idx = pd.date_range("2025-01-01", periods=100, freq="D")
    fund = pd.DataFrame({"per": np.full(100, -3.0),      # 적자 표기
                         "pbr": np.full(100, 1.0)}, index=idx)
    out = attach_krx_value(
        _price_df(pd.date_range("2025-01-01", periods=120, freq="D")),
        "005930.KS", fetch=lambda s: fund)
    assert out["val_per"].dropna().empty, (
        "적자 PER(음수)이 값으로 남았다 — '싸다'가 아니라 '재지 못한다'다")


def test_the_challenger_is_in_the_ring_and_attached_everywhere():
    from quant.live.retrain import build_challengers
    ring = build_challengers({"strategy": "ml", "params": {}}, "2026-08-19")
    assert any(c.get("strategy") == "value_anchor" for c in ring), "링에 없다"
    for rel in ("quant/live/daily.py", "quant/live/retrain.py"):
        src = (ROOT / rel).read_text("utf-8")
        assert "attach_krx_value" in src, f"{rel}이 가치를 부착하지 않는다"
    assert (ROOT / "quant" / "live" / "daily.py").read_text(
        "utf-8").count("attach_krx_value(df, symbol)") >= 2, (
        "일일 파이프라인 두 경로 중 한 곳이 부착을 빼먹었다")
