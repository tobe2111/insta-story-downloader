"""알파 9차 계약 검사 — VIX 기간구조 피처 + 실적 캘린더 가드.

핵심 계약:
  ① x_vix_ts = VIX/VIX3M — 손계산 일치, VIX3M 실패 시 x_vix만 남는다
  ② 실적 캘린더: 캐시(state/earnings.json)에 남고 신선하면 재조회 없음
  ③ 가드: 발표 ±1일 창에서만 (0.5, 날짜), 밖이면 (1.0, None), 실패 무해
  ④ 페이퍼·포트폴리오 두 경로에 배선 + 기록 필드(earnings_guard) + 사유 문구
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.data import crossasset  # noqa: E402
from quant.data.crossasset import attach_cross_asset  # noqa: E402
from quant.data.earnings import (  # noqa: E402
    earnings_guard_factor,
    next_earnings_date,
)

ROOT = Path(__file__).resolve().parent.parent


def _df(n: int = 60, start: str = "2026-06-01", base: float = 100.0) -> pd.DataFrame:
    idx = pd.date_range(start, periods=n, freq="D")
    v = base + np.arange(n, dtype=float)
    return pd.DataFrame({"open": v, "high": v + 1, "low": v - 1,
                         "close": v, "volume": 1000.0}, index=idx)


def setup_function(_):
    import os
    crossasset._MEMO.clear()
    os.environ.pop("FRED_API_KEY", None)


# ── ① VIX 기간구조 ─────────────────────────────────────────────


def test_vix_ts_hand_math_and_partial_failure():
    def fetch(market, symbol, limit):
        if symbol == "^VIX":
            return _df(60, base=30.0)          # 첫 봉 30
        if symbol == "^VIX3M":
            return _df(60, base=24.0)          # 첫 봉 24 → 비율 1.25(백워데이션)
        return _df(60)
    out = attach_cross_asset(_df(), "us_stock", "AAPL", fetch=fetch)
    assert "x_vix_ts" in out.columns
    assert abs(float(out["x_vix_ts"].iloc[0]) - 30.0 / 24.0) < 1e-9

    crossasset._MEMO.clear()

    def fetch2(market, symbol, limit):
        if symbol == "^VIX3M":
            raise RuntimeError("VIX3M 없음")
        return _df(60, base=20.0)
    out2 = attach_cross_asset(_df(), "kr_stock", "005930.KS", fetch=fetch2)
    assert "x_vix" in out2.columns and "x_vix_ts" not in out2.columns

    from quant.live.explain import FEATURE_KO, _feature_note
    assert "x_vix_ts" in FEATURE_KO
    assert "백워데이션" in _feature_note("x_vix_ts", 1.15)
    assert "콘탱고" in _feature_note("x_vix_ts", 0.80)

    from quant.strategies.ml import FEATURE_SET
    assert int(FEATURE_SET.split(":")[0][2:]) >= 6


# ── ② 캘린더 캐시 ──────────────────────────────────────────────


def test_earnings_cache_written_and_reused(tmp_path):
    calls = []

    def fetch(symbol):
        calls.append(symbol)
        return ["2026-08-20", "2026-11-19"]

    today = dt.date(2026, 8, 9)
    d = next_earnings_date("AAPL", today, state_dir=str(tmp_path), fetch=fetch)
    assert d == dt.date(2026, 8, 20)
    cache = json.loads((tmp_path / "earnings.json").read_text())
    assert cache["AAPL"]["dates"] == ["2026-08-20", "2026-11-19"]
    # 신선한 캐시 → 재조회 없음
    next_earnings_date("AAPL", today, state_dir=str(tmp_path), fetch=fetch)
    assert calls == ["AAPL"]


def test_earnings_fetch_failure_is_harmless(tmp_path):
    def boom(symbol):
        raise RuntimeError("야후 죽음")
    assert next_earnings_date("AAPL", dt.date(2026, 8, 9),
                              state_dir=str(tmp_path), fetch=boom) is None
    f, d = earnings_guard_factor("AAPL", dt.date(2026, 8, 9),
                                 state_dir=str(tmp_path), fetch=boom)
    assert f == 1.0 and d is None


# ── ③ 가드 창 ──────────────────────────────────────────────────


def test_guard_only_inside_window(tmp_path):
    fetch = lambda s: ["2026-08-20"]  # noqa: E731
    inside = earnings_guard_factor("AAPL", dt.date(2026, 8, 19),
                                   state_dir=str(tmp_path), fetch=fetch)
    assert inside == (0.5, "2026-08-20")
    on_day = earnings_guard_factor("AAPL", dt.date(2026, 8, 20),
                                   state_dir=str(tmp_path), fetch=fetch)
    assert on_day == (0.5, "2026-08-20")
    outside = earnings_guard_factor("AAPL", dt.date(2026, 8, 15),
                                    state_dir=str(tmp_path), fetch=fetch)
    assert outside == (1.0, None)


# ── ④ 배선 ─────────────────────────────────────────────────────


def test_guard_wired_into_both_paths_and_recorded():
    dl = (ROOT / "quant" / "live" / "daily.py").read_text(encoding="utf-8")
    assert dl.count("earnings_guard_factor") >= 2    # 페이퍼·포트폴리오 두 경로
    assert '"earnings_guard"' in dl
    assert "실적 가드" in dl                          # 사유 문구
