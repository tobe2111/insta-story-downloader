"""경험 보정이 **가장 과신한 예측에도 닿는가** (감사 150).

확률 보정은 "모델은 97%라지만 경험상 50%였다"를 병기하는 장치다. 구간을
0.10 폭으로 나누고, 표본 30건 이상이면서 예측 평균이 실제 적중률의 윌슨
95% 신뢰구간 밖이면 '어긋남 확정'으로 보고 그 구간에 개입한다.

그런데 **구간 판정이 두 곳에서 달랐다.**

    표를 만들 때  k = min(int(p * bins), bins - 1)   ← p=1.0을 마지막 구간에
    적용할 때     row["lo"] <= p < row["hi"]         ← p=1.0은 어디에도 안 걸림

같은 판정을 한 번은 이렇게, 한 번은 저렇게 쓴 것이다. 결과:

    예측 0.97 · 실제 적중률 0.50 · 표본 80 → 어긋남 확정
        prob 0.970 → 보정 0.50 (개입)
        prob 0.999 → 보정 0.50 (개입)
        prob 1.000 → 보정 1.00 (개입 없음)   ← 가장 과신한 값만 빠져나간다

p=1.0은 **증거로는 세어지는데 보정은 안 받는다.** 하필 "100% 오른다"는
모델의 말이 통째로 검문을 피해 간다.

감사 146(같은 판정을 다섯 곳에서 제각기)과 같은 계열이다 — 판정을 한
함수로 모아야 갈라지지 않는다.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.calibration_guard import (  # noqa: E402
    BIN_WIDTH,
    _bin_of,
    calibration_table,
    recalibrated_prob,
)


def _overconfident_history(prob: float = 0.97, n: int = 80) -> list:
    """예측은 prob인데 실제로는 절반만 오르는 장부 — 어긋남이 확정된다."""
    hist, price = [], 100.0
    for i in range(n):
        hist.append({"prob_up": prob, "price": price})
        price = price * 1.01 if i % 2 == 0 else price * 0.99
    hist.append({"prob_up": prob, "price": price})
    return hist


HIST = _overconfident_history()
TABLE = calibration_table([HIST])


def test_the_evidence_is_actually_confirmed():
    """전제 — 이 구간이 '어긋남 확정'이어야 아래 검사들이 의미를 갖는다."""
    row = [r for r in TABLE if r["lo"] <= 0.97 < r["hi"]]
    assert row, f"0.97이 든 구간이 표에 없다: {TABLE}"
    assert row[0]["confirmed"], f"어긋남이 확정되지 않았다: {row[0]}"
    assert row[0]["n"] >= 30 and abs(row[0]["actual"] - 0.5) < 0.05


def test_a_certain_call_is_corrected_like_any_other():
    """확률 1.0도 같은 구간이니 같은 보정을 받아야 한다."""
    for p in (0.90, 0.97, 0.999, 1.0):
        val, active = recalibrated_prob(p, [HIST], TABLE)
        assert active, (
            f"prob={p}가 확정 구간에 드는데 보정이 안 걸린다 — "
            "'100% 오른다'는 말만 검문을 피해 간다")
        assert abs(val - 0.5) < 0.05, f"prob={p} → {val}"


def test_an_unconfirmed_band_is_left_alone():
    """대조군 — 증거가 없는 구간에서는 모델의 말을 그대로 둔다.

    이 검사가 없으면 위 검사는 '언제나 보정한다'는 코드로도 통과한다.
    """
    for p in (0.10, 0.50, 0.60):
        val, active = recalibrated_prob(p, [HIST], TABLE)
        assert not active, f"prob={p}는 표본이 없는데 개입했다 → {val}"
        assert val == p


def test_the_two_places_use_one_rule():
    """표의 구간 경계와 적용의 구간 판정이 같은 함수에서 나와야 한다."""
    bins = max(1, round(1.0 / BIN_WIDTH))
    for row in TABLE:
        # 구간의 아래끝·가운데·(마지막 구간이면) 위끝이 전부 같은 칸이어야 한다
        mid = (row["lo"] + row["hi"]) / 2
        assert _bin_of(row["lo"], bins) == _bin_of(mid, bins), row
        if row["hi"] >= 1.0:
            assert _bin_of(1.0, bins) == _bin_of(mid, bins), (
                "마지막 구간에서 1.0이 다른 칸으로 샌다 — 이게 감사 150이었다")


def test_out_of_range_probabilities_do_not_crash():
    """모델이 이상한 값을 뱉어도 판정이 무너지면 안 된다."""
    for p in (-0.5, 1.5, float("nan"), float("inf")):
        val, active = recalibrated_prob(p, [HIST], TABLE)
        assert isinstance(active, bool)
        assert val is not None
