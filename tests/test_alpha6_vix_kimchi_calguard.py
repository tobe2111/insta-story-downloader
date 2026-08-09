"""알파 6차 계약 검사 — VIX·김치 프리미엄 피처 + 확률 보정 개입 준비.

핵심 계약:
  ① 미국·한국 주식에 x_vix(수준/100)가 붙는다 — ffill 정렬, 실패 시 생략
  ② 코인에 x_kimchi(업비트/바이낸스·환율 합성)가 붙고 손계산과 일치한다
  ③ 보정 가드: 표본 30건 이상 + 예측이 윌슨 CI 밖인 확률대만 '확정'되고,
     그 구간에서만 경험 보정값을 내놓는다(증거 없는 곳은 원래 확률 유지)
  ④ 보정값은 기록(prob_up_cal) 전용으로 배선된다 — 사이징 개입 없음
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.data import crossasset  # noqa: E402
from quant.data.crossasset import attach_cross_asset  # noqa: E402
from quant.live.calibration_guard import (  # noqa: E402
    MIN_INTERVENE_SAMPLES,
    calibration_table,
    recalibrated_prob,
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


# ── ① VIX ─────────────────────────────────────────────────────


def test_vix_attached_for_us_and_kr_as_level():
    def fetch(market, symbol, limit):
        if symbol == "^VIX":
            return _df(80, start="2026-05-20", base=20.0)   # VIX≈20~100
        return _df(80, start="2026-05-20")
    out = attach_cross_asset(_df(), "us_stock", "AAPL", fetch=fetch)
    assert "x_vix" in out.columns
    # 수준/100 스케일 — 마지막 값은 원지수/100
    assert 0.0 < float(out["x_vix"].iloc[-1]) < 1.5
    out_kr = attach_cross_asset(_df(), "kr_stock", "005930.KS", fetch=fetch)
    assert "x_vix" in out_kr.columns


def test_vix_failure_silently_skipped():
    def fetch(market, symbol, limit):
        if symbol == "^VIX":
            raise RuntimeError("VIX 조회 실패")
        return _df(80, start="2026-05-20")
    out = attach_cross_asset(_df(), "us_stock", "AAPL", fetch=fetch)
    assert "x_vix" not in out.columns
    assert "x_spy_ret5" in out.columns          # 다른 피처는 계속 붙는다


# ── ② 김치 프리미엄 ────────────────────────────────────────────


def test_kimchi_premium_matches_hand_math():
    """업비트 1억4천, 바이낸스 10만, 환율 1350 → 프리미엄 ≈ +3.7%."""
    def fetch(market, symbol, limit):
        if market == "upbit":
            return _df(60, base=140_000_000.0)
        if symbol == "BTC/USDT":
            return _df(60, base=100_000.0)
        if symbol == "KRW=X":
            return _df(60, base=1350.0)
        return _df(60)
    out = attach_cross_asset(_df(), "crypto", "BTC/USDT", fetch=fetch)
    assert "x_kimchi" in out.columns
    expect = 140_000_000.0 / (100_000.0 * 1350.0) - 1.0   # 첫 봉 기준 손계산
    assert abs(float(out["x_kimchi"].iloc[0]) - expect) < 1e-6


def test_kimchi_skipped_when_any_leg_fails():
    def fetch(market, symbol, limit):
        if market == "upbit":
            raise RuntimeError("업비트 죽음")
        return _df(60)
    out = attach_cross_asset(_df(), "crypto", "ETH/USDT", fetch=fetch)
    assert "x_kimchi" not in out.columns
    assert "x_btc_ret5" in out.columns          # 다리 하나 실패해도 나머지 유지


def test_ml_and_explain_cover_new_features():
    from quant.live.explain import FEATURE_KO, _feature_note
    from quant.strategies.ml import FEATURE_SET, _features
    assert int(FEATURE_SET.split(":")[0][2:]) >= 5   # 피처셋 세대(하위 호환 검사)
    df = _df(120)
    df["x_vix"] = 0.22
    df["x_kimchi"] = 0.05
    feats = _features(df)
    assert "x_vix" in feats.columns and "x_kimchi" in feats.columns
    assert "x_vix" in FEATURE_KO and "x_kimchi" in FEATURE_KO
    assert "공포" in _feature_note("x_vix", 0.35)        # 지수 35 → 공포 구간
    assert "과열" in _feature_note("x_kimchi", 0.05)     # +5% → 국내 매수 과열


# ── ③ 보정 가드 — 통계 확정 시에만 개입 ────────────────────────


def _history_exact(prob: float, ups: int, downs: int) -> list:
    """모델이 매일 prob이라 말했고 실제로 ups번 오르고 downs번 내린 가짜 장부."""
    out, price = [], 100.0
    moves = [1.01] * ups + [0.99] * downs
    for m in moves:
        out.append({"prob_up": prob, "price": price})
        price *= m
    out.append({"prob_up": None, "price": price})    # 마지막 짝 상대
    return out


def test_confirmed_bin_recalibrates_to_actual():
    # 모델은 늘 65%라 했지만 실제 상승은 40건 중 14건(35%) — CI 밖, 확정
    h = _history_exact(0.65, ups=14, downs=26)
    table = calibration_table([h])
    row = [r for r in table if r["lo"] <= 0.65 < r["hi"]][0]
    assert row["n"] >= MIN_INTERVENE_SAMPLES and row["confirmed"]
    adj, active = recalibrated_prob(0.65, [h])
    assert active and abs(adj - 0.35) < 0.01


def test_well_calibrated_bin_left_alone():
    # 65%라 했고 실제 63% — CI 안, 개입하지 않는다
    h = _history_exact(0.65, ups=25, downs=15)
    adj, active = recalibrated_prob(0.65, [h])
    assert not active and adj == 0.65


def test_small_sample_never_intervenes():
    # 표본 10건은 아무리 어긋나도 확정 아님 — 증거 부족
    h = _history_exact(0.70, ups=1, downs=9)
    adj, active = recalibrated_prob(0.70, [h])
    assert not active and adj == 0.70
    assert recalibrated_prob(None, [h]) == (None, False)


# ── ④ 배선 — 기록 전용, 사이징 비개입 ──────────────────────────


def test_wired_into_daily_record_only():
    dl = (ROOT / "quant" / "live" / "daily.py").read_text(encoding="utf-8")
    assert "prob_up_cal" in dl and "recalibrated_prob" in dl
    # 보정값이 비중 계산(size/target_weight)에 쓰이지 않는다 — 표시 전용 원칙
    seg = dl.split("recalibrated_prob")[0]
    assert "target_weight" in seg               # 매매는 보정 계산보다 앞(원확률)
