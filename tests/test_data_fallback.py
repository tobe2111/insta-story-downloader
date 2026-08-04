"""데이터 소스 이중화 계약 검사 — 한 소스가 죽어도 실데이터로 기록을 잇는다.

네트워크 없이 검증한다: 소스 함수를 대체 주입해 폴백 '순서'와 표식(attrs)을
고정한다. 실제 원격 응답 형식은 야간 잡이 매일 검증하는 셈이다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.data.crypto import CryptoDataProvider  # noqa: E402
from quant.data.stock import StockDataProvider  # noqa: E402


def _df(n: int = 5) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    return pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0,
                         "close": 1.0, "volume": 1.0}, index=idx)


# ── 주식: yfinance → yahoo-http → stooq → 합성 ────────────────────────────

def test_stock_uses_secondary_source_when_primary_fails(monkeypatch):
    p = StockDataProvider("us_stock")
    monkeypatch.setattr(p, "_via_yfinance",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("죽음")))
    monkeypatch.setattr(p, "_via_yahoo_http", lambda *a, **k: _df())
    df = p.get_ohlcv("SPY", "1d", limit=5)
    assert not df.attrs.get("synthetic_fallback")
    assert df.attrs["source"] == "yahoo-http"


def test_stock_third_source_then_synthetic(monkeypatch):
    p = StockDataProvider("us_stock")
    boom = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("죽음"))  # noqa: E731
    monkeypatch.setattr(p, "_via_yfinance", boom)
    monkeypatch.setattr(p, "_via_yahoo_http", boom)
    monkeypatch.setattr(p, "_via_stooq", lambda *a, **k: _df())
    assert p.get_ohlcv("SPY", "1d", limit=5).attrs["source"] == "stooq"

    monkeypatch.setattr(p, "_via_stooq", boom)
    df = p.get_ohlcv("SPY", "1d", limit=5)
    assert df.attrs.get("synthetic_fallback") is True    # 전부 실패 → 표식된 합성


def test_stock_secondary_sources_daily_only():
    p = StockDataProvider("us_stock")
    with pytest.raises(ValueError):
        p._via_yahoo_http("SPY", "1h", None, None, 100)  # 일봉 전용
    with pytest.raises(ValueError):
        p._via_stooq("069500.KS", "1d", None, None, 100)  # 미국 티커 전용


# ── 코인: 기본 거래소 → 보조 거래소 → 합성 ────────────────────────────────

class _FakeClient:
    def __init__(self, fail: bool):
        self.fail = fail

    def fetch_ohlcv(self, symbol, timeframe="1d", since=None, limit=500):
        if self.fail:
            raise RuntimeError("거래소 점검")
        return [[1735689600000 + i * 86400000, 1, 1, 1, 1, 1]
                for i in range(limit or 5)]


def test_crypto_falls_back_to_secondary_exchange(monkeypatch):
    import quant.data.crypto as qc

    built = []

    def fake_build(exchange_id, api_key="", secret=""):
        built.append(exchange_id)
        # 기본(binance)은 실패, 첫 보조(okx)는 성공
        return _FakeClient(fail=(exchange_id == "binance"))

    monkeypatch.setattr(qc, "_build_client", fake_build)
    p = qc.CryptoDataProvider("binance")
    df = p.get_ohlcv("BTC/USDT", "1d", limit=5)
    assert df.attrs["source"] == "okx"
    assert not df.attrs.get("synthetic_fallback")
    assert built[:2] == ["binance", "okx"]               # 순서 고정


def test_crypto_all_exchanges_down_marks_synthetic(monkeypatch):
    import quant.data.crypto as qc

    monkeypatch.setattr(qc, "_build_client",
                        lambda *a, **k: _FakeClient(fail=True))
    p = qc.CryptoDataProvider("binance")
    df = p.get_ohlcv("BTC/USDT", "1d", limit=5)
    assert df.attrs.get("synthetic_fallback") is True
