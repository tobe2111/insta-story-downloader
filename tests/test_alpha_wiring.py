"""알파 개선 배치 계약 검사 — 사이징·보정·피처·캘린더·밴드·드리프트 연결.

핵심 계약:
  ① 변동성 타깃팅 연율화가 시장별로 맞다(코인 365, 주식 252)
  ② 보정(calibrate) 챌린저가 링에 참전한다 — 강제 적용이 아니라 오디션
  ③ ML이 마지막 예측확률(last_proba_)을 노출하고 기록·설명이 같은 숫자를 쓴다
  ④ 변동성 구조 피처(GK·RV비율)와 펀딩 피처가 존재하고 해시에 묶인다
  ⑤ 옵션만기·월말 마이너 캘린더가 결정적으로 계산되고 가드가 작동한다
  ⑥ 무행동 밴드 — 잔조정 주문은 생략, 청산은 항상 실행
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.events import is_minor_event_day, minor_event_dates  # noqa: E402
from quant.strategies.ml import (  # noqa: E402
    FEATURE_NAMES,
    FEATURE_SET,
    MLStrategy,
    _features,
)


def _df(n: int, base: float = 100.0, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    ret = rng.normal(0.0005, 0.02, n)
    close = base * np.cumprod(1 + ret)
    opn = close * (1 + rng.normal(0, 0.004, n))
    return pd.DataFrame({
        "open": opn,
        "high": np.maximum(opn, close) * (1 + abs(rng.normal(0, 0.005, n))),
        "low": np.minimum(opn, close) * (1 - abs(rng.normal(0, 0.005, n))),
        "close": close, "volume": 1000.0 + rng.integers(0, 500, n)},
        index=idx)


# ── ① 시장별 연율화 ─────────────────────────────────────────────


def test_risk_annualization_by_market():
    from quant.live.daily import _risk_for
    assert _risk_for("crypto").config.periods_per_year == 365
    assert _risk_for("synthetic").config.periods_per_year == 365
    assert _risk_for("kr_stock").config.periods_per_year == 252
    assert _risk_for("us_stock").config.periods_per_year == 252


# ── ② 링 구성: 보정 챌린저 + 마이너 이벤트 변형 ────────────────


def test_ring_includes_calibrated_and_minor_event_variants():
    from quant.live.retrain import DEFAULT_CHALLENGERS, build_challengers
    cals = [c for c in DEFAULT_CHALLENGERS if c.get("calibrate")]
    assert {c["calibrate"] for c in cals} == {"isotonic", "sigmoid"}
    ring = build_challengers(
        {"strategy": "ma_cross", "params": {"fast": 10, "slow": 30}},
        seed="2026-08-06:x", evolve=True)
    minors = [c for c in ring if c.get("strategy") == "event_wrap"
              and c.get("params", {}).get("include_minor")]
    assert len(minors) == 1 and minors[0]["params"]["factor"] == 0.5


# ── ③ 예측확률 노출 + 설명 일치 ────────────────────────────────


def test_ml_exposes_last_proba_and_explain_uses_it():
    df = _df(160)
    strat = MLStrategy(model="logreg", train_window=80, retrain_every=10,
                       min_train=40)
    strat.generate_signals(df)
    assert strat.last_proba_ is not None and 0.0 <= strat.last_proba_ <= 1.0

    from quant.live.explain import explain_signal
    spec = {"strategy": "ml", "params": {"model": "logreg", "threshold": 0.55}}
    txt = explain_signal(spec, df, 0.5, strat)
    assert f"{strat.last_proba_:.0%}" in txt   # 서술 확률 = 실제 모델 출력

    from quant.live.daily import _last_proba
    assert _last_proba(strat) == strat.last_proba_

    class Wrap:                                 # 래퍼 체인 관통 확인
        def __init__(self, base):
            self.base = base
    assert _last_proba(Wrap(Wrap(strat))) == strat.last_proba_
    assert _last_proba(object()) is None


# ── ④ 피처: 변동성 구조 + 펀딩 ─────────────────────────────────


def test_features_include_vol_structure_and_funding():
    assert "gk_vol" in FEATURE_NAMES and "rv_5_60" in FEATURE_NAMES
    assert FEATURE_SET.startswith("fs4")       # fs4: +OI+FRED
    df = _df(120)
    f = _features(df)
    assert f["gk_vol"].iloc[-1] > 0            # GK 변동성은 양수
    assert np.isfinite(f["rv_5_60"].iloc[-1])
    assert "x_funding" not in f.columns        # 컬럼 없으면 피처도 없다
    df2 = df.copy()
    df2["funding"] = 0.0001
    f2 = _features(df2)
    assert "x_funding" in f2.columns


def test_data_sha256_covers_funding_column():
    from quant.utils.repro import data_sha256
    df = _df(60)
    h0 = data_sha256(df)
    df2 = df.copy(); df2["funding"] = 0.0001
    df3 = df.copy(); df3["funding"] = 0.0002
    assert data_sha256(df2) != h0              # 펀딩 추가 → 다른 입력
    assert data_sha256(df2) != data_sha256(df3)  # 펀딩 변조도 드러난다


def test_attach_funding_graceful_and_aligned(monkeypatch):
    import quant.data.funding as fd
    df = _df(30)
    # 실패(빈 이력) → 원본 그대로, 컬럼 없음
    monkeypatch.setattr(fd, "fetch_funding_history",
                        lambda *a, **k: pd.Series(dtype=float))
    assert "funding" not in fd.attach_funding(df, "BTC/USDT").columns
    # 성공 → funding 컬럼이 봉 인덱스에 정렬돼 붙는다
    hist = pd.Series([0.0001, -0.0002],
                     index=pd.DatetimeIndex([df.index[5], df.index[10]]))
    monkeypatch.setattr(fd, "fetch_funding_history", lambda *a, **k: hist)
    out = fd.attach_funding(df, "BTC/USDT")
    assert "funding" in out.columns and len(out) == len(df)
    assert out["funding"].iloc[5] == pytest.approx(0.0001)


# ── ⑤ 마이너 캘린더 (옵션만기·월말) ────────────────────────────


def test_minor_calendar_deterministic_and_guard_scales():
    assert is_minor_event_day(date(2026, 8, 21))    # 2026-08 셋째 금요일
    assert is_minor_event_day(date(2026, 8, 31))    # 월말
    assert is_minor_event_day(date(2026, 8, 30))    # 월말 전일
    assert not is_minor_event_day(date(2026, 8, 12))
    assert len(minor_event_dates()) > 300           # 10년치 만기+월말

    from quant.strategies.base import Strategy
    from quant.strategies.event_guard import EventGuard

    class Const(Strategy):
        name = "const"
        allow_short = False

        def generate_signals(self, df):
            return pd.Series(1.0, index=df.index)

    idx = pd.DatetimeIndex([date(2026, 8, 12), date(2026, 8, 21)])
    df = pd.DataFrame({"close": [1.0, 1.0]}, index=idx)
    sig = EventGuard(Const(), pad_days=0, factor=0.5,
                     include_minor=True).generate_signals(df)
    assert sig.iloc[0] == 1.0 and sig.iloc[1] == 0.5   # 만기일만 절반


# ── ⑥ 무행동 밴드 ──────────────────────────────────────────────


def test_rebalance_band_skips_dust_but_always_exits():
    from quant.broker import PaperBroker
    b = PaperBroker(cash=10000.0)
    assert b.target_weight("X", 0.50, 100.0, 10000.0) is not None  # 첫 진입
    eq = b.equity({"X": 100.0})
    # 비중 50%→52%: 밴드(5%p) 미만 잔조정 — 주문 생략
    assert b.target_weight("X", 0.52, 100.0, eq, rebalance_band=0.05) is None
    # 청산은 밴드와 무관하게 항상 실행
    assert b.target_weight("X", 0.0, 100.0, eq, rebalance_band=0.05) is not None


# ── 기록 필드: prob_up·drift_psi ───────────────────────────────


def test_daily_record_carries_prob_and_drift(tmp_path):
    from quant.live.daily import run_daily_paper
    from quant.live.retrain import save_champions
    d = str(tmp_path)
    save_champions({"synthetic:DEMO": {
        "strategy": "ma_cross", "params": {"fast": 10, "slow": 30},
        "promotions": 0}}, d)
    rec = run_daily_paper("synthetic", "DEMO", lookback=400, state_dir=d,
                          require_real_data=False)
    assert "prob_up" in rec and "drift_psi" in rec
    assert rec["prob_up"] is None              # ma_cross 챔피언은 확률이 없다
    assert rec["drift_psi"] is None or rec["drift_psi"] >= 0.0


# ── 2차 배치: ERC 배분·킬스위치·유니버스 확장·아카이브 ─────────


def test_erc_slices_derisk_high_vol_and_fallback():
    from quant.live.daily import _erc_slices
    rng = np.random.default_rng(0)
    idx = pd.date_range("2026-01-01", periods=90, freq="D")
    rets = {"crypto:BTC": pd.Series(rng.normal(0, 0.05, 90), index=idx),
            "kr_stock:KB": pd.Series(rng.normal(0, 0.01, 90), index=idx)}
    s = _erc_slices(rets, 2)
    assert s["crypto:BTC"] < s["kr_stock:KB"]      # 위험 기여 균등 → 고변동 축소
    # 표본 부족 → None(균등 폴백 신호)
    short = {k: v.iloc[:10] for k, v in rets.items()}
    assert _erc_slices(short, 2) is None


def test_kill_switch_stages_and_hysteresis():
    from quant.live.daily import _kill_switch_scale as ks
    assert ks(1.0, -0.05) == 1.0                   # 평시
    assert ks(1.0, -0.16) == 0.5                   # -15% 돌파 → 절반
    assert ks(0.5, -0.26) == 0.0                   # -25% 돌파 → 관망
    assert ks(0.0, -0.16) == 0.0                   # 회복 전 재진입 금지
    assert ks(0.0, -0.12) == 0.5                   # 1단계 복귀
    assert ks(0.5, -0.12) == 0.5                   # 유지
    assert ks(0.5, -0.05) == 1.0                   # 완전 복귀


def test_universe_expanded_with_info_coverage():
    from quant.markets import AUTO_TARGETS, SYMBOL_INFO
    assert len(AUTO_TARGETS) == 20
    for market, symbol in AUTO_TARGETS:            # 전 종목 이름·이유 필수
        info = SYMBOL_INFO.get(f"{market}:{symbol}")
        assert info and info.get("name") and info.get("why"), (market, symbol)


def test_portfolio_record_has_alloc_and_risk_scale(tmp_path):
    from quant.live.daily import run_daily_portfolio, write_docs_status
    from quant.live.retrain import save_champions
    d = str(tmp_path)
    save_champions({
        "synthetic:DEMO": {"strategy": "ma_cross",
                           "params": {"fast": 10, "slow": 30}, "promotions": 0},
        "synthetic:DEMO2": {"strategy": "ma_cross",
                            "params": {"fast": 5, "slow": 20}, "promotions": 0},
    }, d)
    rec = run_daily_portfolio([("synthetic", "DEMO"), ("synthetic", "DEMO2")],
                              lookback=200, state_dir=d,
                              require_real_data=False)
    assert rec["risk_scale"] == 1.0                # 첫날은 낙폭 0
    assert "alloc" in rec and len(rec["alloc"]) == 2
    assert "drawdown_pct" in rec
    # status.json에 탈락자 아카이브 데이터가 실린다
    (tmp_path / "retrain_history.jsonl").write_text(
        json.dumps({"asof": "2026-08-05", "market": "synthetic",
                    "symbol": "DEMO", "promoted": False,
                    "n_candidates": 15, "trials_total": 15}) + "\n",
        encoding="utf-8")
    st = write_docs_status(d, docs_path=str(tmp_path / "docs" / "status.json"))
    assert st["retrain_recent"][0]["n_candidates"] == 15


def test_site_has_wrong_note_archive_and_uptime_cards():
    DOCS = Path(__file__).resolve().parent.parent / "docs"
    paper = (DOCS / "paper.html").read_text(encoding="utf-8")
    assert "오답 노트" in paper and "탈락자 아카이브" in paper
    trust = (DOCS / "trust.html").read_text(encoding="utf-8")
    assert "가동률" in trust and "20종목" in trust
