"""밤의 두 회차를 **나중에 합칠 수 있는가** — 재료가 장부에 남는지 검사한다.

■ 왜 (2026-09-01 장부 실측)

밤 배치는 하루 두 번 돌고, 두 번째 회차는 앞 회차가 이미 심사한 종목을
건너뛴다. 그래서 한 밤의 두 줄은 **서로 겹치지 않는 종목**을 본다:

    밤 2026-08-31 : 12종목 + 5종목  (같은 명단 3설정)
    밤 2026-09-01 : 13종목 + 11종목 (같은 명단 3설정)

합치면 횡단 폭이 거의 두 배다 — 패널 관문이 존재하는 이유 그 자체다.
그런데 장부에 남던 것은 설정별 **요약**(평균·t·날짜 수)뿐이라 합칠 방법이
없었다. 서로 다른 종목 집합에서 나온 두 t로 union 의 t 를 만들 수는 없다.

그리고 이 재료는 **지나가면 되살릴 수 없다** — 그 밤의 백테스트를 통째로
다시 돌려야 하고 챔피언은 그 사이 바뀐다. 그래서 승격을 옮기기(작업 #56)
전에 재료부터 남긴다.
"""
from __future__ import annotations

import json
import math

import pandas as pd
import pytest

from quant.live.panel_gate import (MIN_PANEL_SYMBOLS, PanelCollector,
                                   daily_terms, merge_daily_terms,
                                   panel_verdict, symbol_terms,
                                   verdict_from_terms)

SPEC = json.dumps({"strategy": "bollinger", "params": {"n": 20}},
                  sort_keys=True)
T_REF = 1.35


def _series(seed: int, n: int = 200, start: str = "2026-01-01") -> pd.Series:
    """결정적 계열 — 난수 표류로 판정이 흔들리지 않게 한다."""
    idx = pd.date_range(start, periods=n, freq="D")
    vals = [0.01 * math.sin(seed * 0.7 + i * 0.31) + 0.0004 * seed
            for i in range(n)]
    return pd.Series(vals, index=idx)


def _panel(n_symbols: int = 12) -> dict[str, pd.Series]:
    return {f"KRX:{i:06d}": _series(i + 1) for i in range(n_symbols)}


def _split(per: dict, first: int) -> tuple[dict, dict]:
    keys = sorted(per)
    return ({k: per[k] for k in keys[:first]},
            {k: per[k] for k in keys[first:]})


def test_merging_two_runs_gives_exactly_the_one_pot_answer():
    """두 회차를 합친 판정 = 처음부터 한 통에 담았을 때의 판정."""
    per = _panel(12)
    whole = panel_verdict(per, t_threshold=T_REF)
    assert not whole["skipped"]

    a, b = _split(per, 7)
    merged = merge_daily_terms([daily_terms(a), daily_terms(b)])
    got = verdict_from_terms(merged, {**symbol_terms(a), **symbol_terms(b)},
                             t_threshold=T_REF)

    assert not got["skipped"]
    assert got["n_symbols"] == whole["n_symbols"] == 12
    assert got["n_dates"] == whole["n_dates"]
    assert got["t_stat"] == pytest.approx(whole["t_stat"], rel=1e-6)
    assert got["mean_diff"] == pytest.approx(whole["mean_diff"], rel=1e-6)
    assert got["pass"] is whole["pass"]


def test_one_run_alone_really_says_something_else():
    """대조군 — 안 합치면 답이 다르다.

    이게 없으면 위 시험은 "아무거나 똑같다"를 통과할 수 있다.
    """
    per = _panel(12)
    whole = panel_verdict(per, t_threshold=T_REF)
    a, _ = _split(per, 7)
    half = verdict_from_terms(daily_terms(a), symbol_terms(a),
                              t_threshold=T_REF)
    assert not half["skipped"]
    assert half["n_symbols"] == 7
    assert half["t_stat"] != pytest.approx(whole["t_stat"], rel=1e-3)


def test_the_side_by_side_symbol_gate_survives_the_merge():
    """①안의 병기(종목별 판정)도 합친 뒤 그대로 살아 있다."""
    per = _panel(12)
    whole = panel_verdict(per, t_threshold=0.0)
    a, b = _split(per, 7)
    merged = merge_daily_terms([daily_terms(a), daily_terms(b)])
    got = verdict_from_terms(merged, {**symbol_terms(a), **symbol_terms(b)},
                             t_threshold=0.0)
    assert got["symbol_t_n"] == whole["symbol_t_n"] == 12
    assert got["symbol_pass"] == whole["symbol_pass"]
    assert got["symbol_wins"] == whole["symbol_wins"]
    assert got["symbol_t_median"] == pytest.approx(whole["symbol_t_median"],
                                                   abs=1e-3)


