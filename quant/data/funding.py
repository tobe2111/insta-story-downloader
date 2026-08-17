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
from quant.data.derivatives import ladder_reason, perp_symbol, walk_ladder
from quant.data.source_health import note_exception, note_source_failure
from quant.utils.logging import get_logger

log = get_logger("data.funding")


def _price_source(df) -> str | None:
    """그 종목 시세를 실제로 준 거래소 — 부가 지표도 거기부터 물어본다."""
    try:
        return str(df.attrs.get("source") or "") or None
    except Exception:  # noqa: BLE001  # pragma: no cover
        return None


def fetch_funding_history(
    symbol: str,
    exchange: str = "binanceusdm",
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
                   exchange: str | None = None, fetch=None) -> pd.DataFrame:
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
    #
    # ⚠️ exchange를 명시하지 않으면 **시세와 같은 사다리**를 내려간다(감사
    #    270). 예전 기본값은 `binance` 한 곳이었고, 그 문이 막힌 환경에서
    #    시세는 okx로 폴백하는데 펀딩만 매일 빈손으로 돌아왔다.
    try:
        if fetch is not None:          # 호출자가 출처를 지정했다 — 사다리 없음
            hist = fetch(symbol)
            if hist is None or hist.empty:
                note_source_failure(df, "funding", "펀딩 이력이 비어 있음")
                return df
            source = str(exchange or "주입")
        elif exchange:                 # 거래소를 콕 집었다 — 그 한 곳만 본다
            hist = fetch_funding_history(perp_symbol(symbol),
                                         exchange=exchange, limit=1000)
            if hist is None or hist.empty:
                note_source_failure(df, "funding",
                                    f"{exchange} 펀딩 이력이 비어 있음(현물 "
                                    "심볼·지역 차단·점검 가능)")
                return df
            source = exchange
        else:
            hist, source, tried = walk_ladder(
                _price_source(df), symbol,
                lambda s, ex: fetch_funding_history(s, exchange=ex, limit=1000),
                capability="fetchFundingRateHistory")
            if hist is None:
                # 조용히 넘어가지 않는다 — 이유가 장부에 남아야 원인을 좁힌다.
                # 거래소 이름 없이 "없음"만 남기면 다음 사람이 처음부터
                # 다시 조사한다(감사 269가 사용자 자료에서 배운 것과 같다).
                note_source_failure(df, "funding", ladder_reason(tried))
                return df
        out = df.copy()
        out["funding"] = align_funding_to_bars(hist, df.index)
        # 어느 거래소에서 받았는지 남긴다 — 거래소마다 정산 주기가 달라
        # 값이 튄 날 제공처 교체를 먼저 의심할 수 있어야 한다.
        out.attrs["funding_source"] = source
        return out
    except Exception as exc:  # noqa: BLE001 — 부가 정보 실패가 본류를 막으면 안 됨
        log.warning("펀딩 컬럼 부착 실패(%s) — 펀딩 피처 없이 진행", exc)
        note_exception(df, "funding", exc)
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
