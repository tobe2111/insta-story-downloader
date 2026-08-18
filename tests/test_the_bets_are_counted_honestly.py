"""실효 독립 베팅 수(ENB)와 평시/하락일 상관 — 2026-08-18 외부 검토 ①·④.

지켜야 할 약속:
- 다 같이 움직이는 포트폴리오의 ENB는 1에 붙는다(종목 수가 아니라).
- 서로 무관하게 움직이면 ENB는 종목 수에 붙는다 — 단, 종목 수를 넘는
  낙관(음의 상관)은 공개하지 않는다.
- 표본이 부족하면 숫자 대신 이유를 내놓는다.
- 하락일 상관은 하락일만 골라 재야 한다 — 전체 평균을 복사하면 거짓.
- 이 숫자들은 진단 전용이다: status.json/risk.json에 실리되 사이징
  경로에는 닿지 않는다(구조 동결).
"""
from __future__ import annotations

import json
import os

import pytest

from quant.risk.effective_bets import (
    MIN_DAYS, correlation_regimes, effective_bets, returns_by_symbol)


def _write_ledger(state_dir, name, market, symbol, equities):
    os.makedirs(os.path.join(state_dir, "paper"), exist_ok=True)
    hist = [{"date": f"2026-08-{d + 1:02d}", "equity": e}
            for d, e in enumerate(equities)]
    with open(os.path.join(state_dir, "paper", name), "w",
              encoding="utf-8") as f:
        json.dump({"market": market, "symbol": symbol, "history": hist}, f)


def _equities(returns, start=10_000.0):
    out, eq = [], start
    for r in [0.0] + list(returns):
        eq *= 1.0 + r
        out.append(round(eq, 6))
    return out


# 부호가 서로 직교(내적 0)하는 수익률 패턴 — 상관이 정확히 0이 되는 재료.
_ORTHO_A = [+1, -1, +1, -1, +1, -1, +1, -1]
_ORTHO_B = [+1, +1, -1, -1, +1, +1, -1, -1]


def test_a_herd_counts_as_one_bet(tmp_path):
    """전 종목이 똑같이 움직이면 몇 종목을 들었든 베팅은 1개다."""
    rets = [0.01, -0.02, 0.015, -0.01, 0.02, -0.015, 0.01, -0.02]
    for i in range(4):
        _write_ledger(tmp_path, f"crypto_S{i}.json", "crypto", f"S{i}/USDT",
                      _equities(rets))
    out = effective_bets(str(tmp_path))
    assert out.get("enb") == pytest.approx(1.0, abs=0.01), out
    assert out["n_symbols"] == 4


def test_independent_symbols_count_separately(tmp_path):
    """상관 0인 두 종목은 2개의 베팅으로 센다."""
    _write_ledger(tmp_path, "a.json", "crypto", "A/USDT",
                  _equities([0.01 * s for s in _ORTHO_A]))
    _write_ledger(tmp_path, "b.json", "crypto", "B/USDT",
                  _equities([0.01 * s for s in _ORTHO_B]))
    out = effective_bets(str(tmp_path))
    assert out.get("enb") == pytest.approx(2.0, abs=0.01), out


def test_negative_correlation_never_exceeds_symbol_count(tmp_path):
    """음의 상관은 산수로는 ENB > N을 만든다 — 그 낙관은 공개하지 않는다."""
    r = [0.01 * s for s in _ORTHO_A]
    _write_ledger(tmp_path, "a.json", "crypto", "A/USDT", _equities(r))
    _write_ledger(tmp_path, "b.json", "crypto", "B/USDT",
                  _equities([-x for x in r]))
    out = effective_bets(str(tmp_path))
    assert out.get("enb") is not None and out["enb"] <= 2.0, out


def test_a_thin_sample_returns_a_reason_not_a_number(tmp_path):
    _write_ledger(tmp_path, "a.json", "crypto", "A/USDT",
                  _equities([0.01, -0.01]))
    _write_ledger(tmp_path, "b.json", "crypto", "B/USDT",
                  _equities([0.02, -0.02]))
    out = effective_bets(str(tmp_path))
    assert "enb" not in out and "표본 부족" in out.get("reason", ""), out
    assert str(MIN_DAYS) in out["reason"]


def test_flat_and_portfolio_ledgers_are_left_out(tmp_path):
    """내내 현금인 종목은 상관이 정의되지 않고, 통합 계좌는 합이라 제외."""
    _write_ledger(tmp_path, "a.json", "crypto", "A/USDT",
                  _equities([0.01 * s for s in _ORTHO_A]))
    _write_ledger(tmp_path, "b.json", "crypto", "B/USDT",
                  _equities([0.01 * s for s in _ORTHO_B]))
    _write_ledger(tmp_path, "flat.json", "crypto", "F/USDT",
                  _equities([0.0] * 8))
    _write_ledger(tmp_path, "portfolio_ALL.json", "portfolio", "ALL",
                  _equities([0.05] * 8))
    assert "portfolio:ALL" not in returns_by_symbol(str(tmp_path))
    out = effective_bets(str(tmp_path))
    assert out["n_symbols"] == 2 and out["n_flat_excluded"] == 1, out


