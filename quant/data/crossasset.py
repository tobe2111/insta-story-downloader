"""크로스에셋 피처 — 다른 시장의 흐름을 x_* 컬럼으로 붙인다 (알파 5차).

가격 유도 지표만으로는 '시장 바깥'을 못 본다. 종목별로 관련 시장의 흐름을
컬럼으로 부착해 ML 피처(x_*)로 쓴다:

    코인(BTC 제외)  : x_btc_ret5     — 비트코인 5일 수익률(코인 시장 전체 조류)
    코인(전체)      : x_kimchi       — 김치 프리미엄(업비트 vs 바이낸스 가격차,
                                       국내 수급 과열/이탈의 고유 신호)
    미국 주식       : x_spy_ret5     — S&P500 5일 수익률(시장 베타 맥락)
                      x_tnx_chg5     — 미 10년물 금리 5일 변화(할인율 압력)
                      x_vix          — VIX 변동성지수/100(옵션시장의 공포 가격)
    한국 주식       : x_spy_ret5     — 미국 전일 흐름(개장 전 알 수 있는 정보)
                      x_usdkrw_ret5  — 원/달러 5일 변화(수출주·외인 수급 맥락)
                      x_vix          — VIX(글로벌 위험선호는 한국 개장 전 정보)

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

from quant.data.source_health import note_exception, note_source_failure
from quant.utils.logging import get_logger

log = get_logger("data.crossasset")

# 실행(프로세스) 내 벤치마크 메모 — 20종목 순회가 같은 SPY를 20번 받지 않게
_MEMO: dict = {}

# 이 모듈이 만들지 않는 선택 피처 — 각자 자기 부착 함수가 책임진다.
#   x_funding·x_funding_chg ← attach_funding이 붙이는 'funding' 컬럼에서 파생
#   x_oi_chg5               ← attach_open_interest의 'oi' 컬럼에서 파생
#   x_frgn5·x_inst5         ← attach_krx_flows가 직접 붙임
_NOT_OURS = frozenset({"x_funding", "x_funding_chg", "x_oi_chg5",
                       "x_frgn5", "x_inst5"})


def _upbit_ohlcv(symbol: str, limit: int) -> pd.DataFrame:
    """업비트 일봉 — 김치 프리미엄의 원화 가격 다리. ccxt 직접 사용.

    업비트는 국내 데이터 프로바이더 경로가 없어 여기서만 쓴다.
    (업비트 공개 API는 1회 최대 200봉 — 프리미엄은 최근 구간이면 충분하다.)
    """
    import ccxt
    client = ccxt.upbit({"enableRateLimit": True})
    raw = client.fetch_ohlcv(symbol, "1d", limit=min(int(limit), 200))
    df = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close",
                                    "volume"])
    df.index = pd.to_datetime(df["ts"], unit="ms")
    return df.drop(columns=["ts"])


def _bench_close(market: str, symbol: str, limit: int = 800,
                 fetch=None, refresh: bool = False) -> pd.Series | None:
    """벤치마크 종가 시계열(날짜 정규화·중복 제거). 실패 시 None.

    ⚠️ 이 메모는 **프로세스가 사는 동안 안 늙는다**(감사 252). 하루 한 번
       도는 배치에서는 그게 옳다 — 같은 배치 안에서 종목마다 다른 값을
       쓰면 자산이 어긋난다. 그런데 며칠씩 도는 프로세스(실시간 루프,
       조종석 서버)에서는 **첫 조회값이 영영 고정**된다.

       `refresh=True`면 그 키를 버리고 다시 받는다. 이게 없어서 위층
       `fx.usdkrw(refresh=True)`가 이름만 refresh였다.
    """
    key = (market, symbol, limit)
    if refresh:
        _MEMO.pop(key, None)
    elif key in _MEMO:
        return _MEMO[key]
    try:
        if fetch is not None:
            df = fetch(market, symbol, limit)
        elif market == "upbit":               # 원화 코인 시세(김프 계산용)
            df = _upbit_ohlcv(symbol, limit)
        else:
            from quant.data import get_provider
            df = get_provider(market).get_ohlcv(symbol, "1d", limit=limit)
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


def _kimchi_series(fetch=None) -> pd.Series | None:
    """김치 프리미엄 이력(날짜 → 프리미엄 비율). 실패 시 None. 실행 내 메모.

    업비트 BTC/KRW ÷ (바이낸스 BTC/USDT × 원/달러) − 1. 국내 매수 과열이면
    양수(+), 국내 이탈이면 음수(역프리미엄). 셋 다 공개 시세라 스냅샷·해시에
    남아 재현 가능하다 — 뉴스 원문 없이 '국내 수급'을 숫자로 읽는 방법.
    """
    key = ("_kimchi",)
    if key in _MEMO:
        return _MEMO[key]
    try:
        krw = _bench_close("upbit", "BTC/KRW", limit=200, fetch=fetch)
        usd = _bench_close("crypto", "BTC/USDT", fetch=fetch)
        fx = _bench_close("us_stock", "KRW=X", fetch=fetch)
        if krw is None or usd is None or fx is None:
            _MEMO[key] = None
            return None
        idx = krw.index.intersection(usd.index)
        # 환율은 주말 결측(주식 달력) — ffill로 '마지막으로 알려진 환율' 사용
        fx_al = fx.reindex(idx.union(fx.index)).sort_index().ffill().reindex(idx)
        prem = (krw.reindex(idx) / (usd.reindex(idx) * fx_al) - 1.0).dropna()
        _MEMO[key] = prem if len(prem) else None
    except Exception as exc:  # noqa: BLE001
        log.warning("김치 프리미엄 계산 실패: %s", exc)
        _MEMO[key] = None
    return _MEMO[key]


def _fred(series: str) -> pd.Series | None:
    """FRED 시리즈 하나 — 키(FRED_API_KEY) 없으면 None. 실행 내 메모.

    macro 모듈이 발표 시차를 인덱스에 반영해 주므로(룩어헤드 방지) 여기서는
    그대로 ffill 정렬만 하면 된다. 사용 시리즈:
        T10Y2Y       장단기 금리차 — 경기침체 선행지표
        BAMLH0A0HYM2 하이일드 스프레드 — 신용시장 스트레스(위험의 가격)
        DTWEXBGS     달러인덱스(광의) — 글로벌 유동성·위험선호
        T10YIE       10년 기대인플레이션(BEI) — 연준 정책 기대
    """
    import os
    key = ("_fred", series)
    if key in _MEMO:
        return _MEMO[key]
    if not os.getenv("FRED_API_KEY"):
        _MEMO[key] = None
        return None
    try:
        from quant.data.macro import fred_series
        s = fred_series(series)
        _MEMO[key] = s if s is not None and len(s) else None
    except Exception as exc:  # noqa: BLE001
        log.warning("FRED %s 조회 실패: %s", series, exc)
        _MEMO[key] = None
    return _MEMO[key]


def _fred_t10y2y() -> pd.Series | None:
    """FRED 장단기 금리차(T10Y2Y) — 기존 호출 경로 호환용 별칭."""
    return _fred("T10Y2Y")


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
            # 김치 프리미엄 — 국내 수급의 고유 신호(모든 코인에 시장 공통)
            kim = _kimchi_series(fetch=fetch)
            if kim is not None:
                out["x_kimchi"] = _align(kim, out.index)
            # 달러·신용(FRED) — 코인은 '달러 유동성 자산'이라 달러 강세와
            # 신용 경색이 공통 역풍이다(키 없으면 조용히 생략)
            usd = _fred("DTWEXBGS")
            if usd is not None:
                out["x_usd_chg5"] = _align(usd.pct_change(5), out.index)
            hy = _fred("BAMLH0A0HYM2")
            if hy is not None:
                out["x_hy_spread"] = _align(hy, out.index)
        elif market == "us_stock":
            t10 = _fred_t10y2y()
            if t10 is not None:
                out["x_t10y2y"] = _align(t10, out.index)
            hy = _fred("BAMLH0A0HYM2")           # 신용 스트레스(위험의 가격)
            if hy is not None:
                out["x_hy_spread"] = _align(hy, out.index)
            usd = _fred("DTWEXBGS")              # 달러 강세 = 대형주 실적 역풍
            if usd is not None:
                out["x_usd_chg5"] = _align(usd.pct_change(5), out.index)
            bei = _fred("T10YIE")                # 기대인플레 변화 = 연준 기대
            if bei is not None:
                out["x_t10yie_chg5"] = _align(bei.diff(5), out.index)
            if symbol != "SPY":
                spy = _bench_close("us_stock", "SPY", fetch=fetch)
                if spy is not None:
                    out["x_spy_ret5"] = _align(spy.pct_change(5), out.index)
            tnx = _bench_close("us_stock", "^TNX", fetch=fetch)
            if tnx is not None:
                out["x_tnx_chg5"] = _align(tnx.diff(5), out.index)
            # VIX/100 — 옵션시장이 가격에 매긴 '공포'. 수준 자체가 정보라
            # 변화율이 아닌 수준을 쓴다(0.1~0.8 스케일).
            vix = _bench_close("us_stock", "^VIX", fetch=fetch)
            if vix is not None:
                out["x_vix"] = _align(vix / 100.0, out.index)
                # 기간구조(단기/3개월) — 1 초과 = 백워데이션(당장의 공포가
                # 미래보다 비쌈, 스트레스 급성기). 수준(x_vix)과 다른 정보.
                v3m = _bench_close("us_stock", "^VIX3M", fetch=fetch)
                if v3m is not None:
                    out["x_vix_ts"] = _align(vix / v3m.reindex(vix.index)
                                             .ffill(), out.index)
        elif market == "kr_stock":
            t10 = _fred_t10y2y()
            if t10 is not None:
                out["x_t10y2y"] = _align(t10, out.index)
            hy = _fred("BAMLH0A0HYM2")           # 글로벌 신용 경색 = 외인 이탈
            if hy is not None:
                out["x_hy_spread"] = _align(hy, out.index)
            usd = _fred("DTWEXBGS")              # 달러 강세 = 원화·수출주 압박
            if usd is not None:
                out["x_usd_chg5"] = _align(usd.pct_change(5), out.index)
            spy = _bench_close("us_stock", "SPY", fetch=fetch)
            if spy is not None:
                out["x_spy_ret5"] = _align(spy.pct_change(5), out.index)
            fx = _bench_close("us_stock", "KRW=X", fetch=fetch)
            if fx is not None:
                out["x_usdkrw_ret5"] = _align(fx.pct_change(5), out.index)
            vix = _bench_close("us_stock", "^VIX", fetch=fetch)
            if vix is not None:
                out["x_vix"] = _align(vix / 100.0, out.index)
                v3m = _bench_close("us_stock", "^VIX3M", fetch=fetch)
                if v3m is not None:
                    out["x_vix_ts"] = _align(vix / v3m.reindex(vix.index)
                                             .ffill(), out.index)
    except Exception as exc:  # noqa: BLE001
        log.warning("크로스에셋 부착 실패 %s/%s: %s", market, symbol, exc)
        note_exception(df, "crossasset", exc)
        return df
    # 이 시장에 붙었어야 할 컬럼 중 실제로 안 붙은 것 — 어느 소스가 죽었는지
    # 이름으로 남긴다. 없으면 '없다'는 사실조차 로그에만 남고 사라진다.
    #
    # ⚠️ 이 함수가 만들지 **않는** 피처는 빼야 한다. 펀딩·미결제약정·KRX
    #    수급은 각자의 부착 함수가 만들고 자기 실패 사유를 따로 남긴다.
    #    여기서 같이 세면 원인이 두 곳에 중복으로 찍혀 오히려 좁히기 어렵다.
    from quant.strategies.ml import applicable_optional_features
    for col in applicable_optional_features(market, symbol):
        if col in _NOT_OURS or col in out.columns:
            continue
        note_source_failure(out, col, "이 시장에 붙어야 할 소스가 값을 "
                                      "돌려주지 않음(FRED 키 없음·네트워크·"
                                      "응답 없음 가능)")
    return out
