"""복수 데이터 소스 교차 검증 — 한 소스만 믿지 않는다.

같은 종목을 서로 다른 제공자(예: 거래소 API vs yfinance)에서 받아 종가를
비교하면 배당·분할 조정 오류, 통화 단위 혼동, 수집 버그를 조기에 잡을 수 있다.
두 소스가 크게 어긋나면 '어느 쪽이 맞는지'는 이 함수가 알 수 없다 — 사람이
원본 공시를 확인해야 한다. 이 모듈은 어긋남을 '보고만' 한다.

사용 예:
    from quant.data.crosscheck import compare_sources
    stats = compare_sources(df_yfinance, df_broker, tolerance=0.01)
    if not stats["ok"]:
        print("두 소스의 종가가 1% 이상 어긋납니다 — 조정(배당·분할) 방식을 확인하세요.")
"""
from __future__ import annotations

import pandas as pd


def compare_sources(
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    tolerance: float = 0.01,
    column: str = "close",
) -> dict:
    """두 OHLCV DataFrame의 겹치는 구간에서 가격 차이를 통계로 반환한다.

    tolerance : 허용 상대 오차 (기본 1%). max_rel_diff가 이를 넘으면 ok=False.
    column    : 비교할 컬럼 (기본 'close').

    반환:
        n_common      : 겹치는 봉 수 (0이면 비교 불가).
        max_rel_diff  : 최대 상대 차이 |a-b| / |a| — 겹침 없으면 NaN.
        mean_rel_diff : 평균 상대 차이 — 겹침 없으면 NaN.
        n_exceed      : tolerance를 넘는 봉 수.
        ok            : 겹침이 있고 최대 차이가 tolerance 이내면 True.
                        겹침이 없으면 False — '검증 못 함'은 '통과'가 아니다.
    """
    nan = float("nan")
    empty = {"n_common": 0, "max_rel_diff": nan, "mean_rel_diff": nan,
             "n_exceed": 0, "ok": False}
    if df_a is None or df_b is None or len(df_a) == 0 or len(df_b) == 0:
        return empty
    if column not in df_a.columns or column not in df_b.columns:
        return empty

    a, b = df_a[column].align(df_b[column], join="inner")
    pair = pd.DataFrame({"a": a, "b": b}).dropna()
    if len(pair) == 0:
        return empty

    # 상대 차이는 a 기준 — 0 나눗셈은 발생 시 inf로 드러나게 두어 오염을 숨기지 않는다.
    rel = (pair["a"] - pair["b"]).abs() / pair["a"].abs()
    max_diff = float(rel.max())
    return {
        "n_common": int(len(pair)),
        "max_rel_diff": max_diff,
        "mean_rel_diff": float(rel.mean()),
        "n_exceed": int((rel > tolerance).sum()),
        "ok": bool(max_diff <= tolerance),
    }
