"""데이터 제공자 계층 버그 수정 회귀 테스트 (합성/캐시/암호화폐).

감사에서 발견한 결정론·캐시 충돌·타임스탬프 버그를 고정한다.
(pandas 필요 — 네트워크는 목으로 대체하므로 오프라인에서 동작)
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.data.cache import CachedDataProvider, _provider_id
from quant.data.crypto import CryptoDataProvider
from quant.data.synthetic import SyntheticDataProvider, _symbol_seed


# ── 합성 데이터 결정론 ──────────────────────────────────────────────────
def test_symbol_seed_is_deterministic_and_known():
    """blake2b 기반 시드는 프로세스/PYTHONHASHSEED와 무관하게 고정값이다."""
    a = _symbol_seed("BTC/USDT")
    b = _symbol_seed("BTC/USDT")
    assert a == b
    assert 0 <= a < 10_000
    # 다른 심볼은 (거의 항상) 다른 시드
    assert _symbol_seed("ETH/USDT") != a


def test_synthetic_same_symbol_reproducible():
    p1 = SyntheticDataProvider(seed=7)
    p2 = SyntheticDataProvider(seed=7)
    d1 = p1.get_ohlcv("AAPL", "1d", limit=50)
    d2 = p2.get_ohlcv("AAPL", "1d", limit=50)
    assert (d1["close"].to_numpy() == d2["close"].to_numpy()).all()


def test_synthetic_different_symbols_differ():
    p = SyntheticDataProvider(seed=7)
    a = p.get_ohlcv("AAA", "1d", limit=50)["close"].to_numpy()
    b = p.get_ohlcv("BBB", "1d", limit=50)["close"].to_numpy()
    assert not (a == b).all()


# ── 캐시 제공자 정체성 ──────────────────────────────────────────────────
def test_provider_id_distinguishes_exchanges():
    binance = CryptoDataProvider(exchange="binance")
    upbit = CryptoDataProvider(exchange="upbit")
    assert _provider_id(binance) != _provider_id(upbit)
    assert "binance" in _provider_id(binance)


def test_cache_keys_do_not_collide_across_providers(tmp_path):
    """서로 다른 거래소가 같은 심볼로 캐시를 덮어쓰지 않는다(버그 수정)."""
    class Stub:
        def __init__(self, exchange_id, price):
            self.exchange_id = exchange_id
            self._price = price

        def get_ohlcv(self, symbol, timeframe="1d", start=None, end=None, limit=500):
            idx = pd.date_range("2020-01-01", periods=limit, freq="D")
            return pd.DataFrame(
                {"open": self._price, "high": self._price, "low": self._price,
                 "close": self._price, "volume": 1.0}, index=idx)

    a = CachedDataProvider(Stub("binance", 100.0), cache_dir=str(tmp_path))
    b = CachedDataProvider(Stub("upbit", 200.0), cache_dir=str(tmp_path))
    da = a.get_ohlcv("BTC", "1d", limit=10)
    db = b.get_ohlcv("BTC", "1d", limit=10)
    # 캐시 키가 분리되어 각 거래소의 값이 보존되어야 한다
    assert da["close"].iloc[0] == 100.0
    assert db["close"].iloc[0] == 200.0


# ── 암호화폐 end 필터 + UTC 타임스탬프 ──────────────────────────────────
class _FakeExchange:
    def fetch_ohlcv(self, symbol, timeframe="1d", since=None, limit=500):
        base = 1_577_836_800_000  # 2020-01-01 UTC (ms)
        day = 86_400_000
        return [[base + i * day, 100.0, 101.0, 99.0, 100.5, 5.0]
                for i in range(10)]


def test_crypto_respects_end_filter():
    """end를 주면 그 이후 봉은 잘라낸다(fetch_ohlcv는 since만 지원 → 사후 필터)."""
    prov = CryptoDataProvider.__new__(CryptoDataProvider)
    prov.exchange_id = "binance"
    prov._client = _FakeExchange()
    df = prov.get_ohlcv("BTC/USDT", "1d", end=datetime(2020, 1, 5), limit=10)
    assert df.index.max() <= pd.Timestamp("2020-01-05")
    assert len(df) == 5   # 01-01 ~ 01-05
