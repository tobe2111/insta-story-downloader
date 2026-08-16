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

from quant.data.source_health import note_exception, note_source_failure
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
    # ⚠️ **단위를 한 계열 안에서 섞지 않는다**(감사 205). 예전에는
    #
    #        v = row.get("openInterestAmount") or row.get("openInterestValue")
    #
    #    였다. 파이썬에서 `0.0`은 거짓이라, **미결제약정이 진짜 0인 하루**가
    #    끼면 계약수(Amount) 대신 **달러 명목값(Value)**으로 떨어진다.
    #    두 필드는 자릿수가 4~5자리 다르다. 실측(계약수 1000 → 0 → 1100):
    #
    #        파싱 결과   1,000 → 64,000,000 → 1,100
    #        하루 변화율 **+6,399,900%** → **-100%**
    #
    #    이 값은 ML 피처 `x_oi_chg5`로 들어간다. 하루짜리 0이 모델에 그런
    #    점프를 먹이는 것이다 — 결측보다 나쁘다(결측은 NaN으로 걸러진다).
    #
    #    그래서 **필드를 계열 단위로 한 번만 고른다.** 먼저 나온 유효한 필드를
    #    그 계열의 단위로 삼고, 그 필드가 없는 행은 건너뛴다. 값이 0이어도
    #    0으로 읽는다 — '0'과 '없음'은 다르다.
    field = None
    for row in raw or []:
        if not isinstance(row, dict):
            continue
        for name in ("openInterestAmount", "openInterestValue"):
            try:
                fv = float(row.get(name))
            except (TypeError, ValueError):
                continue
            if math.isfinite(fv) and fv >= 0:
                field = name
                break
        if field:
            break
    if field is None:
        return empty

    idx, vals = [], []
    for row in raw or []:
        if not isinstance(row, dict):
            continue
        ts = row.get("timestamp")
        try:
            v = float(row.get(field))
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
            note_source_failure(df, "oi",
                                "미결제약정 이력이 비어 있음(거래소 미지원·"
                                "지역 차단·심볼 불일치 가능)")
            return df
        out = df.copy()
        target = pd.DatetimeIndex(out.index).normalize()
        out["oi"] = pd.Series(s.reindex(target, method="ffill").to_numpy(),
                              index=out.index)
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("OI 부착 실패(%s) — 원본 유지", exc)
        note_exception(df, "oi", exc)
        return df
