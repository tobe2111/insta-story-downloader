"""피처 건강 계약 검사 — 조용히 줄어드는 피처를 잡는다.

배경(2026-08-11 발견): 외부 소스(야후·바이낸스·FRED·KRX)가 죽으면 선택
피처가 통째로 빠지는데(28개 → 17개), 장부에는 여전히 같은 fs8 태그로
기록된다. 그러면 판정 시계 90일이 '매일 다른 구조'를 재게 되고, 재현성
검증도 그날의 데이터 가용성을 재현하지 못한다.

핵심 계약:
  ① 예측기(optional_features_from_df)가 실제 피처 빌더와 정확히 일치한다
  ② 필수 피처는 외부 소스와 무관하게 항상 만들어진다
  ③ 통째로 빠진 피처는 경보한다(한 종목만 없는 것은 시장 차이라 조용)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.strategies.ml import (  # noqa: E402
    FEATURE_NAMES,
    OPTIONAL_FEATURES,
    _features,
    feature_health,
    optional_features_from_df,
)

ROOT = Path(__file__).resolve().parent.parent

# ⚠️ 목록에서 **파생**한다. 예전에는 여기에 이름을 손으로 적었는데, 그
#    이름들이 실제로는 만들어지지 않는 유령이었다(감사 106) — 픽스처가
#    목록과 같은 거짓말을 하고 있어서 검사가 초록인 채로 계측기가 매일
#    "선택 피처 0/11"을 기록했다. 이제 목록이 바뀌면 픽스처도 따라간다.
_DERIVED = {"x_funding", "x_funding_chg", "x_oi_chg5"}   # 원본 컬럼에서 파생
_ALL_SOURCES = {"funding": 0.0001, "oi": 1e6}
_ALL_SOURCES.update({c: 0.5 for c in OPTIONAL_FEATURES if c not in _DERIVED})


def _df(extra=None):
    from quant.data.synthetic import SyntheticDataProvider
    d = SyntheticDataProvider().get_ohlcv("DEMO", "1d", limit=200)
    for k, v in (extra or {}).items():
        d[k] = v
    return d


# ── ① 예측기와 실제의 일치 ─────────────────────────────────────


def test_predictor_matches_actual_feature_builder():
    """싼 예측기가 실제 빌더와 어긋나면 건강 기록 자체가 거짓이 된다."""
    for extra in ({}, {"funding": 0.0001, "oi": 1e6}, _ALL_SOURCES):
        d = _df(extra)
        predicted = set(optional_features_from_df(d))
        actual = {c for c in _features(d).columns if c in OPTIONAL_FEATURES}
        assert predicted == actual, f"불일치: {predicted ^ actual}"


def test_all_sources_present_yields_every_optional_feature():
    d = _df(_ALL_SOURCES)
    assert set(optional_features_from_df(d)) == set(OPTIONAL_FEATURES)


# ── ② 필수 피처는 항상 ─────────────────────────────────────────


def test_required_features_survive_source_outage():
    """외부 소스가 전부 죽어도 가격 유도 피처는 남아야 한다."""
    h = feature_health(_features(_df()))
    assert h["missing_required"] == []
    assert h["required"] == h["required_expected"] == len(FEATURE_NAMES)
    assert h["optional"] == 0          # 소스가 없으니 선택 피처는 0


def test_feature_count_gap_is_real_and_measurable():
    """소스 유무로 실제 피처 수가 달라진다 — 이 격차가 기록되어야 한다."""
    few = len(_features(_df()).columns)
    many = len(_features(_df(_ALL_SOURCES)).columns)
    assert many - few == len(OPTIONAL_FEATURES)
    assert few == len(FEATURE_NAMES)


# ── ③ 배선·경보 ────────────────────────────────────────────────


def test_wired_into_daily_record():
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert "optional_features_from_df" in src
    assert '"feature_health"' in src
    assert "missing_everywhere" in src


def test_flag_watch_alerts_on_total_outage(tmp_path, monkeypatch):
    from quant.live import flag_watch

    class _Spy:
        def __init__(self): self.sent = []
        def send(self, m): self.sent.append(m)

    spy = _Spy()
    monkeypatch.setattr("quant.live.notifications.get_notifier", lambda: spy)
    st = {"paper": {"portfolio:ALL": {"history": [{
        "date": "2026-08-11",
        "feature_health": {"optional_max": 0, "optional_possible": 11,
                           "union": 0,
                           "missing_everywhere": ["x_btc", "x_spy"],
                           "thinnest": {"key": "us_stock:SPY", "n": 0}}}]}}}
    new = flag_watch.check_and_notify_flags(st, str(tmp_path))
    assert any(k.startswith("features_missing:") for k in new)
    assert any("피처 유실" in m for m in spy.sent)


def test_no_alert_when_features_are_complete(tmp_path, monkeypatch):
    from quant.live import flag_watch

    class _Spy:
        def __init__(self): self.sent = []
        def send(self, m): self.sent.append(m)

    monkeypatch.setattr("quant.live.notifications.get_notifier", lambda: _Spy())
    st = {"paper": {"portfolio:ALL": {"history": [{
        "date": "2026-08-11",
        "feature_health": {"optional_max": 11, "optional_possible": 11,
                           "union": 11, "missing_everywhere": [],
                           "thinnest": {"key": "crypto:BTC/USDT", "n": 3}}}]}}}
    new = flag_watch.check_and_notify_flags(st, str(tmp_path))
    assert not any(k.startswith("features_missing:") for k in new)


# ── ④ 시장별 기대치 — 계측의 '분모'가 실제와 같은가 ────────────

"""배경(2026-08-14 발견): 계측기가 어느 종목이든 선택 피처 **전체**를
기대치로 삼았다. 그런데 코인에 KRX 수급(x_frgn5)이, 한국주식에 펀딩비
(x_funding)가 붙을 리 없다. 모든 소스가 살아 있어도 한 종목이 받을 수
있는 최대는 9개라, 사이트의 '피처 결손' 경고(분모의 절반 미만이면 점등)는
**정상 상태에서도 켜져 있었다.** 항상 켜진 경고등은 꺼진 것과 같다.

