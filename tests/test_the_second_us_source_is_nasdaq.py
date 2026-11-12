"""미국 보조 시세 소스는 나스닥이다 (2026-11-13 감사 383).

감사 382가 오류에 받은 본문을 싣게 한 뒤 첫 배치(11-12)의 stooq 응답이
"This site requires JavaScript to verify your browser"(봇 차단)였다 — 미국 23종목이
사흘 내내 그 벽에 막혀 대조에서 빠졌다. 받은 것을 보고 소스를 바꿨다.
"""
import json

import pandas as pd
import pytest

from quant.data import second_opinion as S
from quant.data.stock import StockDataProvider, _nasdaq_rows
from quant.utils.http import HttpError

# 나스닥 historical 응답의 모양 — 최신이 위, 날짜는 MM/DD/YYYY, 값은 "$1,234.50".
ROWS = [
    {"date": "11/12/2026", "close": "$1,210.00", "volume": "1,000", "open": "$1,200.00",
     "high": "$1,215.00", "low": "$1,195.00"},
    {"date": "11/11/2026", "close": "$1,200.00", "volume": "N/A", "open": "N/A",
     "high": "N/A", "low": "N/A"},
    {"date": "11/10/2026", "close": "$1,100.00", "volume": "900", "open": "$1,090.00",
     "high": "$1,105.00", "low": "$1,080.00"},
]


def _ok(rows):
    return json.dumps({"data": {"symbol": "X", "tradesTable": {"rows": rows}},
                       "status": {"rCode": 200}})


def _p():
    return StockDataProvider(market="us_stock")


def test_rows_are_read_oldest_first_with_dollars_and_commas():
    df = _nasdaq_rows(ROWS)
    assert list(df.index) == list(pd.to_datetime(["2026-11-10", "2026-11-11", "2026-11-12"]))
    assert df["close"].tolist() == [1100.0, 1200.0, 1210.0]


def test_a_day_with_only_a_close_is_kept():
    """ETF 표는 시가 칸이 'N/A'인 날이 있다 — 대조는 종가만 쓴다."""
    df = _nasdaq_rows(ROWS)
    assert pd.Timestamp("2026-11-11") in df.index


def test_an_etf_is_found_on_the_second_asset_class():
    asked = []

    def get(url, hdr, timeout=15):
        asked.append(url)
        if "assetclass=stocks" in url:          # 틀린 자산군은 400으로 온다
            raise HttpError("HTTP 400 for nasdaq")
        return _ok(ROWS)
    df = _p()._via_nasdaq("SPY", "1d", None, None, 30, _get=get)
    assert len(asked) == 2 and "assetclass=etf" in asked[1]
    assert df.attrs["source"] == "nasdaq" and len(df) == 3


def test_an_empty_table_moves_on_and_says_why():
    def get(url, hdr, timeout=15):
        return json.dumps({"data": None, "status": {"rCode": 400,
                                                    "bCodeMessage": "Symbol not exists"}})
    with pytest.raises(ValueError) as e:
        _p()._via_nasdaq("ZZZ", "1d", None, None, 30, _get=get)
    assert "stocks" in str(e.value) and "etf" in str(e.value)
    assert "Symbol not exists" in str(e.value)


def test_a_bot_wall_carries_what_came_back():
    """감사 382의 규약 그대로 — 받은 것을 오류에 싣는다."""
    def get(url, hdr, timeout=15):
        return "<html><body>This site requires JavaScript to verify your browser</body></html>"
    with pytest.raises(ValueError) as e:
        _p()._via_nasdaq("AAPL", "1d", None, None, 30, _get=get)
    assert "requires JavaScript" in str(e.value)


@pytest.mark.parametrize("sym", ["005930.KS", "BTC/USDT"])
def test_only_us_tickers(sym):
    with pytest.raises(ValueError):
        _p()._via_nasdaq(sym, "1d", None, None, 30, _get=lambda *a, **k: _ok(ROWS))


def test_the_us_second_opinion_asks_nasdaq_not_stooq():
    name, _ = S._second("us_stock", "SPY", "yfinance")
    assert name == "nasdaq"
    # 주 소스가 나스닥이면 같은 소스 두 번이 되지 않게 다른 것을 묻는다.
    name2, _ = S._second("us_stock", "SPY", "nasdaq")
    assert name2 != "nasdaq"


def test_nasdaq_and_yahoo_agree_on_returns_despite_unadjusted_levels():
    """무조정가(나스닥)와 조정가(야후)는 수준이 달라도 일수익은 같다."""
    idx = pd.to_datetime(["2026-11-06", "2026-11-09", "2026-11-10", "2026-11-11", "2026-11-12"])
    a = pd.DataFrame({"close": [100, 101, 102, 101, 103.0]}, index=idx)
    b = pd.DataFrame({"close": [200, 202, 204, 202, 206.0]}, index=idx)
    assert S.compare_returns(a, b)["ok"] is True
