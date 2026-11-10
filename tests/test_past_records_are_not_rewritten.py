"""감사 378 — 지나간 기록이 조용히 바뀌면 커밋 전에 잡는다."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from quant.live.ledger_history import rewritten_past

ROOT = Path(__file__).resolve().parents[1]


def _rows(*pairs):
    return [{"date": d, "equity": e} for d, e in pairs]


def test_an_edited_old_row_is_reported():
    prev = _rows(("2026-11-01", 100), ("2026-11-02", 101), ("2026-11-03", 102))
    cur = _rows(("2026-11-01", 100), ("2026-11-02", 999), ("2026-11-03", 102),
                ("2026-11-04", 103))
    got = rewritten_past(prev, cur)
    assert got == [{"date": "2026-11-02", "what": "changed", "fields": ["equity"]}]


def test_a_vanished_old_row_is_reported():
    prev = _rows(("2026-11-01", 100), ("2026-11-02", 101), ("2026-11-03", 102))
    cur = _rows(("2026-11-01", 100), ("2026-11-03", 102))
    assert rewritten_past(prev, cur) == [{"date": "2026-11-02", "what": "gone"}]


def test_designed_changes_are_allowed():
    prev = _rows(("2026-11-01", 100), ("2026-11-02", 101), ("2026-11-03", 102))
    # 마지막 날 되돌림 · 앞에서 잘림 · 새 날짜 추가
    cur = _rows(("2026-11-02", 101), ("2026-11-03", 555), ("2026-11-04", 103))
    assert rewritten_past(prev, cur) == []
    # 빠진 봉 복구 — 사이에 새 날짜가 끼어든다
    prev2 = _rows(("2026-11-01", 100), ("2026-11-03", 102), ("2026-11-04", 103))
    cur2 = _rows(("2026-11-01", 100), ("2026-11-02", 101), ("2026-11-03", 102),
                 ("2026-11-04", 103))
    assert rewritten_past(prev2, cur2) == []


def test_an_emptied_ledger_is_reported():
    prev = _rows(("2026-11-01", 100), ("2026-11-02", 101))
    assert rewritten_past(prev, []) == [{"date": "2026-11-01", "what": "gone"}]


def test_the_real_ledgers_keep_their_past():
    """방금 쓴 장부(작업 폴더) vs 직전 커밋 — 배치의 장부 관문이 커밋 전에 돌린다."""
    try:
        subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                       capture_output=True)
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git 이력이 없다 — 못 쟀다")
    bad = {}
    for p in sorted((ROOT / "state" / "paper").glob("*.json")):
        rel = p.relative_to(ROOT).as_posix()
        r = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=ROOT,
                           capture_output=True, text=True)
        if r.returncode != 0:
            continue                                  # 새 장부 — 견줄 과거가 없다
        try:
            prev = json.loads(r.stdout).get("history") or []
            cur = json.loads(p.read_text("utf-8")).get("history") or []
        except ValueError:
            bad[rel] = [{"what": "unreadable"}]
            continue
        got = rewritten_past(prev, cur)
        if got:
            bad[rel] = got[:3]
    assert not bad, f"지나간 기록이 바뀌었다(옛 기록은 고치지 않는다): {bad}"


def test_the_gate_runs_this_check():
    src = (ROOT / "scripts" / "ledger_gate.py").read_text("utf-8")
    assert "tests/test_past_records_are_not_rewritten.py" in src
