"""과대확신은 **양방향**이다 (감사 160).

ML 전략은 "상승 확률 70%" 같은 숫자로 포지션 크기를 정한다. 모델이 70%라고
말할 때 실제로 70%가 오르지 않으면 그 사이징은 근거 없는 베팅이다.
`calibration_summary`는 그걸 잡으라고 만든 진단이다.

그런데 **위쪽만 보고 있었다.**

    if r["mean_prob"] > 0.5 and gap > 0.1:   # ← 0.5 초과 구간만

같은 크기의 오차(0.23)를 넣어 보면:

    예측 0.78 · 실제 0.55  →  "← 과대확신"       잡힘
    예측 0.22 · 실제 0.45  →  (아무 표시 없음)    안 잡힘

브라이어 점수는 **둘 다 0.3004**로 똑같이 나쁘다. 뒤쪽은 "22%만 오른다"고
강하게 말해 놓고 실제로는 45%가 오른 경우다 — 하락 쪽 과대확신이고,
이 시스템은 그 확률로 축소·숏 방향 사이징도 한다.

'확신'은 0.5에서 얼마나 멀어졌는가다. 예측이 그 방향으로 실제보다 더 멀리
갔으면 과대확신이다 — 위든 아래든.

──────────────────────────────────────────────────────────────
같은 질문에 두 곳이 다르게 답하고 있었다

라이브 가드(`quant/live/calibration_guard.py`)는 윌슨 신뢰구간으로
"예측 평균이 실제 적중률의 CI 밖인가"를 묻는다. 그건 **처음부터
양방향**이었다 — 실측으로 0.22 → 0.45를 정확히 잡아 보정한다.

오프라인 요약만 위쪽을 봤다. FROZEN_IDEAS ㉞와 같은 계열이다.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.calibration_guard import (  # noqa: E402
    calibration_table,
    recalibrated_prob,
)
from quant.robustness.calibration import (  # noqa: E402
    brier_score,
    calibration_summary,
)

N = 200


def _outcomes(n_up: int, n_total: int = N) -> list[float]:
    return [1.0] * n_up + [0.0] * (n_total - n_up)


# 같은 크기(0.23)의 오차, 방향만 다르다
OVER_UP = (_outcomes(110), [0.78] * N)      # 78%라 했는데 55%
OVER_DOWN = (_outcomes(90), [0.22] * N)     # 22%라 했는데 45%
WELL_CALIBRATED = (_outcomes(44), [0.22] * N)   # 22%라 했고 22%


def test_the_two_errors_are_equally_bad_by_brier():
    """전제 — 두 경우가 정말 같은 크기의 오차인가."""
    up = brier_score(*OVER_UP)
    down = brier_score(*OVER_DOWN)
    assert abs(up - down) < 1e-9, (
        f"두 오차가 다르다({up:.4f} vs {down:.4f}) — 이 검사가 헛돈다")
    assert up > 0.25, "무지한 상수 예측(0.25)보다 나쁘지 않으면 전제가 깨졌다"


def test_overconfidence_on_the_way_up_is_flagged():
    text = calibration_summary(*OVER_UP)
    assert "←" in text and "⚠️" in text, text


def test_overconfidence_on_the_way_down_is_flagged_too():
    """이것이 감사 160이다 — 같은 오차인데 조용히 통과했다."""
    text = calibration_summary(*OVER_DOWN)
    assert "←" in text and "⚠️" in text, (
        "22%라 말해 놓고 45%가 오른 구간이 조용히 통과한다 — "
        f"하락 쪽 과대확신이 안 보인다:\n{text}")


def test_the_direction_is_named():
    """어느 쪽으로 과했는지 말해야 사람이 사이징을 어떻게 고칠지 안다."""
    assert "과대확신(상승)" in calibration_summary(*OVER_UP)
    assert "과대확신(하락)" in calibration_summary(*OVER_DOWN)


def test_a_well_calibrated_model_is_not_flagged():
    """대조군 — 평시에 울리면 매일 울려서 아무도 안 본다.

    ⚠️ 여기서 `"과대확신" not in text`로 쓰면 안 된다 — 정상 문구가
       "뚜렷한 **과대확신** 구간은 없습니다"라서 그 단어가 들어 있다.
       오늘만 세 번째로 같은 실수를 했다(감사 136·154·160). 문구를
       부정하지 말고 **경보에만 있는 표식**(←, ⚠️)을 본다.
    """
    text = calibration_summary(*WELL_CALIBRATED)
    assert "←" not in text and "⚠️" not in text, text
    assert "뚜렷한 과대확신 구간은 없습니다" in text


def test_underconfidence_is_not_called_overconfidence():
    """반대쪽 대조군 — '실제보다 약하게 말한 것'은 과대확신이 아니다.

    78%라 했는데 95%가 올랐다면 모델이 소심했던 것이다. 사이징이 작아졌을
    뿐 과대 베팅은 아니므로 이 경보의 대상이 아니다.
    """
    text = calibration_summary(_outcomes(190), [0.78] * N)
    assert "←" not in text and "⚠️" not in text, text


# ── 라이브 가드와 답이 같은가 ─────────────────────────────────


def test_the_live_guard_was_already_symmetric():
    """라이브 쪽은 윌슨 CI라 처음부터 양방향이었다 — 두 곳의 답이 같아야 한다."""
    hist, price = [], 100.0
    pattern = [True] * 9 + [False] * 11        # 45% 상승
    for i in range(N):
        hist.append({"prob_up": 0.22, "price": price})
        price = price * 1.01 if pattern[i % 20] else price * 0.99
    hist.append({"prob_up": 0.22, "price": price})

    table = calibration_table([hist])
    row = [r for r in table if r["lo"] <= 0.22 < r["hi"]]
    assert row and row[0]["confirmed"], (
        f"라이브 가드가 하락 쪽 어긋남을 확정하지 못한다: {row}")

    value, active = recalibrated_prob(0.22, [hist], table)
    assert active and abs(value - 0.45) < 0.03, (value, active)

    # 오프라인 요약도 같은 사건을 '과대확신'이라 불러야 한다
    assert "과대확신(하락)" in calibration_summary(*OVER_DOWN)
