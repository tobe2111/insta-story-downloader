"""알파 5차 계약 검사 — 크로스에셋 피처·수급 모멘텀·체결 공개·TradingView.

핵심 계약:
  ① 시장별로 맞는 크로스에셋 컬럼(x_*)이 붙는다 (코인=BTC, 미국=SPY·금리,
     한국=SPY·환율) — 자기 자신은 제외
  ② 정렬은 전진충전(ffill)만 — 미래 벤치마크 값이 과거 봉에 붙을 수 없다
  ③ 합성 폴백·조회 실패 벤치마크는 조용히 생략(df 불변, 예외 없음)
  ④ ML이 x_ 컬럼을 자동 포함하고, 펀딩 변화(x_funding_chg)를 파생한다 (fs3)
  ⑤ 재학습·페이퍼 두 경로 모두에 부착이 연결돼 있다(스냅샷·해시 보존)
  ⑥ 홈페이지에 체결(시점·가격)·예약 주문·TradingView 차트가 나온다
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


def _df(n: int = 60, start: str = "2026-06-01") -> pd.DataFrame:
    idx = pd.date_range(start, periods=n, freq="D")
    v = 100.0 + np.arange(n, dtype=float)
    return pd.DataFrame({"open": v, "high": v + 1, "low": v - 1,
                         "close": v, "volume": 1000.0}, index=idx)


def _fetch(market, symbol, limit):
    """가짜 벤치마크 — 어떤 심볼이 요청됐는지 기록한다."""
    _fetch.calls.append((market, symbol))
    return _df(80, start="2026-05-20")


def setup_function(_):
    import os
    crossasset._MEMO.clear()
    _fetch.calls = []
    os.environ.pop("FRED_API_KEY", None)   # 테스트는 FRED 네트워크 미사용


# ── ① 시장별 컬럼 구성 ─────────────────────────────────────────


def test_crypto_alt_gets_btc_and_btc_itself_does_not():
    out = attach_cross_asset(_df(), "crypto", "ETH/USDT", fetch=_fetch)
    assert "x_btc_ret5" in out.columns
    out2 = attach_cross_asset(_df(), "crypto", "BTC/USDT", fetch=_fetch)
    assert "x_btc_ret5" not in out2.columns


def test_us_gets_spy_and_rates_spy_excludes_self():
    out = attach_cross_asset(_df(), "us_stock", "AAPL", fetch=_fetch)
    assert "x_spy_ret5" in out.columns and "x_tnx_chg5" in out.columns
    out2 = attach_cross_asset(_df(), "us_stock", "SPY", fetch=_fetch)
    assert "x_spy_ret5" not in out2.columns and "x_tnx_chg5" in out2.columns


def test_kr_gets_us_flow_and_fx():
    out = attach_cross_asset(_df(), "kr_stock", "005930.KS", fetch=_fetch)
    assert "x_spy_ret5" in out.columns and "x_usdkrw_ret5" in out.columns


def test_benchmark_fetched_once_per_run():
    """20종목 순회가 같은 벤치를 반복 조회하지 않는다(메모)."""
    for sym in ("AAPL", "MSFT", "NVDA"):
        attach_cross_asset(_df(), "us_stock", sym, fetch=_fetch)
    spy_calls = [c for c in _fetch.calls if c[1] == "SPY"]
    assert len(spy_calls) == 1


# ── ② 전진충전 정렬(룩어헤드 없음) ─────────────────────────────


def test_alignment_is_ffill_only_no_future():
    df = _df(30, start="2026-06-01")

    def fetch(market, symbol, limit):
        # 벤치는 df 중간(6/15)까지만 존재 — 이후 봉에는 마지막 값이 ffill
        return _df(15, start="2026-06-01")
    out = attach_cross_asset(df, "crypto", "ETH/USDT", fetch=fetch)
    col = out["x_btc_ret5"]
    # 벤치 마지막 날짜(6/15) 이후 값은 전부 같아야 한다(ffill — 새 정보 없음)
    tail = col.loc["2026-06-15":]
    assert tail.nunique() == 1
    # 벤치 시작 전(5일 수익률 미정의 구간)은 NaN — 미래를 당겨오지 않는다
    assert col.iloc[:5].isna().all() or np.isfinite(col.iloc[5])


# ── ③ 실패 안전 ────────────────────────────────────────────────


def test_synthetic_fallback_bench_is_ignored():
    def fetch(market, symbol, limit):
        d = _df(80)
        d.attrs["synthetic_fallback"] = True
        return d
    out = attach_cross_asset(_df(), "kr_stock", "005930.KS", fetch=fetch)
    assert "x_spy_ret5" not in out.columns    # 가짜 벤치로 피처를 만들지 않는다


def test_fetch_failure_leaves_df_unchanged():
    def fetch(market, symbol, limit):
        raise RuntimeError("네트워크 죽음")
    df = _df()
    out = attach_cross_asset(df, "us_stock", "AAPL", fetch=fetch)
    assert list(out.columns) == list(df.columns)


# ── ④ ML 통합 — x_ 자동 포함 + 펀딩 변화 ───────────────────────


def test_ml_includes_x_columns_and_funding_change():
    from quant.strategies.ml import FEATURE_SET, _features
    assert FEATURE_SET.startswith("fs4")
    df = _df(120)
    df["x_spy_ret5"] = 0.01
    df["funding"] = 0.0001
    feats = _features(df)
    assert "x_spy_ret5" in feats.columns
    assert "x_funding" in feats.columns and "x_funding_chg" in feats.columns


def test_explain_names_cover_new_features():
    from quant.live.explain import FEATURE_KO, _feature_note
    for k in ("x_btc_ret5", "x_spy_ret5", "x_tnx_chg5", "x_usdkrw_ret5",
              "x_funding_chg"):
        assert k in FEATURE_KO
    assert "%" in _feature_note("x_spy_ret5", 0.021)


# ── ⑤ 파이프라인 연결 ──────────────────────────────────────────


def test_attach_wired_into_retrain_and_daily():
    rt = (ROOT / "quant" / "live" / "retrain.py").read_text(encoding="utf-8")
    dl = (ROOT / "quant" / "live" / "daily.py").read_text(encoding="utf-8")
    assert rt.count("attach_cross_asset") >= 2      # import + 호출
    assert dl.count("attach_cross_asset") >= 4      # 개별·통합 두 경로


# ── ⑥ 홈페이지 — 체결·예약·차트 ────────────────────────────────


def test_today_shows_fills_pending_and_tradingview():
    t = (ROOT / "docs" / "today.html").read_text(encoding="utf-8")
    assert "오늘의 체결" in t and "예약 주문" in t
    assert "pending_next_open" in t and "다음 장 시가" in t
    assert "tradingview" in t.lower() and "BINANCE:" in t and "KRX:" in t


def test_portfolio_record_carries_pending_and_typed_fills():
    dl = (ROOT / "quant" / "live" / "daily.py").read_text(encoding="utf-8")
    assert "pending_next_open" in dl
    assert '"type": "시가"' in dl and '"type": "즉시"' in dl


def test_fng_wired_for_crypto_and_named():
    """공포탐욕지수(x_fng)가 코인 경로에 연결되고 한글 해석이 있다.

    뉴스 '원문'은 재현 검증이 불가능해 판단에 쓰지 않는다 — 숫자로 정제·
    보관되는 심리 지표만 쓴다는 원칙의 구현.
    """
    ca = (ROOT / "quant" / "data" / "crossasset.py").read_text(encoding="utf-8")
    assert "x_fng" in ca and "fear_greed_history" in ca
    from quant.live.explain import FEATURE_KO, _feature_note
    assert "x_fng" in FEATURE_KO
    assert "탐욕" in _feature_note("x_fng", 0.8)
    assert "공포" in _feature_note("x_fng", 0.2)


# ── ⑦ 수급 2축(OI) + FRED 장단기 금리차 ────────────────────────


def test_oi_attach_and_ml_derives_change():
    """OI 수준 컬럼 부착 → ML이 x_oi_chg5 파생. 실패 시 원본 유지."""
    from quant.data.openinterest import attach_open_interest
    from quant.strategies.ml import _features
    df = _df(40)
    oi = pd.Series(1000.0 + np.arange(35) * 10,
                   index=pd.date_range("2026-06-01", periods=35, freq="D"))
    out = attach_open_interest(df, "BTC/USDT", fetch=lambda s: oi)
    assert "oi" in out.columns
    feats = _features(out)
    assert "x_oi_chg5" in feats.columns
    # 실패 폴백
    bad = attach_open_interest(df, "BTC/USDT",
                               fetch=lambda s: (_ for _ in ()).throw(RuntimeError()))
    assert "oi" not in bad.columns


def test_oi_wired_next_to_funding():
    rt = (ROOT / "quant" / "live" / "retrain.py").read_text(encoding="utf-8")
    dl = (ROOT / "quant" / "live" / "daily.py").read_text(encoding="utf-8")
    assert rt.count("attach_open_interest") >= 2
    assert dl.count("attach_open_interest") >= 4     # 개별·통합 두 경로


def test_fred_t10y2y_gated_by_key_and_wired(monkeypatch):
    """FRED 피처는 키가 있을 때만 붙는다(없으면 조용히 생략)."""
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    crossasset._MEMO.clear()
    out = attach_cross_asset(_df(), "us_stock", "AAPL", fetch=_fetch)
    assert "x_t10y2y" not in out.columns             # 키 없음 → 생략
    ca = (ROOT / "quant" / "data" / "crossasset.py").read_text(encoding="utf-8")
    assert "T10Y2Y" in ca and "FRED_API_KEY" in ca
    # 워크플로가 시크릿을 전달한다
    for wf in ("nightly-retrain.yml", "daily-paper.yml"):
        y = (ROOT / ".github" / "workflows" / wf).read_text(encoding="utf-8")
        assert "FRED_API_KEY" in y
    from quant.live.explain import FEATURE_KO
    assert "x_oi_chg5" in FEATURE_KO and "x_t10y2y" in FEATURE_KO
