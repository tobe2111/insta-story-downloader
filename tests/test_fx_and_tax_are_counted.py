"""원화 계좌의 환전 비용과 세금 — 세전·환전 전 숫자만 말하던 구멍 (감사 339)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.broker.paper import PaperBroker  # noqa: E402
from quant.live import tax_kr  # noqa: E402


def test_only_the_net_dollar_flow_is_converted():
    """미국 종목끼리 갈아타면 달러는 계좌 안에 머문다 — 순매수만 환전한다."""
    fills = [{"key": "us_stock:SPY", "side": "sell", "amount": 300_000},
             {"key": "us_stock:QQQ", "side": "buy", "amount": 320_000},
             {"key": "kr_stock:069500.KS", "side": "buy", "amount": 500_000},
             {"key": "crypto:BTC/USDT", "side": "buy", "amount": 100_000}]
    amount, cost = tax_kr.fx_charge(fills, 0.0025)
    assert amount == 20_000
    assert abs(cost - 50.0) < 1e-9


def test_the_owner_can_set_the_real_spread(tmp_path):
    assert tax_kr.fx_spread(str(tmp_path)) == tax_kr.FX_SPREAD_DEFAULT
    (tmp_path / "engine.json").write_text(json.dumps({"fx_spread": 0.0005}))
    assert tax_kr.fx_spread(str(tmp_path)) == 0.0005
    (tmp_path / "engine.json").write_text(json.dumps({"fx_spread": 5}))
    assert tax_kr.fx_spread(str(tmp_path)) == tax_kr.FX_SPREAD_DEFAULT, (
        "500%를 요율로 받아들였다 — 퍼센트와 비율을 헷갈린 값")


def test_the_broker_records_realized_gains_on_sells():
    b = PaperBroker(cash=1_000_000, fee=0.0)
    b.market_order("us_stock:SPY", "buy", 10, 100.0)
    b.market_order("us_stock:SPY", "sell", 4, 150.0)
    assert b.realized == [("us_stock:SPY", 200.0)]


def test_the_foreign_deduction_makes_small_accounts_tax_free():
    """100만원 계좌에서 가장 중요한 사실 — 해외 250만원 공제 아래면 0."""
    est = tax_kr.estimate({"us_stock:SPY": 1_200_000}, "2026")
    assert est["tax"]["foreign"] == 0
    est = tax_kr.estimate({"us_stock:SPY": 3_500_000}, "2026")
    assert abs(est["tax"]["foreign"] - 220_000) < 1e-6


def test_domestic_listed_foreign_etfs_pay_from_the_first_won():
    est = tax_kr.estimate({"kr_stock:133690.KS": 100_000,
                           "kr_stock:069500.KS": 100_000}, "2026")
    assert abs(est["tax"]["kr_etf"] - 15_400) < 1e-6, "나스닥 ETF 차익은 15.4%"
    assert est["realized"]["exempt"] == 100_000, "국내주식형 ETF는 비과세"


def test_crypto_is_taxed_only_from_2027():
    assert tax_kr.estimate({"crypto:BTC/USDT": 5_000_000}, "2026")["tax"]["crypto"] == 0
    assert tax_kr.estimate({"crypto:BTC/USDT": 5_000_000}, "2027")["tax"]["crypto"] > 0


def test_the_ledger_writes_both_and_the_front_page_reads_them():
    daily = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert '"fx": {"amount"' in daily and '"tax_estimate": tax_kr.estimate' in daily
    index = (ROOT / "docs" / "index.html").read_text("utf-8")
    assert "pfLast.tax_estimate" in index and "pfLast.fx" in index


def test_the_backtest_charges_fx_only_on_the_net_dollar_flow():
    """검증 엔진도 장부와 같은 셈 — 달러 자산끼리 갈아타면 환전이 없다."""
    import pandas as pd
    from quant.portfolio import trend_core as T
    idx = pd.bdate_range("2024-01-01", periods=6)
    cl = pd.DataFrame({"us_stock:A": 100.0, "us_stock:B": 100.0,
                       "kr_stock:C": 100.0}, index=idx)
    tgt = pd.DataFrame(0.0, index=idx, columns=cl.columns)
    tgt.iloc[0:2, 0] = 0.5                 # A 매수
    tgt.iloc[2:, 1] = 0.5                  # A → B 갈아타기(순 환전 0)
    cfg = T.TrendConfig(rebalance="D", band=0.0)
    base = T.simulate(cl, {k: 0.0 for k in cl}, cfg, targets=tgt)
    fx = T.simulate(cl, {k: 0.0 for k in cl}, cfg, targets=tgt,
                    fx_keys={"us_stock:A", "us_stock:B"}, fx_cost=0.01)
    assert abs(float(fx.cost.sum()) - 0.5 * 0.01) < 1e-9, (
        "갈아탄 날에도 환전 비용을 물렸다 — 매매마다 물리면 비용이 부푼다")
    assert float(base.cost.sum()) == 0.0
