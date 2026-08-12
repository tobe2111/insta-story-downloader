"""무기한 선물 펀딩비 실데이터 — ccxt fetchFundingRateHistory.

백테스트의 고정 펀딩률(CostModel.funding)은 보수적 근사일 뿐이다. 실데이터를
쓰면 '펀딩이 유리했던 구간'과 '불리했던 구간'을 구분할 수 있다. 다만:

⚠️ 과거 펀딩률이 미래에도 반복된다는 보장은 없다. 특히 롱 과열 구간의
   펀딩 수취를 전략 수익의 핵심으로 삼으면 백테스트가 낙관적으로 왜곡된다.

ccxt 미설치·네트워크 오류 시 빈 Series로 graceful 폴백한다(예외를 던지지 않음).
"""
from __future__ import annotations

import math
from typing import Optional

import pandas as pd

from quant.broker.base import safe_amount
from quant.utils.logging import get_logger

log = get_logger("data.funding")


def fetch_funding_history(
    symbol: str,
    exchange: str = "binance",
    since: Optional[int] = None,
    limit: int = 1000,
) -> pd.Series:
    """거래소 펀딩률 이력을 (정산시각 → 펀딩률) Series로 반환한다.

    부호 규약(거래소 관례): 양수 = 롱이 지불, 음수 = 숏이 지불.
    since: epoch ms (선택). 실패 시 빈 Series 반환(폴백) — 호출자는 빈 값이면
    고정 펀딩률 등 보수적 기본값을 쓰는 것을 권장한다.
    """
    empty = pd.Series(dtype=float, name="funding_rate")
    try:
        import ccxt

        klass = getattr(ccxt, exchange)
        client = klass({"enableRateLimit": True})
        raw = client.fetch_funding_rate_history(symbol, since=since, limit=limit)
    except Exception as exc:  # noqa: BLE001 — ccxt 미설치/미지원 거래소/네트워크
        log.warning("펀딩비 이력 조회 실패(%s) — 빈 값으로 폴백합니다.", exc)
        return empty

    idx, vals = [], []
    for row in raw or []:
        if not isinstance(row, dict):
            continue
        ts = row.get("timestamp")
        # 금액류는 safe_amount로 검증(inf/NaN/비수치 거부). 펀딩률은 음수가 정상.
        rate = safe_amount(row.get("fundingRate"), default=math.nan,
                           allow_negative=True)
        if ts is None or not math.isfinite(rate):
            continue
        try:
            idx.append(pd.Timestamp(int(ts), unit="ms"))
        except (TypeError, ValueError, OverflowError):
            continue
        vals.append(rate)
    if not idx:
        return empty
    s = pd.Series(vals, index=pd.DatetimeIndex(idx), name="funding_rate")
    return s.sort_index()


def attach_funding(df: pd.DataFrame, symbol: str,
                   exchange: str = "binance", fetch=None) -> pd.DataFrame:
    """OHLCV 데이터프레임에 'funding' 컬럼(봉당 펀딩률)을 붙여 반환한다.

    ML 피처(x_funding)용 — 가격에서 유도할 수 없는 포지셔닝 정보를 컬럼으로
    싣는 이유는 재현성이다: 입력 스냅샷(csv.gz)에 함께 보존돼 verify가 같은
    피처로 재현할 수 있고, data_sha256에도 포함돼 변조가 드러난다.
    실패(ccxt 미설치·네트워크·현물 심볼)하면 컬럼 없이 원본을 그대로 반환한다
    — 피처는 '있으면 쓰는' 선택적 맥락이지 필수가 아니다.
    """
    # fetch 주입 — 형제인 attach_open_interest·attach_krx_flows는 처음부터
    # 받고 있었는데 여기만 없어서 **네트워크 없이는 검사할 수 없었다**(감사
    # 173). 검사할 수 없는 코드는 검사되지 않는다.
    try:
        get = fetch or (lambda s: fetch_funding_history(s, exchange=exchange,
                                                        limit=1000))
        hist = get(symbol)
        if hist is None or hist.empty:
            return df
        out = df.copy()
        out["funding"] = align_funding_to_bars(hist, df.index)
        return out
    except Exception as exc:  # noqa: BLE001 — 부가 정보 실패가 본류를 막으면 안 됨
        log.warning("펀딩 컬럼 부착 실패(%s) — 펀딩 피처 없이 진행", exc)
        return df


def align_funding_to_bars(funding: pd.Series, bar_index) -> pd.Series:
    """펀딩 정산 이벤트를 봉 인덱스에 맞춘 '봉당 펀딩률' Series로 변환한다.

    각 정산 이벤트를 '정산시각 이후의 첫 봉'에 합산한다 — 정산이 일어난 뒤의
    봉에만 반영되므로 룩어헤드가 없다. 마지막 봉 이후의 이벤트는 버린다.
    결과는 CostModel(funding_series=...)에 그대로 넣을 수 있다.
    """
    bar_index = pd.DatetimeIndex(bar_index)
    out = pd.Series(0.0, index=bar_index, name="funding_rate")
    if funding is None or len(funding) == 0 or len(bar_index) == 0:
        return out
    f = funding.sort_index()
    # searchsorted(side='left') → 정산시각 이상(>=)의 첫 봉 위치
    pos = bar_index.searchsorted(f.index, side="left")
    vals = f.to_numpy()
    for p, v in zip(pos, vals):
        if p < len(bar_index) and math.isfinite(float(v)):
            out.iloc[int(p)] += float(v)
    return out
