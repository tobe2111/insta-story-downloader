"""공개되는 모든 수익률 자료에는 **비용 기준**이 실린다 — 없으면 이 검사가 실패한다.

■ 왜 (2026-09-02 사장님 지시)

"각 수수료도 고려해서 수익을 생각해야지 — 선물 말고 다른 모든 투자 마찬가지."
전 트랙을 훑으니 밤 검증 3종은 비용이 아예 없었고 그림자 넷은 시장 무관
10bp 고정이었다. 사람이 새 트랙을 만들 때 수수료를 빠뜨리면 아무도 모른다 —
그래서 **장치**를 둔다: 공개 자료가 비용 기준을 안 실으면 여기서 빨간불.
"""
from __future__ import annotations

import json

import pytest

from quant.live import alloc_ladder, diversity_shadow, gen2, unshackled
from quant.live.daily import cost_basis_bp, measured_cost_model
from quant.live.futures_challenger import public_report


def test_cost_basis_is_per_market_and_measured(tmp_path):
    bp = cost_basis_bp(str(tmp_path))
    # ⚠️ 한국은 **두 줄**이다(2026-09-03). 증권거래세가 주식에만 붙고 ETF는
    #    비과세라, 한 숫자로 적으면 둘 중 하나는 반드시 거짓말이 된다.
    #    운용 한국 12종목 중 6종목이 ETF이므로 이 구분은 장식이 아니다.
    assert set(bp) == {"kr_stock", "us_stock", "crypto", "kr_stock_etf"}
    assert all(v is not None and v > 0 for v in bp.values())
    # 대조군 — 시장마다 다른 값이다(고정 10bp 였다면 전부 같았을 것)
    assert len(set(bp.values())) >= 2
    for m, v in bp.items():
        sym = "069500.KS" if m == "kr_stock_etf" else None
        market = "kr_stock" if m == "kr_stock_etf" else m
        assert v == pytest.approx(
            measured_cost_model(market, str(tmp_path),
                                symbol=sym).total_one_way() * 1e4, abs=0.05)
    assert bp["kr_stock_etf"] < bp["kr_stock"], (
        "ETF가 주식보다 싸지 않다 — 거래세 면제가 공개 자료에 안 닿았다")


def _run_shadow(tmp_path, market: str):
    """그림자 하나를 두 봉 전진시켜 실제로 문 비용을 돌려준다."""
    k = f"{market}:X"
    gen2.run_gen2(bar="2026-09-01", weights={k: 1.0}, marks={k: 100.0}, state_dir=str(tmp_path))
    rec = gen2.run_gen2(bar="2026-09-02", weights={k: 0.0}, marks={k: 100.0}, state_dir=str(tmp_path))
    return gen2.START_CASH - rec["equity"]


def test_shadows_charge_the_markets_own_cost(tmp_path):
    """한국 종목을 돌린 그림자는 미국 종목을 돌린 그림자보다 더 많이 낸다."""
    kr = _run_shadow(tmp_path / "kr", "kr_stock")
    us = _run_shadow(tmp_path / "us", "us_stock")
    assert kr > us > 0
    # 대조군 — 고정 10bp 였다면 두 값이 같았을 것
    flat = gen2.START_CASH * (1.0 * gen2.FEE + 1.0 * gen2.FEE)
    assert kr != pytest.approx(flat, rel=1e-3) or us != pytest.approx(flat, rel=1e-3)


def test_every_public_payload_names_its_cost_basis(tmp_path):
    k = "us_stock:SPY"
    gen2.run_gen2(bar="2026-09-01", weights={k: 1.0}, marks={k: 1.0}, state_dir=str(tmp_path))
    unshackled.run_unshackled(bar="2026-09-01", weights={k: 1.0}, slices={k: 1.0},
                              marks={k: 1.0}, n_total=1, state_dir=str(tmp_path))
    import pandas as pd
    alloc_ladder.run_alloc_ladder(bar="2026-09-01", weights={k: 1.0},
                                  rets_map={k: pd.Series([0.001] * 60)},
                                  marks={k: 1.0}, n_total=1, state_dir=str(tmp_path))
    diversity_shadow.run_diversity_shadow(bar="2026-09-01", pairs={k: (1.0, 1.0)},
                                          marks={k: 1.0}, state_dir=str(tmp_path))
    for name, pub in (("gen2", gen2.gen2_public), ("unshackled", unshackled.unshackled_public),
                      ("alloc_ladder", alloc_ladder.ladder_public),
                      ("diversity", diversity_shadow.diversity_public)):
        d = pub(str(tmp_path))
        assert d and d.get("cost_basis_bp"), f"{name}: 비용 기준이 없다"
    fut = public_report({"start_cash": 100.0, "cash": 100.0, "positions": {}, "rounds": [], "curve": []})
    assert fut.get("cost_basis_bp")


def test_the_main_account_ledger_already_carries_cost():
    """본 계좌 장부는 날마다 cost 를 남긴다 — 이 검사의 기준선."""
    d = json.load(open("state/paper/portfolio_ALL.json", encoding="utf-8"))
    last = d["history"][-1]
    assert "cost" in last and "cost_paid" in last and "bench_cost_rate" in last
