"""오디션-현실 격차 계약 검사 — 챔피언을 뽑는 세계 = 돈이 도는 세계.

배경(2026-08-11 발견): 매일 밤 챔피언을 선발하는 오디션이 실제 운용 환경과
세 군데 어긋나 있었다.
    체결 시점  백테스트=그 봉 종가   vs  실제=다음 세션 시가(실측 갭 79bp)
    거래 비용  가정 28bp(한국주식)   vs  실측 ~93bp — 3.3배
    회전 통제  밴드 없음             vs  밴드+쿨다운+평활
셋 다 오디션을 낙관적으로 만들어, 특히 고회전 전략이 부당하게 유리하게
평가됐다. 실제로는 낼 수 없는 성과를 근거로 챔피언이 뽑히던 상태.

핵심 계약:
  ① 백테스터가 '다음 시가 체결'을 지원하고, 기본값은 기존 동작과 동일
  ② 실측 비용이 가정을 넘으면 오디션이 실측을 쓴다(표본 충분할 때만)
  ③ 오디션 대결이 체결 규칙·밴드를 백테스터까지 전달한다
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent


def _df(n=300, seed=11, gap=0.01):
    """개장 갭이 있는 합성 봉.

    갭은 '전일 종가 → 당일 시가'다(당일 종가 대비가 아니다). gap=0이면
    시가가 전일 종가와 같아져, 종가 체결과 시가 체결이 수학적으로 같아진다 —
    모델의 무결성을 확인하는 기준점.
    """
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    prev_close = np.concatenate([[close[0]], close[:-1]])
    open_ = prev_close * (1 + rng.normal(0, gap, n)) if gap else prev_close
    return pd.DataFrame(
        {"open": open_, "high": np.maximum(open_, close) * 1.01,
         "low": np.minimum(open_, close) * 0.99, "close": close,
         "volume": rng.uniform(1e6, 2e6, n)},
        index=pd.date_range("2024-01-01", periods=n, freq="D"))


# ── ① 다음 시가 체결 ───────────────────────────────────────────


def test_next_open_fill_default_is_bit_identical():
    """기본값은 기존 동작과 완전히 같아야 한다 — 과거 기록의 재현이 깨지면 안 된다."""
    from quant.backtest import Backtester
    from quant.strategies import get_strategy
    df, s = _df(), get_strategy("ma_cross", fast=10, slow=30)
    a = Backtester(s).run(df).equity.iloc[-1]
    b = Backtester(s, next_open_fill=False).run(df).equity.iloc[-1]
    assert a == b


def test_next_open_fill_changes_result_and_charges_the_gap():
    """시가 체결은 '새로 산 몫'만 개장 갭을 겪는다 — 결과가 달라져야 한다."""
    from quant.backtest import Backtester
    from quant.strategies import get_strategy
    df, s = _df(), get_strategy("ma_cross", fast=10, slow=30)
    close_fill = Backtester(s).run(df).equity.iloc[-1]
    open_fill = Backtester(s, next_open_fill=True).run(df).equity.iloc[-1]
    assert close_fill != open_fill
    # 갭이 0이면 두 방식이 사실상 같아야 한다(모델의 무결성 확인)
    flat = _df(gap=0.0)
    a = Backtester(s).run(flat).equity.iloc[-1]
    b = Backtester(s, next_open_fill=True).run(flat).equity.iloc[-1]
    assert a == pytest.approx(b, rel=1e-9)


def test_next_open_fill_falls_back_without_open_column():
    """open 컬럼이 없으면 조용히 종가 체결로 — 데이터 부족이 크래시가 되면 안 된다."""
    from quant.backtest import Backtester
    from quant.strategies import get_strategy
    df = _df().drop(columns=["open"])
    s = get_strategy("ma_cross", fast=10, slow=30)
    a = Backtester(s).run(df).equity.iloc[-1]
    b = Backtester(s, next_open_fill=True).run(df).equity.iloc[-1]
    assert a == b


# ── ② 실측 비용 ────────────────────────────────────────────────


def test_measured_cost_model_uses_measurement_when_sample_suffices(monkeypatch):
    from quant.backtest.costs import CostModel
    from quant.live.daily import measured_cost_model
    monkeypatch.setattr(
        "quant.reporting.fill_gap.fill_gap_report",
        lambda state_dir="state": {"markets": {
            "kr_stock": {"n": 40, "assumed_bp": 14.0, "mean_adverse_bp": 79.0}}})
    got = measured_cost_model("kr_stock", "state")
    base = CostModel.for_market("kr_stock")
    assert (got.fee + got.slippage) > (base.fee + base.slippage)
    # 왕복 93bp ≈ 편도 46.5bp
    assert (got.fee + got.slippage) == pytest.approx(0.00465, abs=1e-5)


def test_measured_cost_never_cheaper_than_assumption(monkeypatch):
    """실측이 더 유리해도 가정을 낮추지 않는다 — 보수적인 쪽을 유지한다."""
    from quant.backtest.costs import CostModel
    from quant.live.daily import measured_cost_model
    monkeypatch.setattr(
        "quant.reporting.fill_gap.fill_gap_report",
        lambda state_dir="state": {"markets": {
            "us_stock": {"n": 40, "assumed_bp": 6.0, "mean_adverse_bp": -50.0}}})
    got = measured_cost_model("us_stock", "state")
    base = CostModel.for_market("us_stock")
    assert (got.fee + got.slippage) == pytest.approx(base.fee + base.slippage)


def test_thin_measurement_keeps_assumption(monkeypatch):
    from quant.backtest.costs import CostModel
    from quant.live.daily import measured_cost_model
    monkeypatch.setattr(
        "quant.reporting.fill_gap.fill_gap_report",
        lambda state_dir="state": {"markets": {
            "kr_stock": {"n": 3, "assumed_bp": 14.0, "mean_adverse_bp": 900.0}}})
    got = measured_cost_model("kr_stock", "state")
    base = CostModel.for_market("kr_stock")
    assert (got.fee + got.slippage) == pytest.approx(base.fee + base.slippage)


# ── ③ 오디션 배선 ──────────────────────────────────────────────


def test_champion_challenger_passes_fill_rules_to_backtester():
    from quant.live.champion_challenger import ChampionChallenger
    from quant.strategies import get_strategy
    df = _df()
    a = get_strategy("ma_cross", fast=10, slow=30)
    b = get_strategy("ma_cross", fast=5, slow=40)
    plain = ChampionChallenger(a, b, min_obs=30).evaluate(df)
    real = ChampionChallenger(a, b, min_obs=30, next_open_fill=True,
                              rebalance_band=0.05).evaluate(df)
    # 체결·밴드가 실제로 백테스터까지 전달됐다면 판정 재료가 달라진다
    assert plain.get("mean_diff") != real.get("mean_diff")


# ── ④ 재현성 — 결정의 전제를 결정과 함께 보존 ──────────────────


def test_audition_env_recorded_and_replayed():
    """실측 비용은 날마다 변한다 — 오늘 값으로 어제 결정을 재생하면 안 된다."""
    from quant.live.retrain import _audition_kwargs_from_record
    rec = {"market": "kr_stock", "audition_env": {
        "fee": 0.00015, "slippage": 0.0045,
        "next_open_fill": True, "rebalance_band": 0.28}}
    kw = _audition_kwargs_from_record(rec)
    assert kw["next_open_fill"] is True
    assert kw["rebalance_band"] == pytest.approx(0.28)
    assert kw["cost_model"].slippage == pytest.approx(0.0045)


def test_old_records_replay_with_original_assumptions():
    """audition_env 이전 기록은 그때 쓰던 조건으로 재현된다(하위 호환)."""
    from quant.backtest.costs import CostModel
    from quant.live.retrain import _audition_kwargs_from_record
    kw = _audition_kwargs_from_record({"market": "kr_stock"})
    base = CostModel.for_market("kr_stock")
    assert kw["cost_model"].fee == pytest.approx(base.fee)
    assert kw["cost_model"].slippage == pytest.approx(base.slippage)
    assert "next_open_fill" not in kw     # 옛 기록은 종가 체결·밴드 0이 기본
    assert "rebalance_band" not in kw


def test_ledger_writes_audition_env():
    src = (ROOT / "quant" / "live" / "retrain.py").read_text("utf-8")
    assert '"audition_env"' in src
    assert "_audition_kwargs_from_record(rec)" in src
    # verify가 '오늘의 가정'으로 과거를 재생하면 재현이 깨진다
    assert 'cost_model=CostModel.for_market(rec["market"]))' not in src


def test_parliament_uses_same_fill_rules():
    """의석 채점도 오디션과 같은 세계에서 — 같은 격차가 재발하면 안 된다."""
    src = (ROOT / "quant" / "live" / "retrain.py").read_text("utf-8")
    p = (ROOT / "quant" / "live" / "parliament.py").read_text("utf-8")
    assert "next_open_fill=next_open_fill" in p
    assert "rebalance_band=rebalance_band" in p
    # 오디션과 의회가 '같은' 조건을 쓴다 — 한쪽만 고치면 격차가 남는다
    assert "next_open_fill=audition_next_open" in src      # 오디션
    assert "next_open_fill=market not in IMMEDIATE_FILL_MARKETS" in src  # 의회
    assert src.count("_rebalance_band_rel(market, state_dir)") >= 2


def test_retrain_wires_measured_cost_and_fill_rules():
    src = (ROOT / "quant" / "live" / "retrain.py").read_text("utf-8")
    assert "measured_cost_model(market, state_dir)" in src
    assert "next_open_fill=market not in IMMEDIATE_FILL_MARKETS" in src
    assert "rebalance_band=_rebalance_band_rel(market, state_dir)" in src
    # 가정 비용만 쓰던 옛 호출이 남아 있으면 격차가 되살아난다
    assert "cost_model=CostModel.for_market(market))" not in src
