"""무기한 선물 미결제약정(OI) — 펀딩비와 함께 코인 수급의 양대 공개 지표.

미결제약정 = 청산되지 않은 선물 계약 총량. 늘면 새 포지션이 쌓이는 중(추세에
연료), 줄면 포지션이 풀리는 중(청산·차익실현). 펀딩비(방향 과열도)와 결이
다른 정보라 함께 쓰면 수급 그림이 완성된다.

⚠️ 정직한 한계: 바이낸스 공개 API는 OI '이력'을 약 30일만 보관한다. 그래서
   이 피처는 최근 구간에만 값이 있고 그 이전은 NaN이다 — ML의 valid 판정은
   기본 피처만 보므로 무해하고, 시간이 지나며 스냅샷에 이력이 쌓인다.

ccxt 미설치·네트워크 오류 시 원본 df를 그대로 반환한다(예외 없음).
"""
from __future__ import annotations

import math

import pandas as pd

from quant.utils.logging import get_logger

log = get_logger("data.openinterest")


def fetch_oi_history(symbol: str, exchange: str = "binanceusdm",
                     timeframe: str = "1d", limit: int = 30) -> pd.Series:
    """미결제약정 이력을 (시각 → OI 수량) Series로 반환한다. 실패 시 빈 Series."""
    empty = pd.Series(dtype=float, name="oi")
    try:
        import ccxt
        client = getattr(ccxt, exchange)({"enableRateLimit": True})
        raw = client.fetch_open_interest_history(
            symbol, timeframe=timeframe, limit=limit)
    except Exception as exc:  # noqa: BLE001 — ccxt 미설치/미지원/네트워크
        log.warning("OI 이력 조회 실패(%s) — 빈 값으로 폴백합니다.", exc)
        return empty
    idx, vals = [], []
    for row in raw or []:
        if not isinstance(row, dict):
            continue
        ts = row.get("timestamp")
        v = row.get("openInterestAmount") or row.get("openInterestValue")
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        if ts is None or not math.isfinite(v) or v < 0:
            continue
        try:
            idx.append(pd.Timestamp(int(ts), unit="ms").normalize())
        except (TypeError, ValueError, OverflowError):
            continue
        vals.append(v)
    if not idx:
        return empty
    s = pd.Series(vals, index=pd.DatetimeIndex(idx), name="oi").sort_index()
    return s[~s.index.duplicated(keep="last")]


def attach_open_interest(df: pd.DataFrame, symbol: str,
                         fetch=fetch_oi_history) -> pd.DataFrame:
    """일봉 df에 'oi' 컬럼(미결제약정 수준)을 부착한다 — 펀딩과 같은 원리.

    원시 '수준'을 컬럼으로 저장하는 이유: 스냅샷·데이터 해시에 남아 verify가
    같은 피처(ML이 x_oi_chg5로 파생)로 그날의 결정을 재현할 수 있다.
    전진충전 정렬만 사용(룩어헤드 불가). 실패 시 원본 그대로.
    """
    try:
        s = fetch(symbol)
        if s is None or s.empty:
            return df
        out = df.copy()
        target = pd.DatetimeIndex(out.index).normalize()
        out["oi"] = pd.Series(s.reindex(target, method="ffill").to_numpy(),
                              index=out.index)
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("OI 부착 실패(%s) — 원본 유지", exc)
        return df
