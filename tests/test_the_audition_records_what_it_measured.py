"""오디션이 문턱만 적고 기록(記錄)을 안 남긴다 (2026-08-14 감사 235).

`state/retrain_history.jsonl` 159건을 열어 보고 나온 결함이다. 필드는 이랬다:

    select_t 2.0 · confirm_t 2.5 · n_candidates 23 · promoted false
    reason "선발전에서 챔피언을 통계적으로 이긴 후보 없음(후보 23개)"

**넘어야 할 높이는 있는데 실제로 얼마나 뛰었는지가 없다.** 그래서 답할 수
없는 질문이 쌓였다:

  · 159번 중 승격 1번 — 1등 후보의 t가 1.99였나 0.02였나?
    앞이면 문턱이 조금 높은 것이고, 뒤면 챌린저 격자가 통째로 무의미한
    것이다. **고칠 곳이 완전히 다른데** 장부만으로는 구분할 수 없었다.
  · 결승전까지 간 12번은 무엇이 모자랐나 — 결승 t가 기록되지 않았다.
  · t가 커도 평균 차이가 잔돈이면 갈아탈 이유가 없다 — 효과 크기도 없었다.

이 제품은 "판단 근거를 장부에 남긴다"를 정체성으로 내건다. 결정의
**전제**(실측 비용·체결 가정·데이터 해시)는 이미 남기고 있었는데, 정작
**결과**가 통째로 빠져 있었다.

같은 감사에서 하나 더: 장부의 `select_folds`가 숫자 `3`으로 박혀 있었고
`nightly_retrain`의 기본값과 **따로** 놀았다. 한쪽만 바꾸면 장부가 실제와
다른 조건을 말하고, `verify`는 그 장부대로 재현하므로 재현이 어긋난다 —
'조작 불가능'은 재현이 맞을 때만 사실이다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.live import retrain as rt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _cand(t, n=120, mean=1e-4, wins=2, folds=3, name="ml", params=None):
    return {"spec": {"strategy": name, "params": params or {"model": "gb"}},
            "n": n, "mean_diff": mean, "t_stat": t, "swap": t > 2.0,
            "fold_wins": wins, "n_folds": folds}


# ── 얼마나 가까웠는지가 남는가 ────────────────────────────────

def test_a_losing_night_still_records_how_close_it_got():
    """아무도 못 이긴 밤에도 **1등의 t**가 남아야 한다.

    이게 없어서 '문턱이 높은 것'과 '후보가 무의미한 것'을 구분 못 했다.
    """
    ev = rt.audition_evidence({"candidates": [_cand(0.31), _cand(1.87),
                                              _cand(-0.4)]})
    assert ev["best"]["t"] == 1.87
    assert ev["top_t"] == [1.87, 0.31, -0.4]


def test_the_two_diagnoses_are_now_distinguishable():
    """1.99와 0.02는 다른 진단이다 — 장부가 둘을 구분해야 한다."""
    close = rt.audition_evidence({"candidates": [_cand(1.99)]})
    hopeless = rt.audition_evidence({"candidates": [_cand(0.02)]})
    assert close["best"]["t"] != hopeless["best"]["t"]
    assert close["best"]["t"] > 1.9 and hopeless["best"]["t"] < 0.1


def test_the_effect_size_is_recorded_next_to_the_t():
    """t만 남기면 '통계적으로 유의한 잔돈'을 못 걸러낸다."""
    ev = rt.audition_evidence({"candidates": [_cand(3.5, mean=2e-7)]})
    assert ev["best"]["mean_diff"] == pytest.approx(2e-7, abs=1e-9)
    assert ev["best"]["n"] == 120


def test_the_fold_gate_result_is_recorded():
    """폴드 과반 게이트에서 떨어진 것과 t에서 떨어진 것은 다른 사건이다."""
    ev = rt.audition_evidence({"candidates": [_cand(3.0, wins=1, folds=3)]})
    assert ev["best"]["fold_wins"] == 1 and ev["best"]["n_folds"] == 3


def test_the_winning_spec_is_named():
    """어느 설정이 1등이었는지 — 격자를 고치려면 이게 필요하다."""
    ev = rt.audition_evidence({"candidates": [
        _cand(2.5, name="ma_cross", params={"fast": 5, "slow": 20})]})
    assert ev["best"]["strategy"] == "ma_cross"
    assert ev["best"]["params"] == {"fast": 5, "slow": 20}


def test_the_final_round_is_recorded():
    """결승까지 간 밤에 무엇이 모자랐는지 — 12번이 이 기록 없이 지나갔다."""
    ev = rt.audition_evidence({
        "candidates": [_cand(3.1)],
        "final": {"t_stat": 1.42, "n": 55, "mean_diff": 3e-5, "swap": False}})
    assert ev["final"] == {"t": 1.42, "n": 55, "mean_diff": 3e-5,
                           "swap": False}


# ── 망가진 입력에도 장부를 못 쓰게 되면 안 된다 ────────────────

def test_no_candidates_is_a_quiet_empty_not_a_crash():
    """후보가 하나도 안 돈 밤(데이터 부족 등)에도 기록은 나가야 한다."""
    ev = rt.audition_evidence({"candidates": []})
    assert ev == {"top_t": []}
    assert "best" not in ev


def test_a_broken_t_does_not_take_the_record_down():
    """t가 NaN인 후보가 섞여도 나머지 기록은 남는다."""
    ev = rt.audition_evidence({"candidates": [
        _cand(float("nan")), _cand(1.2), {"spec": {}, "t_stat": None}]})
    assert ev["best"]["t"] == 1.2
    assert ev["top_t"] == [1.2]


def test_the_record_stays_small():
    """하루 20줄씩 자라는 파일이다 — 상위 몇 개만 남긴다."""
    ev = rt.audition_evidence({"candidates": [_cand(float(i))
                                              for i in range(30)]})
    assert len(ev["top_t"]) == 3
    assert ev["top_t"] == [29.0, 28.0, 27.0]


# ── 실제로 장부에 실리는가 ────────────────────────────────────

def test_the_writer_actually_puts_it_in_the_ledger():
    """함수가 맞아도 **아무도 안 부르면** 장부는 그대로 비어 있다.

    이 저장소가 여러 번 당한 모양이다(감사 229 — '부품은 있는데 배선이 없다').
    """
    src = (ROOT / "quant" / "live" / "retrain.py").read_text("utf-8")
    assert '"audition_result": audition_evidence(decision)' in src, (
        "오디션 결과를 장부 기록에 싣지 않는다")


def test_the_old_ledger_is_the_evidence_this_was_missing():
    """기존 159건에 그 필드가 없다는 사실 자체를 못박아 둔다.

    과거를 고치지 않는 것이 이 저장소의 규칙이라 옛 줄은 그대로 둔다.
    다만 '왜 새 필드를 넣었는지'의 근거는 남긴다.
    """
    path = ROOT / "state" / "retrain_history.jsonl"
    if not path.exists():
        pytest.skip("장부 파일 없음(새 설치)")
    rows = [json.loads(x) for x in path.read_text("utf-8").splitlines() if x.strip()]
    old = [r for r in rows if "audition_result" not in r]
    assert old, "옛 기록이 사라졌다 — 과거는 고치지 않는다"
    # 가장 최근의 옛 기록은 문턱을 갖고 있으면서 기록(記錄)은 없다.
    # (맨 처음 줄들은 문턱 필드조차 없던 더 이른 세대다 — 그것도 고치지 않는다.)
    latest = old[-1]
    assert "select_t" in latest and "confirm_t" in latest, "문턱조차 없다"
    assert "audition_result" not in latest


# ── 폴드 수가 두 곳에서 갈라지지 않는가 ────────────────────────

def test_the_recorded_fold_count_is_the_one_actually_used():
    """장부의 폴드 수가 **실제로 쓴 값**이어야 한다 — verify가 그걸 믿는다."""
    import inspect
    sig = inspect.signature(rt.nightly_retrain)
    assert sig.parameters["select_folds"].default == rt.SELECT_FOLDS, (
        "기본값과 상수가 갈라졌다")
    src = (ROOT / "quant" / "live" / "retrain.py").read_text("utf-8")
    assert '"select_folds": SELECT_FOLDS' in src, "장부에 숫자를 박아 넣었다"
    assert "select_folds=SELECT_FOLDS" in src, (
        "실제 호출에 폴드 수를 넘기지 않는다 — 기본값에 의존하면 "
        "기본값이 바뀌는 날 장부만 옛 값을 말한다")


def test_verify_reads_the_fold_count_from_the_ledger():
    """대조군 — verify가 장부의 값을 쓰는지. 안 쓰면 위 검사가 무의미하다."""
    src = (ROOT / "quant" / "live" / "retrain.py").read_text("utf-8")
    assert 'rec.get("select_folds"' in src
