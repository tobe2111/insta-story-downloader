"""현금이 왜 남는지 설명되고, 넘친 예산의 처리가 **기계에 의해** 재지는가 (감사 332).

사장님 질문(2026-10-01): *"현금은 왜 계속 이 비율로 들고있는거야?"* →
(2026-10-06) *"둘 다 진행."*

지키는 것:
  ① 최종 비중 식은 **한 곳**(`_final_weight`)에만 있다 — 본 계좌와 그림자가
     같은 식을 쓴다.
  ② 재분배는 상한을 넘지 않고, 예산이 0인 종목에는 주지 않고, 갈 곳이 있으면
     예산을 다 쓴다. 버림은 본 계좌와 같은 식이다.
  ③ 현금 단계표는 장부의 실제 값으로 이어지고, 게이트 몫을 따로 보여 준다.
  ④ 그림자 두 계좌는 **예산 처리만** 다르다 — 넘침이 없는 날 둘은 같다.
     1봉 지연 · 비용 차감 · 같은 봉 멱등 · 과거 봉 거부.
  ⑤ 공개 자료는 비용 기준과 등록된 판정일을 싣는다.
  ⑥ 배선 — 본 계좌 회차에서만 돌고, 장부·status·화면까지 닿는다.
  ⑦ 등록의 시작일은 장부의 첫 기록과 같다(장부가 생긴 뒤부터 검사가 문다).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from quant.live import budget_shadow as BS
from quant.live import daily as D

ROOT = Path(__file__).resolve().parent.parent


# ── ① 식은 한 곳 ─────────────────────────────────────────────────
def test_the_final_weight_is_one_formula():
    w = D._final_weight(0.5, eff_scale=0.8, vscale=3.0, guard=0.5, valid=0.5,
                        kcap=None, slice_=0.1)
    assert w == pytest.approx(0.5 * 0.8 * 3.0 * 0.5 * 0.5 * 0.1)
    capped = D._final_weight(0.5, eff_scale=1.0, vscale=10.0, kcap=0.25,
                             slice_=0.1)
    assert capped == pytest.approx(0.25 * 0.1)       # 켈리 상한은 슬라이스 전
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    body = src.split("def _target_w(", 1)[1].split("\n    # ", 1)[0]
    assert "_final_weight(" in body and "np.clip" not in body, (
        "본 계좌의 목표 식이 다시 따로 적혔다 — 그림자와 갈라진다")


# ── ② 재분배 ────────────────────────────────────────────────────
def test_redistribution_respects_the_cap_and_spends_what_it_can():
    raw = {"bond": 0.40, "usd": 0.30, "a": 0.10, "b": 0.10, "c": 0.10}
    cap = 0.25
    out = BS.redistribute(raw, cap)
    assert max(out.values()) <= cap + 1e-12
    assert sum(out.values()) == pytest.approx(1.0)        # 갈 곳이 있으면 다 쓴다
    assert out["a"] == pytest.approx(out["b"]) == pytest.approx(out["c"])
    kept = BS.discard(raw, cap)
    assert sum(kept.values()) == pytest.approx(0.25 + 0.25 + 0.3)


def test_redistribution_never_funds_a_symbol_the_allocator_gave_nothing():
    out = BS.redistribute({"x": 0.9, "y": 0.0, "z": 0.1}, 0.3)
    assert out["y"] == 0.0
    assert out["x"] == pytest.approx(0.3) and out["z"] == pytest.approx(0.3)


def test_when_everything_is_capped_the_rest_has_nowhere_to_go():
    out = BS.redistribute({"a": 0.6, "b": 0.6}, 0.3)
    assert out == {"a": 0.3, "b": 0.3}


def test_discard_matches_the_main_account_rule():
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert "slices = {k: min(v, cap) for k, v in raw_slices.items()}" in src
    assert BS.discard({"a": 0.2, "b": 0.01}, 0.075) == {"a": 0.075, "b": 0.01}


# ── ③ 현금 단계표 ────────────────────────────────────────────────
def _waterfall(**over):
    kw = dict(weights={"a": 0.5, "b": 0.5, "c": 0.0},
              raw_slices={"a": 0.6, "b": 0.3, "c": 0.1},
              slices={"a": 0.4, "b": 0.3, "c": 0.1},
              eff_scale=1.0, vscale=4.0, guard_damp={}, valid_damp={"a": 0.5,
                                                                    "b": 0.0},
              kelly_caps={}, fitted={"a": 0.38}, n=3,
              valid_grades={"a": {"grade": "경고"}, "b": {"grade": "실패"},
                            "c": {"grade": "통과"}, "retired": {"grade": "실패"}},
              deferred={"c": 1})
    kw.update(over)
    return D.cash_waterfall(**kw)


def test_the_waterfall_walks_the_same_steps_as_the_order():
    w = _waterfall()
    assert w["budget_raw"] == pytest.approx(1.0)
    assert w["budget"] == pytest.approx(0.8)               # 넘친 0.2를 버렸다
    assert w["signal"] == pytest.approx(0.5 * 0.4 + 0.5 * 0.3)
    assert w["risk"] == pytest.approx(4 * (0.5 * 0.4 + 0.5 * 0.3))
    assert w["gated"] == pytest.approx(4 * 0.5 * 0.5 * 0.4)    # b는 게이트 0
    assert w["applied"] == pytest.approx(0.38)
    assert w["cash"] == pytest.approx(0.62)
    # 게이트는 실제로 곱한 배수로 센다(오늘 판단한 종목만): a 0.5 · b 0 · c 1
    assert w["gate_counts"] == {"full": 1, "partial": 1, "zero": 1}
    assert w["deferred_lots"] == 1


def test_the_waterfall_never_breaks_the_ledger():
    assert D._safe_waterfall(weights=None) is None


# ── ④ 그림자 두 계좌 ─────────────────────────────────────────────
def _final(k, w, slice_, vs):
    return D._final_weight(w, eff_scale=1.0, vscale=vs, slice_=slice_)


def _rets(keys):
    import numpy as np
    rng = np.random.default_rng(3)
    return {k: pd.Series(rng.normal(0, 0.01, 90)) for k in keys}


def _step(tmp, bar, marks, raw, weights=None, cap=0.5):
    keys = list(raw)
    return BS.run_budget_shadow(
        bar=bar, weights=weights or {k: 1.0 for k in keys}, raw_slices=raw,
        cap=cap, rets_map=_rets(keys), tgt_vol=0.10, final=_final,
        marks=marks, state_dir=str(tmp))


def test_without_overflow_the_two_accounts_are_identical(tmp_path):
    raw = {"us_stock:A": 0.3, "us_stock:B": 0.3}
    r1 = _step(tmp_path, "2026-10-06", {"us_stock:A": 100, "us_stock:B": 50}, raw)
    r2 = _step(tmp_path, "2026-10-07", {"us_stock:A": 110, "us_stock:B": 50}, raw)
    for r in (r1, r2):
        assert r["arms"]["discard"] == r["arms"]["redistribute"]


def test_with_overflow_only_the_budget_differs_and_the_lag_is_one_bar(tmp_path):
    raw = {"us_stock:A": 0.9, "us_stock:B": 0.1}
    r1 = _step(tmp_path, "2026-10-06", {"us_stock:A": 100, "us_stock:B": 50}, raw)
    a1 = r1["arms"]
    assert a1["discard"]["budget"] == pytest.approx(0.6)          # 0.5 + 0.1
    assert a1["redistribute"]["budget"] == pytest.approx(1.0)     # 0.5 + 0.5
    # 첫 봉은 전일 목표가 없어 가격이 움직여도 수익이 없다(1봉 지연)
    assert a1["discard"]["day_ret"] == 0.0 == a1["redistribute"]["day_ret"]
    r2 = _step(tmp_path, "2026-10-07", {"us_stock:A": 100, "us_stock:B": 60}, raw)
    a2 = r2["arms"]
    assert a2["redistribute"]["day_ret"] > a2["discard"]["day_ret"] > 0
    assert a1["discard"]["equity"] < BS.START_CASH            # 비용을 문다


def test_same_bar_is_idempotent_and_a_backwards_bar_is_refused(tmp_path):
    raw = {"us_stock:A": 0.4}
    m = {"us_stock:A": 100}
    r1 = _step(tmp_path, "2026-10-07", m, raw)
    assert _step(tmp_path, "2026-10-07", m, raw) == r1
    assert _step(tmp_path, "2026-10-06", m, raw) is None
    st = json.loads((tmp_path / BS.FILE).read_text("utf-8"))
    assert [r["date"] for r in st["history"]] == ["2026-10-07"]


def test_gated_symbols_stay_out_of_both_accounts(tmp_path):
    """게이트가 0으로 만든 종목은 재분배 쪽에서도 0이다 — 같은 안전장치."""
    def final(k, w, s, vs):
        return D._final_weight(w, eff_scale=1.0, vscale=vs, slice_=s,
                               valid=0.0 if k == "us_stock:A" else 1.0)
    raw = {"us_stock:A": 0.9, "us_stock:B": 0.1}
    BS.run_budget_shadow(bar="2026-10-06", weights={k: 1.0 for k in raw},
                         raw_slices=raw, cap=0.5, rets_map=_rets(raw),
                         tgt_vol=0.10, final=final,
                         marks={"us_stock:A": 1, "us_stock:B": 1},
                         state_dir=str(tmp_path))
    st = json.loads((tmp_path / BS.FILE).read_text("utf-8"))
    for arm in BS.ARMS:
        assert "us_stock:A" not in st["arms"][arm]["prev_weights"]


# ── ⑤ 공개 자료 ──────────────────────────────────────────────────
def test_the_public_block_names_cost_basis_and_the_registered_date(tmp_path):
    raw = {"us_stock:A": 0.9, "us_stock:B": 0.1}
    for i, pb in enumerate([50, 55, 52, 58]):
        _step(tmp_path, f"2026-10-0{6 + i}", {"us_stock:A": 100, "us_stock:B": pb}, raw)
    pub = BS.budget_shadow_public(str(tmp_path))
    assert pub["cost_basis_bp"]
    from quant.live.prereg import PREREGISTERED
    assert pub["judge_on"] == PREREGISTERED["budget_shadow"]["judge_on"]
    assert pub["paired"]["n"] == 3 and pub["days"] == 4
    assert set(pub["arms"]) == set(BS.ARMS)
    assert BS.budget_shadow_public(str(tmp_path / "none")) is None


# ── ⑥ 배선 ───────────────────────────────────────────────────────
def test_the_wiring_reaches_ledger_status_and_screen():
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert '"cash_waterfall": _safe_waterfall(' in src
    assert 'status["budget_shadow"] = budget_shadow_public(state_dir)' in src
    call = src.split("from quant.live.budget_shadow import run_budget_shadow", 1)[0]
    assert call.rstrip().endswith("try:") and "if use_champions:" in call[-200:], (
        "그림자가 본 계좌 회차 밖에서도 돈다 — 대조군 신호가 섞인다(2026-09-07)")
    for page in ("index.html", "paper.html"):
        html = (ROOT / "docs" / page).read_text("utf-8")
        assert "data-cash-waterfall" in html and "assets/cash-waterfall.js" in html


def _node():
    exe = shutil.which("node")
    assert exe, "node가 없으면 건너뛰지 않고 실패한다"
    return exe


def test_the_card_reads_the_last_ledger_row_that_has_the_waterfall():
    code = ("global.window={};require(%r);const C=window.CashWaterfall;"
            "const st={paper:{'portfolio:ALL':{history:["
            "{date:'2026-10-05',cash_waterfall:{applied:0.3}},{date:'2026-10-06'}]}}};"
            "process.stdout.write(JSON.stringify([C.lastRow(st).date,"
            "C.STAGES.map(s=>s[0])]))"
            % str(ROOT / "docs" / "assets" / "cash-waterfall.js"))
    out = json.loads(subprocess.run([_node(), "-e", code], capture_output=True,
                                    text=True, check=True).stdout)
    assert out[0] == "2026-10-05"
    keys = set(_waterfall())
    assert set(out[1]) <= keys, "화면의 단계 이름이 장부의 칸과 다르다"


# ── ⑦ 등록 시작일 = 장부의 첫 기록 ───────────────────────────────
def test_the_registered_start_is_the_first_ledger_row():
    from quant.live.prereg import PREREGISTERED
    path = ROOT / "state" / BS.FILE
    if not path.exists():
        return               # 첫 밤 배치 전 — 아직 물 장부가 없다
    hist = json.loads(path.read_text("utf-8"))["history"]
    first = min(r["date"] for r in hist)
    assert first == PREREGISTERED["budget_shadow"]["start"], (
        f"등록한 시작일과 실제 첫 기록({first})이 다르다 — 시작일은 실측이어야 "
        "한다(prereg 규칙). 다르면 AMENDMENTS에 날짜·이유와 함께 고친다")


def test_an_unmeasured_grade_is_not_counted_as_a_pass():
    """'미측정'은 배수가 경고와 같은 절반이다 — 이름으로 세면 통과처럼 보인다."""
    w = _waterfall(valid_damp={"a": 0.5, "b": 0.5, "c": 0.5},
                   valid_grades={"a": {"grade": "미측정"}, "b": {"grade": "만료"},
                                 "c": {"grade": "경고"}})
    assert w["gate_counts"] == {"full": 0, "partial": 3, "zero": 0}
