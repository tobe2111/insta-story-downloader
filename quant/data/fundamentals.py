"""주식 펀더멘탈 지표 + 팩터 랭킹 — Financial Modeling Prep(FMP) API.

가격(기술적)만 보던 시스템에 재무·밸류에이션(PER·PBR·ROE 등)을 더해 '팩터
투자'를 가능하게 한다. 여러 종목을 팩터로 교차 비교(cross-sectional)해 상위
종목에 비중을 배분한다.

환경변수: FMP_API_KEY (무료 티어 제한 있음). 네트워크/키 없으면 빈 값 폴백.

⚠️ 팩터 투자도 마법이 아니다. 밸류·퀄리티 팩터는 주식에서 '장기적으로' 프리미엄이
있었지만, 수년씩 부진하기도 한다. 반드시 검증 후 사용할 것.
"""
from __future__ import annotations

import math
import os
from typing import Optional

import numpy as np
import pandas as pd

from quant.utils.http import get_json
from quant.utils.logging import get_logger
from quant.utils.numerics import degenerate_spread

log = get_logger("data.fundamentals")

# 요청한 팩터 중 이 비율만큼은 값이 있어야 후보로 본다(감사 165).
# 결측을 0으로 채우면 '자료 없음'이 '딱 평균'과 같아져, 팩터 하나만
# 우연히 좋은 부실 데이터 종목이 완전한 종목을 제친다.
MIN_FACTOR_COVERAGE = 0.5

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
    url = (f"{_FMP_URL}/ratios-ttm/{quote(symbol, safe='')}"
           f"?apikey={quote(key, safe='')}")
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

    zs: dict[str, pd.Series] = {}
    for fac, direction in factors.items():
        if fac not in df.columns:
            continue
        col = pd.to_numeric(df[fac], errors="coerce")
        std = float(col.std(ddof=0))
        # ⚠️ **std가 0이 아니라고 '차이가 있다'는 뜻은 아니다**(감사 165).
        #    z-점수는 규모를 지워 버린다. 그래서 종목 간 PER 차이가
        #    2e-7이어도(= 사실상 같은 값) z는 ±1.22로 나온다 — 진짜
        #    신호와 **똑같은 세기**다.
        #
        #    실측: ROE가 0.05→0.35로 뚜렷한 3종목에, 전부 30.0 근방인
        #    의미 없는 PER 열을 하나 더하면 세 종목 점수가 전부 정확히
        #    0이 된다. 잡음이 진짜 신호를 통째로 지운다.
        #
        #    감사 159가 만든 판정을 그대로 쓴다 — 계열의 크기 대비
        #    표준편차가 무의미하게 작으면 그 팩터는 안 쓴다.
        if not np.isfinite(std) or degenerate_spread(
                std, float(col.abs().mean())):
            continue
        zs[fac] = ((col - col.mean()) / std) * float(direction)
    if not zs:
        return {}

    Z = pd.DataFrame(zs)                      # index=종목, columns=쓸 만한 팩터
    # ⚠️ 결측 팩터를 0으로 채우면 '자료 없음'이 '딱 평균'이 된다(감사 165).
    #    실측: PER·PBR·ROE 세 팩터 중 ROE 하나만 있는 종목이, 셋 다 좋은
    #    종목과 나란히 상위 2종목에 뽑혔다. 나머지 둘을 평균으로 받았기
    #    때문이다. 자료가 부실할수록 극단값 하나로 올라오기 쉬워진다.
    #
    #    합이 아니라 **있는 팩터의 평균**으로 점수를 낸다(팩터 수가 다른
    #    종목끼리 비교 가능해진다). 그리고 최소 몇 개는 있어야 후보로 본다.
    have = Z.notna().sum(axis=1)
    need = max(1, math.ceil(len(Z.columns) * MIN_FACTOR_COVERAGE))
    score = Z.mean(axis=1).where(have >= need).dropna()
    if score.empty:
        return {}

    # 동점은 종목명으로 갈라 재현 가능하게 만든다. 예전에는 정렬이
    # 입력 순서에 기대서, 같은 자료를 종목 순서만 바꿔 넣으면 뽑히는
    # 종목이 달라졌다(감사 147과 같은 원리).
    order = sorted(score.index, key=lambda s: (-float(score[s]), str(s)))
    if top_n is not None:
        order = order[:max(1, int(top_n))]
    else:
        order = [s for s in order if float(score[s]) > 0]   # 점수 양수만
    if not order:
        return {}
    w = 1.0 / len(order)
    return {str(sym): w for sym in order}
