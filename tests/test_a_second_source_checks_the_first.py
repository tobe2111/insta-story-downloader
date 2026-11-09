"""오늘 매매에 쓰는 시세를 다른 소스와 대조한다 (2026-11-09 감사 363)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant.data import second_opinion as S


def _df(rets, start="2026-11-02", source="yfinance", scale=1.0):
    idx = pd.bdate_range(start, periods=len(rets) + 1)
    close = scale * 100 * np.cumprod([1.0] + list(1 + np.array(rets)))
    df = pd.DataFrame({"close": close}, index=idx)
    df.attrs["source"] = source
    return df


def test_matching_returns_pass_even_when_price_levels_differ():
    a = _df([0.01, -0.005, 0.002, 0.003, -0.01])
    b = _df([0.01, -0.005, 0.002, 0.003, -0.01], scale=1.07)    # 무조정가는 수준이 다르다
    assert S.compare_returns(a, b)["ok"] is True


def test_a_day_that_disagrees_is_named():
    a = _df([0.01, -0.005, 0.002, 0.003, -0.01])
    b = _df([0.01, -0.005, 0.002, -0.05, -0.01])
    out = S.compare_returns(a, b)
    assert out["ok"] is False and "%p" in out["why"]


def test_too_little_overlap_is_unmeasured_not_failed():
    a = _df([0.01, 0.0])
    b = _df([0.01, 0.0], start="2025-01-01")
    assert S.compare_returns(a, b)["ok"] is None


def test_korea_says_it_has_no_independent_source():
    out = S.second_opinion("kr_stock", "069500.KS", _df([0.01] * 5))
    assert out["ok"] is None and "독립 소스" in out["why"]


def test_a_dead_second_source_does_not_block(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("stooq down")
    monkeypatch.setattr(S, "_second", lambda m, s, p: ("stooq", boom))
    monkeypatch.setattr(S, "_dead", {})
    out = S.second_opinion("us_stock", "SPY", _df([0.01] * 5))
    assert out["ok"] is None and "응답 없음" in out["why"]
    for _ in range(S.BREAK_AFTER):
        S.second_opinion("us_stock", "QQQ", _df([0.01] * 5))
    out = S.second_opinion("us_stock", "IEF", _df([0.01] * 5))
    assert "더 묻지 않는다" in out["why"], "죽은 소스를 종목마다 계속 기다린다"


def test_the_batch_holds_a_disagreeing_symbol_and_says_so():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    src = (root / "quant" / "live" / "daily.py").read_text("utf-8")
    assert 'raise RuntimeError(f"두 소스 불일치' in src and "if require_real_data:" in src
    assert '"second_opinion":' in src
    html = (root / "docs" / "index.html").read_text("utf-8")
    assert "pfLast.second_opinion" in html


def test_a_disagreeing_symbol_is_held_by_the_real_batch(monkeypatch, tmp_path):
    """계좌를 실제로 돌린다 — 어긋난 종목은 그날 건너뛰고 사유가 남는다."""
    import json

    import quant.data.second_opinion as SO
    import quant.live.daily as dl

    class _P:
        def get_ohlcv(self, symbol, *a, **k):
            idx = pd.date_range(end=pd.Timestamp.today().normalize() - pd.Timedelta(days=1),
                                periods=300, freq="D")
            c = 100 * np.exp(np.cumsum(np.random.default_rng(len(symbol)).normal(0, 0.01, 300)))
            df = pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99,
                               "close": c, "volume": 1e6}, index=idx)
            df.attrs["source"] = "yfinance"
            return df

    class _Flat:
        name, allow_short = "fixed", False

        def generate_signals(self, df):
            return pd.Series(0.0, index=df.index)

    monkeypatch.setattr(dl, "usdkrw", lambda *a, **k: 1400.0)
    monkeypatch.setattr("quant.data.get_provider", lambda m: _P())
    monkeypatch.setattr(dl, "champion_strategy", lambda *a, **k: _Flat())
    monkeypatch.setattr(dl, "champion_spec", lambda *a, **k: {"strategy": "fixed", "params": {}})
    monkeypatch.setattr(dl, "bar_status", lambda *a, **k: None)
    monkeypatch.setattr(SO, "second_opinion", lambda m, s, df: (
        {"ok": False, "why": "어긋남"} if s == "QQQ" else {"ok": True, "n": 5}))
    out = dl.run_daily_portfolio([("us_stock", "SPY"), ("us_stock", "QQQ")],
                                 state_dir=str(tmp_path), require_real_data=True)
    st = json.loads((tmp_path / "paper" / "portfolio_ALL.json").read_text("utf-8"))
    rec = st["history"][-1]
    champ = rec.get("champion") or {}
    assert "us_stock:QQQ" in (champ.get("skipped") or []), champ
    assert "두 소스 불일치" in (champ.get("skipped_why") or {}).get("us_stock:QQQ", "")
    assert rec["second_opinion"]["mismatch"] == {"us_stock:QQQ": "어긋남"}
