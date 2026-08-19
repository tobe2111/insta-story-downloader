"""주식 데이터 제공자 (yfinance 기반) — 미국/국내 공용.

국내 종목은 티커에 접미사를 붙인다:
    삼성전자  -> 005930.KS  (KOSPI)
    카카오게임즈 -> 293490.KQ (KOSDAQ)
미국 종목은 접미사 없이 그대로 사용한다 (예: AAPL, TSLA).
"""
from __future__ import annotations

import os

from datetime import datetime
from typing import Optional

import pandas as pd

from quant.data.base import PRICE_COLUMNS as _PRICE_COLS
from quant.data.base import DataProvider
from quant.utils.logging import get_logger

log = get_logger("data.stock")

# yfinance interval 매핑
_TF_MAP = {"1d": "1d", "1h": "1h", "1wk": "1wk", "1m": "1m", "5m": "5m", "15m": "15m"}

# ── 알파카(공식 무료 시세) ───────────────────────────────────────────
#
# 키가 환경에 있을 때만 쓴다. 값은 **환경에서만** 읽고 어디에도 복사하지
# 않는다 — 키를 변수에 담아 장부·로그·예외로 흘리는 순간 보안선이 깨진다.
ALPACA_DATA_BASE = "https://data.alpaca.markets/v2"
ALPACA_FEED = "iex"          # 무료 티어. 통합 시세(SIP)는 유료 — 정직하게 표기
_ALPACA_TF = {"1d": "1Day", "1h": "1Hour", "15m": "15Min",
              "5m": "5Min", "1m": "1Min", "1wk": "1Week"}
_ALPACA_ENV = ("ALPACA_KEY_ID", "ALPACA_SECRET_KEY")


def alpaca_configured() -> bool:
    """알파카 키가 환경에 갖춰졌는가 — 값 자체는 돌려주지 않는다."""
    return all((os.environ.get(k) or "").strip() for k in _ALPACA_ENV)


def _alpaca_headers() -> dict:
    """요청 헤더. 이 함수 밖으로 키가 나가지 않는다."""
    return {"APCA-API-KEY-ID": os.environ.get("ALPACA_KEY_ID", "").strip(),
            "APCA-API-SECRET-KEY": os.environ.get(
                "ALPACA_SECRET_KEY", "").strip(),
            "User-Agent": "quant/1.0"}


