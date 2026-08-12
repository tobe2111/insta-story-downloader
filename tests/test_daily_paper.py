"""매일 자동 페이퍼(quant/live/daily.py) 계약 검사.

핵심 계약: ① 계좌 상태가 실행 간에 이어진다 ② 같은 봉에 재실행해도 이중
매매가 없다(멱등) ③ 사이트용 status.json이 올바르게 모인다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.live.daily import run_daily_paper, write_docs_status  # noqa: E402
from quant.live.retrain import save_champions  # noqa: E402


def _setup_champion(state_dir: str) -> None:
    """빠른 결정적 챔피언(ma_cross)을 심어 ML 학습 비용 없이 경로를 검증한다."""
    save_champions({"synthetic:DEMO": {
        "strategy": "ma_cross", "params": {"fast": 10, "slow": 30},
        "promotions": 0}}, state_dir)


def test_daily_paper_persists_and_is_idempotent(tmp_path):
    d = str(tmp_path)
    _setup_champion(d)

    r1 = run_daily_paper("synthetic", "DEMO", lookback=200, state_dir=d,
                         require_real_data=False)
    assert r1.get("skipped") is not True
    st_path = tmp_path / "paper" / "synthetic_DEMO.json"
    st = json.loads(st_path.read_text(encoding="utf-8"))
    assert len(st["history"]) == 1
    assert st["history"][0]["champion"] == {"fast": 10, "slow": 30}

    # 같은 봉에 재실행 → 이중 매매 금지(멱등)
    r2 = run_daily_paper("synthetic", "DEMO", lookback=200, state_dir=d,
                         require_real_data=False)
    assert r2.get("skipped") is True
    st = json.loads(st_path.read_text(encoding="utf-8"))
    assert len(st["history"]) == 1                 # 기록이 늘지 않았다

    # 다음 날(새 봉) 시뮬레이션: last_bar를 과거로 되돌리면 새 사이클로 이어진다
    prev_cash = st["cash"]
    st["last_bar"] = "1999-01-01"
    st_path.write_text(json.dumps(st), encoding="utf-8")
    r3 = run_daily_paper("synthetic", "DEMO", lookback=200, state_dir=d,
                         require_real_data=False)
    assert r3.get("skipped") is not True
    st2 = json.loads(st_path.read_text(encoding="utf-8"))
    assert len(st2["history"]) == 2
    # 계좌가 초기화되지 않고 이어졌다(시작 현금으로 리셋되면 안 됨)
    assert st2["history"][1]["equity"] != 10_000.0 or prev_cash != 10_000.0


def test_daily_paper_refuses_fallback_data(tmp_path, monkeypatch):
    """실데이터 수신 실패로 '합성 폴백'이 감지되면 기록을 오염시키지 않고 중단."""
    import quant.data as qd

    real_provider = qd.get_provider("synthetic")

    class _FallbackStub:
        def get_ohlcv(self, *a, **k):
            df = real_provider.get_ohlcv("DEMO", "1d", limit=100)
            df.attrs["synthetic_fallback"] = True   # 폴백 데이터 흉내
            return df

    monkeypatch.setattr(qd, "get_provider", lambda market, **k: _FallbackStub())
    with pytest.raises(RuntimeError, match="합성 폴백"):
        run_daily_paper("crypto", "BTC/USDT", state_dir=str(tmp_path))
    assert not (tmp_path / "paper").exists()        # 어떤 기록도 남기지 않았다


def test_write_docs_status(tmp_path):
    d = str(tmp_path)
    _setup_champion(d)
    run_daily_paper("synthetic", "DEMO", lookback=200, state_dir=d,
                    require_real_data=False)
    out = tmp_path / "docs" / "status.json"
    status = write_docs_status(d, docs_path=str(out))
    assert "synthetic:DEMO" in status["paper"]
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["paper"]["synthetic:DEMO"]["history"], "히스토리가 비면 안 됨"
    assert saved["champions"]["synthetic:DEMO"]["params"]["fast"] == 10
    assert saved["updated"] == saved["paper"]["synthetic:DEMO"]["history"][-1]["date"]


# ── 주간 요약 (pandas 불필요) ──────────────────────────────────────────────

def _write_paper_state(tmp_path, market, symbol, dates_equities):
    import json as _json
    d = tmp_path / "paper"
    d.mkdir(exist_ok=True)
    hist = [{"date": dt, "price": 100.0, "weight": 0.5, "equity": eq,
             "return_pct": round((eq / 10000 - 1) * 100, 2), "hit_rate": 0.52}
            for dt, eq in dates_equities]
    (d / f"{market}_{symbol}.json").write_text(_json.dumps(
        {"market": market, "symbol": symbol, "start_cash": 10000,
         "cash": 0, "quantity": 1, "avg_price": 100,
         "last_bar": dates_equities[-1][0], "history": hist}), encoding="utf-8")


def test_weekly_summary_and_format(tmp_path):
    import json as _json

    from quant.live.daily import format_weekly, weekly_summary

    _write_paper_state(tmp_path, "crypto", "BTC", [
        ("2026-07-27", 10000), ("2026-07-28", 10100), ("2026-07-29", 9900),
        ("2026-07-30", 10200), ("2026-07-31", 10300), ("2026-08-01", 10400),
        ("2026-08-02", 10500), ("2026-08-03", 10600),
    ])
    (tmp_path / "retrain_history.jsonl").write_text(_json.dumps({
        "asof": "2026-08-01", "market": "crypto", "symbol": "BTC",
        "promoted": True, "champion": {"model": "gb"},
        "champion_strategy": "ml"}) + "\n", encoding="utf-8")

    s = weekly_summary(str(tmp_path))
    assert s["period"] == ["2026-07-28", "2026-08-03"]   # 마지막 날 기준 7일
    m = s["markets"]["crypto:BTC"]
    assert m["n_days"] == 7
    assert m["week_return_pct"] == 6.0                   # 10000 → 10600
    assert m["worst_day"] == {"date": "2026-07-29", "pct": -1.98}
    assert len(s["swaps"]) == 1 and s["swaps"][0]["strategy"] == "ml"

    text = format_weekly(s)
    assert "주간 요약" in text and "crypto:BTC" in text
    assert "챔피언 교체" in text and "수익 보장이 아닙니다" in text


def test_weekly_summary_empty(tmp_path):
    from quant.live.daily import format_weekly, weekly_summary

    s = weekly_summary(str(tmp_path))
    assert s["markets"] == {} and "없습니다" in format_weekly(s)


def test_run_daily_paper_all_tolerates_partial_failure(tmp_path, monkeypatch):
    """한 종목의 실패가 나머지를 막지 않고, 전 종목 실패 시에만 예외."""
    import quant.live.daily as dl

    _setup_champion(str(tmp_path))
    calls = []

    def fake_run(market, symbol, **kw):
        calls.append(symbol)
        if symbol == "BAD":
            raise RuntimeError("데이터 없음")
        return {"date": "2026-08-04", "equity": 10100.0, "return_pct": 1.0,
                "weight": 0.5}

    monkeypatch.setattr(dl, "run_daily_paper", fake_run)
    out = dl.run_daily_paper_all(
        targets=[("synthetic", "DEMO"), ("synthetic", "BAD")],
        state_dir=str(tmp_path), require_real_data=False)
    assert calls == ["DEMO", "BAD"]              # 실패 후에도 순회 계속
    assert out["ok"] == ["synthetic:DEMO"]
    assert "synthetic:BAD" in out["failed"]

    import pytest as _pytest
    with _pytest.raises(RuntimeError):           # 전 종목 실패 → 조기 경보
        dl.run_daily_paper_all(targets=[("synthetic", "BAD")],
                               state_dir=str(tmp_path))


# ── 통합 포트폴리오 챌린지 ────────────────────────────────────────────────

def test_portfolio_account_runs_and_is_idempotent(tmp_path):
    from quant.live.daily import run_daily_portfolio
    from quant.live.retrain import save_champions

    d = str(tmp_path)
    save_champions({
        "synthetic:DEMO": {"strategy": "ma_cross",
                           "params": {"fast": 10, "slow": 30}, "promotions": 0},
        "synthetic:DEMO2": {"strategy": "ma_cross",
                            "params": {"fast": 5, "slow": 20}, "promotions": 0},
    }, d)
    targets = [("synthetic", "DEMO"), ("synthetic", "DEMO2")]

    r1 = run_daily_portfolio(targets, lookback=200, state_dir=d,
                             require_real_data=False)
    assert r1.get("skipped") is not True
    st = json.loads((tmp_path / "paper" / "portfolio_ALL.json")
                    .read_text(encoding="utf-8"))
    assert st["market"] == "portfolio" and len(st["history"]) == 1
    assert abs(st["history"][0]["price"] - 100.0) < 1e-6   # 지수 첫 관측 = 100
    assert st["history"][0]["champion"]["symbols"] == 2

    r2 = run_daily_portfolio(targets, lookback=200, state_dir=d,
                             require_real_data=False)
    assert r2.get("skipped") is True                       # 같은 봉 → 멱등

    # 다음 날 시뮬레이션: last_bar를 되돌리면 계좌가 이어진다
    st["last_bar"] = "1999-01-01"
    (tmp_path / "paper" / "portfolio_ALL.json").write_text(
        json.dumps(st), encoding="utf-8")
    r3 = run_daily_portfolio(targets, lookback=200, state_dir=d,
                             require_real_data=False)
    assert r3.get("skipped") is not True
    st2 = json.loads((tmp_path / "paper" / "portfolio_ALL.json")
                     .read_text(encoding="utf-8"))
    assert len(st2["history"]) == 2

    # ⚠️ '계좌가 이어진다'를 **주석으로만** 적어 두고 기록 개수만 세고
    #    있었다(감사 133). 보유를 장부에 저장하지 않게 만들어도 이 검사는
    #    통과했다 — 그러면 매일 빈 계좌로 시작해 현금만 줄어든 채로 남고,
    #    장부에는 있지도 않은 손실이 매일 찍힌다. 계좌 연속성은 이 실험의
    #    가장 기본 전제다. 이어지는지 **숫자로** 본다.
    assert st["positions"], "첫날 아무것도 안 샀다 — 아래 연속성 검사가 헛돈다"
    assert st2["positions"], (
        "이튿날 보유가 사라졌다 — 계좌가 이어지지 않는다(빈 계좌로 재시작)")
    eq1 = float(st["history"][0]["equity"])
    eq2 = float(st2["history"][1]["equity"])
    assert abs(eq2 - eq1) / eq1 < 0.10, (
        f"같은 봉 데이터인데 자산이 {eq1:,.0f} → {eq2:,.0f}로 튀었다 — "
        "보유가 이월되지 않아 생긴 유령 손익일 수 있다")


def test_portfolio_refuses_when_all_symbols_fail(tmp_path, monkeypatch):
    import quant.data as qd
    from quant.live.daily import run_daily_portfolio

    real = qd.get_provider("synthetic")

    class _FallbackStub:
        def get_ohlcv(self, *a, **k):
            df = real.get_ohlcv("DEMO", "1d", limit=100)
            df.attrs["synthetic_fallback"] = True   # 폴백 데이터 흉내
            return df

    monkeypatch.setattr(qd, "get_provider", lambda market, **k: _FallbackStub())
    with pytest.raises(RuntimeError):                # 전 종목 거부 → 기록 금지
        run_daily_portfolio([("crypto", "BTC/USDT")], lookback=100,
                            state_dir=str(tmp_path), require_real_data=True)
    assert not (tmp_path / "paper" / "portfolio_ALL.json").exists()


# ── 만원 → 1억 챌린지 (매칭 입금 · 분리 회계) ─────────────────────────────

def test_add_deposit_ledger_and_principal(tmp_path):
    from quant.live.daily import GOAL_KRW, add_deposit

    # 8마일 챌린지: 통합 계좌 시작금 8만원 + 입금 1만원 = 원금 9만원
    out = add_deposit(10000, "슈퍼챗 홍길동", state_dir=str(tmp_path),
                      date="2026-08-05")
    assert out["principal"] == 90000 and out["goal"] == GOAL_KRW
    st = json.loads((tmp_path / "paper" / "portfolio_ALL.json")
                    .read_text(encoding="utf-8"))
    assert st["cash"] == 90000                       # 현금 증액
    assert st["start_cash"] == 80000                 # 8종목 × 만원
    assert st["deposits"][0]["memo"] == "슈퍼챗 홍길동"

    add_deposit(5000, state_dir=str(tmp_path), date="2026-08-06")
    st = json.loads((tmp_path / "paper" / "portfolio_ALL.json")
                    .read_text(encoding="utf-8"))
    assert len(st["deposits"]) == 2 and st["cash"] == 95000

    with pytest.raises(ValueError):                  # 상한·양수 검증
        add_deposit(0, state_dir=str(tmp_path))
    with pytest.raises(ValueError):
        add_deposit(20_000_000, state_dir=str(tmp_path))


def test_time_weighted_return_removes_deposit_effect():
    """입금으로 자산이 뛰어도 TWR(실력 지표)은 속지 않는다."""
    from quant.live.daily import time_weighted_return

    # 1일차 10,000→10,100(+1%), 2일차에 10,000 입금 후 20,100(운용 손익 0),
    # 3일차 20,100→20,301(+1%)
    history = [
        {"date": "2026-08-01", "equity": 10100},
        {"date": "2026-08-02", "equity": 20100},
        {"date": "2026-08-03", "equity": 20301},
    ]
    deposits = [{"date": "2026-08-02", "amount": 10000}]
    twr = time_weighted_return(history, deposits)
    assert abs(twr - 2.01) < 0.01                    # (1.01×1.00×1.01)−1 ≈ +2.01%
    # 입금을 수익으로 치는 순진한 계산이라면 +103%가 나왔을 것
    naive = (20301 / 10000 - 1) * 100
    assert naive > 100 and twr < 3


def test_docs_status_challenge_fields(tmp_path):
    import quant.live.daily as dl

    dl.add_deposit(10000, "테스트", state_dir=str(tmp_path), date="2026-08-05")
    # 수동으로 기록 1건 구성(운용 손익 +500 가정)
    p = tmp_path / "paper" / "portfolio_ALL.json"
    st = json.loads(p.read_text(encoding="utf-8"))
    st["history"] = [{"date": "2026-08-05", "equity": 90500,
                      "return_pct": 2.5, "price": 100, "weight": 0.5}]
    p.write_text(json.dumps(st), encoding="utf-8")

    out = dl.write_docs_status(str(tmp_path),
                               docs_path=str(tmp_path / "s.json"))
    pf = out["paper"]["portfolio:ALL"]
    assert pf["principal"] == 90000 and pf["pnl"] == 500
    assert pf["goal"] == dl.GOAL_KRW
    assert pf["deposits"][0]["amount"] == 10000


def test_8mile_portfolio_start_cash(tmp_path, monkeypatch):
    """8마일 챌린지: 새 통합 계좌는 8만원으로 시작하고 TWR도 그 기준으로 계산."""
    import quant.live.daily as dl

    assert dl.PORTFOLIO_START_CASH == 80_000.0
    # 새 계좌 생성 경로(add_deposit 폴백)가 8만원 기반인지
    out = dl.add_deposit(1000, state_dir=str(tmp_path), date="2026-08-05")
    assert out["principal"] == 81000
    # 저장된 start_cash를 존중하는지(과거 만원 계좌 하위호환)
    p = tmp_path / "paper" / "portfolio_ALL.json"
    st = json.loads(p.read_text(encoding="utf-8"))
    st["start_cash"] = 10000.0
    st["cash"] = 11000.0
    p.write_text(json.dumps(st), encoding="utf-8")
    out2 = dl.add_deposit(500, state_dir=str(tmp_path), date="2026-08-06")
    assert out2["principal"] == 11500                # 10000 + 1000 + 500
