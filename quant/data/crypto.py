"""암호화폐 데이터 제공자 (ccxt 기반)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd

from quant.data.base import DataProvider
from quant.utils.logging import get_logger

log = get_logger("data.crypto")


# 처음 물어보는 거래소.
DEFAULT_EXCHANGE = "binance"

# 기본 거래소 실패 시 순서대로 시도하는 보조 거래소 — 전 세계 공용 현물 시세라
# 어느 거래소든 BTC/USDT 같은 주요 페어의 일봉은 사실상 동일하다.
_FALLBACK_EXCHANGES = ("okx", "kucoin", "kraken")


def spot_ladder(preferred: str | None = None) -> tuple[str, ...]:
    """코인 시세를 물어볼 거래소 순서 — **이 사다리의 정본은 여기 하나뿐이다.**

    ⚠️ 왜 함수인가 (감사 270). 시세는 이 사다리를 타고 실제로 okx까지
    내려가 데이터를 받아 왔는데, 같은 코인의 **펀딩비·미결제약정**은
    `binance`가 코드에 그대로 박혀 있었다. 바이낸스는 이 환경에서 막혀
    있으므로 그 셋은 **몇 주 동안 한 번도 붙지 않았다.** 시세는 되는데
    부가 지표만 안 되는, 겉으로는 설명이 안 되는 상태였다.

    사다리를 두 곳에 적으면 반드시 어긋난다(FROZEN_IDEAS ①). 그래서
    파생 지표 쪽(`quant.data.derivatives`)도 이 함수를 읽어 순서를 만든다.

    preferred: 먼저 물어볼 거래소(그 종목 시세를 실제로 준 곳). 시세와
    같은 거래소에서 부가 지표를 받으면 둘이 같은 장부를 보게 된다.
    """
    order = ([preferred] if preferred else []) + [DEFAULT_EXCHANGE]
    order += list(_FALLBACK_EXCHANGES)
    out: list[str] = []
    for ex in order:
        if ex and ex not in out:
            out.append(ex)
    return tuple(out)


def _tf_ms(timeframe: str) -> int:
    """타임프레임 한 봉의 밀리초 — 페이지네이션 커서 계산용."""
    unit = timeframe[-1]
    n = int(timeframe[:-1] or 1)
    per = {"m": 60_000, "h": 3_600_000, "d": 86_400_000,
           "w": 604_800_000}.get(unit)
    if per is None:
        raise ValueError(f"알 수 없는 타임프레임: {timeframe}")
    return n * per


# 페이지네이션 안전장치 — 거래소가 같은 페이지를 계속 주거나 한 봉씩만
# 주는 병리적 경우에도 반드시 끝난다. 800봉을 300봉 상한으로 받는 데
# 3~4회면 충분하므로 20회는 넉넉한 여유다.
_MAX_PAGES = 20


def _fetch_paged(client, symbol: str, timeframe: str,
                 since: int | None, limit: int) -> list:
    """요청한 봉 수를 채울 때까지 나눠 받는다 — 거래소별 1회 상한을 넘기 위해.

    ⚠️ 왜 필요한가(2026-08-14 발견). 바이낸스가 막힌 환경에서는 보조 거래소
    okx로 폴백하는데, okx는 **한 번에 300봉**이 상한이다. 그래서 800봉을
    요청해도 300봉만 왔고, 코인 5종목이 전부 300봉으로 굴러갔다. 그 결과:

      · 챔피언(학습창 250봉)이 오디션 선발 구간(300−120=180봉)에서
        **한 번도 학습하지 못했다** → 후보 19개 중 18개가 신호 0으로
        챔피언과 동일 → 코인 오디션은 매일 아무것도 검증하지 못했다
      · 실제 운용에서도 예측 가능한 구간이 50봉뿐이라 코인 노출이
        주식(27~36%)의 1/4 수준(5~15%)에 머물렀다
      · 300봉으로 잰 과최적화 지표(BTC PBO 0.78)도 표본 부족의 산물이었다

    한 번에 다 주는 거래소(바이낸스 등)에서는 첫 페이지로 끝나므로 동작이
    바뀌지 않는다 — 모자랄 때만 이어 받는다.

    since가 없으면 '최근 limit봉'을 원하는 것이므로, 필요한 만큼 과거로
    거슬러 올라간 시각을 시작점으로 잡는다(거래소는 since부터 앞으로 준다).

    ⚠️ **그리고 현재에 닿을 때까지 받아야 한다** (2026-08-16 실전 사고, 감사 261).
    첫 판은 `len(rows) >= limit`에서 멈췄다. 그런데 시작점은 `limit*1.2` 뒤라,
    800개를 다 모은 시점이 아직 **165일 전**이었다. 즉 앞에서부터 800개를
    받고 **최근 165일을 통째로 못 받았다.**

        실측(2026-08-16 야간 배치): 코인 5종목이 bars=800으로 '성공'했는데
        마지막 봉이 **2026-03-04** — 5개월 반 묵은 데이터로 챔피언을 결정했다.
        (감사 243의 정체 경보가 정확히 165일로 잡아냈다.)

    "봉 수를 채웠다"와 "최신까지 받았다"는 다른 조건이다. 개수로 멈추면
    **더 오래된 쪽**이 남는다 — 판단에 쓸 수 없는 쪽이다. 그래서 멈추는
    기준을 개수가 아니라 **도달 시각**으로 바꾸고, 넘치면 뒤에서 자른다.
    """
    step = _tf_ms(timeframe)
    now_ms = int(pd.Timestamp.now("UTC").timestamp() * 1000)
    # ⚠️ 두 요청은 **다른 것을 원한다** — 여기를 뭉뚱그린 것이 사고의 뿌리다.
    #    · 시작점을 **받았다**  → "그 지점부터 limit봉"(호출자가 구간을 안다)
    #    · 시작점이 **없다**    → "**최신** limit봉"(우리가 시작점을 정한다)
    #    뒤쪽에서 개수로 멈추면 우리가 정한 시작점이 한참 과거라 최신을 놓친다.
    tail = since is None
    if tail:
        # 휴장·점검으로 빠지는 봉이 있으므로 20% 여유를 두고 거슬러 올라간다.
        since = now_ms - int(limit * 1.2 + 5) * step
    rows: list = []
    seen: set = set()
    cursor = since
    for _ in range(_MAX_PAGES):
        # ⚠️ 남은 개수(limit - len(rows))로 조르면 마지막 페이지가 잘려
        #    최신 봉을 못 받는다. 한 번에 줄 수 있는 만큼 받게 둔다.
        # ⚠️ '최신 limit봉'을 받는 중이면 남은 개수로 조르면 안 된다 —
        #    마지막 페이지가 잘려 최신 봉을 못 받는다.
        page = client.fetch_ohlcv(symbol, timeframe=timeframe, since=cursor,
                                  limit=limit if tail else limit - len(rows))
        if not page:
            break
        fresh = [r for r in page if r and r[0] not in seen]
        if not fresh:
            break                       # 진전 없음 — 같은 페이지의 반복
        for r in fresh:
            seen.add(r[0])
        rows.extend(fresh)
        last_ts = max(r[0] for r in fresh)
        # 멈추는 기준이 요청 종류에 따라 다르다. 구간 요청은 개수를 채우면
        # 끝이고, '최신 limit봉'은 **현재에 닿아야** 끝이다.
        if (last_ts + step > now_ms) if tail else (len(rows) >= limit):
            break
        nxt = last_ts + step
        if nxt <= cursor:
            break                       # 커서가 안 움직이면 무한루프다
        cursor = nxt
    rows.sort(key=lambda r: r[0])
    return rows[-limit:] if len(rows) > limit else rows


def _build_client(exchange_id: str, api_key: str = "", secret: str = ""):
    """ccxt 클라이언트 생성 (테스트에서 대체 주입할 수 있게 모듈 함수로 분리)."""
    import ccxt

    klass = getattr(ccxt, exchange_id)
    return klass({"apiKey": api_key, "secret": secret, "enableRateLimit": True})


class CryptoDataProvider(DataProvider):
    """ccxt를 통해 거래소 OHLCV를 가져온다 (기본: 바이낸스).

    기본 거래소가 실패하면 보조 거래소(_FALLBACK_EXCHANGES)를 순서대로 시도하고,
    전부 실패해야만 SyntheticDataProvider로 폴백한다 — 단일 거래소 의존은
    야간 자동화의 최약점이었다(지역 차단·점검 하나로 그날 기록이 빈다).
    """

    def __init__(self, exchange: str = DEFAULT_EXCHANGE, api_key: str = "",
                 secret: str = ""):
        self.exchange_id = exchange
        self._client = None
        try:
            self._client = _build_client(exchange, api_key, secret)
        except Exception as exc:  # noqa: BLE001
            log.warning("ccxt 초기화 실패(%s). 보조 거래소/합성 폴백으로 진행합니다.", exc)

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1d",
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 500,
    ) -> pd.DataFrame:
        ladder = spot_ladder(self.exchange_id)
        attempts: list[tuple[str, object]] = [
            (ex, self._client if (ex == self.exchange_id
                                  and self._client is not None) else None)
            for ex in ladder]

        for ex_id, client in attempts:
            try:
                if client is None:
                    client = _build_client(ex_id)
                df = self._fetch(client, symbol, timeframe, start, end, limit)
                df.attrs["source"] = ex_id
                if ex_id != self.exchange_id:
                    log.info("%s: 보조 거래소(%s)로 시세 수신 (%d봉)",
                             symbol, ex_id, len(df))
                return df
            except Exception as exc:  # noqa: BLE001
                log.warning("%s 시세 조회 실패[%s]: %s", symbol, ex_id, exc)

        log.warning("%s: 모든 거래소 실패. 합성 데이터로 폴백.", symbol)
        return self._fallback(symbol, timeframe, start, end, limit)

    def _fetch(self, client, symbol, timeframe, start, end, limit) -> pd.DataFrame:
        # 거래소 타임스탬프는 UTC epoch(ms) 기준이다. naive datetime을
        # start.timestamp()로 바꾸면 로컬 시간대가 섞여 since가 어긋나므로,
        # 시간대 정보가 없으면 UTC로 간주해 변환한다.
        since = None
        if start is not None:
            ts = pd.Timestamp(start)
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            since = int(ts.timestamp() * 1000)
        raw = _fetch_paged(client, symbol, timeframe, since, limit)
        df = pd.DataFrame(
            raw, columns=["ts", "open", "high", "low", "close", "volume"]
        )
        # unit="ms"는 거래소 epoch(UTC)를 그대로 tz-naive 타임스탬프로 만든다.
        df.index = pd.to_datetime(df["ts"], unit="ms")
        # end가 지정되면 그 이후 봉은 잘라낸다(fetch_ohlcv는 since만 지원).
        # 인덱스는 naive-UTC이므로, end가 tz-aware여도 naive-UTC로 맞춰 비교한다
        # (안 맞추면 'naive vs aware' TypeError → 조용한 합성 폴백이 난다).
        if end is not None:
            end_ts = pd.Timestamp(end)
            if end_ts.tzinfo is not None:
                end_ts = end_ts.tz_convert("UTC").tz_localize(None)
            df = df[df.index <= end_ts]
        out = self._validate(df)
        # ⚠️ 여기엔 빈 결과 검사가 **아예 없었다**(감사 163, 주식 쪽 형제).
        #    거래소가 빈 리스트를 주거나(상장폐지·심볼 오타·점검) end 컷이
        #    다 잘라내면 0봉 프레임이 그대로 '성공'으로 올라가, 보조 거래소를
        #    안 거치고 합성 폴백 표식도 없이 반환됐다.
        if out.empty:
            raise ValueError("검증 후 빈 결과")
        return out

    @staticmethod
    def _fallback(symbol, timeframe, start, end, limit) -> pd.DataFrame:
        from quant.data.synthetic import SyntheticDataProvider

        df = SyntheticDataProvider().get_ohlcv(
            symbol, timeframe, start, end, limit
        )
        # '진짜 시세가 아니라 폴백'임을 표식한다. 이 표식이 없으면
        # CachedDataProvider가 더미 데이터를 실제 거래소 키로 디스크에 저장해,
        # 네트워크가 복구된 뒤에도 TTL 동안 가짜 시세를 계속 재사용한다.
        df.attrs["synthetic_fallback"] = True
        return df