class StockDataProvider(DataProvider):
    """주식 OHLCV — 실데이터 소스 3중 체인, 전부 실패해야만 합성 폴백.

    단일 소스(yfinance) 의존은 야간 자동화의 최약점이었다: 야후/라이브러리가
    흔들리는 날은 기록이 통째로 빈다. 순서대로 시도한다:
        1) yfinance          (기본 — 조정가·범위 모드 등 기능이 가장 풍부)
        2) 야후 chart HTTP    (같은 데이터를 라이브러리 없이 직접 — yfinance
                              라이브러리 파손/레이트리밋과 독립적인 경로)
        3) Stooq CSV         (야후와 완전히 다른 무료 소스 — 미국 일봉 전용)
    성공한 소스 이름을 attrs["source"]에 남긴다. 보조 소스는 무조정가라
    yfinance(auto_adjust)와 미세하게 다를 수 있다 — 빈 기록보다 낫다.
    """

    def __init__(self, market: str = "us_stock"):
        # market: 'us_stock' | 'kr_stock' (문서/폴백 용도)
        self.market = market

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1d",
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 500,
    ) -> pd.DataFrame:
        sources = self._sources()
        for name, fetch in sources:
            try:
                df = fetch(symbol, timeframe, start, end, limit)
                if df is None or df.empty:
                    raise ValueError("빈 결과")
                out = self._drop_unclosed(self._validate(df))
                # ⚠️ **비었는지는 검증 '뒤에도' 봐야 한다**(감사 163).
                #    위의 검사는 소스가 준 원본만 본다. 그런데 프레임을
                #    비울 수 있는 것은 그 뒤에 있다 — `_validate`의 dropna와
                #    `_drop_unclosed`의 미완결 봉 제거다. 둘이 다 지워도
                #    여기까지 '성공'으로 내려와 source를 붙이고 반환했다.
                #    그러면 보조 소스 2개를 건너뛰고, 합성 폴백 표식도 안
                #    붙어서 **아무도 데이터가 없다는 걸 모른다.** 3중 소스
                #    체인은 소스 하나가 흔들려도 기록이 안 비게 하려고 만든
                #    것인데, 그 목적이 통째로 무력화된다.
                if out.empty:
                    raise ValueError("검증 후 빈 결과")
                out.attrs["source"] = name
                if name != "yfinance":
                    log.info("%s: 보조 소스(%s)로 시세 수신 (%d봉)",
                             symbol, name, len(out))
                return out
            except Exception as exc:  # noqa: BLE001
                log.warning("%s 조회 실패[%s]: %s", symbol, name, exc)

        log.warning("%s: 모든 실데이터 소스 실패. 합성 데이터로 폴백.", symbol)
        from quant.data.synthetic import SyntheticDataProvider

        fb = SyntheticDataProvider(start_price=70_000.0).get_ohlcv(
            symbol, timeframe, start, end, limit
        )
        # 폴백 표식 — 캐시가 더미 데이터를 실제 시세로 저장·재사용하지 않게.
        fb.attrs["synthetic_fallback"] = True
        return fb

    def _sources(self):
        """시도 순서. 알파카 키가 **환경에 있으면** 맨 앞에 선다.

        ⚠️ 왜 조건부인가 (2026-08-19, 사장님 지시 "알파카로 하고").
           미국 장중 시세를 야후로 받으면 요청을 조일 때 차단당한다 —
           비공식 경로라 한도를 사전에 알 수도, 항의할 수도 없다. 알파카는
           공식 무료 티어(분당 200요청)라 그 위험이 사라진다.

           그런데 키는 **저장소에 없다.** 깃허브 시크릿에만 있고, 개발
           기계와 공개 PR 검사에는 없다. 그래서 "키가 있으면 쓰고 없으면
           지금까지 하던 대로"가 유일하게 정직한 구조다 — 키를 전제로
           짜면 키 없는 곳에서 조용히 죽고, 야후만 전제로 짜면 키가 있어도
           안 쓴다.

        ⚠️ 무료 티어는 **IEX 거래소 시세**다(전체 시장의 일부). 야후보다
           안정적이지만 통합 시세(SIP)와는 다를 수 있다 — 체결 가정 검증이
           그 차이를 그대로 드러낸다. 숨기지 않는다.
        """
        chain = []
        if self.market == "us_stock" and alpaca_configured():
            chain.append(("alpaca", self._via_alpaca))
        chain += [("yfinance", self._via_yfinance),
                  ("yahoo-http", self._via_yahoo_http),
                  ("stooq", self._via_stooq)]
        return tuple(chain)

    def _via_alpaca(self, symbol, timeframe, start, end, limit) -> pd.DataFrame:
        """알파카 시세 API — 공식 무료 티어(IEX). 키는 환경에서만 읽는다.

        ⚠️ 키를 로그·장부·예외 메시지에 절대 싣지 않는다. 이 저장소의
           보안선(자격증명은 수집도 저장도 하지 않는다)은 동의로도 풀리지
           않으며, 검사가 소스에 자격증명 문자열이 있는지 감시한다.
        """
        import urllib.parse

        from quant.utils.http import get_json

        tf = _ALPACA_TF.get(timeframe)
        if tf is None:
            raise ValueError(f"알파카 어댑터가 모르는 눈금: {timeframe}")
        url = (f"{ALPACA_DATA_BASE}/stocks/{urllib.parse.quote(symbol)}/bars"
               f"?timeframe={tf}&limit={max(1, min(int(limit), 10000))}"
               f"&feed={ALPACA_FEED}&adjustment=raw")
        data = get_json(url, _alpaca_headers(), timeout=15)
        bars = data.get("bars") or []
        if not bars:
            raise ValueError("알파카: 빈 결과")
        df = pd.DataFrame(
            {"open": [b["o"] for b in bars], "high": [b["h"] for b in bars],
             "low": [b["l"] for b in bars], "close": [b["c"] for b in bars],
             "volume": [b.get("v", 0) for b in bars]},
            index=pd.to_datetime([b["t"] for b in bars], utc=True),
        ).dropna(subset=_PRICE_COLS)
        return _cut_range(df, start, end, limit)

    def _drop_unclosed(self, df: pd.DataFrame, now=None) -> pd.DataFrame:
        """미완결·유령 일봉 제거 — 장 마감 전의 '오늘' 봉과 미래 날짜 봉을 버린다.

        야후는 거래소 현지 날짜가 바뀌면(예: KST 자정 직후) 아직 열리지도 않은
        세션의 봉을 미리 내놓는다. 이 봉은 값이 계속 변해서
            · asof(마지막 봉 날짜)가 하루 앞서 이동 → 멱등 가드 무력화
              (같은 날 재시도 크론이 두 번째 학습·기록을 남긴다 — 2026-08-07
              한국 주식 6종목 중복 기록의 실제 원인)
            · 재현성 해시가 실행 시각마다 달라짐
            · 미완결 봉을 라벨·피처로 학습
        을 일으킨다. 규칙: 일봉에서 봉 날짜가 거래소 현지 '오늘'인데 아직
        정규장 마감 전이거나, 미래 날짜면 그 봉을 버린다. 마감 후에는 그날
        봉을 인정한다(미국 20:30 UTC 실행 = 마감 후라 영향 없음).
        """
        from quant.live.market_hours import SCHEDULES, _market_now
        sched = SCHEDULES.get(self.market)
        if sched is None or df.empty:
            return df
        # 일봉 판정: 인덱스 간격이 아니라 호출 맥락이 아닌 데이터로 — 마지막
        # 두 봉의 간격이 1일 미만이면 인트라데이로 보고 건드리지 않는다.
        if len(df) >= 2 and (df.index[-1] - df.index[-2]) < pd.Timedelta(days=1):
            return df
        tzname, _open_t, close_t = sched
        local = _market_now(tzname, now)
        while len(df):
            bar_date = pd.Timestamp(df.index[-1]).date()
            if bar_date > local.date() or (
                    bar_date == local.date() and local.time() < close_t):
                df = df.iloc[:-1]
            else:
                break
        return df

    # ── 소스별 구현 ────────────────────────────────────────────────────

    def _via_yfinance(self, symbol, timeframe, start, end, limit) -> pd.DataFrame:
        import yfinance as yf

        interval = _TF_MAP.get(timeframe, "1d")
        # ⚠️ start '또는' end가 주어지면 범위 모드다. period를 함께 넘기면
        # yfinance가 period를 우선해 start/end를 무시하고 '최근 limit봉'을 주는데,
        # end만 준 워크포워드 요청에서는 요청한 컷오프 이후(미래) 봉이 섞여
        # 룩어헤드가 된다. 범위 모드에선 period를 반드시 None으로 둔다.
        range_mode = start is not None or end is not None
        period = None if range_mode else _limit_to_period(limit, interval)
        df = yf.download(
            symbol, start=start, end=end, period=period,
            interval=interval, progress=False, auto_adjust=True,
        )
        if df is None or df.empty:
            raise ValueError("빈 결과")
        # yfinance는 MultiIndex 컬럼을 반환할 수 있음
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.rename(columns=str.lower)
        if range_mode:
            # 범위 모드: 방어적으로 end 이후 봉을 잘라낸다(룩어헤드 차단).
            if end is not None:
                df = df[df.index <= _align_ts(pd.Timestamp(end), df.index)]
        else:
            # period 모드에서만 최근 limit봉으로 자른다.
            df = df.tail(limit)
        return df

    def _via_yahoo_http(self, symbol, timeframe, start, end, limit) -> pd.DataFrame:
        """야후 chart API를 표준 라이브러리로 직접 호출한다 (일봉 전용)."""
        if _TF_MAP.get(timeframe, "1d") != "1d":
            raise ValueError("yahoo-http 폴백은 일봉만 지원")
        import urllib.parse

        # 공용 HTTP 헬퍼로 받는다(감사 178) — 응답 크기 상한 32MB,
        # 교차 호스트 리다이렉트 방어, 비밀 가리기를 함께 받는다.
        from quant.utils.http import get_json

        rng = ("3mo" if limit <= 60 else "1y" if limit <= 240
               else "2y" if limit <= 480 else "5y" if limit <= 1200 else "max")
        url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
               f"{urllib.parse.quote(symbol)}?interval=1d&range={rng}")
        data = get_json(url, {"User-Agent": "Mozilla/5.0"}, timeout=15)
        r = data["chart"]["result"][0]
        q = r["indicators"]["quote"][0]
        df = pd.DataFrame(
            {"open": q["open"], "high": q["high"], "low": q["low"],
             "close": q["close"], "volume": q["volume"]},
            index=pd.to_datetime(r["timestamp"], unit="s").normalize(),
        ).dropna(subset=_PRICE_COLS)   # 거래량 결측으로 봉을 지우지 않는다(감사 163)
        return _cut_range(df, start, end, limit)

    def _via_stooq(self, symbol, timeframe, start, end, limit) -> pd.DataFrame:
        """Stooq 무료 CSV — 야후와 독립적인 소스. 미국 티커 일봉 전용."""
        if _TF_MAP.get(timeframe, "1d") != "1d":
            raise ValueError("stooq 폴백은 일봉만 지원")
        sym = symbol.lower()
        if "." in sym:                     # 069500.KS 등 접미사 티커는 미지원
            raise ValueError("stooq 폴백은 미국 티커만 지원")
        import io

        from quant.utils.http import get_text          # 상한·방어 공유(감사 178)

        url = f"https://stooq.com/q/d/l/?s={sym}.us&i=d"
        text = get_text(url, {"User-Agent": "Mozilla/5.0"}, timeout=15)
        df = pd.read_csv(io.StringIO(text))
        if "Close" not in df.columns:
            raise ValueError("stooq 응답 형식 오류")
        df = df.rename(columns=str.lower).set_index(pd.to_datetime(df["Date"]))
        df = df[["open", "high", "low", "close", "volume"]].dropna(
            subset=_PRICE_COLS)        # 거래량 결측으로 봉을 지우지 않는다(감사 163)
        return _cut_range(df, start, end, limit)