아래 검사는 MARKET_OPTIONAL_FEATURES 표를 **실제 부착 함수를 돌려서**
대조한다. 손으로 적은 목록이 실제와 어긋나 계측기가 유령을 세던 사고가
이미 있었다(감사 106) — 표만 고치고 코드를 안 고치면 여기서 실패한다.
네트워크는 쓰지 않는다: 네 부착 함수 모두 fetch 주입을 받는다.
"""

_UNIVERSE = [("crypto", "BTC/USDT"), ("crypto", "ETH/USDT"),
             ("us_stock", "SPY"), ("us_stock", "AAPL"),
             ("kr_stock", "005930.KS")]


def _all_sources_alive(monkeypatch, dates):
    """크로스에셋의 모든 외부 소스가 성공하는 세계를 만든다(네트워크 없음)."""
    import pandas as pd
    from quant.data import crossasset as ca

    series = pd.Series(range(1, len(dates) + 1), index=dates, dtype=float)
    monkeypatch.setattr(ca, "_MEMO", {})
    monkeypatch.setattr(ca, "_bench_close",
                        lambda *a, **k: series.copy())
    monkeypatch.setattr(ca, "_fng_series", lambda **k: series.copy())
    monkeypatch.setattr(ca, "_kimchi_series", lambda **k: series.copy())
    monkeypatch.setattr(ca, "_fred", lambda s: series.copy())
    monkeypatch.setattr(ca, "_fred_t10y2y", lambda: series.copy())
    return series


def _attach_everything(monkeypatch, market, symbol):
    """실전(daily.py)과 같은 순서로 모든 부착 함수를 돌린 df를 만든다."""
    import pandas as pd
    from quant.data.crossasset import attach_cross_asset

    d = _df()
    dates = pd.DatetimeIndex(d.index).normalize()
    s = _all_sources_alive(monkeypatch, dates)
    if market == "crypto":
        from quant.data.funding import attach_funding
        from quant.data.openinterest import attach_open_interest
        d = attach_funding(d, symbol,
                           fetch=lambda _s: pd.Series(1e-4, index=dates))
        d = attach_open_interest(d, symbol,
                                 fetch=lambda _s: pd.Series(1e6, index=dates))
    if market == "kr_stock":
        from quant.data.krx import attach_krx_flows
        flows = pd.DataFrame({"frgn": s.to_numpy(), "inst": s.to_numpy()[::-1]},
                             index=dates)
        d = attach_krx_flows(d, symbol, fetch=lambda _s: flows)
    return attach_cross_asset(d, market, symbol)


def test_market_table_matches_what_the_attachers_actually_build(monkeypatch):
    """표에 적힌 이름 = 모든 소스가 살아 있을 때 실제로 만들어지는 피처."""
    from quant.strategies.ml import applicable_optional_features

    for market, symbol in _UNIVERSE:
        d = _attach_everything(monkeypatch, market, symbol)
        actual = {c for c in _features(d).columns if c in OPTIONAL_FEATURES}
        table = set(applicable_optional_features(market, symbol))
        assert table == actual, (
            f"{market}:{symbol} 표와 실제가 다르다 — "
            f"표에만: {sorted(table - actual)} · 실제에만: {sorted(actual - table)}")


def test_a_fully_healthy_symbol_scores_a_perfect_meter(monkeypatch):
    """모든 소스가 살아 있으면 충족률 100% — 이게 안 되면 경고등이 항상 켜진다."""
    from quant.strategies.ml import feature_health

    for market, symbol in _UNIVERSE:
        d = _attach_everything(monkeypatch, market, symbol)
        h = feature_health(_features(d), market, symbol)
        assert h["coverage"] == 1.0, (
            f"{market}:{symbol} 전부 붙었는데 충족률이 {h['coverage']:.0%}다 — "
            f"누락으로 센 것: {h['missing_optional']}")
        assert h["missing_optional"] == []
        assert h["unexpected_optional"] == [], (
            f"표에 없는 피처가 붙었다: {h['unexpected_optional']}")


def test_the_old_denominator_was_unreachable_for_every_market():
    """분모가 왜 틀렸는지를 못으로 박는다 — 17은 어느 시장도 도달 못 한다."""
    from quant.strategies.ml import applicable_optional_features

    for market, symbol in _UNIVERSE:
        n = len(applicable_optional_features(market, symbol))
        assert n < len(OPTIONAL_FEATURES), (
            f"{market}:{symbol}의 기대치가 전체 목록과 같다 — 분모가 안 좁혀졌다")
    # 시장별로 실제로 다르다(같으면 표가 시장을 구분하지 않는 것)
    counts = {m: len(applicable_optional_features(m, s)) for m, s in _UNIVERSE}
    assert len(set(counts.values())) > 1, f"시장별 기대치가 전부 같다: {counts}"


def test_unknown_market_does_not_score_a_free_perfect(monkeypatch):
    """모르는 시장에 분모 0을 주면 '완벽한 건강'으로 위장된다 — 그걸 막는다."""
    from quant.strategies.ml import applicable_optional_features, feature_health

    assert applicable_optional_features("mars_stock", "X") == OPTIONAL_FEATURES
    h = feature_health(_features(_df()), "mars_stock", "X")
    assert h["optional_expected"] == len(OPTIONAL_FEATURES)
    assert h["coverage"] == 0.0


def test_aggregate_denominator_follows_the_universe():
    """유니버스에 없는 시장의 피처는 '전 종목 누락'이 아니다."""
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert "applicable_optional_features" in src, (
        "집계가 아직 전체 목록을 분모로 쓴다 — 코인만 도는 날 x_frgn5가 "
        "누락으로 잡혀 경보가 상시 점등된다")
    assert '"coverage"' in src