def test_an_overlapping_symbol_is_refused_not_double_counted():
    """겹친 종목은 두 번 세지 않는다 — 합치지 않고 겹쳤다고 말한다."""
    per = _panel(12)
    a, b = _split(per, 7)
    b = dict(b, **{k: per[k] for k in sorted(a)[:2]})   # 2종목 겹치게
    merged = merge_daily_terms([daily_terms(a), daily_terms(b)])
    assert merged.get("overlap"), "겹침을 못 봤다"
    assert len(merged["overlap"]) == 2
    got = verdict_from_terms(merged, None, t_threshold=T_REF)
    assert got["skipped"] is True
    assert "겹" in got["reason"]


def test_double_counting_would_have_tilted_the_average():
    """대조군 — 겹침을 안 막으면 겹친 종목이 **두 표를 행사한다.**

    회차 A(종목 0~4)와 회차 B(종목 3~7)가 두 종목을 공유하면, 합집합은
    8종목인데 날짜별 개수는 10으로 세어진다. 그러면 겹친 두 종목이 횡단
    평균에서 두 배의 무게를 갖고, 패널 t가 **그 두 종목 쪽으로 기운다.**
    """
    per = _panel(8)
    keys = sorted(per)
    a = {k: per[k] for k in keys[:5]}
    b = {k: per[k] for k in keys[3:]}
    truth = panel_verdict(per, t_threshold=T_REF)

    merged = merge_daily_terms([daily_terms(a), daily_terms(b)])
    assert merged["overlap"] == keys[3:5]
    assert verdict_from_terms(merged, None, t_threshold=T_REF)["skipped"] is True

    merged.pop("overlap")            # 안전장치를 일부러 떼고 본다
    tilted = verdict_from_terms(merged, None, t_threshold=T_REF)
    assert max(merged["counts"]) == 10 > len(merged["symbols"]) == 8
    assert tilted["t_stat"] != pytest.approx(truth["t_stat"], rel=1e-3)


def test_the_material_is_kept_before_the_min_symbol_filter():
    """거르기는 **합친 뒤** 한 번만 — 회차마다 거르면 되살아나지 않는다.

    두 회차가 각각 3종목뿐인 날은 회차 안에서는 최소 종목 수(5)를 못 채운다.
    합치면 6종목이 되어 그 날이 살아나야 한다.
    """
    thin = pd.Timestamp("2026-06-01")
    per = _panel(6)
    a, b = _split(per, 3)
    ta, tb = daily_terms(a), daily_terms(b)
    assert ta["counts"][ta["dates"].index(thin.strftime("%Y-%m-%d"))] == 3
    va = verdict_from_terms(ta, None, t_threshold=T_REF)
    assert va["skipped"] is True     # 3종목이라 회차 혼자서는 못 잰다
    merged = merge_daily_terms([ta, tb])
    i = merged["dates"].index(thin.strftime("%Y-%m-%d"))
    assert merged["counts"][i] == 6 >= MIN_PANEL_SYMBOLS
    assert not verdict_from_terms(merged, None, t_threshold=T_REF)["skipped"]


def test_the_collector_hands_over_material_for_every_spec():
    """수집기가 설정마다 합산 재료를 내놓는다."""
    coll = PanelCollector()
    per = _panel(8)
    for key, series in per.items():
        coll.add(key, {SPEC: series})
    terms = coll.terms_for(SPEC)
    assert terms["symbols"] == sorted(per)
    assert len(terms["dates"]) == len(terms["sums"]) == len(terms["counts"])
    assert len(terms["symbol_terms"]) == 8
    assert all(len(v) == 2 for v in terms["symbol_terms"].values())


# ── 장부와 밤 단위 읽기 ────────────────────────────────────────────────────

def _record(tmp_path, per: dict, asof: str, roster: str):
    from quant.live.retrain import record_panel
    coll = PanelCollector()
    for key, series in per.items():
        coll.add(key, {SPEC: series})
    return record_panel(asof, coll, str(tmp_path), n_symbols_seen=len(per),
                        roster_asof=roster)


