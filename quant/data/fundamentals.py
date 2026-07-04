"""주식 펀더멘탈 지표 + 팩터 랭킹 — Financial Modeling Prep(FMP) API.

가격(기술적)만 보던 시스템에 재무·밸류에이션(PER·PBR·ROE 등)을 더해 '팩터
투자'를 가능하게 한다. 여러 종목을 팩터로 교차 비교(cross-sectional)해 상위
종목에 비중을 배분한다.

환경변수: FMP_API_KEY (무료 티어 제한 있음). 네트워크/키 없으면 빈 값 폴백.

⚠️ 팩터 투자도 마법이 아니다. 밸류·퀄리티 팩터는 주식에서 '장기적으로' 프리미엄이
있었지만, 수년씩 부진하기도 한다. 반드시 검증 후 사용할 것.
"""
from __future__ import annotations

import os
from typing import Optional

import pandas as pd

from quant.utils.http import get_json
from quant.utils.logging import get_logger

log = get_logger("data.fundamentals")

_FMP_URL = "https://financialmodelingprep.com/api/v3"


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_fmp_ratios(payload) -> dict:
    """FMP ratios 응답(list/dict)을 표준 지표 dict로 변환한다."""
    row = {}
    if isinstance(payload, list) and payload:
        row = payload[0] or {}
    elif isinstance(payload, dict):
        row = payload

    def g(*keys):
        for k in keys:
            if k in row and row[k] is not None:
                n = _num(row[k])
                if n is not None:
                    return n
        return None

    out = {
        "pe": g("peRatioTTM", "peRatio"),
        "pb": g("priceToBookRatioTTM", "priceToBookRatio"),
        "roe": g("returnOnEquityTTM", "returnOnEquity"),
        "debt_equity": g("debtEquityRatioTTM", "debtEquityRatio"),
        "div_yield": g("dividendYieldTTM", "dividendYield"),
    }
    return {k: v for k, v in out.items() if v is not None}


def fmp_ratios(symbol: str, api_key: Optional[str] = None,
               timeout: float = 15.0) -> dict:
    """한 종목의 최근(TTM) 재무비율을 반환한다(실패 시 빈 dict)."""
    key = api_key or os.getenv("FMP_API_KEY", "")
    if not key:
        log.warning("FMP_API_KEY 가 없어 펀더멘탈을 건너뜁니다.")
        return {}
    # symbol을 경로에 넣기 전 인코딩 — '/','?','&' 주입으로 URL을 재구성하지 못하게.
    from urllib.parse import quote
    url = f"{_FMP_URL}/ratios-ttm/{quote(symbol, safe='')}?apikey={key}"
    try:
        return _parse_fmp_ratios(get_json(url))
    except Exception as exc:  # noqa: BLE001
        log.warning("FMP 조회 실패(%s: %s) — 건너뜁니다.", symbol, exc)
        return {}


def rank_factors(data: dict[str, dict], factors: dict[str, float],
                 top_n: Optional[int] = None) -> dict[str, float]:
    """여러 종목을 멀티팩터로 교차 랭킹해 목표 비중(합=1)을 반환한다.

    data    : {종목: {팩터: 값}} 예) {"AAPL": {"pe": 30, "roe": 1.2}, ...}
    factors : {팩터: 방향} 방향 +1=클수록 좋음(ROE), -1=작을수록 좋음(PER·PBR)
    top_n   : 상위 몇 종목에 배분할지(기본 = 전체 중 점수 양수)

    각 팩터를 종목 간 z-점수로 표준화한 뒤 방향을 곱해 합산 → 점수. 상위 종목에
    균등 배분한다(롱 온리). 표본이 부족하면 빈 dict.
    """
    if not data or not factors:
        return {}
    df = pd.DataFrame(data).T   # index=종목, columns=팩터
    score = pd.Series(0.0, index=df.index)
    used = False
    for fac, direction in factors.items():
        if fac not in df.columns:
            continue
        col = pd.to_numeric(df[fac], errors="coerce")
        std = col.std(ddof=0)
        if not std or std != std:      # std 0 또는 NaN → 무의미
            continue
        z = (col - col.mean()) / std
        score = score.add((z * float(direction)).fillna(0.0), fill_value=0.0)
        used = True
    if not used:
        return {}

    ranked = score.sort_values(ascending=False)
    if top_n is not None:
        ranked = ranked.head(max(1, top_n))
    else:
        ranked = ranked[ranked > 0]        # 점수 양수만
    if ranked.empty:
        return {}
    w = 1.0 / len(ranked)
    return {sym: w for sym in ranked.index}
