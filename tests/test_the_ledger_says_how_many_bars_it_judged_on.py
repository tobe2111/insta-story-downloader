"""판단의 **표본이 몇 개였는지**를 장부가 말하는가 (감사 266).

장부는 마지막 봉이 얼마나 묵었는지(`bar_age_days`)와 얼마나 만들어졌는지
(`bar_partial`)는 매일 남긴다. 그런데 **몇 봉으로 판단했는지**는 남기지
않았다. 그래서 이런 일이 몇 주 동안 안 보였다.

    코인 5종목이 800봉을 요청하고 **300봉**을 받고 있었다.
    (주 거래소가 막혀 폴백한 거래소의 1회 응답 상한 — 감사 251)

장부에는 매일 "정상"이라고 적혔다. 그 사이에
  · 챔피언은 학습창 250봉을 **선발 구간 180봉**에서 겨루었고,
  · 그렇게 나온 과최적화 지표(BTC PBO 0.78)도 표본 부족의 산물이었고,
  · 코인 비중이 주식의 1/4로 눌린 것도 여기서 비롯됐다.

**받은 양을 안 적으면 덜 받은 것을 알 방법이 없다.** 페이지네이션은
고쳤지만(감사 251), 고친 것이 다시 풀렸을 때 알아차릴 방법은 여전히
없었다 — 같은 결함이 다음에 다른 제공처에서 나면 또 몇 주가 걸린다.

여기서 지키는 것:
  ① 요청보다 적게 받으면 **장부에 남는다**.
  ② 그 사실이 화면과 알림으로 **사람에게 닿는다**.
  ③ 정상인 날은 조용하다 — 매일 울리는 경보는 꺼진 경보다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live import daily as D  # noqa: E402

SRC = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")


def _frame(n: int) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    close = pd.Series(np.linspace(100.0, 130.0, n), index=idx)
    return pd.DataFrame({"open": close, "high": close * 1.01,
                         "low": close * 0.99, "close": close,
                         "volume": 1e6}, index=idx)


# ── ① 장부에 남는가 ─────────────────────────────────────────────

def test_the_record_carries_the_shortfall():
    assert '"bars_short": bars_short or None,' in SRC, (
        "몇 봉으로 판단했는지를 장부가 말하지 않는다 — 300봉짜리 결론과 "
        "800봉짜리 결론이 기록상 구별되지 않는다")


def test_a_shortfall_is_measured_against_what_was_asked_for():
    """'적다'는 절대 개수가 아니라 **요청 대비**로 판정해야 한다.

    종목마다 요청량이 다를 수 있고, 앞으로 lookback이 바뀌면 절대 문턱은
    그날부터 거짓말을 한다.
    """
    assert "int(lookback * BARS_SHORTFALL_RATIO)" in SRC, (
        "부족 판정이 요청량과 무관한 값에 걸려 있다")


def test_the_threshold_would_have_caught_the_real_incident():
    """문턱이 실제 사고를 잡는가 — 상수를 자기 자신과 비교하면 무의미하다.

    바깥에서 온 사실 둘로 가둔다: 실제 사고는 800 요청에 300 수신(37.5%)
    이었고, 거래소 점검으로 몇 봉 빠지는 정상 상황(≈99%)은 걸리면 안 된다.
    """
    assert 300 / 800 < D.BARS_SHORTFALL_RATIO, (
        f"문턱 {D.BARS_SHORTFALL_RATIO}가 실제 사고(800→300)를 놓친다")
    assert D.BARS_SHORTFALL_RATIO < 0.99, (
        "문턱이 너무 빡빡해 정상적인 결측 몇 봉에도 매일 울린다")


def test_a_full_delivery_leaves_the_ledger_quiet():
    """정상인 날에는 아무것도 남기지 않는다 — 장부가 소음이 되면 안 된다."""
    lookback = 800
    for got in (lookback, int(lookback * 0.95)):
        assert not (got < int(lookback * D.BARS_SHORTFALL_RATIO)), (
            f"{got}/{lookback}봉은 정상인데 부족으로 잡힌다")


def test_the_real_incident_is_flagged():
    lookback, got = 800, 300
    assert got < int(lookback * D.BARS_SHORTFALL_RATIO), (
        "800봉 요청에 300봉을 받아도 장부가 조용하다 — 이것이 감사 251이 "
        "몇 주 동안 안 보였던 이유다")


# ── ② 사람에게 닿는가 ───────────────────────────────────────────

def _flags(record: dict) -> dict:
    from quant.live.flag_watch import _current_flags
    return _current_flags({"paper": {"portfolio:ALL": {"history": [record]}}})


def test_a_shortfall_reaches_a_human():
    flags = _flags({"date": "2026-08-16", "bars_short": {
        "crypto:BTC/USDT": {"asked": 800, "got": 300},
        "crypto:ETH/USDT": {"asked": 800, "got": 300}}})
    hit = [v for k, v in flags.items() if k.startswith("bars_short")]
    assert hit, f"표본 부족이 알림으로 안 나간다: {sorted(flags)}"
    assert "300" in hit[0] and "800" in hit[0], (
        "몇 봉을 요청해 몇 봉을 받았는지 숫자가 안 나온다 — 사람이 심각도를 "
        "가늠할 수 없다")


def test_the_alert_names_the_worst_symbol_not_an_arbitrary_one():
    """예로 드는 종목은 **가장 심한 것**이어야 한다.

    아무거나 고르면 "1개 종목이 790/800봉"처럼 읽혀 심각도가 가려진다.
    """
    flags = _flags({"date": "2026-08-16", "bars_short": {
        "kr_stock:005930.KS": {"asked": 800, "got": 700},
        "crypto:BTC/USDT": {"asked": 800, "got": 300}}})
    msg = next(v for k, v in flags.items() if k.startswith("bars_short"))
    assert "BTC" in msg, f"가장 심한 종목이 아니라 다른 것을 예로 든다: {msg}"


def test_a_clean_day_stays_quiet():
    flags = _flags({"date": "2026-08-16", "bars_short": None})
    assert not [k for k in flags if k.startswith("bars_short")], (
        "아무 일도 없는 날에 표본 부족 경보가 울린다")


def test_it_reaches_the_front_page_too():
    index = (ROOT / "docs" / "index.html").read_text("utf-8")
    assert "bars_short" in index, (
        "표본 부족이 첫 화면 경고에 안 나온다 — 알림 채널이 막힌 날에는 "
        "아무도 모르게 된다")


# ── ③ 실제로 값으로 도는가 ─────────────────────────────────────

def test_the_shortfall_is_recorded_when_a_provider_gives_less(monkeypatch,
                                                              tmp_path):
    """가짜 제공처가 적게 주면 그 사실이 **기록에 실제로 남는가**.

    문자열 검사만으로는 '적어 두기만 하고 안 도는' 코드를 못 잡는다.
    """
    import json as _json

    short = _frame(300)

    class _P:
        def get_ohlcv(self, *a, **k):
            return short.copy()

    class _S:
        name = "fixed"
        allow_short = False

        def generate_signals(self, df):
            return pd.Series(0.5, index=df.index)

    monkeypatch.setattr(D, "usdkrw", lambda *a, **k: 1400.0)
    monkeypatch.setattr("quant.data.get_provider", lambda m: _P())
    monkeypatch.setattr(D, "champion_strategy", lambda *a, **k: _S())
    monkeypatch.setattr(D, "champion_spec",
                        lambda *a, **k: {"strategy": "fixed", "params": {}})

    D.run_daily_portfolio([("crypto", "BTC/USDT")], state_dir=str(tmp_path),
                          require_real_data=False, lookback=800)
    st = _json.loads((tmp_path / "paper" / "portfolio_ALL.json")
                     .read_text("utf-8"))
    rec = st["history"][-1]
    assert rec.get("bars_short"), (
        "800봉을 요청해 300봉을 받았는데 장부가 조용하다")
    got = rec["bars_short"]["crypto:BTC/USDT"]
    assert got == {"asked": 800, "got": 300}, got


def test_a_full_delivery_records_nothing(monkeypatch, tmp_path):
    """반대 방향도 값으로 확인한다 — 항상 켜지는 기록은 기록이 아니다."""
    import json as _json

    full = _frame(800)

    class _P:
        def get_ohlcv(self, *a, **k):
            return full.copy()

    class _S:
        name = "fixed"
        allow_short = False

        def generate_signals(self, df):
            return pd.Series(0.5, index=df.index)

    monkeypatch.setattr(D, "usdkrw", lambda *a, **k: 1400.0)
    monkeypatch.setattr("quant.data.get_provider", lambda m: _P())
    monkeypatch.setattr(D, "champion_strategy", lambda *a, **k: _S())
    monkeypatch.setattr(D, "champion_spec",
                        lambda *a, **k: {"strategy": "fixed", "params": {}})

    D.run_daily_portfolio([("crypto", "BTC/USDT")], state_dir=str(tmp_path),
                          require_real_data=False, lookback=800)
    st = _json.loads((tmp_path / "paper" / "portfolio_ALL.json")
                     .read_text("utf-8"))
    assert not st["history"][-1].get("bars_short"), (
        "요청한 만큼 다 받았는데도 부족으로 기록된다")


# ── 실제 저장소 상태에 대한 사실 확인 ───────────────────────────

def test_yesterdays_crypto_snapshots_show_the_incident_was_real():
    """이 감사가 가상의 걱정이 아니라는 것을 저장소 안의 값으로 고정한다.

    2026-08-15 스냅샷은 페이지네이션 수정 **이전** 코드가 남긴 것이고,
    코인 5종목이 전부 정확히 300봉이다. 이 검사가 미래에 실패한다면
    그건 좋은 소식이다(더 이상 300봉이 아니라는 뜻).
    """
    import gzip
    snap = ROOT / "state" / "snapshots" / "2026-08-15"
    files = sorted(snap.glob("crypto_*.csv.gz")) if snap.exists() else []
    if not files:
        pytest.skip("그날 스냅샷이 정리됐다 — 사실 고정은 여기까지")
    counts = {}
    for f in files:
        with gzip.open(f, "rt") as fh:
            counts[f.name] = sum(1 for _ in fh) - 1
    assert all(c == 300 for c in counts.values()), (
        f"전제가 달라졌다(좋은 신호일 수 있다): {counts}")
