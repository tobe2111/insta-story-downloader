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
