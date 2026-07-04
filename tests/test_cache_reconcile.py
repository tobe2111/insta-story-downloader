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


def test_cache_evicts_oldest_over_cap(tmp_path):
    """캐시 파일 수가 상한을 넘으면 오래된 것부터 삭제된다(무한 성장 방지)."""
    inner = _CountingProvider()
    cached = CachedDataProvider(inner, cache_dir=str(tmp_path), max_files=3)
    for i in range(6):                       # 6개 서로 다른 종목 → 파일 6개 시도
        cached.get_ohlcv(f"SYM{i}", "1d", limit=50)
    csvs = list(Path(str(tmp_path)).glob("*.csv"))
    assert len(csvs) <= 3                     # 상한으로 제한됨
    # 가장 최근 것(SYM5)은 남아 있어야 한다
    assert any("SYM5" in p.name for p in csvs)


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
