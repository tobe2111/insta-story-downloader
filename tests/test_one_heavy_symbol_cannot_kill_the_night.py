"""무거운 종목 하나가 밤 배치를 통째로 죽이지 못한다 (감사 334).

실측(2026-10-09): 야간 재학습이 2026-10-05부터 **10회 연속 취소**(5밤).
XLP 챔피언이 앙상블('vote' + 등위 보정)이라 후보 하나에 28~55초, 53개면 약
35분. 이어달리기 예산은 **종목 사이에서만** 검사해서, 명단 16분째에 그 종목에
닿으면 잡 한도 45분을 넘었다. 잡이 취소되면 그날 돈 종목의 기록도, 다음 밤의
시작 지점(커서)도 저장되지 않는다 → 다음 밤 같은 자리에서 또 죽는다.

그동안 오디션 0회, 13F 조회 0회. 경보는 `if: failure()`라 **취소에는 안 울렸다.**

지키는 것:
  ① 종목 안(후보 사이)에서도 시간 관문을 본다 — 그리고 그 신호가 후보 하나의
     실패를 삼키는 `except`에 먹히지 않는다.
  ② 걸리면 지금까지 돈 것을 저장하고, 커서는 **그 종목부터** 이어 돈다.
  ③ 첫 종목이 걸렸다면(빈 밤 전체로도 못 돈다) 맨 뒤로 보낸다 — 아니면
     매일 같은 자리에서 잘려 나머지가 영영 굶는다.
  ④ 잘린 사실이 장부(run_health)에 남는다.
  ⑤ 경보 단계가 취소에도 울린다.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import quant.live.retrain as R

ROOT = Path(__file__).resolve().parent.parent
TARGETS = [("us_stock", "TIP"), ("us_stock", "DBC"), ("us_stock", "XLP"),
           ("us_stock", "VNQ")]


@pytest.fixture(autouse=True)
def _reset():
    R._HARD_DEADLINE[0] = None
    yield
    R._HARD_DEADLINE[0] = None


def _frame(n=400, seed=5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.02, n)))
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame({"open": close, "high": close * 1.01,
                         "low": close * 0.99, "close": close,
                         "volume": 1e6}, index=idx)


class _Fixed:
    name = "fixed"
    allow_short = True

    def __init__(self, s):
        self._s = s

    def generate_signals(self, df):
        return self._s.reindex(df.index).fillna(0.0)


# ── ① 후보 사이의 관문 ───────────────────────────────────────────
def test_the_audition_stops_between_candidates_once_past_the_hard_deadline():
    df = _frame()
    flat = pd.Series(0.0, index=df.index)
    R._HARD_DEADLINE[0] = -1.0                       # 이미 지났다
    with pytest.raises(R.BudgetCut):
        R.nightly_retrain(df, {"strategy": "fixed", "params": {}},
                          [{"strategy": "fixed", "params": {"x": 1}}],
                          build=lambda s: _Fixed(flat), confirm_window=120,
                          select_folds=0)


def test_without_a_deadline_the_audition_runs_as_before():
    df = _frame()
    flat = pd.Series(0.0, index=df.index)
    out = R.nightly_retrain(df, {"strategy": "fixed", "params": {}},
                            [{"strategy": "fixed", "params": {"x": 1}}],
                            build=lambda s: _Fixed(flat), confirm_window=120,
                            select_folds=0)
    assert "promoted" in out


# ── ②③④ 배치가 저장하고 이어 돈다 ───────────────────────────────
def _run(monkeypatch, tmp_path, heavy):
    seen = []

    def fake(market, symbol, **kw):
        key = f"{market}:{symbol}"
        seen.append(key)
        if key == heavy:
            raise R.BudgetCut("종목 도중 시간 관문")
        return {"skipped": False, "asof": "2026-10-08", "panel_diffs": {}}

    monkeypatch.setattr(R, "run_retrain", fake)
    monkeypatch.setenv("QUANT_RETRAIN_BUDGET_SEC", "1800")
    out = R.run_retrain_all(targets=TARGETS, state_dir=str(tmp_path))
    cur = json.loads((tmp_path / "retrain_cursor.json").read_text("utf-8"))
    health = json.loads((tmp_path / "run_health.json").read_text("utf-8"))["retrain"]
    return out, cur, health, seen


def test_a_cut_mid_roster_saves_the_night_and_resumes_at_that_symbol(
        monkeypatch, tmp_path):
    out, cur, health, seen = _run(monkeypatch, tmp_path, "us_stock:XLP")
    assert out["ok"] == ["us_stock:TIP", "us_stock:DBC"]   # 저장된다
    assert "us_stock:VNQ" not in seen                     # 그 뒤는 안 돈다
    assert cur["next_key"] == "us_stock:XLP"              # 내일 그 종목부터
    assert cur["not_reached"] == ["us_stock:XLP", "us_stock:VNQ"]
    assert health["budget_cut"] == {"key": "us_stock:XLP", "too_heavy": False}
    assert health["not_reached"] == 2
    assert not health["failed"], "시간 관문은 실패가 아니다"
    assert R._HARD_DEADLINE[0] is None, "관문이 배치 뒤에도 남아 다른 호출을 자른다"


def test_a_symbol_too_heavy_for_a_whole_night_goes_to_the_back(
        monkeypatch, tmp_path):
    out, cur, health, _ = _run(monkeypatch, tmp_path, "us_stock:TIP")
    assert cur["next_key"] == "us_stock:DBC", "같은 자리에서 매일 잘리는 고리"
    assert cur["not_reached"][-1] == "us_stock:TIP"
    assert health["budget_cut"]["too_heavy"] is True


def test_the_hard_deadline_leaves_room_before_the_job_limit():
    # 잡 45분 = 단계 시작 약 1분 + 예산 30분 + 여유 + 커밋·13F 몫
    wf = (ROOT / ".github/workflows/nightly-retrain.yml").read_text("utf-8")
    assert "timeout-minutes: 45" in wf and 'QUANT_RETRAIN_BUDGET_SEC: "1800"' in wf
    assert 1800 + R.HARD_MARGIN_SEC <= 45 * 60 - 4 * 60


# ── ⑤ 취소에도 경보 ──────────────────────────────────────────────
def test_every_failure_alarm_also_fires_on_cancellation():
    missing = []
    for wf in sorted((ROOT / ".github/workflows").glob("*.yml")):
        t = wf.read_text("utf-8")
        if "if: failure()" in t and "if: failure() || cancelled()" not in t:
            missing.append(wf.name)
    assert not missing, f"취소(시간 초과)에 안 울리는 경보: {missing}"


def test_a_symbol_too_heavy_for_a_whole_night_raises_an_alarm():
    from quant.live.flag_watch import _current_flags
    st = {"run_health": {"retrain": {"budget_cut": {"key": "us_stock:XLP",
                                                    "too_heavy": True}}}}
    assert any(k.startswith("retrain_too_heavy:") for k in _current_flags(st))
    # 도중에 멈췄을 뿐인 밤은 정상 경로라 울리지 않는다
    st["run_health"]["retrain"]["budget_cut"]["too_heavy"] = False
    assert not any(k.startswith("retrain_too_heavy:") for k in _current_flags(st))


# ── ⑤ 잡 한도가 종목 도중에 죽여도 다음 회차가 안다 (감사 338) ─────────
class _Killed(BaseException):
    """GitHub가 잡을 취소하는 것 — 파이썬의 어떤 except도 못 잡는다."""


def _killed_run(monkeypatch, tmp_path, victim):
    seen = []

    def fake(market, symbol, **kw):
        key = f"{market}:{symbol}"
        seen.append(key)
        if key == victim:
            raise _Killed()
        return {"skipped": False, "asof": "2026-10-10", "panel_diffs": {}}

    monkeypatch.setattr(R, "run_retrain", fake)
    monkeypatch.setenv("QUANT_RETRAIN_BUDGET_SEC", "1800")
    try:
        R.run_retrain_all(targets=TARGETS, state_dir=str(tmp_path))
    except _Killed:
        pass
    R._HARD_DEADLINE[0] = None
    return seen


def test_a_job_killed_mid_symbol_leaves_a_trace(monkeypatch, tmp_path):
    """2026-10-10 실측: XLP 도중 잡 한도에 죽었고 커서가 안 남았다."""
    _killed_run(monkeypatch, tmp_path, "us_stock:DBC")
    cur = json.loads((tmp_path / "retrain_cursor.json").read_text("utf-8"))
    assert cur["in_progress"] == "us_stock:DBC"
    assert cur["in_progress_first"] is False
    assert cur["next_key"] == "us_stock:DBC"


def test_a_symbol_that_killed_the_job_from_the_front_goes_to_the_back(
        monkeypatch, tmp_path):
    first = TARGETS[0][0] + ":" + TARGETS[0][1]
    _killed_run(monkeypatch, tmp_path, first)        # 맨 앞에서 죽는다
    out, cur, health, seen = _run(monkeypatch, tmp_path, "__none__")
    assert seen[0] != first and seen[-1] == first, (
        "맨 앞에서 잡을 죽인 종목이 다시 맨 앞에 선다 — 감사 334의 교착")
    assert health["budget_cut"] == {"key": first, "too_heavy": True,
                                    "died": True}
    assert "in_progress" not in cur, "다 돈 밤의 커서에 흔적이 남았다"
