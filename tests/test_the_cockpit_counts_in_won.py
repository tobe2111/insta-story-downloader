"""조종석의 실시간 평가도 원화로 센다 (감사 231).

배경:
  감사 212에서 통합 계좌를 원화로 다시 열고 체결·평가를 환산하게 고쳤다.
  그런데 **조종석/방송 화면만 옛 회계로 남아 있었다.** `_live_prices`는
  현지 통화 그대로 돌려주는데 호출부는 그 값을 원화 장부의 현금에 그대로
  더한다:

      평가 = 현금(원) + 수량 × 달러가격          ← 단위가 섞인다

  실측(오늘 보유 기준): 올바른 평가 1,327,716원 vs 조종석이 내는 값
  371,051원 — 계좌를 **27.9%로 축소**해 보여주고, 그 차이가 그대로
  '실시간 수익률'로 방송된다. 하필 조종석은 사장님이 실제로 들여다보는
  화면이다.

  같은 판정을 두 곳에 두면 한 곳만 고치게 된다 — 감사 219가 말한 그대로다.

핵심 계약:
  · 화면에 나가는 값은 전부 원화다
  · 환율을 못 받으면 해외 종목은 **빼고** 돌려준다(1.0으로 안 때운다).
    그러면 호출부가 실시간 평가 자체를 만들지 않는다
  · 국내 종목은 환율 없이도 그대로 나온다(대조군)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from quant.web import app as A  # noqa: E402


class _Prov:
    def __init__(self, px):
        self.px = px

    def get_ohlcv(self, symbol, tf, limit=2):
        df = pd.DataFrame({"close": [self.px, self.px]})
        df.attrs["synthetic_fallback"] = False
        return df


def _patch(monkeypatch, *, rate, prices):
    monkeypatch.setattr(A, "_PRICE_CACHE", {"ts": 0.0, "prices": {}})
    import quant.data as qd
    import quant.data.fx as fx
    monkeypatch.setattr(fx, "usdkrw", lambda *a, **k: rate)
    monkeypatch.setattr(qd, "get_provider",
                        lambda market: _Prov(prices[market]))


def test_foreign_prices_come_back_in_won(monkeypatch):
    _patch(monkeypatch, rate=1412.5,
           prices={"us_stock": 772.49, "crypto": 75.89, "kr_stock": 166000.0})
    got = A._live_prices(["us_stock:SPY", "crypto:SOL/USDT",
                          "kr_stock:105560.KS"])
    assert got["us_stock:SPY"] == 772.49 * 1412.5, (
        "달러 가격이 그대로 나온다 — 원화 현금에 더해지면 계좌가 쪼그라든다")
    assert got["crypto:SOL/USDT"] == 75.89 * 1412.5
    # 대조군 — 국내 종목은 환산 대상이 아니다
    assert got["kr_stock:105560.KS"] == 166000.0


def test_without_a_rate_foreign_symbols_are_dropped_not_guessed(monkeypatch):
    """환율을 못 받으면 값을 만들지 않는다 — 그래야 호출부가 포기한다."""
    _patch(monkeypatch, rate=None,
           prices={"us_stock": 772.49, "crypto": 75.89, "kr_stock": 166000.0})
    got = A._live_prices(["us_stock:SPY", "crypto:SOL/USDT",
                          "kr_stock:105560.KS"])
    assert "us_stock:SPY" not in got
    assert "crypto:SOL/USDT" not in got
    assert got["kr_stock:105560.KS"] == 166000.0   # 국내는 계속 나온다


def test_a_missing_foreign_price_blocks_the_live_equity(monkeypatch, tmp_path):
    """빠진 종목이 있으면 '실시간 평가'를 아예 만들지 않는다.

    일부만 더한 평가는 계좌를 실제보다 작게 보이게 한다 — 그것이 감사 231이
    실제로 만든 숫자였다.
    """
    import json

    paper = tmp_path / "paper"
    paper.mkdir()
    (paper / "portfolio_ALL.json").write_text(json.dumps({
        "market": "portfolio", "symbol": "ALL", "currency": "KRW",
        "start_cash": 1_000_000.0, "cash": 370_373.0,
        "positions": {"us_stock:SPY": {"quantity": 0.7644,
                                       "avg_price": 1_090_000.0}},
        "history": [{"date": "2026-08-14", "equity": 1_327_716.0,
                     "return_pct": 32.8, "price": 100.0}]}), "utf-8")
    _patch(monkeypatch, rate=None, prices={"us_stock": 772.49})
    payload = json.loads(A.broadcast_json(str(tmp_path), with_live=True))
    pf = next(a for a in payload["accounts"] if a["market"] == "portfolio")
    assert "live_equity" not in pf, (
        "환율을 모르는데 실시간 평가를 만들었다")
    assert pf["equity"] == 1_327_716.0            # 확정값은 그대로 보여준다


def test_the_live_equity_matches_the_won_ledger(monkeypatch, tmp_path):
    """대조군 — 환율이 있으면 실시간 평가가 원화 장부와 같은 자리에 선다."""
    import json

    paper = tmp_path / "paper"
    paper.mkdir()
    (paper / "portfolio_ALL.json").write_text(json.dumps({
        "market": "portfolio", "symbol": "ALL", "currency": "KRW",
        "start_cash": 1_000_000.0, "cash": 370_373.0,
        "positions": {"us_stock:SPY": {"quantity": 1.0,
                                       "avg_price": 1_090_000.0}},
        "history": [{"date": "2026-08-14", "equity": 1_461_000.0,
                     "return_pct": 46.1, "price": 100.0}]}), "utf-8")
    _patch(monkeypatch, rate=1412.5, prices={"us_stock": 772.49})
    payload = json.loads(A.broadcast_json(str(tmp_path), with_live=True))
    pf = next(a for a in payload["accounts"] if a["market"] == "portfolio")
    want = round(370_373.0 + 772.49 * 1412.5, 2)
    assert pf["live_equity"] == want, (
        f"실시간 평가가 {pf['live_equity']:,} — 원화 기준이면 {want:,}이어야 한다")
    # 원화 장부와 같은 자릿수여야 한다(환산 누락이면 수십만 원대로 떨어진다)
    assert pf["live_equity"] > 1_000_000


def test_positions_get_their_own_quotes_not_borrowed_ones(monkeypatch, tmp_path):
    """통합 계좌 보유 종목의 시세를 **직접** 요청해야 한다 (감사 231).

    예전에는 '계좌 키'만 넘겼다. 통합 계좌 키(portfolio:ALL)는 시세가 없어
    건너뛰므로, 보유 종목 가격은 "마침 같은 이름의 종목 계좌가 목록에
    있어서" 딸려 오던 것이었다. 그 계좌가 기록이 없어 빠지는 날엔 한 종목
    때문에 실시간 평가가 통째로 사라진다 — 조용히.
    """
    import json

    asked = []

    def spy(keys, ttl=45.0):
        asked.extend(keys)
        return {"us_stock:SPY": 772.49 * 1412.5}

    paper = tmp_path / "paper"
    paper.mkdir()
    (paper / "portfolio_ALL.json").write_text(json.dumps({
        "market": "portfolio", "symbol": "ALL", "currency": "KRW",
        "start_cash": 1_000_000.0, "cash": 370_373.0,
        "positions": {"us_stock:SPY": {"quantity": 1.0,
                                       "avg_price": 1_090_000.0}},
        "history": [{"date": "2026-08-14", "equity": 1_461_000.0,
                     "return_pct": 46.1, "price": 100.0}]}), "utf-8")
    monkeypatch.setattr(A, "_live_prices", spy)
    payload = json.loads(A.broadcast_json(str(tmp_path), with_live=True))
    assert "us_stock:SPY" in asked, (
        "보유 종목 시세를 요청하지 않는다 — 종목 계좌에 얹혀 가고 있다")
    pf = next(a for a in payload["accounts"] if a["market"] == "portfolio")
    assert pf["live_equity"] > 1_000_000


def test_the_quote_relay_returns_nothing_when_it_fails(monkeypatch):
    """중계가 실패하면 **빈 응답**이다 — 없는 값을 지어내지 않는다.

    못 받은 것을 옛 값으로 채우고 '실시간'이라 쓰는 것이 감사 229에서
    고친 결함이다. 여기서 같은 실수를 반복하지 않는다.
    """
    import json
    import urllib.request

    def boom(*a, **k):
        raise OSError("네트워크 없음")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    got = json.loads(A.quotes_proxy("symbols=AAPL"))
    assert got["quotes"] == {}, "실패했는데 시세를 만들어 냈다"
    assert "error" in got, "실패를 조용히 삼켰다"


def test_the_quote_relay_passes_through_what_it_gets(monkeypatch):
    """대조군 — 정상 응답은 그대로 흘려보낸다(여기서 판정하지 않는다)."""
    import io
    import json
    import urllib.request

    body = json.dumps({"quotes": {"AAPL": {"price": 268.1, "source": "finnhub",
                                           "delayed": False}}}).encode()

    class _R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _R(body))
    got = json.loads(A.quotes_proxy("symbols=AAPL"))
    assert got["quotes"]["AAPL"]["source"] == "finnhub"
    assert got["quotes"]["AAPL"]["delayed"] is False
