"""엔진 선택은 **기계가** 한다 — 수익률로, 규칙은 결과보다 먼저 (감사 341).

사장님(2026-10-10): "어떤 엔진을 선택할 지는 수익률에 따라서 머신러닝이
결정하는거지 그걸 내가 결정하는건 아닌 것 같아."
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.portfolio import engine_select as E  # noqa: E402
from quant.portfolio import trend_core as T  # noqa: E402


def _rets(n=E.WINDOW + 40, edge=0.0, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-01", periods=n)
    base = rng.normal(0.0002, 0.01, n)
    return pd.DataFrame({"risk12": base,
                         "notional50": base + edge + rng.normal(0, 0.002, n)},
                        index=idx)


def test_the_switch_threshold_is_borrowed_not_invented():
    from quant.live.retrain import CONFIRM_T_CAP
    assert E.T_SWITCH == CONFIRM_T_CAP, "문턱을 여기서 따로 정하면 관문이 아니라 편의다"


def test_a_clearly_better_candidate_is_picked():
    r = _rets(edge=0.0008)
    dec = E.choose(r, r.index[-1], "risk12")
    assert dec["choice"] == "notional50" and dec["reason"] == "switch"
    assert dec["t"] >= E.T_SWITCH


def test_a_higher_number_that_is_only_noise_does_not_switch():
    """수익률 순위만으로 바꾸면 매달 갈아타며 수수료만 낸다."""
    r = _rets(edge=0.00002)
    dec = E.choose(r, r.index[-1], "risk12")
    assert dec["choice"] == "risk12"
    assert dec["reason"] in ("not_significant", "incumbent_best")


def test_a_fresh_switch_is_held():
    r = _rets(edge=0.0008)
    dec = E.choose(r, r.index[-1], "risk12", held_days=E.MIN_HOLD - 1)
    assert dec["choice"] == "risk12" and dec["reason"] == "min_hold"


def test_a_pathological_drawdown_is_never_picked():
    r = _rets(edge=0.0008)
    crash = r.index[-200]
    r.loc[crash:crash + pd.Timedelta(days=30), "notional50"] = -0.03
    r.iloc[-150:, 1] += 0.01                     # 그 뒤 크게 회복해 수익은 높다
    dec = E.choose(r, r.index[-1], "risk12")
    assert dec["table"]["notional50"]["mdd"] / 100 < E.MDD_FLOOR
    assert dec["choice"] == "risk12"


def test_short_history_keeps_the_incumbent():
    r = _rets(n=200, edge=0.002)
    assert E.choose(r, r.index[-1], "risk12")["reason"] == "no_full_window"


def _results(edge):
    r = _rets(n=E.WINDOW + 400, edge=edge)
    out = {}
    for n in r.columns:
        eq = (1 + r[n]).cumprod()
        w = pd.DataFrame({"us_stock:SPY": 0.5 if n == "risk12" else 1.0,
                          "kr_stock:069500.KS": 0.0}, index=r.index)
        out[n] = T.TrendResult(equity=eq, returns=r[n], weights=w,
                               turnover=r[n] * 0, cost=r[n] * 0, gross=r[n] * 0)
    return r, out


def test_the_selector_is_backtested_with_switching_costs():
    r, res = _results(edge=0.0008)
    start = str(r.index[E.WINDOW + 5].date())
    meta = E.meta_backtest(res, {"us_stock:SPY": 0.001}, start=start,
                           fx_keys={"us_stock:SPY"}, fx_cost=0.0025)
    assert meta["switches"], "앞선 후보로 한 번은 갈아타야 한다"
    sw = meta["switches"][0]
    assert sw["to"] == "notional50"
    assert abs(sw["cost_pct"] - 0.5 * (0.001 + 0.0025) * 100) < 1e-6, (
        "갈아타는 비용은 보유 차이 × (편도 + 환전)")
    d = pd.Timestamp(sw["date"])
    old_r = float(r.at[d, sw["from"]])
    got = float(meta["returns"].at[d])
    assert abs(got - ((1 + old_r) * (1 - sw["cost_pct"] / 100) - 1)) < 1e-12, (
        "갈아탄 날 비용을 선택기 수익에서 안 뺐다 — 규칙이 실제보다 좋아 보인다")
    prev_fri = r.index[(r.index < d) & (r.index.weekday == 4)][-1]
    assert r.index[r.index > prev_fri][0] == d, "금요일에 고르고 다음 영업일에 갈아탄다"


def test_the_gate_keeps_the_baseline_when_the_rule_does_not_beat_it():
    r, res = _results(edge=-0.0005)
    meta = E.meta_backtest(res, {}, start=str(r.index[E.WINDOW + 5].date()))
    g = E.gate(meta, res, start=str(r.index[E.WINDOW + 5].date()))
    assert not g["pass"]


def test_a_stale_or_failed_choice_is_not_used():
    st = {"active": "notional50", "asof": "2026-10-09", "gate": {"pass": True}}
    assert E.active_choice(st, "2026-10-12") == "notional50"
    assert E.active_choice(st, "2026-11-30") is None, "주간 잡이 멈추면 옛 선택을 안 쓴다"
    assert E.active_choice({**st, "gate": {"pass": False}}, "2026-10-12") is None
    assert E.active_choice({**st, "active": "nope"}, "2026-10-12") is None


def _frames(n=420):
    rng = np.random.default_rng(3)
    idx = pd.bdate_range("2024-01-01", periods=n)
    out = {}
    for i, k in enumerate(["us_stock:SPY", "us_stock:IEF", "kr_stock:069500.KS",
                           "us_stock:GLD", "crypto:BTC/USDT"]):
        out[k] = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0008 * (i + 1), 0.01, n))),
                           index=idx)
    return out


def test_the_daily_run_follows_the_machine_choice(tmp_path):
    from quant.live import daily as D
    (tmp_path / "engine.json").write_text(json.dumps({"engine": "trend_core",
                                                      "variant": "risk12"}))
    closes = _frames()
    weights = {k: 0.0 for k in closes}
    last = str(pd.bdate_range("2024-01-01", periods=420)[-1].date())
    (tmp_path / E.SELECT_FILE).write_text(json.dumps(
        {"active": "notional50", "asof": last, "gate": {"pass": True}}))
    out = D._core_targets(str(tmp_path), closes, weights)
    assert out["variant"] == "notional50" and out["selected_by"] == "engine_select"
    tgt, _ = E.candidate_targets(T.align_business_days(closes), "notional50")
    day = pd.Timestamp(out["target_day"])
    assert out["weights"]["us_stock:SPY"] == round(float(tgt.loc[day, "us_stock:SPY"]), 6)

    (tmp_path / E.SELECT_FILE).write_text(json.dumps(
        {"active": "notional50", "asof": last, "gate": {"pass": False}}))
    out = D._core_targets(str(tmp_path), closes, weights)
    assert out["variant"] == "risk12" and out["selected_by"] == "engine.json"


def test_every_reason_the_rule_can_give_is_said_on_screen():
    src = (ROOT / "quant" / "portfolio" / "engine_select.py").read_text("utf-8")
    run = (ROOT / "scripts" / "engine_select_run.py").read_text("utf-8")
    codes = set(re.findall(r'\["reason"\] = "(\w+)"', src + run))
    codes |= set(re.findall(r'"reason": "(\w+)"', src))
    js = (ROOT / "docs" / "assets" / "engine-select.js").read_text("utf-8")
    missing = [c for c in codes if f'"{c}":' not in js]
    assert codes and not missing, f"화면이 말하지 못하는 이유: {missing}"


def test_the_choice_reaches_both_screens():
    daily = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert 'status["engine_select"] = engine_select_public(state_dir)' in daily
    for page in ("index.html", "paper.html"):
        html = (ROOT / "docs" / page).read_text("utf-8")
        assert "assets/engine-select.js" in html and "data-engine-select" in html


def test_the_weekly_job_commits_only_from_main():
    wf = (ROOT / ".github" / "workflows" / "engine-select.yml").read_text("utf-8")
    assert "github.ref == 'refs/heads/main'" in wf
    assert "failure() || cancelled()" in wf
