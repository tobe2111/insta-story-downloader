"""실효 독립 베팅 수(ENB)와 평시/하락일 상관 — 외부 검토 반영분.

2026-08-18 외부 검토의 두 지적을 그대로 구현한다:

① "종목 수가 아니라 **실효 독립 베팅 수**를 공개하라." — 20종목을 들고
   있어도 서로 같이 움직이면 실제로는 몇 개의 베팅만 한 셈이다. 여기서
   그 숫자를 재서 status.json으로 공개한다.

② "평균 상관이 아니라 **하락일 상관을 병기**하라." — 시장이 떨어지는 날
   상관은 1로 몰린다(다 같이 떨어진다). 평시 평균만 보여주면 분산 효과를
   과대평가하게 된다. 평시/하락일을 나란히 재서 risk.json에 싣는다.

⚠️ 둘 다 **진단 전용**이다. 사이징·킬스위치 등 실행 경로는 건드리지
   않는다(구조 동결 — 2세대 백로그에서만 실행 반영을 논의한다).

방법의 정직성:
- 재료는 페이퍼 장부의 **일별 자산 수익률**(실제 베팅의 결과)이다.
  가격 수익률이 아니라 자산 수익률을 쓰는 이유: 현금으로 쉰 날은 0%로
  들어가므로, "포지션이 실제로 얼마나 겹쳤는가"를 재게 된다.
- 표본이 작을 때 고유값 분해는 그럴듯한 거짓 정밀도를 만든다. 그래서
  기본 ENB는 등상관 근사 N/(1+(N-1)·ρ̄) 로 계산하고(방법을 함께 기록),
  관측일 수가 종목 수 이상으로 쌓이면 고유값 참여비 (Σλ)²/Σλ² 를
  추가로 병기한다.
- 표본 부족이면 숫자 대신 **이유**를 돌려준다. 없는 표본으로 만든
  숫자는 공개하지 않는다.
"""
from __future__ import annotations

import json
import os

# 등상관 근사도 이 밑으로는 잡음이다 — 겹치는 관측일 최소 요구치.
MIN_DAYS = 5
# 고유값 참여비는 관측일 ≥ 종목 수일 때만 병기한다(랭크 부족 방지).
# 하락일 상관은 하락일이 이 밑이면 이유만 기록한다.
MIN_DOWN_DAYS = 5


def _day_returns(history: list[dict]) -> dict[str, float]:
    """장부 history → {날짜: 일수익률}. 자산이 0 이하인 행은 버린다."""
    out: dict[str, float] = {}
    prev = None
    for rec in history:
        try:
            eq = float(rec.get("equity") or 0.0)
            date = str(rec.get("date") or "")
        except (TypeError, ValueError):
            continue
        if eq <= 0 or not date:
            prev = None
            continue
        if prev is not None and prev > 0:
            out[date] = eq / prev - 1.0
        prev = eq
    return out


