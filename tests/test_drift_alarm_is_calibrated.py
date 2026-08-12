"""드리프트 경보가 **표본 크기에 맞게** 조정돼 있는가 (감사 99).

`quant/robustness/drift.py`는 이렇게 적어 뒀다:

    PSI < 0.1        : 안정
    0.1 <= PSI < 0.25: 주의
    PSI >= 0.25      : 드리프트 — 재학습 또는 모델 중단을 검토할 것

이 문턱은 신용평가 업계 관행이고, **표본 수만~수십만 건을 전제**한다.
그런데 이 저장소는 `n_new=60`(최근 60거래일)으로 잰다. 같은 분포에서
뽑은 두 표본만으로 시뮬레이션하면:

    중앙값 0.19 · 95% 0.44 · 99% 0.94
    → 드리프트가 **전혀 없어도** 절반이 "주의", 29%가 "드리프트"

즉 경보가 매일 울린다. 그러면 진짜 신호(0.97)와 잡음(0.31)이 같은 등급에
묶여 아무도 안 본다. 오늘 실제 장부에서도 20종목 중 17종목이 0.25를
넘었다 — 그대로 두면 "17종목 드리프트"라는 무의미한 경보가 나간다.

고친 방식은 새 통계를 발명하는 게 아니라 **잣대를 표본에 맞추는 것**이다:
그 표본 크기의 귀무분포를 고정 시드로 뽑아 거기에 견준다. 장부에는 값과
등급과 잣대를 함께 남겨, 나중에 읽는 사람이 문턱을 추측하지 않게 한다.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.daily import (            # noqa: E402
    DRIFT_N_NEW,
    DRIFT_N_REF,
    drift_grade,
    drift_reference,
)
from quant.robustness.drift import interpret_psi, psi, psi_null  # noqa: E402


# ── 귀무분포가 실제로 그렇게 넓은가 ────────────────────────────

def test_the_conventional_threshold_fires_on_pure_noise():
    """관행 문턱(0.25)이 이 표본 크기에서 얼마나 자주 헛울리는지 잰다.

    이 검사는 '고쳤다'가 아니라 **왜 고쳤는가**를 고정한다. 나중에
    누가 문턱을 0.25로 되돌리려 할 때 이 숫자가 근거가 된다.
    """
    rng = random.Random(7)
    hits = 0
    trials = 300
    for _ in range(trials):
        x = [rng.gauss(0, 1) for _ in range(DRIFT_N_REF + DRIFT_N_NEW)]
        if psi(x[:DRIFT_N_REF], x[DRIFT_N_REF:]) >= 0.25:
            hits += 1
    rate = hits / trials
    assert rate > 0.15, (
        f"귀무분포에서 0.25 초과가 {rate:.0%}뿐이다 — 이 검사의 전제가 "
        "무너졌다(psi 구현이나 창 크기가 바뀌었는지 확인할 것)")


def test_the_null_reference_is_much_wider_than_the_convention():
    ref = psi_null(DRIFT_N_REF, DRIFT_N_NEW)
    assert ref["p50"] > 0.1, (
        f"귀무 중앙값 {ref['p50']}가 '안정' 문턱 0.1보다 작다면 관행 문턱을 "
        "써도 됐다는 뜻이다 — 이 감사의 전제를 다시 볼 것")
    assert ref["p95"] > 0.25, f"귀무 95%가 {ref['p95']}"


def test_the_reference_is_deterministic():
    """장부에 남는 잣대가 실행마다 바뀌면 과거 기록과 비교할 수 없다."""
    assert psi_null(DRIFT_N_REF, DRIFT_N_NEW) == psi_null(
        DRIFT_N_REF, DRIFT_N_NEW)
    a = psi_null(100, 40, 10, 200, 1)
    psi_null.cache_clear()
    assert a == psi_null(100, 40, 10, 200, 1), "시드가 고정되지 않았다"


# ── 등급이 잣대를 쓰는가 ────────────────────────────────────────

def test_noise_level_psi_is_not_called_drift():
    ref = drift_reference()
    noise = (ref["p50"] + ref["p95"]) / 2          # 잡음 범위 한가운데
    assert "드리프트" not in (drift_grade(noise) or ""), (
        f"PSI {noise:.2f}는 이 표본 크기에서 흔한 값인데 드리프트라 부른다")


def test_a_genuinely_extreme_value_is_still_flagged():
    """조정한다고 무디게 만들면 안 된다 — 진짜 큰 값은 여전히 잡는다."""
    ref = drift_reference()
    assert drift_grade(ref["p99"] + 0.2) == "심한 드리프트"
    assert "드리프트" in (drift_grade(ref["p95"] + 0.05) or "")


def test_grades_are_ordered():
    ref = drift_reference()
    seq = [drift_grade(v) for v in
           (0.0, ref["p50"], ref["p95"], ref["p99"] + 0.1)]
    assert seq == ["안정", "주의 (표본 잡음 범위)", "드리프트", "심한 드리프트"], seq


def test_missing_values_do_not_become_stable():
    """계산불가를 '안정'으로 위장하지 않는다(원래 있던 원칙)."""
    assert drift_grade(None) is None
    assert drift_grade(float("nan")) is None
    assert interpret_psi(float("nan")).startswith("계산불가")


# ── 장부·경보·화면이 같은 잣대를 쓰는가 ────────────────────────

def test_the_ledger_carries_the_yardstick():
    """값만 남기면 읽는 사람이 0.25로 읽는다 — 등급과 잣대를 같이 남긴다."""
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    for field in ('"drift_psi": psi_v,', '"drift_grade": drift_grade(psi_v),',
                  '"drift_ref": drift_reference()'):
        assert field in src, f"장부에 {field}가 없다"


def test_the_cli_alarm_no_longer_hardcodes_the_threshold():
    src = (ROOT / "quant" / "cli.py").read_text("utf-8")
    blk = src.split("drifted = [", 1)[1].split("lines.append", 1)[0]
    assert "0.25" not in blk, (
        f"경보가 아직 관행 문턱을 박아 쓴다:\n{blk}")
    assert "drift_grade" in blk


def test_the_front_page_reads_the_grade_not_the_number():
    """사이트가 숫자를 문턱과 직접 비교하면 같은 실수를 되풀이한다."""
    idx = (ROOT / "docs" / "index.html").read_text("utf-8")
    flags = idx.split("const flags=[]", 1)[1].split("side-flags", 1)[0]
    assert "drift_grade" in flags, "사이트가 드리프트를 표시하지 않는다"
    assert "drift_psi" not in flags, (
        "사이트가 PSI 숫자를 직접 판단한다 — 판단은 기록하는 쪽에서 한다")
