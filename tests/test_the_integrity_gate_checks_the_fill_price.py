"""무결성 관문이 **체결에 쓰는 값**을 보는가 (감사 161).

`scan_ohlcv` + `is_severe`는 페이퍼·포트폴리오 배치 양쪽의 **입구 관문**이다.
데이터가 깨졌으면 그날 매매를 멈추라고 세워 둔 문이다.

그런데 OHLC 밴드 검사가 **close만** 보고 있었다.

    bad = (high < low) | (close > high) | (close < low)
                          ^^^^^           ^^^^^      open이 없다

이 시스템은 주식 체결을 **다음 봉 시가**로 한다 — `_first_bar_after`가
`float(r["open"])`을 그대로 체결가로 쓴다. 즉 관문이 **체결에 쓰는 바로
그 값**을 안 보고 있었다.

실측(밴드 99~101인 봉):

    시가만 5000으로  →  모순 0건 · is_severe False   관문 통과
    종가만 5000으로  →  모순 1건 · is_severe True    막힘

같은 크기로 망가뜨렸는데 한쪽만 잡힌다. 통과하면 그 5000이 그대로 체결가가
되고 장부에 남는다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.data.quality import (  # noqa: E402
    SEVERE_KEYS,
    is_severe,
    quality_report,
    scan_ohlcv,
)

IDX = pd.date_range("2025-01-01", periods=5, freq="D")


def _clean() -> pd.DataFrame:
    return pd.DataFrame({"open": [100.0] * 5, "high": [101.0] * 5,
                         "low": [99.0] * 5, "close": [100.0] * 5,
                         "volume": [1e6] * 5}, index=IDX)


def _broken(col: str, value: float) -> pd.DataFrame:
    df = _clean()
    df.loc[IDX[2], col] = value
    return df


# ── 체결에 쓰는 값이 검사되는가 ───────────────────────────────


@pytest.mark.parametrize("col", ["open", "close"])
def test_a_price_outside_the_band_is_an_integrity_violation(col):
    f = scan_ohlcv(_broken(col, 5000.0))
    assert f["ohlc_violations"] == 1, (
        f"{col}가 밴드(99~101) 밖 5000인데 모순 {f['ohlc_violations']}건 — "
        "관문을 그대로 통과한다")
    assert is_severe(f), f"{col} 오염이 무결성 위반으로 안 잡힌다"


@pytest.mark.parametrize("col", ["open", "close"])
def test_a_price_below_the_band_is_caught_too(col):
    """위로만 검사하고 아래를 빠뜨리는 것도 같은 병이다."""
    f = scan_ohlcv(_broken(col, 1.0))
    assert f["ohlc_violations"] == 1 and is_severe(f), (col, f)


def test_high_below_low_is_still_caught():
    df = _clean()
    df.loc[IDX[1], "high"] = 90.0            # high < low
    assert is_severe(scan_ohlcv(df))


def test_a_clean_frame_passes():
    """대조군 — 정상 데이터를 막으면 그날 매매가 통째로 멈춘다."""
    f = scan_ohlcv(_clean())
    assert f["ohlc_violations"] == 0 and not is_severe(f), f


def test_a_frame_without_open_still_works():
    """open 컬럼이 없는 소스도 있다 — 없다고 터지면 안 된다."""
    f = scan_ohlcv(_clean().drop(columns=["open"]))
    assert f["ohlc_violations"] == 0 and not is_severe(f)


# ── 관문이 실제로 무엇을 막는가 ───────────────────────────────


def test_the_gate_is_wired_to_both_batches():
    """부품이 아니라 배선을 본다 — is_severe가 두 배치의 입구에 있는가."""
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert src.count("is_severe(") >= 2, (
        "페이퍼·포트폴리오 두 경로 모두에서 무결성 관문을 지나야 한다")


def test_the_fill_price_comes_from_open():
    """전제 고정 — 체결이 시가에서 오지 않게 되면 이 감사의 근거가 바뀐다."""
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert 'float(r["open"])' in src, (
        "주식 체결이 더 이상 시가를 쓰지 않는다 — 그러면 무엇을 검사해야 하는지 "
        "다시 판단할 것")


def test_the_report_names_both_prices():
    """사람이 읽는 줄에도 무엇을 봤는지 적혀 있어야 한다."""
    text = quality_report(_clean())
    assert "시가" in text and "종가" in text, text


def test_severe_keys_are_the_integrity_ones():
    """갭·스파이크는 정상 시장에서도 난다 — 그것으로 매매를 막으면 안 된다."""
    assert set(SEVERE_KEYS) == {"duplicate_index", "nonpositive_price",
                                "ohlc_violations"}
    df = _clean()
    df.loc[IDX[3], "close"] = 200.0          # 스파이크 + 밴드 위반
    f = scan_ohlcv(df)
    assert f["spikes"] > 0
    # 스파이크만 있는 경우(밴드 안에서의 큰 등락)는 막지 않는다
    calm = pd.DataFrame({"open": [100.0, 130.0], "high": [100.0, 130.0],
                         "low": [100.0, 130.0], "close": [100.0, 130.0],
                         "volume": [1e6, 1e6]}, index=IDX[:2])
    g = scan_ohlcv(calm)
    assert g["spikes"] == 1 and not is_severe(g), (
        "정상적인 급등(+30%)으로 매매를 멈추면 안 된다")
