"""킬스위치 낙폭 기준 계약 검사 — 입금이 브레이크를 풀면 안 된다.

배경(2026-08-11 감사): 낙폭을 자산(equity) 고점 대비로 쟀다. 그러면 매칭
입금이 고점을 끌어올려, 투자 손실이 그대로인데도 낙폭이 0으로 보인다.
즉 **돈을 더 넣는 순간 킬스위치가 풀린다** — 하필 브레이크가 가장 필요한
상황에서. 지금은 입금이 없어 두 방식의 값이 같지만, 첫 입금 날 발동할
결함이었다.

핵심 계약:
  ① 낙폭은 입금 효과를 제거한 성장 지수 위에서 잰다
  ② 입금이 킬스위치 단계를 완화하지 못한다
  ③ 사이트가 보여주는 MDD도 같은 기준이다(화면과 브레이크가 같은 숫자)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.live.daily import (  # noqa: E402
    _kill_switch_scale,
    drawdown_from_index,
    max_drawdown_from_index,
    time_weighted_return,
    twr_index,
)

ROOT = Path(__file__).resolve().parent.parent


def _h(*pairs):
    return [{"date": d, "equity": float(e)} for d, e in pairs]


# ── ① 성장 지수 ───────────────────────────────────────────────


def test_index_ignores_deposits():
    hist = _h(("2026-01-01", 100_000), ("2026-01-02", 80_000),
              ("2026-01-03", 100_000))
    dep = [{"date": "2026-01-03", "amount": 20_000}]
    idx = twr_index(hist, dep, start_cash=100_000)
    # 자산은 원금을 회복했지만 운용 성과는 여전히 -20%다
    assert abs(idx[-1] - 0.8) < 1e-9
    assert abs(time_weighted_return(hist, dep, 100_000) - (-20.0)) < 0.01


def test_index_matches_equity_when_there_are_no_deposits():
    hist = _h(("2026-01-01", 100_000), ("2026-01-02", 90_000))
    idx = twr_index(hist, [], start_cash=100_000)
    assert abs(idx[-1] - 0.9) < 1e-9
    assert abs(drawdown_from_index(idx) - (-0.10)) < 1e-9


# ── ② 입금이 브레이크를 풀지 못한다 ───────────────────────────


def test_deposit_does_not_release_the_killswitch():
    """이 테스트가 잡는 사고: 낙폭 -20%에서 입금하니 브레이크가 풀림."""
    hist = _h(("2026-01-01", 100_000), ("2026-01-02", 80_000),
              ("2026-01-03", 100_000))
    dep = [{"date": "2026-01-03", "amount": 20_000}]

    # 옛 방식(자산 고점 대비): 입금으로 고점=현재 → 낙폭 0 → 노출 100% 복귀
    peak_eq = max(r["equity"] for r in hist)
    old_dd = hist[-1]["equity"] / peak_eq - 1
    assert old_dd == 0.0
    assert _kill_switch_scale(0.5, old_dd) == 1.0        # 브레이크가 풀린다

    # 새 방식(성장 지수): 낙폭 -20% 유지 → 단계 유지
    new_dd = drawdown_from_index(twr_index(hist, dep, start_cash=100_000))
    assert abs(new_dd - (-0.20)) < 1e-9
    assert _kill_switch_scale(0.5, new_dd) == 0.5        # 브레이크가 산다


def test_recovery_still_releases_the_brake():
    """진짜 회복은 정상적으로 복귀시킨다 — 안전장치가 덫이 되면 안 된다."""
    hist = _h(("2026-01-01", 100_000), ("2026-01-02", 80_000),
              ("2026-01-03", 99_000))
    dd = drawdown_from_index(twr_index(hist, [], start_cash=100_000))
    assert abs(dd - (-0.01)) < 1e-9
    assert _kill_switch_scale(0.5, dd) == 1.0


def test_killswitch_thresholds_unchanged():
    assert _kill_switch_scale(1.0, -0.26) == 0.0
    assert _kill_switch_scale(1.0, -0.16) == 0.5
    assert _kill_switch_scale(0.0, -0.16) == 0.0        # 0에서 바로 복귀 없음
    assert _kill_switch_scale(0.5, -0.12) == 0.5
    assert _kill_switch_scale(1.0, -0.05) == 1.0


# ── ③ 최대낙폭도 같은 기준 ────────────────────────────────────


def test_max_drawdown_uses_the_same_basis():
    hist = _h(("2026-01-01", 100_000), ("2026-01-02", 70_000),
              ("2026-01-03", 100_000))
    dep = [{"date": "2026-01-03", "amount": 30_000}]
    mdd = max_drawdown_from_index(twr_index(hist, dep, start_cash=100_000))
    assert abs(mdd - (-0.30)) < 1e-9


def test_wired_into_daily_and_site():
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert "drawdown = drawdown_from_index(_series)" in src
    assert "mdd = max_drawdown_from_index(twr_index(" in src
    # 자산 고점으로 낙폭을 재던 옛 코드가 되살아나면 안 된다
    assert "equity / peak_eq - 1" not in src
    assert "eq / peak - 1" not in src


# ── 같은 규칙이 세 곳에 복사돼 있었다 ─────────────────────────
#
# 2026-08-11 감사: 낙폭 계산이 (1) 킬스위치 (2) 사이트 status.json
# (3) 방송 화면 세 곳에 각각 적혀 있었고, 앞의 둘만 고쳤더니 방송만
# 옛 기준(자산 고점 대비 + 배열 순서)으로 남았다. 규칙을 복사하면
# 반드시 한 곳이 뒤처진다.


def test_broadcast_uses_the_shared_drawdown_rule():
    src = (ROOT / "quant" / "web" / "app.py").read_text("utf-8")
    assert "max_drawdown_from_index(twr_index(" in src
    assert "chrono(st.get(\"history\", []))" in src
    # 자산 고점 대비로 재던 옛 코드가 되살아나면 안 된다
    assert "eq / peak - 1" not in src


def test_no_ad_hoc_drawdown_formula_on_account_equity():
    """계좌 자산 위에서 낙폭을 직접 계산하는 곳이 남아 있는가.

    robustness/는 제외한다 — 거기 낙폭은 합성 성장지수(cumprod) 위에서
    재는 것이라 입금 개념 자체가 없다. 즉 이미 올바른 기준이다.
    (첫 구현에서 이 구분 없이 훑었다가 monte_carlo를 오탐했다.)
    """
    import re
    bad = []
    for path in (ROOT / "quant").rglob("*.py"):
        if "robustness" in path.parts or "backtest" in path.parts:
            continue
        for i, ln in enumerate(path.read_text("utf-8").splitlines(), 1):
            if re.search(r"(eq|equity)\s*/\s*peak\w*\s*-\s*1", ln):
                bad.append(f"{path.relative_to(ROOT)}:{i}")
    assert not bad, f"공용 헬퍼를 쓰지 않는 낙폭 계산: {bad}"


def test_broadcast_and_site_agree_on_drawdown():
    """방송과 사이트가 같은 계좌에 대해 같은 낙폭을 말하는가."""
    import json

    from quant.live.daily import write_docs_status
    from quant.web.app import broadcast_json

    state = str(ROOT / "state")
    if not (Path(state) / "paper").is_dir():
        return
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        site = write_docs_status(state, docs_path=f"{td}/status.json")
    bc = json.loads(broadcast_json(state, with_live=False))
    site_mdd = {k: v.get("mdd_pct") for k, v in (site.get("paper") or {}).items()}
    for acct in bc.get("accounts", []):
        if acct["key"] in site_mdd:
            assert abs((acct["mdd_pct"] or 0)
                       - (site_mdd[acct["key"]] or 0)) < 0.011, acct["key"]
