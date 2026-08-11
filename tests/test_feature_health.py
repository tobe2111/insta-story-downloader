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

_ALL_SOURCES = {
    "funding": 0.0001, "oi": 1e6,
    "x_btc": 0.5, "x_spy": 0.5, "x_tnx": 0.5, "x_usdkrw": 0.5, "x_vixts": 0.5,
    "x_fred_dgs10": 0.5, "x_fred_t10y2y": 0.5, "x_fred_bamlh0a0hym2": 0.5,
}


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
