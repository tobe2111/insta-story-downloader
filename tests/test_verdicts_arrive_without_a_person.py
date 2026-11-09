"""판정일이 오면 판정은 **사람 없이** 난다 (2026-11-09 감사 361).

사장님: "영구적이어야 해." 판정일이 지나면 기계가 등록된 통계·보정으로 한 번 재고
얼린다. 다시 재지 않는다(판정일 뒤 자료로 판정이 바뀌면 골대 이동이다).
"""
from __future__ import annotations

import json

from quant.live import final_judgement as F
from quant.live.prereg import PREREGISTERED, ml_retire_after


def _ledger(path, rets, start="2026-08-20"):
    import datetime as dt
    eq, rows = 1_000_000.0, []
    d0 = dt.date.fromisoformat(start)
    for i, r in enumerate(rets):
        eq *= 1 + r
        rows.append({"date": str(d0 + dt.timedelta(days=i)), "equity": eq})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"history": rows}), "utf-8")


def test_a_due_experiment_is_judged_once_with_its_registered_correction(tmp_path):
    import random
    rnd = random.Random(0)
    base = [rnd.gauss(0, 0.005) for _ in range(200)]
    _ledger(tmp_path / "alloc_ladder" / "hrp.json", base)
    for alt in ("erc", "equal", "inv_vol"):
        _ledger(tmp_path / "alloc_ladder" / f"{alt}.json", [b - 0.004 for b in base])
    judge = PREREGISTERED["alloc_ladder"]["judge_on"]
    assert "alloc_ladder" not in F.judge_due(str(tmp_path), today=judge), "판정일 당일에 미리 판정했다"
    out = F.judge_due(str(tmp_path), today="2027-05-01")
    rec = out["alloc_ladder"]
    assert rec["comparisons"] == 3
    p = rec["pairs"]["alloc:hrp-erc"]
    assert abs(p["alpha"] - 0.05 / 3) < 1e-4 and rec["code"] == "significant"
    assert p["n"] < 200, "판정일 뒤 자료까지 썼다"
    # 얼린다 — 장부가 바뀌어도 다시 재지 않는다.
    _ledger(tmp_path / "alloc_ladder" / "erc.json", base)
    again = F.judge_due(str(tmp_path), today="2027-06-01")
    assert again["alloc_ladder"] == rec


def test_closed_experiments_are_not_judged_and_say_so(tmp_path):
    out = F.judge_due(str(tmp_path), today="2027-05-01")
    assert out["intraday_1h"]["code"] == "closed" and not out["intraday_1h"]["decided"]
    assert out["gen2_concentration"]["code"] in ("no_data", "thin")


def test_the_trend_core_thresholds_match_the_registration():
    text = PREREGISTERED["trend_core_live"]["expectation"]
    assert f"샤프 ≥ {F.TREND_MEETS}" in text and "0~0.5" in text and "−15%" in text


def test_the_old_ml_system_stops_itself_after_its_last_judgement():
    from quant import cli
    day = ml_retire_after()
    assert cli._ml_retired(today=day) is None
    assert cli._ml_retired(today="2099-01-01") == day


def test_the_daily_batch_and_the_trust_page_carry_the_verdicts():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    assert 'status["prereg"]["final"] = judge_due(state_dir)' in (
        root / "quant" / "live" / "daily.py").read_text("utf-8")
    html = (root / "docs" / "trust.html").read_text("utf-8")
    assert 'id="final-judgements"' in html and "st.prereg||{}).final" in html
    for code in ("closed", "no_data", "thin", "no_difference", "significant",
                 "meets", "below_floor", "fail"):
        assert f"{code}:" in html