def test_the_small_sample_wears_its_caveat(tmp_path):
    """20일 미만 표본의 숫자는 '흔들릴 수 있다'는 표식을 함께 싣는다."""
    for nm, pat in (("a", _ORTHO_A), ("b", _ORTHO_B)):
        _write_ledger(tmp_path, f"{nm}.json", "crypto", f"{nm.upper()}/USDT",
                      _equities([0.01 * s for s in pat]))
    out = effective_bets(str(tmp_path))
    assert "불안정" in out.get("caveat", ""), out


def test_the_eigen_count_appears_only_with_enough_days(tmp_path):
    """관측일 ≥ 종목 수일 때만 고유값 참여비를 병기한다(랭크 부족 방지)."""
    for nm, pat in (("a", _ORTHO_A), ("b", _ORTHO_B)):
        _write_ledger(tmp_path, f"{nm}.json", "crypto", f"{nm.upper()}/USDT",
                      _equities([0.01 * s for s in pat]))
    out = effective_bets(str(tmp_path))
    assert out.get("enb_eigen") == pytest.approx(2.0, abs=0.01), out


def test_down_days_are_measured_apart_from_calm_days(tmp_path):
    """하락일 상관은 하락일만 골라 재야 한다 — 전체 평균의 복사가 아니라.

    재료: 하락일(평균 수익률 < 0)에는 두 종목이 같이 떨어지고(상관 +1),
    상승일에는 서로 반대로 움직이게 만든다. 하락일 상관이 전체 평균과
    같게 나오면 필터가 죽은 것이다.
    """
    down = [-0.02, -0.015, -0.025, -0.01, -0.02]     # 같이 떨어지는 5일
    # 상승일은 평균이 확실히 양수(+2%±1%)라 하락일 필터에 걸리지 않으면서,
    # 두 종목이 반대로 움직여 전체 상관을 끌어내린다.
    up_a = [0.02 + 0.01 * s for s in (+1, -1, +1, -1, +1, -1)]
    up_b = [0.02 - 0.01 * s for s in (+1, -1, +1, -1, +1, -1)]
    a = up_a[:3] + down + up_a[3:]
    b = up_b[:3] + down + up_b[3:]
    _write_ledger(tmp_path, "a.json", "crypto", "A/USDT", _equities(a))
    _write_ledger(tmp_path, "b.json", "crypto", "B/USDT", _equities(b))
    out = correlation_regimes(str(tmp_path))
    assert out["n_down_days"] >= 5
    assert out["avg_corr_down_days"] == pytest.approx(1.0, abs=0.01), out
    assert out["avg_corr_down_days"] > out["avg_corr_all_days"] + 0.1


def test_too_few_down_days_is_said_out_loud(tmp_path):
    """하락일이 부족하면 하락일 상관 대신 그 이유를 싣는다."""
    a = [0.01 * s for s in _ORTHO_A]
    b = [0.012 * s for s in _ORTHO_B]
    _write_ledger(tmp_path, "a.json", "crypto", "A/USDT",
                  _equities([x + 0.02 for x in a]))    # 평균이 늘 양수 → 하락일 0
    _write_ledger(tmp_path, "b.json", "crypto", "B/USDT",
                  _equities([x + 0.02 for x in b]))
    out = correlation_regimes(str(tmp_path))
    assert "avg_corr_down_days" not in out
    assert "하락일" in out.get("down_days_reason", ""), out


def test_the_status_file_carries_the_bet_count(tmp_path):
    """write_docs_status가 status.json에 diversification을 싣는다."""
    from quant.live.daily import write_docs_status
    for nm, pat in (("a", _ORTHO_A), ("b", _ORTHO_B)):
        _write_ledger(tmp_path, f"{nm}.json", "crypto", f"{nm.upper()}/USDT",
                      _equities([0.01 * s for s in pat]))
    docs = tmp_path / "status.json"
    status = write_docs_status(str(tmp_path), docs_path=str(docs))
    assert status["diversification"].get("enb") == pytest.approx(2.0, abs=0.01)
    on_disk = json.loads(docs.read_text("utf-8"))
    assert on_disk["diversification"] == status["diversification"]


def test_the_risk_report_carries_both_correlations(tmp_path):
    """risk_report.build가 평시/하락일 상관을 risk.json 재료에 싣는다."""
    import scripts.risk_report as rr
    for nm, pat in (("a", _ORTHO_A), ("b", _ORTHO_B)):
        _write_ledger(tmp_path, f"{nm}.json", "crypto", f"{nm.upper()}/USDT",
                      _equities([0.01 * s for s in pat]))
    report = rr.build(str(tmp_path))
    corr = report["correlation"]
    assert corr and corr["avg_corr_all_days"] is not None
    assert report["kind"] == "simulation"      # 시뮬레이션 표식은 그대로


def test_the_diagnostic_never_touches_sizing():
    """진단 전용 약속 — 실행 경로(사이징·킬스위치)는 이 모듈을 모른다."""
    import pathlib
    for path in ("quant/risk/manager.py", "quant/risk/portfolio_vol.py",
                 "quant/live/intraday_challenger.py"):
        src = pathlib.Path(path).read_text("utf-8")
        assert "effective_bets" not in src, f"{path}가 진단 모듈을 실행에 쓴다"
