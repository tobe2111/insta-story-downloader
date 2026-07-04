"""데이터 품질 스캔 + 복수 소스 교차 검증 테스트 (합성 데이터, 결정론적)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.data.crosscheck import compare_sources
from quant.data.quality import is_severe, quality_report, scan_ohlcv


def _clean_df(n: int = 100) -> pd.DataFrame:
    """갭·스파이크·모순이 없는 깨끗한 일봉 OHLCV."""
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    close = pd.Series(100 + np.arange(n) * 0.1, index=idx)
    return pd.DataFrame({
        "open": close, "high": close + 1, "low": close - 1,
        "close": close, "volume": np.full(n, 1000.0),
    }, index=idx)


def test_scan_clean_data_has_no_findings():
    f = scan_ohlcv(_clean_df())
    assert all(v == 0 for v in f.values()), f
    assert not is_severe(f)


def test_scan_detects_gaps():
    df = _clean_df(60)
    df = df.drop(df.index[20:23])            # 3봉 누락
    f = scan_ohlcv(df)
    assert f["gaps"] == 3


def test_scan_detects_spike():
    df = _clean_df()
    df.iloc[50, df.columns.get_loc("close")] *= 1.5      # +50% 스파이크
    # high/low를 같이 넓혀 OHLC 모순은 만들지 않는다 — 스파이크만 검증
    df.iloc[50, df.columns.get_loc("high")] = df.iloc[50]["close"] + 1
    f = scan_ohlcv(df)
    assert f["spikes"] >= 1
    assert f["ohlc_violations"] == 0


def test_scan_detects_zero_volume_and_duplicates():
    df = _clean_df()
    df.iloc[10, df.columns.get_loc("volume")] = 0.0
    df = pd.concat([df, df.iloc[[5]]]).sort_index()      # 타임스탬프 중복
    f = scan_ohlcv(df)
    assert f["zero_volume"] == 1
    assert f["duplicate_index"] == 1
    assert is_severe(f)                       # 중복은 무결성 위반


def test_scan_detects_nonpositive_and_ohlc_violations():
    df = _clean_df()
    df.iloc[3, df.columns.get_loc("low")] = -1.0          # 음수 가격
    df.iloc[7, df.columns.get_loc("close")] = df.iloc[7]["high"] + 10  # 밴드 밖
    f = scan_ohlcv(df)
    assert f["nonpositive_price"] == 1
    assert f["ohlc_violations"] >= 1
    assert is_severe(f)


def test_scan_never_mutates_input():
    df = _clean_df()
    df.iloc[3, df.columns.get_loc("low")] = -1.0
    before = df.copy()
    scan_ohlcv(df)
    quality_report(df)
    pd.testing.assert_frame_equal(df, before)


def test_scan_empty_df_graceful():
    f = scan_ohlcv(pd.DataFrame())
    assert all(v == 0 for v in f.values())


def test_quality_report_korean_text():
    text = quality_report(_clean_df())
    assert "데이터 품질" in text and "스파이크" in text
    assert "보장" in text                     # 정직한 한계 고지
    df = _clean_df()
    df.iloc[3, df.columns.get_loc("low")] = -1.0
    assert "무결성 위반이 있습니다" in quality_report(df)


# ── 교차 검증 ────────────────────────────────────────────────────────────


def test_compare_sources_identical_ok():
    df = _clean_df()
    stats = compare_sources(df, df.copy())
    assert stats["ok"] is True
    assert stats["n_common"] == len(df)
    assert stats["max_rel_diff"] == 0.0
    assert stats["n_exceed"] == 0


def test_compare_sources_detects_adjustment_mismatch():
    """배당·분할 조정 차이(5% 스케일)를 tolerance 1%가 잡아낸다."""
    df = _clean_df()
    other = df.copy()
    other["close"] *= 1.05
    stats = compare_sources(df, other, tolerance=0.01)
    assert stats["ok"] is False
    assert stats["n_exceed"] == len(df)
    assert stats["max_rel_diff"] == pytest.approx(0.05, rel=1e-6)


def test_compare_sources_empty_overlap_graceful():
    a = _clean_df()
    b = _clean_df()
    b.index = b.index + pd.Timedelta(days=1000)           # 겹침 없음
    stats = compare_sources(a, b)
    assert stats["n_common"] == 0
    assert stats["ok"] is False                # '검증 못 함'은 '통과'가 아니다
    assert np.isnan(stats["max_rel_diff"])


def test_compare_sources_missing_column_graceful():
    a = _clean_df()
    stats = compare_sources(a, pd.DataFrame({"x": [1.0]}))
    assert stats["n_common"] == 0 and stats["ok"] is False
