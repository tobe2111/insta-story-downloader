"""데이터 캐싱 — 반복 백테스트 시 거래소 API 재호출을 줄인다.

같은 (종목·타임프레임·봉수) 요청을 디스크에 CSV로 저장해두고, TTL 안이면
재사용한다. 최신 데이터가 필요한 경우를 위해 TTL(기본 1시간)을 두어 오래된
캐시는 자동으로 새로 받는다. start/end 범위를 지정한 요청은 캐시하지 않는다.
"""
from __future__ import annotations

import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from quant.data.base import DataProvider
from quant.utils.logging import get_logger

log = get_logger("data.cache")


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def _provider_id(inner: DataProvider) -> str:
    """캐시 키에 쓸 제공자 식별자. 클래스명 + 거래소/시장 구분자."""
    parts = [type(inner).__name__]
    for attr in ("exchange_id", "market"):
        val = getattr(inner, attr, None)
        if val:
            parts.append(str(val))
    return _safe("-".join(parts))


class CachedDataProvider(DataProvider):
    """임의의 DataProvider를 감싸 디스크 캐시를 추가한다."""

    def __init__(self, inner: DataProvider, cache_dir: str = "data_cache",
                 ttl_seconds: int = 3600, max_files: int = 1000):
        self.inner = inner
        self.cache_dir = Path(cache_dir)
        self.ttl_seconds = ttl_seconds
        # 캐시 파일 수 상한. TTL은 '신선도'만 관리하고 파일을 지우지 않으므로,
        # 여러 종목·타임프레임·봉수를 오래 스윕하면 data_cache/가 무한히 커진다.
        # 상한을 넘으면 오래된 것부터 삭제한다. 0 이하면 무제한(비활성).
        self.max_files = max_files

    def _prune(self) -> None:
        """캐시 파일 수가 상한을 넘으면 mtime이 오래된 것부터 삭제한다."""
        if self.max_files <= 0:
            return
        try:
            files = sorted(self.cache_dir.glob("*.csv"),
                           key=lambda p: p.stat().st_mtime)
        except OSError:
            return
        for p in files[:max(0, len(files) - self.max_files)]:
            try:
                p.unlink()
            except OSError:
                pass

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1d",
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 500,
    ) -> pd.DataFrame:
        # 범위 지정 요청은 캐시하지 않는다 (키가 복잡해짐)
        if start is not None or end is not None:
            return self.inner.get_ohlcv(symbol, timeframe, start, end, limit)

        # 캐시 키에 내부 제공자 정체성을 포함한다. 그렇지 않으면 서로 다른
        # 거래소/시장(예: binance vs upbit, us_stock vs kr_stock)이 같은 심볼로
        # 캐시를 덮어써 잘못된 데이터를 반환할 수 있다.
        provider = _provider_id(self.inner)
        path = self.cache_dir / f"{provider}_{_safe(symbol)}_{_safe(timeframe)}_{limit}.csv"
        if path.exists() and (time.time() - path.stat().st_mtime) < self.ttl_seconds:
            try:
                df = pd.read_csv(path, index_col=0, parse_dates=True)
                return self._validate(df)
            except Exception as exc:  # noqa: BLE001
                log.warning("캐시 로드 실패(%s), 새로 받습니다.", exc)

        df = self.inner.get_ohlcv(symbol, timeframe, None, None, limit)
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            df.to_csv(path)
            self._prune()      # 무한 성장 방지(오래된 캐시 삭제)
        except Exception as exc:  # noqa: BLE001
            log.warning("캐시 저장 실패(%s).", exc)
        return df
