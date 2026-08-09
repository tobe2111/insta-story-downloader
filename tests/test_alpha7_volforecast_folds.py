"""알파 7차 계약 검사 — HAR-RV 변동성 예측 사이징 + 오디션 폴드 일관성 게이트.

핵심 계약:
  ① HAR 예측은 워크포워드다 — 미래 수익을 바꿔도 과거 시점의 예측이 안 변한다
  ② 변동성 국면이 높으면 예측도 높다(군집 포착) · 퇴화 입력은 NaN/0 노출
  ③ RiskManager vol_model="har"는 예측·실현의 50/50 수축, 폴백 안전
  ④ 라이브 사이징(_risk_for)이 har를 쓴다
  ⑤ 선발전 평가에 fold_wins가 붙고, 과반 미달은 선발 탈락(게이트)
  ⑥ 장부에 select_folds가 남고 verify는 장부 값으로 재현한다(옛 기록=0)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.risk.manager import RiskConfig, RiskManager  # noqa: E402
from quant.risk.volforecast import har_forecast_vol  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _returns(n: int = 400, seed: int = 7) -> pd.Series:
    rng = np.random.default_rng(seed)
    # 앞 절반 저변동(σ=1%) → 뒤 절반 고변동(σ=4%)
    r = np.concatenate([rng.normal(0, 0.01, n // 2),
                        rng.normal(0, 0.04, n - n // 2)])
    return pd.Series(r, index=pd.date_range("2025-01-01", periods=n, freq="D"))


def _df_from_returns(r: pd.Series) -> pd.DataFrame:
    close = 100.0 * (1 + r).cumprod()
    return pd.DataFrame({"open": close, "high": close * 1.01,
                         "low": close * 0.99, "close": close,
                         "volume": 1000.0}, index=r.index)


# ── ① 룩어헤드 없음 ────────────────────────────────────────────


def test_har_forecast_is_walk_forward():
    r = _returns()
    f1 = har_forecast_vol(r)
    r2 = r.copy()
    r2.iloc[-50:] = 0.20                      # 미래 50봉을 극단값으로 교체
    f2 = har_forecast_vol(r2)
    cut = len(r) - 50
    a, b = f1.iloc[:cut], f2.iloc[:cut]
    assert ((a == b) | (a.isna() & b.isna())).all()   # 과거 예측 불변


# ── ② 군집 포착 + 퇴화 안전 ────────────────────────────────────


def test_har_tracks_vol_regime_and_degenerate_is_nan():
    r = _returns()
    f = har_forecast_vol(r)
    lo = f.iloc[150:200].mean()               # 저변동 국면(적합 이후)
    hi = f.iloc[-50:].mean()                  # 고변동 국면
    assert np.isfinite(lo) and np.isfinite(hi) and hi > lo * 1.5
    assert f.iloc[:50].isna().all()           # 초기 표본 부족 구간은 '모름'
    flat = pd.Series(0.0, index=r.index)      # 거래정지(수익률 0) — 예측 불가
    assert har_forecast_vol(flat).dropna().le(1e-12).all() or \
        har_forecast_vol(flat).isna().all()


# ── ③④ 사이징 통합 ────────────────────────────────────────────


def test_risk_manager_har_blend_and_fallback():
    r = _returns()
    df = _df_from_returns(r)
    target = pd.Series(1.0, index=df.index)
    base = RiskManager(RiskConfig(periods_per_year=365)) \
        .size_positions(df, target)
    har = RiskManager(RiskConfig(periods_per_year=365, vol_model="har")) \
        .size_positions(df, target)
    assert np.isfinite(har).all() and (har.abs() <= 1.0).all()
    # 고변동 국면에서 둘 다 노출을 줄인다(방향 동일) — har도 정상 동작
    assert har.iloc[-30:].mean() < har.iloc[150:200].mean()
    # 예측 불가 구간(초기)은 실현변동성 폴백 = 기존과 동일
    assert ((har.iloc[:40] == base.iloc[:40])
            | (har.iloc[:40].isna() & base.iloc[:40].isna())).all()


def test_live_sizing_uses_har():
    dl = (ROOT / "quant" / "live" / "daily.py").read_text(encoding="utf-8")
    assert 'vol_model="har"' in dl


# ── ⑤ 폴드 일관성 게이트 ───────────────────────────────────────


def test_evaluate_reports_fold_wins():
    from quant.live.champion_challenger import ChampionChallenger
    from quant.strategies import get_strategy
    df = _df_from_returns(_returns(300))
    cc = ChampionChallenger(get_strategy("ma_cross", fast=10, slow=30),
                            get_strategy("breakout", window=40),
                            min_obs=10, t_threshold=0.0)
    r = cc.evaluate(df, folds=3)
    assert r["n_folds"] == 3 and 0 <= r["fold_wins"] <= 3
    r0 = cc.evaluate(df)                      # folds 미지정 = 기존 결과 형태
    assert "fold_wins" not in r0


def test_selection_gate_requires_majority_folds():
    rt = (ROOT / "quant" / "live" / "retrain.py").read_text(encoding="utf-8")
    assert "select_folds" in rt
    assert "fold_wins" in rt and "// 2 + 1" in rt


# ── ⑥ 장부·verify 재현 ─────────────────────────────────────────


def test_ledger_records_folds_and_verify_replays_from_ledger():
    rt = (ROOT / "quant" / "live" / "retrain.py").read_text(encoding="utf-8")
    assert '"select_folds": 3' in rt                       # 장부 기록
    assert 'rec.get("select_folds", 0)' in rt              # 옛 기록은 0으로 재현
