"""암호화폐 데이터 제공자 (ccxt 기반)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd

from quant.data.base import DataProvider
from quant.utils.logging import get_logger

log = get_logger("data.crypto")


# 기본 거래소 실패 시 순서대로 시도하는 보조 거래소 — 전 세계 공용 현물 시세라
# 어느 거래소든 BTC/USDT 같은 주요 페어의 일봉은 사실상 동일하다.
_FALLBACK_EXCHANGES = ("okx", "kucoin", "kraken")


def _build_client(exchange_id: str, api_key: str = "", secret: str = ""):
    """ccxt 클라이언트 생성 (테스트에서 대체 주입할 수 있게 모듈 함수로 분리)."""
    import ccxt

    klass = getattr(ccxt, exchange_id)
    return klass({"apiKey": api_key, "secret": secret, "enableRateLimit": True})


class CryptoDataProvider(DataProvider):
    """ccxt를 통해 거래소 OHLCV를 가져온다 (기본: 바이낸스).

    기본 거래소가 실패하면 보조 거래소(_FALLBACK_EXCHANGES)를 순서대로 시도하고,
    전부 실패해야만 SyntheticDataProvider로 폴백한다 — 단일 거래소 의존은
    야간 자동화의 최약점이었다(지역 차단·점검 하나로 그날 기록이 빈다).
    """

    def __init__(self, exchange: str = "binance", api_key: str = "", secret: str = ""):
        self.exchange_id = exchange
        self._client = None
        try:
            self._client = _build_client(exchange, api_key, secret)
        except Exception as exc:  # noqa: BLE001
            log.warning("ccxt 초기화 실패(%s). 보조 거래소/합성 폴백으로 진행합니다.", exc)

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1d",
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 500,
    ) -> pd.DataFrame:
        attempts: list[tuple[str, object]] = []
        if self._client is not None:
            attempts.append((self.exchange_id, self._client))
        attempts += [(ex, None) for ex in _FALLBACK_EXCHANGES
                     if ex != self.exchange_id]

        for ex_id, client in attempts:
            try:
                if client is None:
                    client = _build_client(ex_id)
                df = self._fetch(client, symbol, timeframe, start, end, limit)
                df.attrs["source"] = ex_id
                if ex_id != self.exchange_id:
                    log.info("%s: 보조 거래소(%s)로 시세 수신 (%d봉)",
                             symbol, ex_id, len(df))
                return df
            except Exception as exc:  # noqa: BLE001
                log.warning("%s 시세 조회 실패[%s]: %s", symbol, ex_id, exc)

        log.warning("%s: 모든 거래소 실패. 합성 데이터로 폴백.", symbol)
        return self._fallback(symbol, timeframe, start, end, limit)

    def _fetch(self, client, symbol, timeframe, start, end, limit) -> pd.DataFrame:
        # 거래소 타임스탬프는 UTC epoch(ms) 기준이다. naive datetime을
        # start.timestamp()로 바꾸면 로컬 시간대가 섞여 since가 어긋나므로,
        # 시간대 정보가 없으면 UTC로 간주해 변환한다.
        since = None
        if start is not None:
            ts = pd.Timestamp(start)
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            since = int(ts.timestamp() * 1000)
        raw = client.fetch_ohlcv(
            symbol, timeframe=timeframe, since=since, limit=limit
        )
        df = pd.DataFrame(
            raw, columns=["ts", "open", "high", "low", "close", "volume"]
        )
        # unit="ms"는 거래소 epoch(UTC)를 그대로 tz-naive 타임스탬프로 만든다.
        df.index = pd.to_datetime(df["ts"], unit="ms")
        # end가 지정되면 그 이후 봉은 잘라낸다(fetch_ohlcv는 since만 지원).
        # 인덱스는 naive-UTC이므로, end가 tz-aware여도 naive-UTC로 맞춰 비교한다
        # (안 맞추면 'naive vs aware' TypeError → 조용한 합성 폴백이 난다).
        if end is not None:
            end_ts = pd.Timestamp(end)
            if end_ts.tzinfo is not None:
                end_ts = end_ts.tz_convert("UTC").tz_localize(None)
            df = df[df.index <= end_ts]
        out = self._validate(df)
        # ⚠️ 여기엔 빈 결과 검사가 **아예 없었다**(감사 163, 주식 쪽 형제).
        #    거래소가 빈 리스트를 주거나(상장폐지·심볼 오타·점검) end 컷이
        #    다 잘라내면 0봉 프레임이 그대로 '성공'으로 올라가, 보조 거래소를
        #    안 거치고 합성 폴백 표식도 없이 반환됐다.
        if out.empty:
            raise ValueError("검증 후 빈 결과")
        return out

    @staticmethod
    def _fallback(symbol, timeframe, start, end, limit) -> pd.DataFrame:
        from quant.data.synthetic import SyntheticDataProvider

        df = SyntheticDataProvider().get_ohlcv(
            symbol, timeframe, start, end, limit
        )
        # '진짜 시세가 아니라 폴백'임을 표식한다. 이 표식이 없으면
        # CachedDataProvider가 더미 데이터를 실제 거래소 키로 디스크에 저장해,
        # 네트워크가 복구된 뒤에도 TTL 동안 가짜 시세를 계속 재사용한다.
        df.attrs["synthetic_fallback"] = True
        return df
