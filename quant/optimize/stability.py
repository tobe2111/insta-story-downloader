"""파라미터 안정성 점수 — '외딴 봉우리'를 수치로 감점한다.

히트맵의 "넓은 초록 고원 = 견고, 외딴 초록 점 = 과최적화"를 눈이 아니라
숫자로 판정한다. 각 파라미터 조합의 점수를 '이웃 조합들(축마다 한 스텝 이동)'
점수와 함께 평균해 robust_score를 만든다. 최적점이 이웃과 함께 좋아야
(고원) 높은 robust_score를 받고, 혼자만 좋으면(봉우리) 깎인다.

사용:
    gs = grid_search(df, MovingAverageCross, grid)
    scored = stability_scores(gs["results"], objective="sharpe")
    best = robust_best(scored, objective="sharpe")   # 견고성 반영 최적 파라미터

⚠️ robust_score가 높아도 미래 수익은 보장되지 않는다 — 파라미터 선택이
   노이즈에 덜 민감하다는 뜻일 뿐이다.
"""
from __future__ import annotations

import math
from typing import Any

from quant.objective import LOWER_IS_BETTER


def _axes(results: list[dict], objective: str) -> dict[str, list]:
    """결과 목록에서 파라미터 축(정렬된 고유값)을 추출한다."""
    axes: dict[str, set] = {}
    for row in results:
        for k, v in row.items():
            if k == objective:
                continue
            axes.setdefault(k, set()).add(v)
    return {k: sorted(vs) for k, vs in axes.items()}


def stability_scores(results: list[dict], objective: str = "sharpe") -> list[dict]:
    """grid_search의 results에 이웃 통계와 robust_score를 붙여 반환한다.

    이웃 = 정확히 한 파라미터가 그 축에서 한 스텝(±1 인덱스) 이동한 조합.
    robust_score = (자신 + 이웃) 점수의 평균. 이웃이 없으면 자신의 점수.
    neighbor_std = 이웃 점수의 표준편차(민감도 지표 — 클수록 위험).
    """
    axes = _axes(results, objective)
    index: dict[tuple, float] = {}
    for row in results:
        key = tuple(sorted((k, v) for k, v in row.items() if k != objective))
        index[key] = row[objective]

    out: list[dict] = []
    for row in results:
        params = {k: v for k, v in row.items() if k != objective}
        neigh: list[float] = []
        for k, v in params.items():
            vals = axes[k]
            i = vals.index(v)
            for j in (i - 1, i + 1):
                if 0 <= j < len(vals):
                    nb = dict(params)
                    nb[k] = vals[j]
                    key = tuple(sorted(nb.items()))
                    if key in index and math.isfinite(index[key]):
                        neigh.append(index[key])
        own = row[objective]
        pool = [own] + neigh if math.isfinite(own) else neigh
        robust = sum(pool) / len(pool) if pool else float("nan")
        if len(neigh) > 1:
            mu = sum(neigh) / len(neigh)
            nstd = math.sqrt(sum((x - mu) ** 2 for x in neigh) / (len(neigh) - 1))
        else:
            nstd = 0.0
        out.append({**row, "n_neighbors": len(neigh),
                    "neighbor_std": nstd, "robust_score": robust})
    return out


def robust_best(scored: list[dict], objective: str = "sharpe") -> dict | None:
    """robust_score 기준 최적 조합의 파라미터를 반환한다(방향 보정 포함)."""
    sign = -1.0 if objective in LOWER_IS_BETTER else 1.0
    best_row = None
    best_val = float("-inf")
    for row in scored:
        v = row.get("robust_score")
        if v is None or not math.isfinite(v):
            continue
        if sign * v > best_val:
            best_val = sign * v
            best_row = row
    if best_row is None:
        return None
    drop = {objective, "n_neighbors", "neighbor_std", "robust_score"}
    return {k: v for k, v in best_row.items() if k not in drop}


def stability_report(scored: list[dict], objective: str = "sharpe") -> str:
    """원점수 1등과 robust 1등을 비교하는 한국어 요약."""
    sign = -1.0 if objective in LOWER_IS_BETTER else 1.0
    fin = [r for r in scored if math.isfinite(r.get(objective, float("nan")))]
    if not fin:
        return "유효한 결과가 없습니다."
    raw = max(fin, key=lambda r: sign * r[objective])
    rob = max((r for r in fin if math.isfinite(r.get("robust_score", float("nan")))),
              key=lambda r: sign * r["robust_score"], default=raw)
    drop = {objective, "n_neighbors", "neighbor_std", "robust_score"}
    p_raw = {k: v for k, v in raw.items() if k not in drop}
    p_rob = {k: v for k, v in rob.items() if k not in drop}
    same = p_raw == p_rob
    lines = [
        f"원점수 1등    : {p_raw} ({objective}={raw[objective]:.3f}, "
        f"이웃 평균={raw['robust_score']:.3f})",
        f"견고성 1등    : {p_rob} ({objective}={rob[objective]:.3f}, "
        f"이웃 평균={rob['robust_score']:.3f})",
    ]
    if same:
        lines.append("판정: 최적점이 고원 위에 있음 — 파라미터 선택이 비교적 견고.")
    else:
        lines.append("판정: ⚠️ 원점수 1등이 '외딴 봉우리'일 수 있음 — "
                     "견고성 1등 파라미터를 쓰는 것이 안전.")
    lines.append("⚠️ 견고해도 미래 수익은 보장되지 않습니다.")
    return "\n".join(lines)
