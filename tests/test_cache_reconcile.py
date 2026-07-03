"""데이터 캐싱 + 재시작 정합성 확인 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.data import CachedDataProvider, SyntheticDataProvider


class _CountingProvider(SyntheticDataProvider):
    """호출 횟수를 세는 합성 제공자."""

    def __init__(self):
        super().__init__(seed=3)
        self.calls = 0

    def get_ohlcv(self, *a, **k):
        self.calls += 1
        return super().get_ohlcv(*a, **k)


def test_cache_avoids_refetch(tmp_path):
    inner = _CountingProvider()
    cached = CachedDataProvider(inner, cache_dir=str(tmp_path), ttl_seconds=3600)
    a = cached.get_ohlcv("BTC", "1d", limit=100)
    b = cached.get_ohlcv("BTC", "1d", limit=100)   # 두 번째는 캐시에서
    assert inner.calls == 1                          # inner는 한 번만 호출
    assert len(a) == len(b) == 100
    assert np.allclose(a["close"].to_numpy(), b["close"].to_numpy(), rtol=1e-4)


def test_cache_range_request_not_cached(tmp_path):
    import datetime as dt

    inner = _CountingProvider()
    cached = CachedDataProvider(inner, cache_dir=str(tmp_path))
    cached.get_ohlcv("X", "1d", start=dt.datetime(2020, 1, 1), limit=50)
    cached.get_ohlcv("X", "1d", start=dt.datetime(2020, 1, 1), limit=50)
    assert inner.calls == 2   # 범위 지정은 캐시 안 함


def test_reconcile_reports_position(tmp_path):
    from quant.broker import PaperBroker
    from quant.live import LiveTrader
    from quant.risk import RiskManager

    sent = []

    class N:
        def send(self, msg, level="info"):
            sent.append(msg)

    broker = PaperBroker(cash=10_000)
    broker.market_order("BTC/USDT", "buy", 0.1, 60_000)   # 실제 포지션 생성
    trader = LiveTrader(SyntheticDataProvider(), None, broker,
                        RiskManager(), "BTC/USDT", notifier=N())
    trader.reconcile()
    assert sent and "재시작 정합성" in sent[0] and "BTC/USDT" in sent[0]
