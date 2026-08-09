"""크로스에셋 피처 — 다른 시장의 흐름을 x_* 컬럼으로 붙인다 (알파 5차).

가격 유도 지표만으로는 '시장 바깥'을 못 본다. 종목별로 관련 시장의 흐름을
컬럼으로 부착해 ML 피처(x_*)로 쓴다:

    코인(BTC 제외)  : x_btc_ret5     — 비트코인 5일 수익률(코인 시장 전체 조류)
    미국 주식       : x_spy_ret5     — S&P500 5일 수익률(시장 베타 맥락)
                      x_tnx_chg5     — 미 10년물 금리 5일 변화(할인율 압력)
    한국 주식       : x_spy_ret5     — 미국 전일 흐름(개장 전 알 수 있는 정보)
                      x_usdkrw_ret5  — 원/달러 5일 변화(수출주·외인 수급 맥락)

컬럼으로 붙이는 이유(펀딩비와 동일): 입력 스냅샷(csv.gz)·데이터 해시에 함께
보존되어 verify가 같은 피처로 그날의 결정을 재현할 수 있다(재현성).

⚠️ 룩어헤드 없음: 벤치마크 시계열을 날짜 정규화 후 전진충전(ffill)으로만
   정렬한다 — 각 봉에는 '그 날짜까지 알려진' 벤치마크 값만 붙는다. 한국 주식의
   같은 날짜 미국 종가는 결정 시점(새벽, 미국 마감 후)에 이미 알려진 정보다.

실패는 조용히 건너뛴다(피처는 선택적 맥락 — 부착 실패가 재학습·기록을 막으면
안 된다). 같은 실행 안에서는 벤치마크를 메모해 중복 조회를 피한다.
"""
from __future__ import annotations

import pandas as pd

from quant.utils.logging import get_logger

log = get_logger("data.crossasset")

# 실행(프로세스) 내 벤치마크 메모 — 20종목 순회가 같은 SPY를 20번 받지 않게
_MEMO: dict = {}


def _bench_close(market: str, symbol: str, limit: int = 800,
                 fetch=None) -> pd.Series | None:
    """벤치마크 종가 시계열(날짜 정규화·중복 제거). 실패 시 None."""
    key = (market, symbol, limit)
    if key in _MEMO:
        return _MEMO[key]
    try:
        if fetch is None:
            from quant.data import get_provider
            df = get_provider(market).get_ohlcv(symbol, "1d", limit=limit)
        else:
            df = fetch(market, symbol, limit)
        if df is None or df.empty or df.attrs.get("synthetic_fallback"):
            _MEMO[key] = None              # 합성 폴백은 벤치로 쓰지 않는다
            return None
        s = df["close"].copy()
        s.index = pd.DatetimeIndex(s.index).normalize()
        s = s[~s.index.duplicated(keep="last")]
        _MEMO[key] = s
        return s
    except Exception as exc:  # noqa: BLE001 — 선택적 피처, 실패는 무해해야 한다
        log.warning("벤치마크 조회 실패 %s/%s: %s", market, symbol, exc)
        _MEMO[key] = None
        return None


def _fng_series(fetch=None) -> pd.Series | None:
    """공포탐욕지수 이력(날짜→0~100). 실패 시 None. 실행 내 메모."""
    key = ("_fng",)
    if key in _MEMO:
        return _MEMO[key]
    try:
        if fetch is not None:                  # 테스트 주입 경로에서는 생략
            _MEMO[key] = None
            return None
        from quant.data.sentiment import fear_greed_history
        s = fear_greed_history()
        _MEMO[key] = s if len(s) else None
    except Exception as exc:  # noqa: BLE001
        log.warning("공포탐욕지수 조회 실패: %s", exc)
        _MEMO[key] = None
    return _MEMO[key]


def _fred_t10y2y() -> pd.Series | None:
    """FRED 장단기 금리차(T10Y2Y) — 경기침체 선행지표. 키 없으면 None.

    macro 모듈이 발표 시차를 인덱스에 반영해 주므로(룩어헤드 방지) 여기서는
    그대로 ffill 정렬만 하면 된다. 실행 내 메모.
    """
    import os
    key = ("_t10y2y",)
    if key in _MEMO:
        return _MEMO[key]
    if not os.getenv("FRED_API_KEY"):
        _MEMO[key] = None
        return None
    try:
        from quant.data.macro import fred_series
        s = fred_series("T10Y2Y")
        _MEMO[key] = s if s is not None and len(s) else None
    except Exception as exc:  # noqa: BLE001
        log.warning("FRED T10Y2Y 조회 실패: %s", exc)
        _MEMO[key] = None
    return _MEMO[key]


def _align(feature: pd.Series, index: pd.Index) -> pd.Series:
    """날짜 정규화 + 전진충전 정렬 — 미래 값이 과거 봉에 붙을 수 없다."""
    target = pd.DatetimeIndex(index).normalize()
    return pd.Series(feature.reindex(target, method="ffill").to_numpy(),
                     index=index)


def attach_cross_asset(df: pd.DataFrame, market: str, symbol: str,
                       fetch=None) -> pd.DataFrame:
    """종목의 시장에 맞는 크로스에셋 컬럼(x_*)을 부착해 반환한다.

    이미 있는 컬럼은 덮어쓴다(스냅샷 재현 시 결정적). fetch는 테스트 주입용
    (market, symbol, limit) -> DataFrame.
    """
    if df is None or df.empty:
        return df
    out = df.copy()
    try:
        if market == "crypto":
            if symbol != "BTC/USDT":
                btc = _bench_close("crypto", "BTC/USDT", fetch=fetch)
                if btc is not None:
                    out["x_btc_ret5"] = _align(btc.pct_change(5), out.index)
            # 공포탐욕지수(0~1) — 뉴스 '원문'이 아니라 숫자로 정제·보관되는
            # 심리 지표. 기사 텍스트는 재현 검증이 불가능해 원칙적으로 쓰지
            # 않지만, 이 지수는 스냅샷·해시에 남아 verify가 재현할 수 있다.
            fng = _fng_series(fetch=fetch)
            if fng is not None:
                out["x_fng"] = _align(fng / 100.0, out.index)
        elif market == "us_stock":
            t10 = _fred_t10y2y()
            if t10 is not None:
                out["x_t10y2y"] = _align(t10, out.index)
            if symbol != "SPY":
                spy = _bench_close("us_stock", "SPY", fetch=fetch)
                if spy is not None:
                    out["x_spy_ret5"] = _align(spy.pct_change(5), out.index)
            tnx = _bench_close("us_stock", "^TNX", fetch=fetch)
            if tnx is not None:
                out["x_tnx_chg5"] = _align(tnx.diff(5), out.index)
        elif market == "kr_stock":
            t10 = _fred_t10y2y()
            if t10 is not None:
                out["x_t10y2y"] = _align(t10, out.index)
            spy = _bench_close("us_stock", "SPY", fetch=fetch)
            if spy is not None:
                out["x_spy_ret5"] = _align(spy.pct_change(5), out.index)
            fx = _bench_close("us_stock", "KRW=X", fetch=fetch)
            if fx is not None:
                out["x_usdkrw_ret5"] = _align(fx.pct_change(5), out.index)
    except Exception as exc:  # noqa: BLE001
        log.warning("크로스에셋 부착 실패 %s/%s: %s", market, symbol, exc)
        return df
    return out