def _ledger(tmp_path) -> list[dict]:
    from quant.live.retrain import PANEL_FILE
    with open(tmp_path / PANEL_FILE, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def test_the_ledger_actually_carries_the_merge_material(tmp_path):
    """장부 줄마다 합산 재료가 실린다 — 안 실리면 그 밤은 영영 못 합친다."""
    _record(tmp_path, _panel(8), "2026-09-02", "2026-09-02")
    spec = _ledger(tmp_path)[0]["specs"][0]
    daily = spec["daily"]
    assert len(daily["symbols"]) == 8
    assert len(daily["dates"]) == len(daily["sums"]) == len(daily["counts"])
    assert len(spec["symbol_terms"]) == 8


def test_the_night_is_read_by_roster_date_not_by_bar_date(tmp_path):
    """밤의 열쇠는 ``roster_asof``다.

    ``asof``는 그 회차가 돈 종목들의 마지막 봉 날짜라 회차마다 다르다.
    실제 장부(2026-09-01)에서 한 밤의 두 줄이 09-01·08-31로 갈렸고,
    ``asof=2026-08-31`` 한 칸에는 **서로 다른 두 밤**의 줄이 들어 있었다.
    """
    from quant.live.retrain import panel_nights
    per = _panel(12)
    a, b = _split(per, 7)
    _record(tmp_path, a, "2026-09-01", "2026-09-01")   # 밤 9/1 1회차
    _record(tmp_path, b, "2026-08-31", "2026-09-01")   # 밤 9/1 2회차
    _record(tmp_path, _panel(6), "2026-08-31", "2026-08-31")   # 밤 8/31

    nights = {n["night"]: n for n in panel_nights(str(tmp_path))}
    assert sorted(nights) == ["2026-08-31", "2026-09-01"]
    assert nights["2026-09-01"]["n_runs"] == 2
    assert nights["2026-08-31"]["n_runs"] == 1

    # 대조군 — asof 로 묶었으면 밤 9/1이 쪼개지고, 8/31 칸에 두 밤이 섞인다.
    by_asof: dict[str, set] = {}
    for rec in _ledger(tmp_path):
        by_asof.setdefault(rec["asof"], set()).add(rec["roster_asof"])
    assert by_asof["2026-08-31"] == {"2026-08-31", "2026-09-01"}
    assert by_asof["2026-09-01"] == {"2026-09-01"}


def test_reading_a_night_gives_the_one_pot_answer(tmp_path):
    """두 회차로 나뉜 밤을 읽으면 한 통에 담았을 때와 같은 판정이 나온다."""
    from quant.live.retrain import PANEL_T_REF, panel_nights
    per = _panel(12)
    a, b = _split(per, 7)
    _record(tmp_path, a, "2026-09-01", "2026-09-01")
    _record(tmp_path, b, "2026-08-31", "2026-09-01")

    night = panel_nights(str(tmp_path))[0]
    assert night["n_symbols_seen"] == 12
    spec = night["specs"][0]
    assert spec["n_runs"] == 2
    whole = panel_verdict(per, t_threshold=PANEL_T_REF)
    assert spec["n_symbols"] == 12
    assert spec["t_stat"] == pytest.approx(whole["t_stat"], rel=1e-6)
    assert not night["unmergeable"]


def test_an_old_line_without_material_says_so_instead_of_vanishing(tmp_path):
    """재료 없는 옛 줄은 **못 합쳤다고 말한다** — 조용히 빠지지 않는다.

    빠지면 "그 밤엔 그 설정이 없었다"와 구별할 수 없고, 그 착각은 나중에
    "왜 이 설정이 저 밤에 없나"를 시장 탓으로 읽게 만든다.
    """
    from quant.live.retrain import PANEL_FILE, panel_nights
    _record(tmp_path, _panel(8), "2026-09-02", "2026-09-02")
    rows = _ledger(tmp_path)
    for spec in rows[0]["specs"]:          # 재료를 지워 옛 줄 모양으로
        spec.pop("daily", None)
        spec.pop("symbol_terms", None)
    with open(tmp_path / PANEL_FILE, "w", encoding="utf-8") as f:
        for rec in rows:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    night = panel_nights(str(tmp_path))[0]
    assert night["specs"] == []
    assert night["unmergeable"] == [SPEC]


def test_a_thin_day_is_still_dropped_after_merging():
    """합친 **뒤에도** 종목이 모자란 날은 버린다.

    거르기를 뒤로 미룬 것이지 없앤 것이 아니다. 그날 두 종목만 남았는데
    다른 날과 똑같이 세면, 그 두 종목의 잡음이 통째로 패널 통계에 들어온다.
    """
    thin = "2026-06-01"
    per = _panel(8)
    for k in sorted(per)[2:]:              # 6종목의 그 날 값을 지운다
        per[k] = per[k].drop(pd.Timestamp(thin))
    terms = daily_terms(per)
    i = terms["dates"].index(thin)
    assert terms["counts"][i] == 2         # 재료에는 그대로 남고
    got = verdict_from_terms(terms, None, t_threshold=T_REF)
    assert got["n_dates"] == len(terms["dates"]) - 1   # 판정에서만 빠진다
