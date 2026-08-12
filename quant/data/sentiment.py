"""거시/심리 지표 — ML 전략의 외부 피처로 쓸 수 있는 '숫자로 딱 떨어지는' 데이터.

지금은 암호화폐 공포탐욕지수(alternative.me, 무료·키 불필요)를 제공한다.
뉴스 텍스트 감성분석과 달리 이 지표는 이미 숫자로 정제돼 있어 피처로 넣기 쉽다.

⚠️ 정직한 주의: 이런 지표를 '넣으면 무조건 좋아진다'가 아니다. 넣고 나서
워크포워드로 '실제로 도움이 되는지' 검증한 뒤에만 유지해야 한다. 대개 시장은
이미 이런 정보를 가격에 반영해 두므로, 추가 엣지는 작거나 없을 수 있다.
"""
from __future__ import annotations

import json

import pandas as pd

from quant.utils.logging import get_logger

log = get_logger("data.sentiment")

_FNG_URL = "https://api.alternative.me/fng/?limit=0&format=json"


def _parse_fng(payload: dict) -> pd.Series:
    """alternative.me 응답(dict)을 날짜→지수(0~100) Series로 변환한다."""
    rows = payload.get("data", []) or []
    idx, vals = [], []
    for r in rows:
        try:
            ts = int(r["timestamp"])
            v = float(r["value"])
        except (KeyError, ValueError, TypeError):
            continue
        idx.append(pd.Timestamp(ts, unit="s").normalize())
        vals.append(v)
    if not idx:
        return pd.Series(dtype=float, name="fear_greed")
    s = pd.Series(vals, index=pd.DatetimeIndex(idx), name="fear_greed").sort_index()
    return s[~s.index.duplicated(keep="last")]


def fear_greed_history(timeout: float = 10.0) -> pd.Series:
    """암호화폐 공포탐욕지수 전체 이력을 날짜→지수(0~100) Series로 반환한다.

    네트워크 실패 시 빈 Series를 반환한다(백테스트가 죽지 않도록 graceful).
    """
    # ⚠️ 공용 HTTP 헬퍼를 쓴다(감사 178). 예전에는 urlopen으로 직접 받고
    #    `resp.read()`로 **본문 전체를 상한 없이** 읽었다. quant/utils/http.py는
    #    바로 그 위험(악의적·오작동 서버의 초대형 응답 → 메모리 고갈)을 막으려고
    #    32MB 상한을 두고 있는데, 이 경로만 그 방어를 지나치고 있었다.
    #    덤으로 교차 호스트 리다이렉트 방어와 비밀 가리기도 함께 받는다.
    try:
        from quant.utils.http import get_json
        payload = get_json(_FNG_URL, timeout=int(timeout))
        s = _parse_fng(payload)
        log.info("공포탐욕지수 %d일치 수신", len(s))
        return s
    except Exception as exc:  # noqa: BLE001
        log.warning("공포탐욕지수 조회 실패(%s) — 외부 피처 없이 진행", exc)
        return pd.Series(dtype=float, name="fear_greed")


def fear_greed_frame(timeout: float = 10.0) -> pd.DataFrame:
    """공포탐욕지수를 0~1로 정규화한 DataFrame(컬럼: fear_greed)으로 반환한다.

    MLStrategy(extra_features=...) 에 바로 넣을 수 있는 형태다. 비어 있으면
    빈 DataFrame을 반환해 ML이 기본 피처만으로 동작하게 한다.
    """
    s = fear_greed_history(timeout=timeout)
    if s.empty:
        return pd.DataFrame()
    return (s / 100.0).to_frame("fear_greed")
