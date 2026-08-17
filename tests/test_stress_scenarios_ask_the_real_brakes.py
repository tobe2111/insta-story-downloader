"""스트레스 시나리오가 **실전 브레이크에게 묻는가** — 그리고 정직한가.

리스크 데스크의 표준 질문("내일 아침 무엇이 우리를 다치게 하는가")을
지금 계좌에 가해 보는 장치다. 이 검사가 지키는 것:

  ① 시나리오의 결과에 실전 킬스위치 **함수 그대로**를 묻는다 — 문턱을
     다시 적지 않는다(FROZEN_IDEAS ①).
  ② 폭락 경로 **중간에** 브레이크가 개입해 뒤의 손실을 줄인다 —
     끝에서 한 번 묻는 것과는 다른 물건이다.
  ③ 현금이 완충한다는 산수를 정확히 한다 — 노출 40%면 시장 -30%는
     계좌 -12%다. 빼고 겁주지도, 넣고 안심시키지도 않는다.
  ④ 멈춘 시세 시나리오는 브레이크가 **못 본다**고 말한다 — 잡는 척하면
     이 시나리오의 요점이 사라진다.
  ⑤ 실제 장부에서 입력을 읽어 돌아간다(값으로 확인).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.risk import stress as S  # noqa: E402

SRC = (ROOT / "quant" / "risk" / "stress.py").read_text("utf-8")


def _run(**kw):
    base = dict(equity=1_000_000.0, principal=1_000_000.0,
                gross_weight=1.0, fx_share=0.5, worst_single_weight=0.15)
    base.update(kw)
    return S.stress_portfolio(**base)


def _sc(rep: dict, name: str) -> dict:
    return next(s for s in rep["scenarios"] if s["scenario"] == name)


# ── ① 문턱을 다시 적지 않는다 ─────────────────────────────────

def test_the_stress_borrows_the_real_kill_switch():
    assert "from quant.live.daily import _kill_switch_scale" in SRC
    body = SRC.split('"""', 2)[-1]
    # 환율 시나리오의 ±15%는 시나리오 파라미터라 무방하다 — 금지하는 것은
    # 낙폭과 문턱을 **비교하는 식**이 여기 다시 적히는 것이다.
    for banned in ("<= -0.25", "<= -0.15", "< -0.25", "< -0.15"):
        assert banned not in body, (
            f"킬스위치 문턱 비교({banned!r})가 스트레스에 다시 적혀 있다 — "
            "실전이 바뀌면 여기만 낡는다")


# ── ② 경로 중간에 브레이크가 개입한다 ─────────────────────────

def test_the_brake_engages_mid_cascade_and_softens_the_rest():
    rep = _run(gross_weight=1.0)
    sc = _sc(rep, "cascade_5x-8")
    # 노출 100%에서 -8%/일이면 이틀째에 낙폭 -15%를 넘는다 — 브레이크가
    # 중간에 잡혀야 하고, 그러면 최종 손실이 '브레이크 없는 복리'보다 작다.
    assert sc["engaged_on_day"] is not None and sc["engaged_on_day"] <= 3, sc
    no_brake = 1_000_000.0 * (1 - 0.08) ** 5
    assert sc["equity_after"] > no_brake + 1, (
        f"브레이크가 잡혔다면서 손실은 무브레이크 복리와 같다: "
        f"{sc['equity_after']} vs {no_brake:.0f} — 개입이 장식이다")


def test_a_one_day_gap_cannot_be_softened():
    """반대 방향 — 하룻밤 갭은 브레이크가 **막을 수 없어야** 한다.

    하루짜리 충격까지 부드러워지면 그건 브레이크가 아니라 분식이다.
    """
    rep = _run(gross_weight=1.0)
    sc = _sc(rep, "gap_-20")
    assert abs(sc["equity_after"] - 800_000.0) < 1, sc
    assert sc["kill_switch_after"] == 0.5, (
        "-20% 뒤에도 시스템이 노출을 안 줄인다")


# ── ③ 현금 완충의 산수 ─────────────────────────────────────────

def test_cash_actually_cushions():
    rep = _run(gross_weight=0.4)
    sc = _sc(rep, "gap_-30")
    assert abs(sc["loss_pct"] - (-12.0)) < 0.01, (
        f"노출 40%에 시장 -30%면 계좌 -12%다: {sc['loss_pct']}% — "
        "완충을 빼면 겁주는 표, 더하면 안심시키는 표가 된다")


def test_fx_shock_hits_only_the_fx_share():
    rep = _run(gross_weight=1.0, fx_share=0.5)
    sc = _sc(rep, "krw_-15")
    assert abs(sc["loss_pct"] - (-7.5)) < 0.01, (
        f"외화 절반 계좌에 환율 -15%면 -7.5%다: {sc['loss_pct']}%")


def test_a_single_name_disaster_is_scaled_by_its_weight():
    rep = _run(worst_single_weight=0.152)
    sc = _sc(rep, "single_-50")
    assert abs(sc["loss_pct"] - (-7.6)) < 0.01, sc


# ── ④ 멈춘 시세는 '못 본다'고 말한다 ──────────────────────────

def test_the_stale_scenario_admits_blindness():
    rep = _run()
    sc = _sc(rep, "stale_5d_-20")
    assert sc.get("blind") is True
    assert sc["kill_switch_after"] is None, (
        "멈춘 시세 시나리오에서 킬스위치가 반응한 것처럼 적혀 있다 — "
        "낙폭이 장부에 없는데 무엇에 반응했다는 것인가. 이 시나리오의 "
        "요점은 '보지 못하는 동안 쌓이는 위험'이다")


# ── ⑤ 실제 장부에서 돌아간다 ───────────────────────────────────

def test_it_reads_the_real_ledger():
    import json
    rep = S.stress_from_state(str(ROOT / "state"))
    assert rep is not None, "실제 장부에서 스트레스를 못 돌린다"
    led = json.loads((ROOT / "state" / "paper" / "portfolio_ALL.json")
                     .read_text("utf-8"))
    rec = led["history"][-1]
    assert abs(rep["inputs"]["equity"] - rec["equity"]) < 0.01, (
        "스트레스 입력이 장부의 자산과 다르다 — 어제 노출로 오늘을 재고 있다")
    assert rep["inputs"]["gross_weight"] == rec["weight"]


def test_the_worst_scenario_is_the_worst():
    rep = _run()
    worst_dd = min(s["drawdown_pct"] for s in rep["scenarios"])
    assert rep["worst"]["drawdown_pct"] == worst_dd


def test_the_output_is_labeled_simulation_with_limits():
    rep = _run()
    assert rep["kind"] == "simulation"
    text = " ".join(rep["honest_limits"])
    for word in ("가정", "유동성"):
        assert word in text, f"정직한 한계에 '{word}'가 빠졌다"