def returns_by_symbol(state_dir: str = "state") -> dict[str, dict[str, float]]:
    """전 종목 페이퍼 장부 → {종목키: {날짜: 일수익률}}.

    통합 계좌(portfolio)는 제외 — 종목들의 합이라 상관을 재는 대상이
    아니다. 읽기 실패는 그 파일만 건너뛴다(진단이 배치를 막으면 안 된다).
    """
    from quant.live.ledger_basics import ledger_files
    out: dict[str, dict[str, float]] = {}
    for pth in ledger_files(state_dir):
        if "portfolio" in os.path.basename(pth).lower():
            continue
        try:
            with open(pth, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        rets = _day_returns(d.get("history") or [])
        if rets:
            out[f"{d.get('market', '?')}:{d.get('symbol', '?')}"] = rets
    return out


def _frame(series: dict[str, dict[str, float]]):
    """종목별 수익률을 날짜 정렬 표로 — 전 종목이 겹치는 날만 남긴다.

    겹치는 날만 쓰는 이유: 시장마다 거래일이 다른데(코인은 주말도 열림),
    빠진 날을 0으로 채우면 상관이 실제보다 낮게 나온다 — 분산 효과를
    부풀리는 방향의 거짓말이라 채우지 않는다.
    """
    import pandas as pd
    df = pd.DataFrame(series).dropna()
    # 상관이 정의되지 않는 무변동 종목(내내 현금 등)은 제외하되 개수는 남긴다.
    flat = [c for c in df.columns if float(df[c].std()) == 0.0]
    return df.drop(columns=flat), len(flat)


def _avg_pairwise_corr(df) -> float | None:
    """상관행렬의 비대각 평균 — '한 쌍을 무작위로 집으면 얼마나 닮았나'."""
    n = df.shape[1]
    if n < 2:
        return None
    corr = df.corr().to_numpy()
    total = float(corr.sum())               # 대각 n개는 항상 1
    return (total - n) / (n * (n - 1))


def effective_bets(state_dir: str = "state") -> dict:
    """실효 독립 베팅 수 — status.json 공개용 스냅샷.

    표본 부족이면 {"reason": ...}만 돌려준다. 이유 없는 침묵도,
    표본 없는 숫자도 만들지 않는다.
    """
    df, n_flat = _frame(returns_by_symbol(state_dir))
    n_days, n_sym = df.shape
    if n_sym < 2 or n_days < MIN_DAYS:
        return {"reason": (
            f"표본 부족 — 전 종목이 겹치는 관측일 {n_days}일 / 최소 "
            f"{MIN_DAYS}일 (무변동 제외 {n_sym}종목). 표본이 쌓이면 "
            "자동으로 숫자가 나타납니다.")}
    rho = _avg_pairwise_corr(df)
    # 등상관 근사: 평균 상관 ρ̄인 N개 자산의 분산은 독립 자산
    # N/(1+(N-1)ρ̄)개의 분산과 같다. ρ̄<0이면 근사가 종목 수를 넘을 수
    # 있는데, 그 낙관은 공개하지 않는다(종목 수로 상한).
    enb = n_sym / (1.0 + (n_sym - 1) * max(rho, 0.0))
    out = {
        "enb": round(min(enb, float(n_sym)), 2),
        "method": "등상관 근사 N/(1+(N-1)ρ̄)",
        "n_symbols": n_sym,
        "n_flat_excluded": n_flat,
        "n_days": n_days,
        "avg_pairwise_corr": round(rho, 4),
        "note": ("명목 종목 수보다 작을수록 포지션이 겹쳐 움직인다는 뜻 — "
                 "진단 전용이며 사이징에는 반영하지 않는다(2세대 백로그)"),
    }
    if n_days < 20:
        # 표본이 작으면 상관 추정 자체가 흔들린다 — 숫자를 감추는 대신
        # 흔들린다는 사실을 함께 싣는다(감추면 나중에 숫자가 크게 바뀔 때
        # 조작처럼 보인다).
        out["caveat"] = (f"관측일 {n_days}일 — 20일 미만이라 추정이 "
                         "불안정하다. 표본이 쌓이면 숫자가 흔들릴 수 있다.")
    if n_days >= n_sym:
        # 표본이 충분할 때만 고유값 참여비를 병기 — 상관행렬의 고유값
        # λ들로 (Σλ)²/Σλ². 등상관 근사와 달리 집단 구조(코인끼리,
        # 주식끼리)를 있는 그대로 반영한다.
        import numpy as np
        lam = np.linalg.eigvalsh(df.corr().to_numpy())
        lam = np.clip(lam, 0.0, None)
        out["enb_eigen"] = round(float(lam.sum() ** 2 / (lam ** 2).sum()), 2)
    return out


def correlation_regimes(state_dir: str = "state") -> dict:
    """평시 vs 하락일 평균 쌍상관 — risk.json 병기용.

    하락일 = 전 종목 등가중 평균 수익률이 0 미만인 날. 하락일 상관이
    평시보다 크면 "떨어질 때는 같이 떨어진다"는 뜻이고, 분산 효과를
    평시 숫자로 낙관하면 안 된다는 경고다.
    """
    df, _ = _frame(returns_by_symbol(state_dir))
    n_days, n_sym = df.shape
    if n_sym < 2 or n_days < MIN_DAYS:
        return {"reason": f"표본 부족 — 겹치는 관측일 {n_days}일 / 최소 {MIN_DAYS}일"}
    all_corr = _avg_pairwise_corr(df)
    down = df[df.mean(axis=1) < 0]
    out = {
        "avg_corr_all_days": round(all_corr, 4),
        "n_days": n_days,
        "n_symbols": n_sym,
        "n_down_days": int(down.shape[0]),
        "note": ("하락일 상관이 평시보다 높으면 분산 효과는 필요한 순간에 "
                 "줄어든다 — 진단 전용, 실행 미반영(구조 동결)"),
    }
    if down.shape[0] >= MIN_DOWN_DAYS:
        out["avg_corr_down_days"] = round(_avg_pairwise_corr(down), 4)
    else:
        out["down_days_reason"] = (
            f"하락일 {down.shape[0]}일 — 최소 {MIN_DOWN_DAYS}일 미만이라 "
            "하락일 상관은 아직 계산하지 않습니다.")
    return out
