"""미완결·유령 일봉 차단 계약 검사 — 2026-08-07 한국 주식 중복 기록의 재발 방지.

야후는 거래소 현지 자정이 지나면 아직 열리지 않은 세션의 봉을 미리 내놓는다.
그 봉이 살아 있으면 asof가 하루 앞서 이동해 멱등 가드가 깨지고(재시도 크론이
같은 날 두 번 학습·기록), 값이 계속 변해 재현성 해시도 흔들린다.

핵심 계약:
  ① 장 마감 전의 '오늘' 봉과 미래 날짜 봉은 버린다
  ② 마감 후의 '오늘' 봉과 과거 봉은 그대로 둔다
  ③ 인트라데이 데이터·스케줄 없는 시장은 건드리지 않는다
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.data.stock import StockDataProvider  # noqa: E402


def _daily(last_day: str, n: int = 5) -> pd.DataFrame:
    idx = pd.date_range(end=last_day, periods=n, freq="D")
    v = 100.0 + np.arange(n)
    return pd.DataFrame({"open": v, "high": v + 1, "low": v - 1,
                         "close": v, "volume": 1000.0}, index=idx)


# 기준 시각: 2026-08-06 22:00 UTC = 한국 8/7 07:00(개장 전) · 미국 8/6 18:00(마감 후)
NOW = datetime(2026, 8, 6, 22, 0, tzinfo=timezone.utc)


def test_kr_phantom_tomorrow_bar_dropped():
    """한국 개장 전(07:00 KST)에 나타난 8/7 유령 봉은 버려진다."""
    p = StockDataProvider("kr_stock")
    out = p._drop_unclosed(_daily("2026-08-07"), now=NOW)
    assert str(out.index[-1])[:10] == "2026-08-06"      # 마지막 완결 세션까지만


def test_us_closed_today_bar_kept():
    """미국은 마감 후(18:00 ET 아님 — 18:00 현지)라 8/6 봉이 유지된다."""
    p = StockDataProvider("us_stock")
    out = p._drop_unclosed(_daily("2026-08-06"), now=NOW)
    assert str(out.index[-1])[:10] == "2026-08-06"


def test_us_preclose_today_bar_dropped():
    """미국 장중(마감 전)에는 '오늘' 봉이 미완결이라 버려진다."""
    p = StockDataProvider("us_stock")
    mid = datetime(2026, 8, 6, 15, 0, tzinfo=timezone.utc)  # 11:00 ET 장중
    out = p._drop_unclosed(_daily("2026-08-06"), now=mid)
    assert str(out.index[-1])[:10] == "2026-08-05"


def test_far_future_bars_all_dropped():
    """미래 날짜 봉이 여러 개여도 전부 버려진다(루프)."""
    p = StockDataProvider("kr_stock")
    out = p._drop_unclosed(_daily("2026-08-09"), now=NOW)
    assert str(out.index[-1])[:10] == "2026-08-06"


def test_intraday_untouched():
    """인트라데이(시간봉)는 건드리지 않는다."""
    idx = pd.date_range("2026-08-07 01:00", periods=5, freq="h")
    df = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0,
                       "close": 1.0, "volume": 1.0}, index=idx)
    p = StockDataProvider("kr_stock")
    assert len(p._drop_unclosed(df, now=NOW)) == 5


def test_unknown_market_untouched():
    p = StockDataProvider("synthetic")
    assert len(p._drop_unclosed(_daily("2026-08-09"), now=NOW)) == 5


def test_paper_histories_have_no_duplicate_dates():
    """실제 장부(state/paper)의 일별 기록에 같은 날짜가 두 번 없다."""
    import glob
    import json
    from collections import Counter
    for path in glob.glob(str(Path(__file__).resolve().parent.parent
                              / "state" / "paper" / "*.json")):
        d = json.load(open(path, encoding="utf-8"))
        dates = Counter(r.get("date") for r in d.get("history", []))
        dup = {k: v for k, v in dates.items() if v > 1}
        assert not dup, (path, dup)
