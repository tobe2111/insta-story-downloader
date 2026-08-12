"""시세를 **어디서 받았는지** 장부에 남는가 (감사 135).

주식 제공자는 야후가 흔들리면 조용히 보조 소스로 넘어간다.

    1) yfinance      — 1차. auto_adjust = **조정가**
    2) yahoo-http    — 보조. 무조정가
    3) stooq         — 보조. 무조정가

제공자는 성공한 소스를 `df.attrs["source"]`에 적고 있었다. 그런데
저장소 전체에서 **그 값을 읽는 곳이 한 곳도 없었다** — 기록만 하고
아무도 안 보는 계측기였다(FROZEN_IDEAS ⑲).

왜 중요한가. 무조정가는 배당락·액면분할 날 가격이 뚝 떨어진 것처럼
보인다. 그 하루짜리 가짜 점프가

    · 장부의 자산·수익률
    · ML 학습 라벨(다음 봉 방향)
    · 오디션의 성적표

에 그대로 들어간다. 그리고 사이트는 "누구든 검증할 수 있다"고 말하는데,
공개 차트와 대조하는 사람은 **왜 어긋나는지 알 길이 없다.**

이 검사는 소스를 장부에 남기게 하고, 1차가 아닌 것은 따로 뽑아 두게 한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.daily import PRIMARY_SOURCE, _source_fallbacks  # noqa: E402


# ── 폴백 판정 규칙 ────────────────────────────────────────────


def test_a_secondary_stock_source_is_flagged():
    got = _source_fallbacks({
        "us_stock:AAPL": "yfinance",
        "us_stock:MSFT": "stooq",
        "kr_stock:005930.KS": "yahoo-http",
    })
    assert got == {"us_stock:MSFT": "stooq",
                   "kr_stock:005930.KS": "yahoo-http"}, got


def test_the_primary_source_is_not_flagged():
    """대조군 — 정상까지 깃발이 서면 매일 경보가 울려 아무도 안 본다."""
    assert _source_fallbacks({"us_stock:AAPL": "yfinance"}) == {}


def test_crypto_exchange_ids_are_not_treated_as_fallbacks():
    """코인은 거래소 id가 곧 소스명이라 1차/보조 구분이 없다."""
    assert _source_fallbacks({"crypto:BTC/USDT": "binance",
                              "crypto:ETH/USDT": "upbit"}) == {}
    assert "crypto" not in PRIMARY_SOURCE


# ── 장부에 실제로 남는가 ──────────────────────────────────────


def _run(tmp_path):
    from quant.live.daily import run_daily_portfolio
    from quant.live.retrain import save_champions
    d = str(tmp_path)
    save_champions({f"synthetic:S{i}": {"strategy": "ma_cross",
                                        "params": {"fast": 10, "slow": 30},
                                        "promotions": 0} for i in range(3)}, d)
    return run_daily_portfolio([("synthetic", f"S{i}") for i in range(3)],
                               lookback=200, state_dir=d,
                               require_real_data=False)


def test_the_portfolio_ledger_records_where_each_price_came_from(tmp_path):
    rec = _run(tmp_path)
    src = rec.get("data_source")
    assert src, "시세 소스가 장부에 없다 — 어디서 받았는지 아무도 모른다"
    assert set(src) == {f"synthetic:S{i}" for i in range(3)}, src
    assert all(isinstance(v, str) and v for v in src.values()), src


def test_the_per_symbol_ledger_records_it_too(tmp_path):
    """같은 규칙을 두 경로에 — 한쪽만 고치면 반드시 어긋난다(FROZEN_IDEAS ①)."""
    from quant.live.daily import run_daily_paper
    from quant.live.retrain import save_champions
    d = str(tmp_path)
    save_champions({"synthetic:DEMO": {"strategy": "ma_cross",
                                       "params": {"fast": 10, "slow": 30},
                                       "promotions": 0}}, d)
    rec = run_daily_paper("synthetic", "DEMO", lookback=200, state_dir=d,
                          require_real_data=False)
    assert rec.get("data_source"), "종목별 장부에 시세 소스가 없다"


def test_a_clean_day_leaves_no_fallback_flag(tmp_path):
    """폴백이 없으면 깃발도 없어야 한다 — 매일 서는 깃발은 아무도 안 본다."""
    assert _run(tmp_path).get("data_source_fallback") is None


def test_the_provider_actually_sets_the_attribute():
    """전제 고정 — 제공자가 소스를 안 적기 시작하면 위 기록이 '?'로 썩는다."""
    from quant.data.synthetic import SyntheticDataProvider
    df = SyntheticDataProvider(seed=3).get_ohlcv("X", "1d", limit=60)
    assert hasattr(df, "attrs")
    src = (ROOT / "quant" / "data" / "stock.py").read_text("utf-8")
    assert 'out.attrs["source"] = name' in src, (
        "주식 제공자가 소스를 안 남긴다 — 폴백을 구분할 수 없다")
