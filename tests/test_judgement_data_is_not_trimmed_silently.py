"""감사 376 — 사전 등록 판정의 재료가 앞에서 잘리면 말한다.

감사 374·375: 장부는 회차 **개수**로 잘리고 판정 창은 **날짜**로 적혀 있어, 회차 주기가
바뀌자 판정 재료가 조용히 줄었다. 자리마다 고치는 대신 성질(첫 날짜가 뒤로 가지
않는다)을 매일 잰다.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _rows(start_day: int, n: int):
    return [{"date": f"2026-09-{d:02d}", "equity": 1_000_000 + d} for d in range(start_day, start_day + n)]


def _write(tmp, start_day, n=20):
    d = tmp / "alloc_ladder"
    d.mkdir(exist_ok=True)
    for arm in ("hrp", "erc", "equal", "inv_vol"):
        (d / f"{arm}.json").write_text(json.dumps({"history": _rows(start_day, n)}))


def test_a_ledger_that_loses_its_head_is_reported(tmp_path):
    from quant.live.prereg_coverage import coverage
    _write(tmp_path, 1)
    first = coverage(str(tmp_path), today="2026-09-25")
    assert not first["lost"] and first["pairs"]["alloc:hrp-erc"]["first"] == "2026-09-01"
    _write(tmp_path, 6)                      # 앞 닷새가 잘렸다 — 진짜 사고의 모양
    second = coverage(str(tmp_path), today="2026-09-26")
    assert "alloc:hrp-erc" in second["lost"], second
    p = second["pairs"]["alloc:hrp-erc"]
    assert p["first_ever"] == "2026-09-01" and p["first"] == "2026-09-06"


def test_growing_data_is_not_an_alarm(tmp_path):
    from quant.live.prereg_coverage import coverage
    _write(tmp_path, 1, 10)
    coverage(str(tmp_path), today="2026-09-12")
    _write(tmp_path, 1, 20)
    assert coverage(str(tmp_path), today="2026-09-22")["lost"] == []


def test_a_late_start_is_named(tmp_path):
    from quant.live.prereg import PREREGISTERED
    from quant.live.prereg_coverage import coverage, LATE_GRACE_DAYS
    import datetime as dt
    start = dt.date.fromisoformat(PREREGISTERED["alloc_ladder"]["start"])
    late = start + dt.timedelta(days=LATE_GRACE_DAYS + 3)
    d = tmp_path / "alloc_ladder"
    d.mkdir()
    rows = [{"date": str(late + dt.timedelta(days=i)), "equity": 1.0 + i} for i in range(5)]
    for arm in ("hrp", "erc", "equal", "inv_vol"):
        (d / f"{arm}.json").write_text(json.dumps({"history": rows}))
    out = coverage(str(tmp_path), today=str(late + dt.timedelta(days=6)))
    assert "alloc:hrp-erc" in out["late_start"]


def test_closed_and_judged_experiments_are_not_watched(tmp_path):
    from quant.live.prereg_coverage import coverage
    (tmp_path / "final_judgements.json").write_text(json.dumps({"alloc_ladder": {}}))
    _write(tmp_path, 1)
    out = coverage(str(tmp_path), today="2026-09-25")
    assert not any(v["experiment"] in ("alloc_ladder", "cadence_ladder", "limit_shadow")
                   for v in out["pairs"].values())


def test_the_alarm_fires_from_the_real_status_shape(tmp_path):
    from quant.live.flag_watch import _current_flags
    from quant.live.prereg_coverage import coverage
    _write(tmp_path, 1)
    coverage(str(tmp_path), today="2026-09-25")
    _write(tmp_path, 6)
    status = {"prereg": {"coverage": coverage(str(tmp_path), today="2026-09-26")}}
    keys = [k for k in _current_flags(status, today="2026-09-26") if k.startswith("prereg_material_lost:")]
    assert keys and "alloc:hrp-erc" in keys[0]


def test_it_is_wired_into_the_batch_and_the_trust_page():
    daily = ((ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
            + (ROOT / "quant" / "live" / "status_doc.py").read_text("utf-8"))
    assert 'status["prereg"]["coverage"] = _prereg_coverage(state_dir)' in daily
    trust = (ROOT / "docs" / "trust.html").read_text("utf-8")
    assert 'id="prereg-coverage"' in trust and "(st.prereg||{}).coverage" in trust


def test_the_round_cadence_case_from_audit_375_is_caught(tmp_path):
    """감사 375의 진짜 모양 — 운용 계좌 history가 400회차에서 잘린다(예전 읽기 방식)."""
    from quant.live import sequential as S
    rows = [{"time": f"2026-11-{10 + i // 3:02d}T0{i % 3}:00:00+09:00", "equity": 1.0 + i}
            for i in range(30)]
    cover: dict = {}
    S._pair("x", rows[-12:], rows, cover=cover)
    assert cover["x"]["first"] == "2026-11-16" and cover["x"]["n"] == 4
