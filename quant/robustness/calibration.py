"""확률 보정 진단 — 모델이 말하는 '확률'은 진짜 확률인가.

ML 전략은 "상승 확률 70%" 같은 숫자로 포지션 크기를 정한다(conviction sizing).
그런데 모델이 70%라고 말할 때 실제로 70%가 오르는 게 아니라면 그 사이징은
근거 없는 베팅이다. 이 모듈은 예측 확률과 실제 결과를 비교해 모델의
'과대확신/과소확신'을 드러낸다.

    brier_score      : 확률 예측의 평균 제곱 오차 (0=완벽, 낮을수록 좋음).
                       항상 0.5를 찍는 무지한 모델의 점수는 0.25 — 이보다
                       나쁘면 그 모델은 동전 던지기만도 못하다.
    calibration_bins : 예측 확률 구간별 (평균 예측, 실제 양성 비율, 표본 수).
                       평균 예측 > 실제 비율이면 과대확신 — 사이징을 줄여야 한다.

⚠️ 보정이 완벽해도 수익은 보장되지 않는다. 보정은 '거짓 확신으로 크게 베팅하는
   사고'를 막을 뿐이며, 엣지 자체는 별개 문제다.

의존성 없는 순수 파이썬 구현 — numpy 없이도 동작한다.
"""
from __future__ import annotations

from typing import Any


def _pairs(y_true: Any, y_prob: Any) -> list[tuple[float, float]]:
    """(정답, 예측확률) 쌍으로 정리하고 유효성을 검증한다."""
    t = [float(v) for v in y_true]
    p = [float(v) for v in y_prob]
    if len(t) != len(p):
        raise ValueError(f"y_true({len(t)})와 y_prob({len(p)})의 길이가 다릅니다.")
    for prob in p:
        if not (0.0 <= prob <= 1.0):
            raise ValueError(f"확률은 [0, 1] 범위여야 합니다: {prob}")
    return list(zip(t, p))


def brier_score(y_true: Any, y_prob: Any) -> float:
    """브라이어 점수 = mean((prob - outcome)^2). 낮을수록 좋다.

    y_true: 실제 결과 (0/1), y_prob: 예측 확률 [0, 1].
    표본이 없으면 NaN — '평가 불가'를 좋은 점수로 위장하지 않는다.
    """
    pairs = _pairs(y_true, y_prob)
    if not pairs:
        return float("nan")
    return sum((p - t) ** 2 for t, p in pairs) / len(pairs)


def calibration_bins(y_true: Any, y_prob: Any, bins: int = 10) -> list[dict]:
    """예측 확률을 bins개 구간으로 나눠 구간별 신뢰도 통계를 반환한다.

    반환: 구간마다 {lo, hi, mean_prob, frac_positive, count}.
        mean_prob     : 구간 내 평균 예측 확률
        frac_positive : 구간 내 실제 양성(상승) 비율
        count         : 구간 내 표본 수 (0이면 mean_prob·frac_positive는 NaN)
    잘 보정된 모델은 mean_prob ≈ frac_positive 가 모든 구간에서 성립한다.
    """
    if bins < 1:
        raise ValueError("bins는 1 이상이어야 합니다.")
    pairs = _pairs(y_true, y_prob)
    sums: list[list[float]] = [[0.0, 0.0, 0] for _ in range(bins)]   # [prob합, 양성합, 수]
    for t, p in pairs:
        k = min(int(p * bins), bins - 1)      # p=1.0은 마지막 구간에 포함
        sums[k][0] += p
        sums[k][1] += t
        sums[k][2] += 1
    nan = float("nan")
    out = []
    for k, (ps, ts, n) in enumerate(sums):
        out.append({
            "lo": k / bins,
            "hi": (k + 1) / bins,
            "mean_prob": ps / n if n else nan,
            "frac_positive": ts / n if n else nan,
            "count": n,
        })
    return out


def calibration_summary(y_true: Any, y_prob: Any, bins: int = 10) -> str:
    """보정 진단을 한국어 문자열로 요약한다 — 과대확신 여부를 정직하게 알린다."""
    bs = brier_score(y_true, y_prob)
    rows = calibration_bins(y_true, y_prob, bins)
    shown_bs = "NaN" if bs != bs else f"{bs:.4f}"
    lines = [
        f"확률 보정 진단 (브라이어 점수: {shown_bs} — 무지한 상수 0.5 예측 = 0.2500)",
        "  구간          평균예측   실제비율   표본",
    ]
    overconfident = 0
    for r in rows:
        if r["count"] == 0:
            continue
        # ⚠️ 과대확신은 **양방향**이다(감사 160). 예전에는 `mean_prob > 0.5`인
        #    구간만 봤다. 그러면 "20% 상승"이라 말해 놓고 실제로 45%가 오른
        #    구간이 조용히 통과한다 — 그건 **하락 쪽 과대확신**이고, 이
        #    시스템은 그 확률로 숏·축소 방향 사이징도 한다.
        #
        #    실측(같은 크기의 오차 0.23):
        #        예측 0.78 · 실제 0.55  → 과대확신 (잡힘)
        #        예측 0.22 · 실제 0.45  → 조용히 통과 (안 잡힘)
        #    브라이어 점수는 둘 다 0.3004로 **똑같이 나쁘다**.
        #
        #    라이브 가드(quant/live/calibration_guard.py)는 윌슨 신뢰구간을
        #    써서 처음부터 양방향을 봤다. 같은 질문에 두 곳이 다르게 답하고
        #    있었던 셈이다(FROZEN_IDEAS ㉞).
        #
        #    '확신'은 0.5에서 얼마나 멀어졌는가다. 예측이 그 방향으로 실제보다
        #    더 멀리 갔으면 과대확신이다.
        gap = (r["mean_prob"] - r["frac_positive"] if r["mean_prob"] >= 0.5
               else r["frac_positive"] - r["mean_prob"])
        flag = ""
        if gap > 0.1:
            flag = ("  ← 과대확신(상승)" if r["mean_prob"] >= 0.5
                    else "  ← 과대확신(하락)")
            overconfident += 1
        lines.append(
            f"  [{r['lo']:.1f},{r['hi']:.1f})   {r['mean_prob']:>7.3f}   "
            f"{r['frac_positive']:>7.3f}   {r['count']:>4d}{flag}"
        )
    if overconfident:
        lines.append(f"  ⚠️ {overconfident}개 구간에서 모델이 실제보다 강하게 확신합니다 — "
                     "이 확률로 사이징하면 과대 베팅이 됩니다. 사이징 상한을 낮추세요.")
    else:
        lines.append("  뚜렷한 과대확신 구간은 없습니다. 단, 보정이 좋아도 수익이 "
                     "보장되는 것은 아닙니다 — 엣지는 별개로 검증하세요.")
    return "\n".join(lines)
