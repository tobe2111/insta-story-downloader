"""데이터 품질 검사 배선 계약 — 매매하는 쪽이 검사받는가.

배경(2026-08-11 감사): scan_ohlcv(중복 봉·음수 가격·OHLC 모순·스파이크)는
**수동 backtest 명령에서만** 돌고 있었다. 정작 실제로 매매하고, 그 기록이
사이트와 방송과 SNS로 나가는 새벽 배치는 데이터를 한 번도 검사하지 않았다.
오염된 데이터 위의 기록은 그럴듯한 거짓말이 된다.

핵심 계약:
  ① 새벽 배치(통합 계좌·종목 계좌)가 무결성을 검사하고, 위반이면 기록하지 않는다
  ② 맥락 판단이 필요한 항목(갭·스파이크)은 장부에 남는다
  ③ 스파이크가 갑자기 늘면 경보한다(분할·배당 미조정 의심)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import quant.live.daily as dl  # noqa: E402
from quant.data.quality import is_severe, scan_ohlcv  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _clean(n=120, seed=1):
    rng = np.random.default_rng(seed)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.008, n))
    return pd.DataFrame(
        {"open": close, "high": close * 1.01, "low": close * 0.99,
         "close": close, "volume": np.full(n, 1e6)},
        index=pd.date_range("2026-01-01", periods=n, freq="D"))


# ── ① 무결성 위반은 기록을 막는다 ─────────────────────────────


def test_severe_findings_are_detected():
    df = _clean()
    assert not is_severe(scan_ohlcv(df))
    bad = df.copy()
    bad.iloc[5, bad.columns.get_loc("high")] = bad["low"].iloc[5] * 0.5  # high<low
    assert is_severe(scan_ohlcv(bad))
    dup = pd.concat([df, df.iloc[[10]]])
    assert is_severe(scan_ohlcv(dup))
    neg = df.copy()
    neg.iloc[7, neg.columns.get_loc("close")] = -1.0
    assert is_severe(scan_ohlcv(neg))


def test_daily_paper_refuses_corrupt_data(monkeypatch, tmp_path):
    bad = _clean()
    bad.iloc[5, bad.columns.get_loc("high")] = bad["low"].iloc[5] * 0.5

    class _P:
        def get_ohlcv(self, *a, **k):
            return bad

    monkeypatch.setattr("quant.data.get_provider", lambda m: _P())
    with pytest.raises(RuntimeError, match="무결성"):
        dl.run_daily_paper("synthetic", "DEMO", state_dir=str(tmp_path),
                           require_real_data=False)


def test_both_daily_paths_scan():
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert src.count("scan_ohlcv(df)") >= 2, "종목 계좌·통합 계좌 둘 다 검사해야"
    assert src.count("is_severe(") >= 2


# ── ② 맥락 항목은 장부에 남는다 ───────────────────────────────


def test_quality_is_recorded_in_the_ledger():
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert '"data_quality"' in src
    for k in ("gaps", "spikes", "zero_volume"):
        assert f'"{k}"' in src


# ── ③ 스파이크 급증 경보 ──────────────────────────────────────


def _spy(monkeypatch):
    sent = []

    class _S:
        def send(self, m, level="info"):
            sent.append(m)
            return True

    monkeypatch.setattr("quant.live.notifications.get_notifier", lambda: _S())
    return sent


def _hist(spikes_series):
    return {"paper": {"portfolio:ALL": {"history": [
        {"date": f"2026-08-{3 + i:02d}", "data_quality": {"spikes": s}}
        for i, s in enumerate(spikes_series)]}}}


def test_spike_surge_is_alerted(tmp_path, monkeypatch):
    from quant.live import flag_watch
    sent = _spy(monkeypatch)
    new = flag_watch.check_and_notify_flags(_hist([0, 0, 1, 12]), str(tmp_path))
    assert any(k.startswith("data_spikes:") for k in new)
    assert any("분할·배당 미조정" in m for m in sent)


def test_steady_spikes_stay_quiet(tmp_path, monkeypatch):
    """코인은 원래 ±20% 봉이 흔하다 — 평소 수준이면 조용해야 한다."""
    from quant.live import flag_watch
    _spy(monkeypatch)
    new = flag_watch.check_and_notify_flags(_hist([8, 9, 8, 9]), str(tmp_path))
    assert not any(k.startswith("data_spikes:") for k in new)


def test_no_spikes_no_alert(tmp_path, monkeypatch):
    from quant.live import flag_watch
    _spy(monkeypatch)
    new = flag_watch.check_and_notify_flags(_hist([0, 0, 0, 0]), str(tmp_path))
    assert not any(k.startswith("data_spikes:") for k in new)