def _cut_range(df: pd.DataFrame, start, end, limit: int) -> pd.DataFrame:
    """start/end 범위를 적용하고(룩어헤드 차단), 아니면 최근 limit봉으로 자른다."""
    if start is not None:
        df = df[df.index >= _align_ts(pd.Timestamp(start), df.index)]
    if end is not None:
        df = df[df.index <= _align_ts(pd.Timestamp(end), df.index)]
    if start is None and end is None:
        df = df.tail(limit)
    return df


def _align_ts(ts: pd.Timestamp, index: pd.Index) -> pd.Timestamp:
    """비교용 타임스탬프를 인덱스의 시간대에 양방향으로 맞춘다.

    intraday 인덱스는 tz-aware(거래소 tz), 일봉 인덱스는 tz-naive다. end로 어떤
    쪽이 오든 'naive vs aware 비교 TypeError → 조용한 합성 폴백'이 나지 않게
    두 방향(aware 인덱스+naive ts, naive 인덱스+aware ts)을 모두 정렬한다.
    """
    ts = pd.Timestamp(ts)
    tz = getattr(index, "tz", None)
    if tz is not None and ts.tzinfo is None:
        return ts.tz_localize(tz)                       # naive ts → 인덱스 tz
    if tz is None and ts.tzinfo is not None:
        return ts.tz_convert("UTC").tz_localize(None)   # aware ts → naive UTC
    return ts


def _limit_to_period(limit: int, interval: str) -> str:
    """대략적인 period 문자열 추정 (일봉 기준)."""
    if interval.endswith("m") or interval == "1h":
        return "60d"
    days = min(limit + 30, 3650)
    if days > 730:
        return "max"
    return f"{days}d"
