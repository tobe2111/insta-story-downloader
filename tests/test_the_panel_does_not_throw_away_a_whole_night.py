"""겹친 종목 하나 때문에 그 밤의 패널 재료를 통째로 버리지 않는다.

■ 무엇이 일어나고 있었나 (2026-09-07 장부 실측)

밤 배치는 하루에 두 번 돈다. 두 회차의 날짜별 합을 포갤 때 **같은 종목이
양쪽에 있으면 두 번 세어져 t가 거짓으로 커지므로**, 합치기가 그 밤을 통째로
버린다(``merge_daily_terms`` → ``overlap``). 그 방어 자체는 옳다.

문제는 **너무 무디다**는 것이다. 겹친 종목이 하나만 있어도 그 밤의 횡단 폭
전체를 잃는다. 실측:

    설정-밤 18건 중 3건(17%)이 겹침으로 버려졌고,
    그 3건은 **전부 2026-09-07 한 밤**이다 — 그 밤 설정 3개가 모두 사라졌다.

왜 겹치나: 멱등 가드는 "새 봉이 있으면 할 일이 남았다"로 보는데, 코인은
회차 사이(약 한 시간)에 새 봉이 생긴다. 그래서 2회차가 같은 코인을 다시 본다.

■ 고친 것

**겹치기 전에 뺀다.** 2회차는 앞 회차가 이미 기록한 종목을 담지 않는다.
남는 두 조각은 서로 겹치지 않으므로 합치기가 정확해지고, 그 밤의 나머지
종목이 살아난다.

  ⚠️ 판정 규칙은 **그대로다** — 문턱도 최소 종목 수도 안 건드렸다. 달라지는
     것은 재료를 모으는 방식뿐이라 `gate_version`을 올리지 않는다.
  ⚠️ 무엇을 뺐는지는 장부에 적는다. 조용히 빼면 "그 밤 그 종목이 원래
     없었다"와 구별되지 않는다.
  ⚠️ 기존 겹침 방어는 **그대로 둔다** — 이 장치가 못 잡는 경로(장부 읽기
     실패 등)가 남아 있고, 그때 뒤를 받치는 것이 그 방어다.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live import retrain as R  # noqa: E402
from quant.live.panel_gate import (  # noqa: E402
    MIN_PANEL_SYMBOLS, PanelCollector, daily_terms, merge_daily_terms,
    verdict_from_terms,
)

SPEC = '{"params": {}, "strategy": "ml"}'


def _series(seed: float, n: int = 130) -> pd.Series:
    idx = pd.date_range("2026-04-01", periods=n, freq="D")
    return pd.Series([seed * (1 + (i % 7) * 0.01) for i in range(n)], index=idx)


def _collector(symbols: list[str]) -> PanelCollector:
    c = PanelCollector()
    for i, s in enumerate(symbols):
        c.add(s, {SPEC: _series(0.001 * (i + 1))})
    return c


# ── 겹치기 전에 뺀다 ───────────────────────────────────────────────────
def test_the_second_run_drops_symbols_the_first_run_already_recorded():
    d = tempfile.mkdtemp()
    first = [f"crypto:C{i}" for i in range(5)]
    R.record_panel("2026-09-07", _collector(first), state_dir=d,
                   n_symbols_seen=5, roster_asof="2026-09-07")
    # 2회차는 같은 코인 5개를 **다시** 보고, 새 주식 5개를 더 본다.
    second = first + [f"us_stock:S{i}" for i in range(5)]
    rec = R.record_panel("2026-09-07", _collector(second), state_dir=d,
                         n_symbols_seen=10, roster_asof="2026-09-07")
    assert rec.get("deduped"), "겹친 종목을 뺐다는 기록이 없다"
    assert sorted(rec["deduped"][SPEC]) == sorted(first), rec["deduped"]
    got = {s["spec_key"]: s for s in rec["specs"]}[SPEC]
    assert sorted((got["daily"] or {})["symbols"]) == \
        sorted(f"us_stock:S{i}" for i in range(5)), got["daily"]["symbols"]


def test_the_night_now_merges_instead_of_being_thrown_away():
    """이 검사가 이 파일의 존재 이유다 — 실제로 잃던 밤을 되살린다."""
    d = tempfile.mkdtemp()
    first = [f"crypto:C{i}" for i in range(5)]
    R.record_panel("2026-09-07", _collector(first), state_dir=d,
                   n_symbols_seen=5, roster_asof="2026-09-07")
    second = first + [f"us_stock:S{i}" for i in range(5)]
    R.record_panel("2026-09-07", _collector(second), state_dir=d,
                   n_symbols_seen=10, roster_asof="2026-09-07")

    night = R.panel_nights(d)[-1]
    spec = {s["spec_key"]: s for s in night["specs"]}[SPEC]
    assert not spec.get("skipped"), (
        f"밤이 통째로 버려졌다: {spec.get('reason')}")
    assert spec["n_symbols"] == 10, (
        f"합쳐진 종목이 {spec['n_symbols']}개다 — 두 회차의 합집합(10)이어야 "
        "한다. 이게 패널 관문이 존재하는 이유(횡단 폭)다")


def test_the_overlap_guard_is_still_there_as_a_backstop():
    """겹치기 방어는 **그대로 둔다** — 이 장치가 못 잡는 길이 남아 있다.

    (장부를 못 읽으면 아무것도 빼지 않는데, 그때 뒤를 받치는 것이 이 방어다.)
    """
    a = daily_terms({f"s{i}": _series(0.001) for i in range(5)})
    b = daily_terms({f"s{i}": _series(0.002) for i in range(5)})
    merged = merge_daily_terms([a, b])
    assert merged.get("overlap"), "겹쳤는데 아무 말도 안 한다"
    v = verdict_from_terms(merged, t_threshold=1.35)
    assert v.get("skipped") and "두 번 세어져" in str(v.get("reason")), v


def test_dropping_is_never_silent():
    """뺀 것이 있으면 장부가 말한다 — 안 적으면 '원래 없었다'와 같아진다."""
    d = tempfile.mkdtemp()
    first = [f"crypto:C{i}" for i in range(5)]
    R.record_panel("2026-09-07", _collector(first), state_dir=d,
                   n_symbols_seen=5, roster_asof="2026-09-07")
    rec = R.record_panel("2026-09-07", _collector(first), state_dir=d,
                         n_symbols_seen=5, roster_asof="2026-09-07")
    assert "deduped" in rec and rec["deduped"][SPEC] == sorted(first)


def test_a_night_with_no_overlap_says_nothing():
    """겹친 것이 없으면 그 칸이 아예 없다 — 매일 켜진 표시는 표시가 아니다."""
    d = tempfile.mkdtemp()
    R.record_panel("2026-09-07", _collector([f"crypto:C{i}" for i in range(5)]),
                   state_dir=d, n_symbols_seen=5, roster_asof="2026-09-07")
    rec = R.record_panel("2026-09-07",
                         _collector([f"us_stock:S{i}" for i in range(5)]),
                         state_dir=d, n_symbols_seen=5,
                         roster_asof="2026-09-07")
    assert "deduped" not in rec, rec.get("deduped")


def test_a_different_night_is_not_touched():
    """앞 **밤**의 종목은 빼지 않는다 — 밤이 다르면 겹침이 아니다."""
    d = tempfile.mkdtemp()
    syms = [f"crypto:C{i}" for i in range(5)]
    R.record_panel("2026-09-06", _collector(syms), state_dir=d,
                   n_symbols_seen=5, roster_asof="2026-09-06")
    rec = R.record_panel("2026-09-07", _collector(syms), state_dir=d,
                         n_symbols_seen=5, roster_asof="2026-09-07")
    assert "deduped" not in rec, rec.get("deduped")
    assert rec["specs"], "어젯밤 종목이라고 오늘 재료를 버렸다"


def test_a_ledger_that_cannot_be_read_drops_nothing():
    """장부를 못 읽으면 **아무것도 안 뺀다.**

    한 번의 읽기 실패가 그 밤의 측정을 통째로 없애면 안 된다 — 그때는
    기존 겹침 방어가 뒤를 받친다.
    """
    c = _collector([f"crypto:C{i}" for i in range(5)])
    out = R._drop_symbols_seen_tonight(c, "/nonexistent-dir", "2026-09-07")
    assert out == {}
    assert c.symbols_for(SPEC) == 5, "장부를 못 읽었는데 재료를 버렸다"


def test_dropping_everything_leaves_a_skip_not_a_fake_verdict():
    """다 빼서 종목이 모자라면 **건너뜀**이지 통과가 아니다."""
    d = tempfile.mkdtemp()
    syms = [f"crypto:C{i}" for i in range(5)]
    R.record_panel("2026-09-07", _collector(syms), state_dir=d,
                   n_symbols_seen=5, roster_asof="2026-09-07")
    rec = R.record_panel("2026-09-07", _collector(syms), state_dir=d,
                         n_symbols_seen=5, roster_asof="2026-09-07")
    assert rec["specs"] == [], "재료가 0인데 판정이 나왔다"
    assert rec["n_specs_judged"] == 0


def test_the_collector_drop_only_touches_the_named_spec():
    c = PanelCollector()
    c.add("crypto:A", {SPEC: _series(0.001), "other": _series(0.002)})
    gone = c.drop(SPEC, ["crypto:A"])
    assert gone == ["crypto:A"]
    assert c.symbols_for(SPEC) == 0
    assert c.symbols_for("other") == 1, "관계없는 설정의 재료를 건드렸다"


def test_the_decision_rule_did_not_move():
    """문턱과 최소 종목 수는 **그대로다** — 바뀐 것은 재료 수집뿐이다.

    관문의 자를 건드렸다면 `gate_version`을 올려야 하는데, 이 작업은 그
    자를 안 건드렸다. 그 사실을 못 박는다.
    """
    assert MIN_PANEL_SYMBOLS == 5
    from quant.live.panel_gate import MIN_PANEL_DATES
    assert MIN_PANEL_DATES == 40
    src = (ROOT / "quant" / "live" / "retrain.py").read_text("utf-8")
    assert "`gate_version`을 올리지 않는다" in src, (
        "규칙을 안 건드렸다는 근거가 코드에 안 적혀 있다")
