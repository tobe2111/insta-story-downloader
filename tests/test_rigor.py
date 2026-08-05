"""엄밀성 5종 계약 검사 — 체결 현실성·다중검정·재현성·섀도·랜덤 벤치마크.

핵심 계약:
  ① 주식은 새벽 판단을 종가로 즉시 체결하지 않는다 — 다음 세션 '시가' 체결
  ② 도전자를 많이 시험할수록 승격 문턱이 올라가고, 누적 시도 수가 장부에 남는다
  ③ 기록(해시·시드·스냅샷)만으로 그날의 결정을 그대로 재현할 수 있다
  ④ 진화 없는 섀도 대조군이 병행 기록되되, 방송 카드에는 섞이지 않는다
  ⑤ 무작위 전략 1,000개 분포 대비 백분위가 결정적으로 계산된다
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import quant.data as qd  # noqa: E402
from quant.live.daily import (  # noqa: E402
    run_daily_paper,
    run_daily_portfolio,
    random_strategy_percentile,
)
from quant.live.retrain import save_champions  # noqa: E402
from quant.utils.repro import (  # noqa: E402
    data_sha256,
    load_snapshot,
    save_snapshot,
)

DOCS = Path(__file__).resolve().parent.parent / "docs"


def _df(n: int, base: float = 100.0) -> pd.DataFrame:
    """결정적 상승 추세 + 파동 — ma_cross가 매수 신호를 내는 실데이터 모형."""
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    t = np.arange(n, dtype=float)
    close = base + t * 0.8 + 3.0 * np.sin(t / 7.0)
    return pd.DataFrame({
        "open": close - 0.5, "high": close + 1.0, "low": close - 1.0,
        "close": close, "volume": 1000.0 + t}, index=idx)


class _Prov:
    def __init__(self, df: pd.DataFrame):
        self.df = df

    def get_ohlcv(self, symbol, timeframe, limit=400):
        return self.df


# ── ① 체결가 현실성 ──────────────────────────────────────────────


def test_stock_decision_queues_and_fills_at_next_open(tmp_path, monkeypatch):
    """주식: 오늘 판단은 대기열에 오르고, 다음 날 '시가'로만 체결된다."""
    d = str(tmp_path)
    save_champions({"kr_stock:TEST": {
        "strategy": "ma_cross", "params": {"fast": 5, "slow": 20},
        "promotions": 0}}, d)

    day1 = _df(60)
    monkeypatch.setattr(qd, "get_provider", lambda market: _Prov(day1))
    r1 = run_daily_paper("kr_stock", "TEST", state_dir=d,
                         require_real_data=False)
    assert r1["fill"] is None                       # 오늘은 체결 없음
    st_path = tmp_path / "paper" / "kr_stock_TEST.json"
    st = json.loads(st_path.read_text(encoding="utf-8"))
    assert st["quantity"] == 0                      # 종가 즉시 체결 금지
    assert st["pending"]["decided_bar"] == str(day1.index[-1])
    assert st["pending"]["weight"] == r1["weight"]
    # 체결 비용에 국내 거래세가 포함된 현실 프리셋(수수료+거래세+슬리피지)
    assert r1["fill_cost"] == pytest.approx(0.00015 + 0.00075 + 0.0005)
    # 회계 기준 태그 + 환경 지문 — 어느 기준·어느 환경의 숫자인지 영구 구분
    assert r1["accounting"] == "next_open_v2"
    assert r1["env"].startswith("py")

    day2 = _df(61)                                  # 다음 세션 봉이 생겼다
    monkeypatch.setattr(qd, "get_provider", lambda market: _Prov(day2))
    r2 = run_daily_paper("kr_stock", "TEST", state_dir=d,
                         require_real_data=False)
    assert r2["fill"] is not None                   # 어제 결정이 오늘 체결됨
    next_open = float(day2["open"].iloc[-1])
    assert r2["fill"]["price"] == pytest.approx(next_open)  # 시가 체결(갭 감수)
    assert r2["fill"]["decided_bar"] == str(day1.index[-1])
    st = json.loads(st_path.read_text(encoding="utf-8"))
    if r1["weight"] > 0:                            # 매수였다면 포지션이 생겼다
        assert st["quantity"] > 0
    assert st["pending"]["decided_bar"] == str(day2.index[-1])  # 오늘 결정은 다시 대기


def test_crypto_fills_immediately_without_pending(tmp_path):
    """코인/합성(24시간 시장): 즉시 체결 — 대기 주문을 만들지 않는다."""
    d = str(tmp_path)
    save_champions({"synthetic:DEMO": {
        "strategy": "ma_cross", "params": {"fast": 10, "slow": 30},
        "promotions": 0}}, d)
    run_daily_paper("synthetic", "DEMO", lookback=200, state_dir=d,
                    require_real_data=False)
    st = json.loads((tmp_path / "paper" / "synthetic_DEMO.json")
                    .read_text(encoding="utf-8"))
    assert not st.get("pending")


# ── ② 다중검정 보정 + ③ 재현성(verify) ──────────────────────────


def test_retrain_multiple_testing_ledger_and_verify(tmp_path):
    """누적 시도 수가 장부에 쌓이고, 기록만으로 그날의 결정이 재현된다."""
    import quant.live.retrain as rt

    d = str(tmp_path)
    save_champions({"synthetic:DEMO": {
        "strategy": "ma_cross", "params": {"fast": 10, "slow": 30},
        "promotions": 0}}, d)
    orig = rt.DEFAULT_CHALLENGERS
    rt.DEFAULT_CHALLENGERS = [
        {"strategy": "ma_cross", "params": {"fast": 20, "slow": 60}}]
    try:
        rt.run_retrain("synthetic", "DEMO", limit=400, state_dir=d,
                       require_real_data=False, evolve=True)
        champs = json.loads((tmp_path / "champions.json")
                            .read_text(encoding="utf-8"))
        n1 = champs["synthetic:DEMO"]["trials_total"]
        assert n1 >= 7                              # 기본1 + 돌연변이4 + 래핑2

        recs = [json.loads(ln) for ln in
                (tmp_path / "retrain_history.jsonl")
                .read_text(encoding="utf-8").splitlines()]
        rec = recs[-1]
        # 재현에 필요한 지문이 전부 기록됐다
        assert rec["champion_before"] == {
            "strategy": "ma_cross", "params": {"fast": 10, "slow": 30}}
        assert rec["mutation_seed"] == f"{rec['asof']}:synthetic:DEMO"
        assert len(rec["data_sha256"]) == 64 and rec["code_sha"]
        assert rec["trials_total"] == n1
        assert rec["select_t"] >= 2.0
        assert 1.0 <= rec["confirm_t"] <= rt.CONFIRM_T_CAP  # 상한 안에서만 상승
        assert rec["env"].startswith("py")                  # 환경 지문 기록
        # 입력 스냅샷이 보존됐다
        snap = tmp_path / "snapshots" / rec["asof"] / "synthetic_DEMO.csv.gz"
        assert snap.exists()

        # 다음 날(멱등 가드 해제) 다시 대결 → 누적 시도 수가 증가한다
        champs["synthetic:DEMO"]["last_run_asof"] = "1999-01-01"
        (tmp_path / "champions.json").write_text(
            json.dumps(champs), encoding="utf-8")
        rt.run_retrain("synthetic", "DEMO", limit=400, state_dir=d,
                       require_real_data=False, evolve=True)
        champs2 = json.loads((tmp_path / "champions.json")
                             .read_text(encoding="utf-8"))
        assert champs2["synthetic:DEMO"]["trials_total"] > n1
        recs2 = [json.loads(ln) for ln in
                 (tmp_path / "retrain_history.jsonl")
                 .read_text(encoding="utf-8").splitlines()]
        assert recs2[-1]["confirm_t"] >= rec["confirm_t"]  # 시도할수록 어려워진다

        # verify — 스냅샷·시드에서 같은 결정이 재현된다
        out = rt.verify_retrain(rec["asof"], state_dir=d)
        assert out and all(r["ok"] for r in out), out
    finally:
        rt.DEFAULT_CHALLENGERS = orig


def test_data_sha256_snapshot_roundtrip_and_immutability(tmp_path):
    df = _df(50)
    h = data_sha256(df)
    assert len(h) == 64 and data_sha256(df.copy()) == h   # 안정적
    tweaked = df.copy()
    tweaked.iloc[0, tweaked.columns.get_loc("close")] += 0.001
    assert data_sha256(tweaked) != h                      # 변조 감지

    save_snapshot(df, str(tmp_path), "2026-08-06", "kr_stock", "005930.KS")
    back = load_snapshot(str(tmp_path), "2026-08-06", "kr_stock", "005930.KS")
    assert data_sha256(back) == h                         # 저장·복원 무손실
    # 불변성: 같은 자리에 다른 데이터를 저장해도 원본이 지켜진다
    save_snapshot(tweaked, str(tmp_path), "2026-08-06", "kr_stock", "005930.KS")
    back2 = load_snapshot(str(tmp_path), "2026-08-06", "kr_stock", "005930.KS")
    assert data_sha256(back2) == h
    assert load_snapshot(str(tmp_path), "1999-01-01", "x", "y") is None


# ── ④ 섀도 대조군 ────────────────────────────────────────────────


def test_shadow_portfolio_recorded_but_not_broadcast_card(tmp_path):
    """섀도(진화 없음) 계좌가 병행 기록되되, 방송 카드 목록에는 안 섞인다."""
    from quant.web.app import broadcast_json

    d = str(tmp_path)
    targets = [("synthetic", "DEMO"), ("synthetic", "DEMO2")]
    rec = run_daily_portfolio(targets, lookback=400, state_dir=d,
                              require_real_data=False, use_champions=False,
                              state_file="portfolio_SHADOW.json")
    assert not rec.get("skipped")
    st = json.loads((tmp_path / "paper" / "portfolio_SHADOW.json")
                    .read_text(encoding="utf-8"))
    assert st["market"] == "portfolio_shadow" and st["symbol"] == "SHADOW"
    assert "random_pctile" in st["history"][-1]

    out = json.loads(broadcast_json(d, with_live=False))
    assert all(a["market"] != "portfolio_shadow" for a in out["accounts"])
    assert out["shadow"]["equity"] == st["history"][-1]["equity"]


# ── ⑤ 무작위 전략 분포 벤치마크 ─────────────────────────────────


def test_random_percentile_is_permutation_matched_and_deterministic():
    """순열 검정: 무작위가 실제와 같은 매매 빈도·비중 분포를 쓰는지 검증."""
    hist = [{"price": 100.0 + i * 0.8 + 3.0 * np.sin(i / 7.0),
             "weight": (0.0, 0.5, 1.0)[i % 3]}      # 실제 비중 수열
            for i in range(30)]
    a = random_strategy_percentile(hist, 5.0, n=200, seed="rand:2026-08-06")
    b = random_strategy_percentile(hist, 5.0, n=200, seed="rand:2026-08-06")
    assert a == b and 0.0 <= a <= 100.0             # 같은 시드 → 같은 값(재현)
    hi = random_strategy_percentile(hist, 500.0, n=200, seed="s")
    lo = random_strategy_percentile(hist, -90.0, n=200, seed="s")
    assert hi > lo and hi == 100.0 and lo == 0.0
    assert random_strategy_percentile(hist[:2], 5.0) is None  # 기록 부족
    # 비중이 늘 일정하면 순열이 전부 같다 — 타이밍 우위 없음(낮은 백분위)이
    # 정직한 값이고, 죽지 않고 계산돼야 한다
    flat = [{"price": p["price"], "weight": 1.0} for p in hist]
    v = random_strategy_percentile(flat, 0.0, n=50, seed="s")
    assert v is not None and 0.0 <= v <= 100.0


def test_confirm_threshold_capped_and_trials_window_rolls():
    """문턱이 단조 증가로 영원히 오르면 진화가 멈춘다 — 상한·롤링 윈도 검증."""
    import quant.live.retrain as rt

    assert rt.confirm_threshold(0) == 1.0
    assert rt.confirm_threshold(3000) < rt.CONFIRM_T_CAP
    assert rt.confirm_threshold(10 ** 9) == rt.CONFIRM_T_CAP  # 상한 고정


def test_recent_trials_only_counts_rolling_window(tmp_path):
    import quant.live.retrain as rt

    lines = [
        {"asof": "2020-01-01", "market": "crypto", "symbol": "BTC",
         "n_candidates": 999},                       # 윈도 밖 — 무시돼야 함
        {"asof": "2026-07-01", "market": "crypto", "symbol": "BTC",
         "n_candidates": 7},
        {"asof": "2026-08-01", "market": "crypto", "symbol": "BTC",
         "n_candidates": 8},
        {"asof": "2026-08-01", "market": "kr_stock", "symbol": "X",
         "n_candidates": 5},                         # 다른 종목 — 무시
    ]
    (tmp_path / "retrain_history.jsonl").write_text(
        "\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    got = rt.recent_trials("crypto", "BTC", "2026-08-05",
                           state_dir=str(tmp_path))
    assert got == 15


# ── 사이트: 섀도가 종목처럼 섞여 그려지면 안 된다 ────────────────


def test_site_pages_filter_shadow_and_explain_repro():
    for page in ("paper.html", "today.html", "weekly.html", "index.html"):
        txt = (DOCS / page).read_text(encoding="utf-8")
        assert ('startsWith("portfolio:")' in txt
                or 'indexOf("portfolio:")===0' in txt), page
    paper = (DOCS / "paper.html").read_text(encoding="utf-8")
    assert "portfolio_shadow:SHADOW" in paper and "무작위" in paper
    trust = (DOCS / "trust.html").read_text(encoding="utf-8")
    assert "재현" in trust and "quant verify" in trust
    assert "다음 거래 세션의 시가" in trust           # 체결 규칙 고지
    # 회계 기준 변경 고백 — 과거는 재계산하지 않고, 변경 사실을 명시한다
    assert "이전 숫자는 낙관적이었습니다" in trust
    assert "이전 숫자는 낙관적이었습니다" in paper
