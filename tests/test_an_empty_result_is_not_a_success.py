"""검증이 프레임을 비웠는데 '성공'이라고 했다 (감사 163).

주식 제공자는 소스 3개를, 코인 제공자는 거래소 5개를 순서대로 시도한다.
소스 하나가 흔들려도 그날 기록이 비지 않게 하려고 만든 구조다.

그 구조가 통째로 무력화되는 구멍이 있었다. **빈 결과 검사가 프레임을
비우는 코드보다 앞에 있었다.**

    df = fetch(...)
    if df is None or df.empty:      # ← 소스가 준 원본만 본다
        raise ValueError("빈 결과")
    out = self._drop_unclosed(self._validate(df))   # ← 여기서 비워질 수 있다
    out.attrs["source"] = name
    return out                       # 0봉인데 '성공'

코인 쪽(`_fetch`)에는 빈 결과 검사가 **아예 없었다.**

0봉 프레임이 '성공'으로 반환되면:
    · 보조 소스·보조 거래소를 건너뛴다
    · `synthetic_fallback` 표식이 안 붙는다 → 가짜 데이터 경보도 안 울린다
    · `attrs["source"]`에는 "yfinance"라고 적힌다 → 장부에 그렇게 남는다

──────────────────────────────────────────────────────────────
무엇이 프레임을 비우는가 — 거래량이 없는 계열

`_validate`가 `dropna()`로 **다섯 컬럼 중 하나라도** 비면 그 봉을 지웠다.
그런데 거래량이 원래 없는 계열이 있다 — 지수(^VIX·^VIX3M·^TNX)와
환율(KRW=X). 이 시스템은 그 넷을 크로스에셋 피처로 전부 받는다.

실측(거래량만 없는 120봉 지수 계열):

    _validate 통과 후 0봉 · source="yfinance" · 합성 폴백 아님

가격은 120봉 다 멀쩡했다. 거래량이 없다는 이유로 전부 지워진 것이다.
한 봉만 결측이어도 마찬가지다 — 시계열에 구멍이 나고, 그 구멍을 건너뛴
수익률이 하루치인 척 라벨과 사이징에 들어간다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.data.base import DataProvider  # noqa: E402
from quant.data.crypto import CryptoDataProvider  # noqa: E402
from quant.data.quality import is_severe, scan_ohlcv  # noqa: E402
from quant.data.stock import StockDataProvider  # noqa: E402

N = 120
IDX = pd.date_range("2024-01-01", periods=N, freq="B")
SOURCES = ("_via_yfinance", "_via_yahoo_http", "_via_stooq")


def _frame(volume) -> pd.DataFrame:
    c = 15.0 + np.sin(np.arange(N) / 7.0)
    return pd.DataFrame({"open": c, "high": c + 0.3, "low": c - 0.3,
                         "close": c, "volume": volume}, index=IDX)


def _index_like() -> pd.DataFrame:
    """^VIX 같은 계열 — 가격은 멀쩡하고 거래량만 통째로 없다."""
    return _frame([np.nan] * N)


def _provider(**by_source) -> StockDataProvider:
    """각 소스가 무엇을 돌려줄지 지정한다. 미지정 소스는 실패한다."""
    p = StockDataProvider(market="us_stock")
    for name in SOURCES:
        made = by_source.get(name)
        if made is None:
            def _fail(*a, **kw):
                raise ValueError("소스 다운")
            setattr(p, name, _fail)
        else:
            setattr(p, name, lambda *a, _m=made, **kw: _m())
    return p


# ── 거래량이 없다고 가격 봉을 지우지 않는가 ───────────────────


def test_a_series_without_volume_survives_validation():
    out = DataProvider._validate(_index_like())
    assert len(out) == N, (
        f"거래량 없는 지수 {N}봉이 {len(out)}봉으로 줄었다 — "
        "가격은 전부 멀쩡한데 거래량 때문에 지워진다")
    assert out["volume"].isna().all(), "없는 거래량을 0으로 지어내면 안 된다"


def test_one_missing_volume_does_not_punch_a_hole():
    """구멍이 나면 그 구멍을 건너뛴 수익률이 하루치인 척 들어간다."""
    vol = [1e6] * N
    vol[50] = np.nan
    out = DataProvider._validate(_frame(vol))
    assert len(out) == N, f"거래량 한 칸 때문에 봉이 {N - len(out)}개 사라졌다"
    assert IDX[50] in out.index


def test_a_bar_without_a_price_is_still_dropped():
    """대조군 — 가격이 없는 봉은 진짜로 못 쓴다. 여기까지 살리면 반대로 위험하다."""
    df = _frame([1e6] * N)
    df.loc[IDX[50], "close"] = np.nan
    out = DataProvider._validate(df)
    assert len(out) == N - 1 and IDX[50] not in out.index


def test_the_index_series_reaches_the_caller_intact():
    """부품이 아니라 배선 — 제공자를 통째로 지났을 때 살아 있는가."""
    df = _provider(_via_yfinance=_index_like).get_ohlcv("^VIX", "1d", limit=N)
    assert len(df) == N, f"{len(df)}봉만 왔다"
    assert not df.attrs.get("synthetic_fallback")
    assert abs(float(df["close"].iloc[0]) - 15.0) < 1.0, "값이 VIX 같지 않다"


# ── 검증이 비운 프레임은 성공이 아니다 ────────────────────────


def _all_prices_missing() -> pd.DataFrame:
    df = _frame([1e6] * N)
    df[["open", "high", "low", "close"]] = np.nan
    return df


def test_a_frame_emptied_by_validation_falls_through_to_the_backup():
    """이것이 감사 163의 본체 — 3중 소스 체인이 무력화되던 자리."""
    p = _provider(_via_yfinance=_all_prices_missing,
                  _via_yahoo_http=lambda: _frame([1e6] * N))
    df = p.get_ohlcv("AAPL", "1d", limit=N)
    assert len(df) == N, (
        f"{len(df)}봉 — 1번 소스가 검증 후 0봉이 됐는데 보조 소스로 안 넘어갔다")
    assert df.attrs["source"] == "yahoo-http", df.attrs


def test_when_every_source_empties_out_it_is_marked_synthetic():
    """전부 실패하면 **가짜라고 표시된** 데이터가 와야 한다.

    표식이 없으면 배치의 require_real_data 가드도, 사이트의 경보 배너도
    울리지 않는다 — 조용히 가짜로 매매하게 된다.
    """
    p = _provider(_via_yfinance=_all_prices_missing,
                  _via_yahoo_http=_all_prices_missing,
                  _via_stooq=_all_prices_missing)
    df = p.get_ohlcv("AAPL", "1d", limit=N)
    assert df.attrs.get("synthetic_fallback"), (
        f"0봉 3연속인데 합성 폴백 표식이 없다: {dict(df.attrs)}")


def test_a_source_that_only_returns_an_unclosed_bar_is_not_a_success():
    """`_drop_unclosed`도 프레임을 비울 수 있다 — 그쪽 경로도 막혔는가."""
    future = pd.Timestamp.now("UTC").tz_localize(None).normalize() + pd.Timedelta(days=3)

    def _only_tomorrow():
        return pd.DataFrame({"open": [100.0], "high": [101.0], "low": [99.0],
                             "close": [100.0], "volume": [1e6]}, index=[future])

    p = _provider(_via_yfinance=_only_tomorrow,
                  _via_yahoo_http=lambda: _frame([1e6] * N))
    df = p.get_ohlcv("AAPL", "1d", limit=N)
    assert df.attrs["source"] == "yahoo-http", (
        "아직 안 끝난 봉 하나만 온 소스를 '성공'으로 받았다")


def test_a_healthy_source_is_still_used_first():
    """대조군 — 멀쩡한 1번 소스를 건너뛰면 그건 고침이 아니라 파괴다."""
    p = _provider(_via_yfinance=lambda: _frame([1e6] * N),
                  _via_yahoo_http=lambda: _frame([2e6] * N))
    df = p.get_ohlcv("AAPL", "1d", limit=N)
    assert df.attrs["source"] == "yfinance" and len(df) == N


# ── 보조 소스도 같은 자리에서 봉을 지우고 있었다 ──────────────
#
# ⚠️ 위 검사들은 `_via_*`를 통째로 가짜로 바꾼다. 그래서 **보조 소스의
#    진짜 파싱 코드는 한 줄도 안 돈다.** 실제로 변이를 놓쳤다 —
#    야후 HTTP 쪽 dropna를 되돌려도 위 검사는 전부 통과했다.
#    `_validate` 앞에서 자기 dropna를 먼저 하는 소스가 둘 있다.


def _fake_urlopen(monkeypatch, body: bytes):
    """가짜 응답을 물린다.

    ⚠️ 감사 178부터 이 소스들은 `urllib.request.urlopen`이 아니라 공용
       헬퍼(`quant.utils.http`)의 `_opener`를 지난다 — 응답 크기 상한과
       리다이렉트 방어를 함께 받기 위해서다. 그래서 가짜도 그쪽에 물린다.
    """
    import io

    import quant.utils.http as H

    class _Resp(io.BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        H, "_opener",
        type("_O", (), {"open": lambda s, r, timeout=None: _Resp(body)})())


def test_the_yahoo_http_source_keeps_bars_without_volume(monkeypatch):
    import json as _json

    n = 30
    ts = [int(t.timestamp())
          for t in pd.date_range("2025-01-01", periods=n, freq="D", tz="UTC")]
    close = [15.0 + i * 0.1 for i in range(n)]
    payload = {"chart": {"result": [{
        "timestamp": ts,
        "indicators": {"quote": [{"open": close, "high": close, "low": close,
                                  "close": close, "volume": [None] * n}]}}]}}
    _fake_urlopen(monkeypatch, _json.dumps(payload).encode())

    df = StockDataProvider(market="us_stock")._via_yahoo_http(
        "^VIX", "1d", None, None, n)
    assert len(df) == n, (
        f"야후 HTTP가 거래량 없는 {n}봉을 {len(df)}봉으로 줄였다 — "
        "이 소스는 _validate 앞에서 자기 dropna를 먼저 한다")


def test_the_stooq_source_keeps_bars_without_volume(monkeypatch):
    n = 30
    rows = "\n".join(
        f"{d:%Y-%m-%d},100.0,101.0,99.0,100.5,"
        for d in pd.date_range("2025-01-01", periods=n, freq="D"))
    _fake_urlopen(monkeypatch,
                  ("Date,Open,High,Low,Close,Volume\n" + rows).encode())

    df = StockDataProvider(market="us_stock")._via_stooq(
        "SPY", "1d", None, None, n)
    assert len(df) == n, f"stooq가 {len(df)}봉으로 줄였다"
    assert df["volume"].isna().all()


# ── 형제: 코인 제공자에도 같은 구멍이 있었다 ──────────────────


class _EmptyExchange:
    """빈 리스트를 주는 거래소 — 상장폐지·심볼 오타·점검 때 실제로 이렇다."""

    def fetch_ohlcv(self, *a, **kw):
        return []


class _GoodExchange:
    def fetch_ohlcv(self, *a, **kw):
        return [[int(t.timestamp() * 1000), 100.0, 101.0, 99.0, 100.5, 5.0]
                for t in pd.date_range("2025-01-01", periods=50, freq="D")]


def _crypto(client, monkeypatch, backup) -> CryptoDataProvider:
    import quant.data.crypto as mod
    p = CryptoDataProvider.__new__(CryptoDataProvider)
    p.exchange_id, p._client = "binance", client
    monkeypatch.setattr(mod, "_build_client", lambda ex, *a, **kw: backup())
    return p


def test_an_empty_exchange_falls_through_to_the_next_one(monkeypatch):
    p = _crypto(_EmptyExchange(), monkeypatch, _GoodExchange)
    df = p.get_ohlcv("BTC/USDT", "1d", limit=50)
    assert len(df) == 50, (
        f"{len(df)}봉 — 기본 거래소가 빈 결과인데 보조 거래소로 안 넘어갔다")
    assert df.attrs["source"] != "binance", df.attrs
    assert not df.attrs.get("synthetic_fallback")


def test_when_every_exchange_is_empty_it_is_marked_synthetic(monkeypatch):
    p = _crypto(_EmptyExchange(), monkeypatch, _EmptyExchange)
    df = p.get_ohlcv("BTC/USDT", "1d", limit=50)
    assert df.attrs.get("synthetic_fallback"), (
        f"모든 거래소가 빈 결과인데 합성 폴백 표식이 없다: {dict(df.attrs)}")


def test_a_healthy_exchange_is_still_used(monkeypatch):
    """대조군."""
    p = _crypto(_GoodExchange(), monkeypatch, _EmptyExchange)
    df = p.get_ohlcv("BTC/USDT", "1d", limit=50)
    assert len(df) == 50 and df.attrs["source"] == "binance"


# ── 사람이 볼 줄에 남는가 ─────────────────────────────────────


def test_missing_volume_is_visible_in_the_report_but_does_not_halt_trading():
    """거래량 결측은 이제 프레임에 남는다 — 보이되, 매매를 막지는 않아야 한다."""
    f = scan_ohlcv(DataProvider._validate(_index_like()))
    assert f["zero_volume"] == N, (
        f"결측 거래량 {N}건이 보고서에 {f['zero_volume']}건으로 보인다 — "
        "`<= 0`은 NaN을 False로 본다")
    assert not is_severe(f), (
        "지수·환율은 거래량이 원래 없다 — 그걸로 그날 매매를 멈추면 안 된다")


def test_a_normal_frame_reports_no_missing_volume():
    """대조군 — 평시에 울리면 매일 울려서 아무도 안 본다."""
    f = scan_ohlcv(DataProvider._validate(_frame([1e6] * N)))
    assert f["zero_volume"] == 0 and not is_severe(f), f


@pytest.mark.parametrize("mod,name", [("quant/data/stock.py", "주식"),
                                      ("quant/data/crypto.py", "코인")])
def test_both_providers_check_after_validating(mod, name):
    """배선 고정 — 두 제공자 모두 '검증 뒤'에 비었는지 보는가."""
    src = (ROOT / mod).read_text("utf-8")
    assert "검증 후 빈 결과" in src, f"{name} 제공자에 검증 후 빈 결과 검사가 없다"
