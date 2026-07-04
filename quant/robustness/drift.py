"""피처 드리프트 감시 — PSI(Population Stability Index).

ML 모델은 '학습 당시의 시장'을 배운다. 시장 구조가 바뀌어 피처 분포가
학습 시점과 달라지면(드리프트) 모델은 조용히 무의미해진다 — 에러도 없이
계속 예측을 뱉지만 그 예측은 이미 다른 세상의 것이다. PSI는 학습 분포와
최근 분포의 차이를 하나의 숫자로 요약해 그 조용한 붕괴를 드러낸다.

관례적 해석 기준 (신용평가 업계 관행 — 절대 법칙이 아니다):
    PSI < 0.1        : 안정 — 분포 변화 미미
    0.1 <= PSI < 0.25: 주의 — 변화 감지, 모델 성과를 함께 확인할 것
    PSI >= 0.25      : 드리프트 — 재학습 또는 모델 중단을 검토할 것

⚠️ PSI가 낮다고 모델이 여전히 유효하다는 보장은 없다(분포는 같아도 관계가
   바뀔 수 있다). 반드시 방향 정확도·OOS 성과와 함께 볼 것.

의존성 없는 순수 파이썬 구현 — numpy 없이도 동작한다.
"""
from __future__ import annotations

import math
from typing import Any

# 빈 구간(count=0)의 log(0)/0나눗셈 방지용 최소 비율
_EPS = 1e-4


def _as_floats(values: Any) -> list[float]:
    """array-like(list/Series/ndarray)를 NaN 제거된 float 리스트로 변환한다."""
    out = []
    for v in values:
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f == f and not math.isinf(f):    # NaN(f != f)·inf 제외
            out.append(f)
    return out


def psi(expected: Any, actual: Any, bins: int = 10) -> float:
    """기대(학습) 분포 대비 실제(최근) 분포의 PSI를 계산한다.

    expected : 기준 분포 표본 (예: 학습 구간의 피처 값)
    actual   : 비교 분포 표본 (예: 최근 구간의 피처 값)
    bins     : 구간 수 — expected의 분위수로 경계를 잡는다 (극단값에 견고).

    빈 구간은 epsilon으로 보정해 log(0) 폭주를 막는다. 표본이 부족하거나
    expected가 상수라 구간을 만들 수 없으면 NaN을 반환한다 — '계산 불가'를
    0(안정)으로 위장하지 않기 위함이다.
    """
    exp = sorted(_as_floats(expected))
    act = _as_floats(actual)
    if len(exp) < bins or len(act) == 0:
        return float("nan")
    if exp[0] == exp[-1]:                    # 상수 피처 — 분포 비교 불가
        return float("nan")

    # expected 분위수로 구간 경계 생성 (중복 경계는 병합)
    edges: list[float] = []
    for i in range(1, bins):
        q = exp[min(len(exp) - 1, int(len(exp) * i / bins))]
        if not edges or q > edges[-1]:
            edges.append(q)
    if not edges:                            # 전부 같은 값 — 분포 비교 불가
        return float("nan")

    def _hist(vals: list[float]) -> list[int]:
        counts = [0] * (len(edges) + 1)
        for v in vals:
            k = 0
            while k < len(edges) and v >= edges[k]:
                k += 1
            counts[k] += 1
        return counts

    exp_counts, act_counts = _hist(exp), _hist(act)
    total = 0.0
    for ec, ac in zip(exp_counts, act_counts):
        pe = max(ec / len(exp), _EPS)
        pa = max(ac / len(act), _EPS)
        total += (pe - pa) * math.log(pe / pa)
    return total


def interpret_psi(value: float) -> str:
    """PSI 값을 관례적 한국어 등급으로 해석한다."""
    if value != value:                       # NaN
        return "계산불가 (표본 부족 또는 상수 피처)"
    if value < 0.1:
        return "안정"
    if value < 0.25:
        return "주의"
    return "드리프트"


def feature_drift_report(train_df: Any, recent_df: Any, bins: int = 10) -> dict[str, float]:
    """두 DataFrame의 공통 컬럼별 PSI를 계산해 {feature: psi}로 반환한다.

    train_df : 학습 구간 피처 (기준 분포)
    recent_df: 최근 구간 피처 (비교 분포)
    """
    common = [c for c in train_df.columns if c in recent_df.columns]
    return {c: psi(list(train_df[c]), list(recent_df[c]), bins) for c in common}


def drift_summary(report: dict[str, float]) -> str:
    """feature_drift_report 결과를 한국어 요약 문자열로 만든다.

    ⚠️ '안정'이 모델의 유효성을 보장하지 않는다 — 성과 지표와 함께 볼 것.
    """
    if not report:
        return "피처 드리프트: 비교할 공통 피처가 없습니다."
    lines = ["피처 드리프트 (PSI — <0.1 안정, 0.1~0.25 주의, ≥0.25 드리프트)"]
    for name, value in sorted(report.items(), key=lambda kv: -(kv[1] if kv[1] == kv[1] else -1)):
        shown = "NaN" if value != value else f"{value:.3f}"
        lines.append(f"  {name:<12s}: {shown:>6s}  [{interpret_psi(value)}]")
    n_drift = sum(1 for v in report.values() if v == v and v >= 0.25)
    if n_drift:
        lines.append(f"  ⚠️ {n_drift}개 피처가 드리프트 — 모델이 배운 시장과 지금 시장이 "
                     "다릅니다. 재학습하거나 비중을 줄이는 것을 검토하세요.")
    else:
        lines.append("  드리프트 등급 피처는 없습니다. 단, 분포가 같아도 피처-수익 관계는 "
                     "바뀔 수 있으니 OOS 성과를 함께 확인하세요.")
    return "\n".join(lines)
