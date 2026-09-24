"""저명 투자자 겹쳐 담기(13F)를 종목 선택 ML 피처(x_guru13f)로 — 미래 참조 금지.

사장님 지시(2026-09-24): "투자 잘하는 사람들의 데이터로 종목 선택 정확도를
높인다." 방침(2026-08-27): 재료는 사람이 붙이고, 쓸지는 기계가 정한다.

이 검사가 지키는 계약:
  ① **point-in-time** — 제출일(공개된 날)에야 값이 생긴다. 그 전 봉에는 절대
     붙지 않는다(미래 참조 = 백테스트가 정직하게 좋아 보이고 관문을 다 통과한다).
  ② 미국 종목에만 붙는다(13F는 미국 상장주식 공시). 코인·한국주식엔 안 붙는다.
  ③ 이력이 없거나 한 번도 안 담긴 종목이면 컬럼 자체가 안 생긴다(재료 없음을
     0으로 지어내지 않는다).
  ④ 붙으면 _features가 통과시켜 모델 입력이 된다. 건강 미터는 이 재료를
     분모로도 유령으로도 세지 않는다(UNMETERED_OPTIONAL).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import quant.data.crossasset as CA               # noqa: E402
import quant.data.thirteenf as TF                # noqa: E402
from quant.strategies.ml import (                # noqa: E402
    OPTIONAL_FEATURES, UNMETERED_OPTIONAL, _features, feature_health)


def _bars(start="2026-05-01", end="2026-06-10"):
    idx = pd.date_range(start=start, end=end, freq="D")
    px = [100.0 + i * 0.1 for i in range(len(idx))]
    return pd.DataFrame({"open": px, "high": [p * 1.01 for p in px],
                         "low": [p * 0.99 for p in px], "close": px,
                         "volume": [1e6] * len(idx)}, index=idx)


def _hist(monkeypatch, history):
    monkeypatch.setattr(TF, "load_history", lambda state_dir="state": history)


# ── ① 미래 참조 없음 (가장 중요) ─────────────────────────────────
def test_the_feature_is_zero_before_the_filing_became_public(monkeypatch):
    # 5/15에 공개된 제출 — AAPL을 2명이 겹쳐 담았다
    _hist(monkeypatch, [{"as_of": "2026-05-15",
                         "cluster": {"AAPL": {"count": 2, "filers": ["a", "b"]}}}])
    out = CA.attach_cross_asset(_bars(), "us_stock", "AAPL",
                                fetch=lambda *a, **k: None)
    g = out["x_guru13f"]
    # 공개 전(5/14 이하)에는 값이 없다 — 미래를 훔쳐보지 않는다
    assert pd.isna(g.loc["2026-05-10"]), "제출 공개 전인데 겹쳐 담기가 붙었다(미래 참조)"
    assert pd.isna(g.loc["2026-05-14"])
    # 공개일부터 값이 생기고 그대로 유지된다(전진충전)
    assert g.loc["2026-05-15"] == 2.0
    assert g.loc["2026-06-01"] == 2.0


def test_a_later_filing_raises_the_count_only_from_its_own_date(monkeypatch):
    _hist(monkeypatch, [
        {"as_of": "2026-05-15", "cluster": {"AAPL": {"count": 1, "filers": ["a"]}}},
        {"as_of": "2026-05-25", "cluster": {"AAPL": {"count": 3, "filers": ["a", "b", "c"]}}},
    ])
    g = CA.attach_cross_asset(_bars(), "us_stock", "AAPL",
                              fetch=lambda *a, **k: None)["x_guru13f"]
    assert g.loc["2026-05-20"] == 1.0        # 아직 첫 제출만 공개
    assert g.loc["2026-05-25"] == 3.0        # 둘째 제출 공개일부터
    assert g.loc["2026-06-05"] == 3.0


# ── ② 미국 종목에만 ──────────────────────────────────────────────
def test_only_us_stocks_get_the_feature(monkeypatch):
    _hist(monkeypatch, [{"as_of": "2026-05-15",
                         "cluster": {"AAPL": {"count": 2, "filers": ["a", "b"]}}}])
    for market, sym in [("crypto", "BTC/USDT"), ("kr_stock", "005930.KS")]:
        out = CA.attach_cross_asset(_bars(), market, sym,
                                    fetch=lambda *a, **k: None)
        assert "x_guru13f" not in out.columns, f"{market}에 13F가 붙었다"


# ── ③ 재료 없음은 컬럼 없음 (지어내지 않는다) ────────────────────
def test_no_history_means_no_column(monkeypatch):
    _hist(monkeypatch, [])
    out = CA.attach_cross_asset(_bars(), "us_stock", "AAPL",
                                fetch=lambda *a, **k: None)
    assert "x_guru13f" not in out.columns


def test_a_symbol_never_held_gets_no_column(monkeypatch):
    """대조군 — 이력은 있지만 이 종목을 아무도 안 담았으면 컬럼 없음."""
    _hist(monkeypatch, [{"as_of": "2026-05-15",
                         "cluster": {"AAPL": {"count": 2, "filers": ["a", "b"]}}}])
    out = CA.attach_cross_asset(_bars(), "us_stock", "MSFT",
                                fetch=lambda *a, **k: None)
    assert "x_guru13f" not in out.columns    # MSFT는 안 담김


# ── ④ 모델이 쓰고, 미터는 무시한다 ───────────────────────────────
def test_features_passes_the_column_to_the_model(monkeypatch):
    _hist(monkeypatch, [{"as_of": "2026-05-15",
                         "cluster": {"AAPL": {"count": 2, "filers": ["a", "b"]}}}])
    out = CA.attach_cross_asset(_bars(), "us_stock", "AAPL",
                                fetch=lambda *a, **k: None)
    feats = _features(out)
    assert "x_guru13f" in feats.columns, "모델 입력에 13F가 안 실렸다"


def test_the_health_meter_neither_counts_nor_flags_it():
    """분모로도 유령으로도 안 센다 — 이력 유무에 따라 경고등이 흔들리지 않게."""
    assert "x_guru13f" in UNMETERED_OPTIONAL
    # 붙어 있어도 unexpected로 잡지 않는다(미국 시장 분모엔 없지만 유령 아님)
    df = _bars()
    df["x_guru13f"] = 2.0
    h = feature_health(_features(df), "us_stock", "AAPL")
    assert "x_guru13f" not in h["unexpected_optional"]
    assert "x_guru13f" not in h["missing_optional"]


def test_it_is_registered_as_an_optional_feature():
    assert "x_guru13f" in OPTIONAL_FEATURES
