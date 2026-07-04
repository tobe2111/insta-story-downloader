"""종목 선별기(스크리너) — 관심종목 목록에서 팩터로 상위 종목을 자동 선택.

사용자가 '후보 종목 목록(유니버스)'을 주면, 재무 팩터(밸류·퀄리티)로 교차
비교해 상위 N개만 골라 목표 비중을 돌려준다. 그 종목만 매매하면 된다.

'무엇을 후보로 볼지'는 사용자가 정하고(과최적화·생존편향 방지),
'그중 무엇이 지금 좋은지'는 이 스크리너가 정한다.

⚠️ 재무 데이터(FMP)가 필요하다. 키/네트워크가 없으면 빈 결과를 돌려주며,
   팩터 프리미엄도 수년씩 부진할 수 있으니 맹신하지 말 것.
"""
from __future__ import annotations

from typing import Callable, Optional, Sequence

from quant.data.fundamentals import fmp_ratios, rank_factors

# 기본 팩터: 싸고(PER·PBR 낮음) 우량한(ROE 높음) 종목 선호 (밸류+퀄리티)
DEFAULT_FACTORS = {"pe": -1.0, "pb": -1.0, "roe": +1.0}


def screen_symbols(
    symbols: Sequence[str],
    factors: Optional[dict[str, float]] = None,
    top_n: Optional[int] = None,
    ratios_fn: Optional[Callable[[str], dict]] = None,
    api_key: Optional[str] = None,
) -> dict:
    """후보 종목을 팩터로 선별한다.

    symbols  : 후보 종목 목록(유니버스)
    factors  : {팩터: 방향}. 기본 = 밸류+퀄리티. (+1=클수록/-1=작을수록 선호)
    top_n    : 상위 몇 종목을 고를지(기본 = 점수 양수 전체)
    ratios_fn: 종목→재무비율 dict 함수(기본 fmp_ratios). 테스트용 주입 가능.

    반환: {"weights": {종목: 비중}, "ratios": {종목: 재무}, "selected": [종목...]}
    """
    factors = factors or DEFAULT_FACTORS
    fetch = ratios_fn or (lambda s: fmp_ratios(s, api_key=api_key))

    ratios: dict[str, dict] = {}
    for sym in symbols:
        r = fetch(sym)
        if r:
            ratios[sym] = r

    weights = rank_factors(ratios, factors, top_n=top_n)
    return {
        "weights": weights,
        "ratios": ratios,
        "selected": list(weights.keys()),
    }
