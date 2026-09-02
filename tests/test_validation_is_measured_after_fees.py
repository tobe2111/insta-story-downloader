"""밤 검증 3종(DSR·PBO·CPCV)이 **수수료 뺀 뒤**로 돈다 — 그리고 기준을 남긴다.

■ 왜 (2026-09-02 사장님 지시 · 실측)

검증 명령에 비용 옵션 자체가 없었고, 저장된 42종목 검증 결과 어디에도
비용 기준이 없었다. 그 결과가 비중 게이트(통과 1.0배 · 경고 0.5배)와
공개 화면의 "검증 성적"에 쓰였다. 오늘 판정이 뒤집히는 종목은 없지만
(비용 전에도 통과 0, DSR 최고 0.21), 언젠가 통과하는 날 그 통과가 수수료
빼기 전 성적일 수 있다 — 그날이 오기 전에 막는다.
"""
from __future__ import annotations

import json
import types

import pandas as pd
import pytest

import quant.cli as cli


class _M:
    sharpe = 0.1; total_return = 0.01; max_drawdown = -0.02


def _fake_df(n=300):
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    px = pd.Series(range(100, 100 + n), index=idx, dtype=float)
    return pd.DataFrame({"open": px, "high": px + 1, "low": px - 1, "close": px, "volume": 1e6})


def _run(monkeypatch, tmp_path, market: str) -> tuple[dict, dict]:
    """검증을 돌려 (세 검정이 받은 fee, 저장된 레코드)를 돌려준다."""
    got: dict = {}
    import quant.optimize as O
    import quant.robustness as RB
    import quant.data as DATA
    import quant.live.daily as D
    import quant.live.retrain as R
    from quant.backtest.costs import CostModel

    monkeypatch.setattr(DATA, "get_provider", lambda m: types.SimpleNamespace(
        get_ohlcv=lambda *a, **k: _fake_df()))
    monkeypatch.setattr(D, "measured_cost_model", lambda m, sd="state", **k: CostModel(fee=0.002, slippage=0.0005))
    monkeypatch.setattr(R, "recent_trials", lambda *a, **k: 0)
    def _wf(*a, **k):
        got["wf"] = k.get("fee")
        return {"oos_metrics": _M(), "segments": [], "dsr": 0.1, "n_trials": 1}
    monkeypatch.setattr(O, "walk_forward", _wf)
    monkeypatch.setattr(RB, "param_returns_matrix", lambda *a, **k: (got.__setitem__("pbo", k.get("fee")), pd.DataFrame([[0.0]]))[1])
    monkeypatch.setattr(RB, "pbo", lambda *a, **k: {"pbo": 0.5})
    monkeypatch.setattr(RB, "pbo_report", lambda r: "pbo")
    monkeypatch.setattr(O, "cpcv", lambda *a, **k: (got.__setitem__("cpcv", k.get("fee")), {"worst_path_return": 0.0, "sharpe_min": 0.0})[1])
    monkeypatch.setattr(O, "cpcv_report", lambda r: "cpcv")
    monkeypatch.setattr(O, "grid_search", lambda *a, **k: (got.__setitem__("grid", k.get("fee")), {"results": [], "best_params": {}})[1])
    monkeypatch.setattr(O, "robust_best", lambda *a, **k: None)
    monkeypatch.setattr(O, "stability_scores", lambda r: [], raising=False)
    monkeypatch.setattr(O, "stability_report", lambda s: "", raising=False)
    save = tmp_path / "validation.json"
    args = cli.build_parser().parse_args(
        ["validate", "--market", market, "--symbol", "X", "--strategy", "ma_cross",
         "--save", str(save)])
    cli._cmd_validate(args)
    rec = next(iter(json.loads(save.read_text("utf-8")).values()))
    return got, rec


def test_all_three_tests_receive_the_measured_fee(monkeypatch, tmp_path):
    got, rec = _run(monkeypatch, tmp_path, "crypto")
    assert got["wf"] == got["pbo"] == got["cpcv"] == got["grid"] == pytest.approx(0.0025)
    assert rec["cost_basis_bp"] == pytest.approx(25.0)


def test_the_practice_market_stays_cost_free_and_says_so(monkeypatch, tmp_path):
    """대조군 — 합성(연습용) 시장은 비용 없이 돌고, 기록이 None 으로 그 사실을 말한다."""
    got, rec = _run(monkeypatch, tmp_path, "synthetic")
    assert got["wf"] is None and got["cpcv"] is None
    assert rec["cost_basis_bp"] is None
