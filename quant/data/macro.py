"""거시경제 지표 — FRED(미 세인트루이스 연준) API.

금리·CPI·장단기 금리차 같은 거시 시계열을 가져와 레짐 필터나 ML 외부 피처로
쓴다. 완전 무료(키 발급만 필요). 네트워크/키가 없으면 빈 값으로 graceful 폴백.

환경변수: FRED_API_KEY

대표 시리즈 id:
    DGS10   : 미 국채 10년 금리
    DGS2    : 미 국채 2년 금리
    T10Y2Y  : 장단기 금리차(10년-2년) — 경기침체 선행지표(음수=역전)
    CPIAUCSL: 미 소비자물가지수(CPI)
    UNRATE  : 미 실업률
    M2SL    : 통화량(M2)

⚠️ 거시 지표를 넣는다고 수익이 오르지 않는다. 시장은 대개 이미 반영해 두므로,
   반드시 워크포워드로 '실제 도움 여부'를 검증한 뒤 유지할 것.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

import pandas as pd

from quant.utils.http import get_json
from quant.utils.logging import get_logger

log = get_logger("data.macro")

_FRED_URL = "https://api.stlouisfed.org/fred/series/observations"

# 자주 쓰는 시리즈 별칭
SERIES = {
    "us10y": "DGS10",
    "us2y": "DGS2",
    "yield_curve": "T10Y2Y",   # 장단기 금리차
    "cpi": "CPIAUCSL",
    "unemployment": "UNRATE",
    "m2": "M2SL",
}


def _parse_fred(payload: dict) -> pd.Series:
    """FRED observations 응답을 날짜→값 Series로 변환한다('.'=결측 제외)."""
    obs = payload.get("observations", []) or []
    idx, vals = [], []
    for o in obs:
        v = o.get("value", ".")
        if v in (".", "", None):
            continue
        try:
            val = float(v)
        except (TypeError, ValueError):
            continue
        idx.append(pd.Timestamp(o["date"]))
        vals.append(val)
    if not idx:
        return pd.Series(dtype=float)
    return pd.Series(vals, index=pd.DatetimeIndex(idx)).sort_index()


def fred_series(series_id: str, api_key: Optional[str] = None,
                start: Optional[datetime] = None, timeout: float = 15.0) -> pd.Series:
    """FRED 시리즈 하나를 날짜→값 Series로 반환한다(빈 Series로 graceful 폴백).

    series_id 는 실제 코드(예: 'DGS10') 또는 별칭(예: 'yield_curve') 모두 허용.
    """
    sid = SERIES.get(series_id, series_id)
    key = api_key or os.getenv("FRED_API_KEY", "")
    if not key:
        log.warning("FRED_API_KEY 가 없어 거시 데이터를 건너뜁니다.")
        return pd.Series(dtype=float, name=sid)
    url = (f"{_FRED_URL}?series_id={sid}&api_key={key}&file_type=json")
    if start is not None:
        url += f"&observation_start={pd.Timestamp(start).date()}"
    try:
        payload = get_json(url)
    except Exception as exc:  # noqa: BLE001
        log.warning("FRED 조회 실패(%s) — 건너뜁니다.", exc)
        return pd.Series(dtype=float, name=sid)
    return _parse_fred(payload).rename(sid)


def fred_frame(series: list[str] | dict[str, str],
               api_key: Optional[str] = None, **kwargs) -> pd.DataFrame:
    """여러 FRED 시리즈를 하나의 DataFrame으로 (날짜 정렬 + 전진충전) 반환한다.

    MLStrategy(extra_features=...) 나 레짐 판단에 바로 쓸 수 있는 형태.
    series: ['DGS10','T10Y2Y'] 또는 {'rate':'DGS10','curve':'T10Y2Y'} (컬럼명 지정).
    """
    items = series.items() if isinstance(series, dict) else [(s, s) for s in series]
    cols = {}
    for name, sid in items:
        s = fred_series(sid, api_key=api_key, **kwargs)
        if not s.empty:
            cols[name] = s
    if not cols:
        return pd.DataFrame()
    df = pd.DataFrame(cols).sort_index().ffill()
    return df
