"""알파 13차 계약 검사 — FRED 확장(신용·달러·기대인플레) + 거시 브리핑 (fs8).

핵심 계약:
  ① 키 없으면 FRED 피처 전부 생략(기존과 동일 동작)
  ② 키 있으면 시장별로 맞는 피처가 붙는다 — 미국(4종)·한국(3종)·코인(2종)
  ③ 새 일별 시리즈 3종의 발표 시차가 1일로 등록(기본 45일 오적용 방지)
  ④ 거시 브리핑: 키 없으면 None, 있으면 items+한글 해석(note) — 표시 전용
  ⑤ status.json 배선 + 사이트 카드 + explain 한글 해석
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.data import crossasset  # noqa: E402
from quant.data.crossasset import attach_cross_asset  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

FRED_FEATS = {"x_t10y2y", "x_hy_spread", "x_usd_chg5", "x_t10yie_chg5"}


def _df(n: int = 60, start: str = "2026-06-01") -> pd.DataFrame:
    idx = pd.date_range(start, periods=n, freq="D")
    v = 100.0 + np.arange(n, dtype=float)
    return pd.DataFrame({"open": v, "high": v + 1, "low": v - 1,
                         "close": v, "volume": 1000.0}, index=idx)


def _fetch(market, symbol, limit):
    return _df(80, start="2026-05-20")


def _fake_fred(monkeypatch):
    """FRED 조회를 네트워크 없이 대체 — 시리즈별 구분 가능한 상수."""
    import quant.data.macro as macro
    base = {"T10Y2Y": 0.5, "BAMLH0A0HYM2": 4.0, "DTWEXBGS": 120.0,
            "T10YIE": 2.3}

    def fake(series_id, **kw):
        v = base.get(series_id)
        if v is None:
            return pd.Series(dtype=float)
        idx = pd.date_range("2026-05-01", periods=80, freq="D")
        return pd.Series(v + np.linspace(0, 1, 80), index=idx)
    monkeypatch.setattr(macro, "fred_series", fake)


def setup_function(_):
    import os
    crossasset._MEMO.clear()
    os.environ.pop("FRED_API_KEY", None)


# ── ①② 키 게이트 + 시장별 구성 ─────────────────────────────────


def test_no_key_no_fred_features(monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    for market, sym in (("us_stock", "AAPL"), ("kr_stock", "005930.KS"),
                        ("crypto", "ETH/USDT")):
        out = attach_cross_asset(_df(), market, sym, fetch=_fetch)
        assert not (set(out.columns) & FRED_FEATS)


def test_with_key_market_specific_features(monkeypatch):
    _fake_fred(monkeypatch)
    monkeypatch.setenv("FRED_API_KEY", "dummy")
    us = attach_cross_asset(_df(), "us_stock", "AAPL", fetch=_fetch)
    assert FRED_FEATS <= set(us.columns)                 # 미국: 4종 전부
    crossasset._MEMO.clear()
    kr = attach_cross_asset(_df(), "kr_stock", "005930.KS", fetch=_fetch)
    assert {"x_t10y2y", "x_hy_spread", "x_usd_chg5"} <= set(kr.columns)
    assert "x_t10yie_chg5" not in kr.columns
    crossasset._MEMO.clear()
    cr = attach_cross_asset(_df(), "crypto", "ETH/USDT", fetch=_fetch)
    assert {"x_usd_chg5", "x_hy_spread"} <= set(cr.columns)
    assert "x_t10y2y" not in cr.columns
    # 수준 피처의 값 확인 — 하이일드 스프레드는 원값 그대로 붙는다
    assert 3.9 < float(us["x_hy_spread"].dropna().iloc[0]) < 5.1


# ── ③ 발표 시차 등록 ───────────────────────────────────────────


def test_new_daily_series_have_one_day_lag():
    from quant.data.macro import PUBLICATION_LAG_DAYS
    for sid in ("BAMLH0A0HYM2", "DTWEXBGS", "T10YIE"):
        assert PUBLICATION_LAG_DAYS[sid] == 1


# ── ④ 거시 브리핑 ──────────────────────────────────────────────


def test_macro_summary_gated_and_interpreted(monkeypatch):
    from quant.live import macro_brief
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    assert macro_brief.macro_summary() is None           # 키 없음 → None
    _fake_fred(monkeypatch)
    monkeypatch.setenv("FRED_API_KEY", "dummy")
    m = macro_brief.macro_summary()
    assert m and len(m["items"]) == 4
    assert "note" in m and m["note"]                     # 한글 해석 존재
    assert any(i["key"] == "usd_idx" and "chg5_pct" in i for i in m["items"])


def test_interpret_hand_cases():
    from quant.live.macro_brief import _interpret
    txt = _interpret({"t10y2y": {"value": -0.3},
                      "hy_spread": {"value": 6.0},
                      "usd_idx": {"chg5_pct": 1.2}})
    assert "역전" in txt and "경색" in txt and "강세" in txt
    txt2 = _interpret({"t10y2y": {"value": 0.8},
                       "hy_spread": {"value": 3.0},
                       "usd_idx": {"chg5_pct": -1.0}})
    assert "정상" in txt2 and "안정" in txt2 and "약세" in txt2


# ── ⑤ 배선 ─────────────────────────────────────────────────────


def test_wired_into_status_site_and_explain():
    dl = (ROOT / "quant" / "live" / "daily.py").read_text(encoding="utf-8")
    assert "macro_summary" in dl and '"macro"' in dl
    p = (ROOT / "docs" / "paper.html").read_text(encoding="utf-8")
    assert "오늘의 거시" in p and "st.macro" in p
    from quant.live.explain import FEATURE_KO, _feature_note
    for k in ("x_hy_spread", "x_usd_chg5", "x_t10yie_chg5"):
        assert k in FEATURE_KO
    assert "경색" in _feature_note("x_hy_spread", 5.5)
    assert "강세" in _feature_note("x_usd_chg5", 0.01)
    from quant.strategies.ml import FEATURE_SET
    assert int(FEATURE_SET.split(":")[0][2:]) >= 8
