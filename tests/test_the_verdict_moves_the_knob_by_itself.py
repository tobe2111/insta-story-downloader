"""판정이 나면 사람 없이 적용된다 (감사 315).

사장님 지시(2026-08-25): *"판정을 하면 이제 너가 조정을 하는게 아니라
머신러닝측에서 하게끔 해줘. 가능할까?"*

가능했다. 다만 먼저 **손잡이**가 없었다.

■ 무엇이 빠져 있었나

이 저장소에는 셋이 이미 있었다 — 사전 등록 원장(무엇을 언제 어떤 통계로
판정할지), 판정 엔진(경계를 넘으면 조기 판정까지), 화면(진도 공개).

그런데 **판정이 나도 아무것도 안 바뀌었다.** `sequential_status()`는
화면에 그려질 뿐이고, 실제 조정은 사람이 코드를 고쳐서 했다. 배분 방식만
해도 `hrp or erc or equal`이라는 고정 순서가 코드에 박혀 있어, "ERC가
이겼다"는 판정이 나도 손댈 곳이 없었다.

■ 여기서 지키는 것

  · **조치는 판정 전에 등록한다.** 결과를 보고 정하면 사전 등록이 아니라
    사후 합리화다 — '운 좋은 승자'를 만드는 바로 그 방식이다.
  · **채택이 없으면 아무것도 안 바뀐다.** 기본값은 오늘의 동작 그대로다.
  · **한 번만 적용한다.** 같은 판정이 매일 다시 걸리면 장부가 뒤집힌다.
  · **진행 중은 패배가 아니다.** 둘을 같게 다루면 안 끝난 실험을 진 것으로
    치고 현행을 굳혀 버린다.
  · **되돌리기 어려운 일은 자동으로 안 한다** — 실거래 개시·원금 변경·
    판매 상태. 대신 **알린다.** 조용히 넘기면 아무도 모른다.
  · **손잡이를 운영 코드가 실제로 읽는다.** 안 읽으면 원장만 바뀌고
    계좌는 그대로다 — 장치가 켜진 적 없는 상태(감사 313과 같은 모양).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.adopt import (  # noqa: E402
    ACTIONS, DEFAULTS, NEVER_AUTOMATIC, apply_verdicts, current, history,
    pending, public,
)

NOW = "2026-08-25T09:00:00+09:00"


def _status(**pairs):
    """판정 엔진이 내놓는 모양 그대로 지어낸다."""
    return {"registered": {}, "pairs": dict(pairs)}


def _won(n=40):
    return {"state": "조기 판정: 우세", "n": n, "sum": 0.9, "boundary": 0.5,
            "mean_daily_pct": 0.6}


def _lost(n=40):
    return {"state": "조기 판정: 열세", "n": n, "sum": -0.9, "boundary": 0.5,
            "mean_daily_pct": -0.6}


def _running(n=40):
    return {"state": "진행 중", "n": n, "sum": 0.1, "boundary": 0.5}


def _thin():
    return {"state": "표본 부족", "n": 5, "min_days": 20}


# ══ ① 채택이 없으면 아무것도 안 바뀐다 ════════════════════════════

def test_a_fresh_install_behaves_exactly_as_before(tmp_path):
    """판정이 하나도 없으면 손잡이는 기본값 — 오늘의 동작 그대로."""
    assert current(str(tmp_path)) == DEFAULTS
    assert history(str(tmp_path)) == []


def test_an_unreadable_ledger_falls_back_to_the_defaults(tmp_path):
    """장부가 깨져도 **알 수 없는 상태로 돌지 않는다.**"""
    (tmp_path / "adopted.json").write_text("{망가짐", encoding="utf-8")
    assert current(str(tmp_path)) == DEFAULTS


def test_an_unknown_knob_is_ignored(tmp_path):
    """모르는 손잡이를 넘겨짚지 않는다."""
    (tmp_path / "adopted.json").write_text(
        json.dumps({"knobs": {"없는손잡이": {"value": "뭔가"}}}),
        encoding="utf-8")
    assert current(str(tmp_path)) == DEFAULTS


# ══ ② 판정이 나면 스스로 돌린다 ═══════════════════════════════════

def test_a_win_moves_the_knob_without_a_human(tmp_path):
    out = apply_verdicts(str(tmp_path), now=NOW,
                         status=_status(**{"alloc:hrp-erc": _won()}))
    assert current(str(tmp_path))["alloc_method"] == "erc", out
    assert out["applied"] and out["applied"][0]["applied"] is True


def test_the_reason_and_evidence_are_written_down(tmp_path):
    """왜 바뀌었는지 **근거와 함께** 남는다 — 조용한 골대 이동 금지."""
    apply_verdicts(str(tmp_path), now=NOW,
                   status=_status(**{"alloc:hrp-erc": _won(n=41)}))
    rec = history(str(tmp_path))[-1]
    assert rec["at"] == NOW and rec["key"] == "alloc:hrp-erc"
    assert rec["why"], "사람이 읽을 이유가 없다"
    assert rec["evidence"]["n"] == 41, rec


def test_a_loss_keeps_the_current_setting(tmp_path):
    """도전이 지면 현행 유지 — **그래도 기록은 남는다.**"""
    apply_verdicts(str(tmp_path), now=NOW,
                   status=_status(**{"alloc:hrp-erc": _lost()}))
    assert current(str(tmp_path))["alloc_method"] == "hrp"
    rec = history(str(tmp_path))[-1]
    assert rec["applied"] is False and "졌" in rec["reason"]


@pytest.mark.parametrize("v", [_running(), _thin()])
def test_an_unfinished_experiment_is_not_treated_as_a_loss(v, tmp_path):
    """⚠️ 진행 중·표본 부족은 패배가 아니다.

    같게 다루면 아직 안 끝난 실험을 진 것으로 치고 현행을 굳혀 버린다.
    """
    out = apply_verdicts(str(tmp_path), now=NOW,
                         status=_status(**{"alloc:hrp-erc": v}))
    assert out["applied"] == [] and out["held"] == []
    assert history(str(tmp_path)) == [], "안 끝난 실험을 기록했다"


def test_the_same_verdict_is_not_applied_twice(tmp_path):
    """한 번만 적용한다 — 매일 다시 걸리면 장부가 뒤집힌다."""
    st = _status(**{"alloc:hrp-erc": _won()})
    apply_verdicts(str(tmp_path), now=NOW, status=st)
    again = apply_verdicts(str(tmp_path), now="2026-08-26T09:00:00+09:00",
                           status=st)
    assert again["applied"] == [] and again["held"] == []
    assert len(history(str(tmp_path))) == 1


def test_a_comparison_with_no_registered_action_is_left_alone(tmp_path):
    """조치를 미리 등록하지 않은 비교는 자동으로 손대지 않는다.

    등록 없이 움직이면 그건 사전 등록이 아니라 즉흥이다.
    """
    out = apply_verdicts(str(tmp_path), now=NOW,
                         status=_status(**{"cadence:1h-15m": _won()}))
    assert out["applied"] == [] and out["held"] == []


# ══ ③ 되돌리기 어려운 일은 자동으로 안 한다 ═══════════════════════

def test_an_irreversible_action_is_announced_not_applied(tmp_path,
                                                          monkeypatch):
    """실거래·원금·판매는 판정이 나도 **알리기만** 한다."""
    monkeypatch.setitem(ACTIONS, "위험한:비교",
                        {"knob": "alloc_method", "on_win": "erc",
                         "on_lose": None, "why": "실거래를 개시합니다",
                         "manual": True})
    out = apply_verdicts(str(tmp_path), now=NOW,
                         status=_status(**{"위험한:비교": _won()}))
    assert out["held"] and out["held"][0]["applied"] is False
    assert current(str(tmp_path))["alloc_method"] == "hrp", (
        "자동 금지인데 손잡이가 돌아갔다")
    assert out["held"][0]["reason"], "왜 안 했는지 안 적었다"


def test_it_never_stays_silent_about_a_held_verdict(tmp_path, monkeypatch):
    """대조군 — 보류해도 **기록에는 남는다.** 조용히 넘기면 아무도 모른다."""
    monkeypatch.setitem(ACTIONS, "위험한:비교",
                        {"knob": "alloc_method", "on_win": "erc",
                         "on_lose": None, "why": "실거래", "manual": True})
    apply_verdicts(str(tmp_path), now=NOW,
                   status=_status(**{"위험한:비교": _won()}))
    assert len(history(str(tmp_path))) == 1


def test_the_public_view_names_what_it_will_never_do():
    p = public("state")
    assert p["never_automatic"] == list(NEVER_AUTOMATIC)
    assert "실거래 개시" in p["never_automatic"]


# ══ ④ 운영 코드가 그 손잡이를 **실제로** 읽는다 ═══════════════════
#
# ⚠️ 여기가 없으면 원장만 바뀌고 계좌는 그대로다 — 장치가 켜진 적 없는
#    상태다(감사 313이 정확히 그 모양이었다).

def _rets(n=120, seed=3):
    import numpy as np
    import pandas as pd
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    return {c: pd.Series(rng.normal(0.0005, 0.01 * (i + 1), n), index=idx)
            for i, c in enumerate("ABCD")}


def test_the_daily_account_follows_the_adopted_method(tmp_path):
    """채택을 바꾸면 본 계좌가 **실제로 다른 방식으로** 나눈다."""
    from quant.live.daily import choose_slices
    r = _rets()
    w = dict.fromkeys(r, 1.0)
    _s, before = choose_slices(r, len(r), w, str(tmp_path))
    assert before == "hrp", before
    apply_verdicts(str(tmp_path), now=NOW,
                   status=_status(**{"alloc:hrp-inv_vol": _won()}))
    _s2, after = choose_slices(r, len(r), w, str(tmp_path))
    assert after == "inv_vol", (
        f"채택 원장은 바뀌었는데 계좌는 {after}로 돈다 — 손잡이가 안 읽힌다")


def test_an_adopted_method_that_fails_today_falls_back(tmp_path):
    """채택은 '선호'이지 '강제'가 아니다.

    그날 그 방식을 못 만들면 폴백이 돈다 — 강제하면 통째로 관망이 된다.
    """
    from quant.live.daily import choose_slices
    apply_verdicts(str(tmp_path), now=NOW,
                   status=_status(**{"alloc:hrp-inv_vol": _won()}))
    thin = {c: s.iloc[:5] for c, s in _rets().items()}
    _s, method = choose_slices(thin, 4, dict.fromkeys(thin, 1.0),
                               str(tmp_path))
    assert method == "equal", method


def test_the_middle_fallbacks_still_run(tmp_path, monkeypatch):
    """⚠️ 채택된 방식이 실패하면 **다음 방식**으로 내려간다 — 균등으로 곧장
    떨어지지 않는다.

    위 검사만으로는 이걸 못 잡는다. 폴백 사다리를 통째로 지워도 맨 끝의
    균등 폴백이 받아서 결과가 'equal'로 같기 때문이다(변이 시험이 확인).
    여기서는 채택된 방식만 실패시키고 **hrp로 내려가는지**를 본다.
    """
    from quant.live.daily import choose_slices
    apply_verdicts(str(tmp_path), now=NOW,
                   status=_status(**{"alloc:hrp-inv_vol": _won()}))
    monkeypatch.setattr("quant.live.alloc_ladder._inv_vol_slices",
                        lambda rets_map, n_total: None)
    r = _rets()
    _s, method = choose_slices(r, len(r), dict.fromkeys(r, 1.0), str(tmp_path))
    assert method == "hrp", (
        f"채택된 방식이 실패했는데 {method}로 갔다 — 중간 폴백이 사라졌다. "
        "그러면 그날 통째로 균등(사실상 관망)이 된다")


# ══ ⑤ 배치가 실제로 부른다 ════════════════════════════════════════
#
# ⚠️ 계산이 맞고 손잡이가 있어도 **배치가 안 부르면** 판정은 영영 적용되지
#    않는다. 처음 배선할 때 나는 `bar`라는 없는 이름을 참조해서, 매일
#    조용히 실패할 뻔했다 — 예외를 삼키는 자리라 아무도 몰랐을 것이다.

def test_the_daily_batch_applies_verdicts(tmp_path, monkeypatch):
    """일일 배치가 판정 적용을 **실제로** 부르고, 결과를 status에 싣는다."""
    from quant.live import daily as D

    seen = {}

    def _fake(state_dir, *, now, status=None):
        seen["now"] = now
        seen["status"] = status
        return {"applied": [], "held": [], "knobs": {}}

    monkeypatch.setattr("quant.live.adopt.apply_verdicts", _fake)
    (tmp_path / "paper").mkdir(parents=True, exist_ok=True)
    (tmp_path / "paper" / "crypto_X.json").write_text(
        json.dumps({"market": "crypto", "symbol": "X",
                    "history": [{"date": "2026-08-25", "equity": 100.0,
                                 "return_pct": 0.0}]}), encoding="utf-8")
    D.write_docs_status(str(tmp_path), str(tmp_path / "status.json"))
    assert "now" in seen, "일일 배치가 판정 적용을 부르지 않는다"
    assert seen["now"] == "2026-08-25", (
        f"채택 시각이 장부 날짜가 아니다: {seen['now']!r} — 없는 이름을 "
        "참조하면 매일 조용히 실패한다")


def test_the_batch_records_what_the_adoption_did(tmp_path):
    """status에 채택 상태가 실린다 — 화면이 읽을 수 있어야 한다."""
    from quant.live import daily as D
    (tmp_path / "paper").mkdir(parents=True, exist_ok=True)
    (tmp_path / "paper" / "crypto_X.json").write_text(
        json.dumps({"market": "crypto", "symbol": "X",
                    "history": [{"date": "2026-08-25", "equity": 100.0,
                                 "return_pct": 0.0}]}), encoding="utf-8")
    D.write_docs_status(str(tmp_path), str(tmp_path / "status.json"))
    st = json.loads((tmp_path / "status.json").read_text("utf-8"))
    ad = st.get("adopted")
    assert ad and "never_automatic" in ad, ad
    assert ad["knobs"]["alloc_method"] == "hrp"
