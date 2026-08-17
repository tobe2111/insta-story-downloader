"""부가 지표가 **시세와 같은 사다리**를 타는가 (감사 270).

무슨 일이 있었나
    코인 5종목의 선택 피처 3개 — 펀딩비, 펀딩 변화, 미결제약정 변화 —
    가 **몇 주 동안 한 번도 붙지 않았다.** 장부의 계측기는
    "이 셋이 전 종목에서 빠졌다"까지만 말했고, 왜인지는 몰랐다.

    이유: 시세를 받는 쪽은 바이낸스가 막히면 okx → kucoin → kraken으로
    내려가는 사다리를 갖고 있었고 **실제로 okx에서 받아 왔다**(장부의
    data_source가 5종목 전부 okx다). 그런데 펀딩비·미결제약정은
    `binance`/`binanceusdm`이 코드에 박혀 있었다. 시세는 폴백하는데
    부가 지표는 폴백하지 않아, 막힌 문을 매일 두드리고 있었다.

    같은 규칙(어디에 물어보는가)이 **두 곳에 따로 적혀** 있어서 생긴
    일이다 — FROZEN_IDEAS ①이 말하는 바로 그 병이다.

여기서 지키는 것
  ① 파생 지표의 사다리는 **시세 사다리에서 나온다**(따로 적지 않는다).
  ② 시세를 준 거래소부터 물어본다 — 둘이 같은 장부를 보게.
  ③ 현물 심볼을 그대로 물어보지 않는다(그러면 "펀딩 없음"이 돌아온다).
  ④ 다 실패하면 **거래소별 사유**가 장부에 남는다.
  ⑤ 제공하지 않는 거래소와 막힌 거래소를 **다른 말로** 적는다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.data import crypto as C  # noqa: E402
from quant.data import derivatives as D  # noqa: E402
from quant.data.source_health import source_errors  # noqa: E402


def _df(n: int = 40, source: str | None = "okx") -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    close = pd.Series(np.linspace(100.0, 120.0, n), index=idx)
    out = pd.DataFrame({"open": close, "high": close * 1.01,
                        "low": close * 0.99, "close": close,
                        "volume": 1e6}, index=idx)
    if source:
        out.attrs["source"] = source
    return out


# ── ① 사다리를 두 곳에 적지 않는다 ─────────────────────────────

def test_the_derivative_ladder_follows_the_price_ladder():
    """현물 사다리에 거래소를 추가하면 파생 쪽도 **자동으로** 따라와야 한다.

    이 검사가 없으면, 다음 사람이 현물에 거래소를 하나 더 넣고 파생은
    잊는다. 그게 정확히 이번에 일어난 일이다.
    """
    spot = C.spot_ladder()
    deriv = D.deriv_ladder()
    # 파생 대응이 있는 현물 거래소는 전부, **같은 순서로** 나와야 한다
    expected = [D._SPOT_TO_DERIV[s] for s in spot if s in D._SPOT_TO_DERIV]
    seen, ordered = set(), []
    for e in expected:
        if e not in seen:
            seen.add(e)
            ordered.append(e)
    assert list(deriv) == ordered, (
        f"파생 사다리가 시세 사다리와 어긋난다: 시세{spot} → 파생{deriv}")


def test_every_price_exchange_has_a_derivative_name():
    """현물 사다리에 거래소를 넣고 대응 이름을 잊으면 **조용히 사라진다.**

    그게 이번 사고의 재발 경로다: 시세 쪽만 늘어나고 파생 쪽은 그대로.
    빠진 거래소는 예외를 던지지 않고 그냥 건너뛰어지므로, 검사가 없으면
    아무도 모른다.
    """
    missing = [s for s in C.spot_ladder() if s not in D._SPOT_TO_DERIV]
    assert not missing, (
        f"시세는 {missing}에도 물어보는데 펀딩·미결제약정은 안 물어본다 — "
        "대응 이름을 추가하거나, 그 거래소가 파생을 안 다룬다면 그 사실을 "
        "대응표에 적으세요")


def test_the_price_ladder_still_starts_where_it_used_to():
    """사다리를 함수로 바꾸면서 순서가 바뀌면 안 된다 (실측 순서 고정)."""
    assert C.spot_ladder() == ("binance", "okx", "kucoin", "kraken")
    assert C.spot_ladder("okx") == ("okx", "binance", "kucoin", "kraken")


# ── ② 시세를 준 거래소부터 물어본다 ────────────────────────────

def test_it_asks_the_exchange_that_actually_served_the_price_first():
    """okx가 시세를 줬으면 펀딩도 okx부터 — 실제 사고의 정확한 반대다."""
    assert D.deriv_ladder("okx")[0] == "okx"
    assert D.deriv_ladder(None)[0] == "binanceusdm", (
        "아무 정보가 없으면 기존 기본값부터 — 동작을 조용히 바꾸지 않는다")


def test_funding_asks_okx_when_the_price_came_from_okx(monkeypatch):
    """문자열이 아니라 **값으로** 확인한다 — 어느 거래소에 물어봤는가."""
    asked: list[tuple[str, str]] = []

    def _fake(symbol, exchange="binanceusdm", since=None, limit=1000):
        asked.append((symbol, exchange))
        if exchange != "okx":
            raise RuntimeError("차단됨")
        return pd.Series([0.0001] * 5,
                         index=pd.date_range("2026-01-05", periods=5, freq="D"))

    from quant.data import funding as F
    monkeypatch.setattr(F, "fetch_funding_history", _fake)
    out = F.attach_funding(_df(source="okx"), "BTC/USDT")
    assert "funding" in out.columns, f"펀딩이 안 붙었다 — 물어본 곳: {asked}"
    assert asked and asked[0][1] == "okx", (
        f"시세를 준 거래소(okx)를 먼저 안 물어본다: {asked}")
    assert out.attrs.get("funding_source") == "okx", (
        "어느 거래소에서 받았는지 안 남는다 — 값이 튄 날 제공처 교체를 "
        "의심할 방법이 없다")


def test_funding_climbs_down_when_the_first_exchange_is_blocked(monkeypatch):
    """첫 칸이 막혀도 사다리를 **끝까지** 내려간다 (바로 그 사고 상황)."""
    asked: list[str] = []

    def _fake(symbol, exchange="binanceusdm", since=None, limit=1000):
        asked.append(exchange)
        if exchange == "binanceusdm":
            raise RuntimeError("지역 차단")
        return pd.Series([0.0001] * 3,
                         index=pd.date_range("2026-01-05", periods=3, freq="D"))

    from quant.data import funding as F
    monkeypatch.setattr(F, "fetch_funding_history", _fake)
    # 시세 출처를 모르는 경우 — 예전 코드는 여기서 그냥 포기했다
    out = F.attach_funding(_df(source=None), "BTC/USDT")
    assert "funding" in out.columns, (
        f"바이낸스가 막히자 그대로 포기했다 — 이것이 감사 270이다: {asked}")
    assert asked[0] == "binanceusdm" and len(asked) >= 2


def test_open_interest_climbs_down_too(monkeypatch):
    asked: list[str] = []

    def _fake(symbol, exchange="binanceusdm", timeframe="1d", limit=30):
        asked.append(exchange)
        if exchange == "binanceusdm":
            raise RuntimeError("지역 차단")
        return pd.Series([1000.0, 1100.0, 1200.0],
                         index=pd.date_range("2026-01-05", periods=3, freq="D"))

    from quant.data import openinterest as O
    monkeypatch.setattr(O, "fetch_oi_history", _fake)
    out = O.attach_open_interest(_df(source=None), "BTC/USDT")
    assert "oi" in out.columns, f"미결제약정도 폴백하지 않는다: {asked}"


# ── ③ 심볼을 바꿔 물어본다 ─────────────────────────────────────

def test_it_asks_for_the_perpetual_not_the_spot_symbol():
    """거래소를 바꿔도 심볼이 현물이면 "펀딩 없음"이 돌아온다.

    통합 라이브러리에서 무기한 선물은 `기초/결제:담보` 형식이다.
    이걸 빼먹으면 사다리를 고쳐도 결과는 그대로 빈손이다 — 고친 줄 알고
    넘어가는 것이 가장 나쁘다.
    """
    assert D.perp_symbol("BTC/USDT") == "BTC/USDT:USDT"
    assert D.perp_symbol("ETH/USDT") == "ETH/USDT:USDT"
    # 이미 선물 심볼이면 건드리지 않는다
    assert D.perp_symbol("BTC/USDT:USDT") == "BTC/USDT:USDT"
    # 코인이 아닌 것은 그대로 (한국주식 코드에 `:`를 붙이면 안 된다)
    assert D.perp_symbol("005930.KS") == "005930.KS"


def test_the_fetcher_receives_the_perpetual_symbol(monkeypatch):
    got: list[str] = []

    def _fake(symbol, exchange="binanceusdm", since=None, limit=1000):
        got.append(symbol)
        return pd.Series([0.0001],
                         index=pd.date_range("2026-01-05", periods=1, freq="D"))

    from quant.data import funding as F
    monkeypatch.setattr(F, "fetch_funding_history", _fake)
    F.attach_funding(_df(), "SOL/USDT")
    assert got == ["SOL/USDT:USDT"], (
        f"현물 심볼을 그대로 물어본다 — 거래소는 '펀딩 없음'을 준다: {got}")


# ── ④ 다 실패하면 이유가 남는다 ────────────────────────────────

def test_a_total_failure_names_every_exchange_it_tried(monkeypatch):
    """"없음"만 남기면 다음 사람이 처음부터 다시 조사한다."""
    def _fake(symbol, exchange="binanceusdm", since=None, limit=1000):
        raise RuntimeError("지역 차단")

    from quant.data import funding as F
    monkeypatch.setattr(F, "fetch_funding_history", _fake)
    df = _df()
    F.attach_funding(df, "BTC/USDT")
    why = source_errors(df).get("funding", "")
    assert why, "다 실패했는데 장부가 조용하다"
    for ex in D.deriv_ladder("okx"):
        assert ex in why, f"{ex}를 시도했는지 여부가 사유에 없다: {why}"


def test_an_empty_answer_counts_as_a_failure_not_a_success(monkeypatch):
    """'연결은 됐는데 줄 게 없다'에서 멈추면 사다리가 첫 칸에서 끝난다."""
    asked: list[str] = []

    def _fake(symbol, exchange="binanceusdm", since=None, limit=1000):
        asked.append(exchange)
        if exchange == "binanceusdm":
            return pd.Series(dtype=float)          # 빈 응답
        return pd.Series([0.0001],
                         index=pd.date_range("2026-01-05", periods=1, freq="D"))

    from quant.data import funding as F
    monkeypatch.setattr(F, "fetch_funding_history", _fake)
    out = F.attach_funding(_df(source=None), "BTC/USDT")
    # ⚠️ 컬럼이 붙었는지만 보면 안 된다(변이 시험이 잡아냈다). 빈 Series도
    #    봉 인덱스에 정렬되면 **0으로 가득 찬 컬럼**이 되므로, 컬럼은
    #    멀쩡히 생기고 값만 전부 0이 된다 — 결측보다 나쁘다.
    assert out.attrs.get("funding_source") == "okx", (
        f"빈 응답을 성공으로 세고 첫 칸에서 멈췄다: {asked}")
    assert float(out["funding"].abs().sum()) > 0, (
        "펀딩 컬럼이 전부 0이다 — 붙은 척만 하고 있다")


# ── ⑤ '없는 것'과 '막힌 것'을 구별한다 ────────────────────────

def test_an_exchange_that_does_not_offer_the_metric_is_not_a_failure():
    """크라켄 선물은 펀딩비는 주지만 미결제약정 '이력'은 주지 않는다.

    이걸 "실패"로 적으면 다음 사람이 방화벽을 뒤지다 하루를 버린다.
    """
    tried: dict[str, str] = {}
    calls: list[str] = []

    def _fetch(sym, ex):
        calls.append(ex)
        raise RuntimeError("차단")

    _, ok, tried = D.walk_ladder("okx", "BTC/USDT", _fetch,
                                 capability="fetchOpenInterestHistory")
    assert ok is None
    unsupported = [ex for ex, why in tried.items() if why == D.UNSUPPORTED]
    if unsupported:      # ccxt가 설치돼 기능표를 읽을 수 있는 환경에서만
        assert all(ex not in calls for ex in unsupported), (
            f"제공하지 않는 거래소에 그래도 물어본다: {unsupported}")
        assert D.UNSUPPORTED != "차단", "두 사건이 같은 말로 적힌다"


def test_unknown_capability_is_not_treated_as_no(monkeypatch):
    """모름을 '아니오'로 바꾸면, 라이브러리가 없는 날 사다리가 통째로 꺼진다."""
    monkeypatch.setattr(D, "supports", lambda ex, cap: None)
    calls: list[str] = []

    def _fetch(sym, ex):
        calls.append(ex)
        return pd.Series(dtype=float)

    D.walk_ladder(None, "BTC/USDT", _fetch, capability="아무거나")
    assert calls, "기능표를 못 읽자 아무 거래소에도 안 물어봤다"


# ── 주입 경로는 그대로 (기존 검사들이 쓰는 길) ────────────────

def test_an_explicit_fetch_still_bypasses_the_ladder():
    """호출자가 출처를 지정하면 사다리를 타지 않는다 — 검사 주입용 경로."""
    from quant.data.funding import attach_funding
    hist = pd.Series([0.0002] * 3,
                     index=pd.date_range("2026-01-05", periods=3, freq="D"))
    out = attach_funding(_df(), "BTC/USDT", fetch=lambda s: hist)
    assert "funding" in out.columns
