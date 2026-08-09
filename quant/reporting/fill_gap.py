"""체결 가정 검증 — 페이퍼 실측 개장 갭 vs 백테스트 비용 가정.

백테스트는 신호 봉 '종가'에서 비중을 바꾸고 고정 수수료+슬리피지
(CostModel)를 빼는 회계다. 반면 페이퍼(v0.5.0 회계)는 주식을 '결정
다음 세션 시가'에만 체결한다 — 결정 종가와 실제 체결 시가 사이의 개장
갭은 백테스트에는 없고 페이퍼에서만 실측되는 비용이다. 페이퍼 장부에는
결정 시점 가격과 체결가가 둘 다 기록되므로, '결정→체결 사이에 가격이
얼마나 불리하게 움직였나'를 표본으로 잴 수 있다.

실측 불리 갭이 가정된 슬리피지 쿠션을 상회하면 백테스트가 낙관적이라는
뜻이다. 그 사실을 숨기지 않고 사이트에 그대로 공개한다(표시 전용 —
사이징·판단에는 개입하지 않는다).
"""
from __future__ import annotations

import json
import os


def _iter_fill_gaps(hist: list[dict]) -> list[tuple[str, float, float]]:
    """기록에서 (체결일, |갭|bp, 불리갭 bp)를 뽑는다.

    갭 = 체결가(다음 세션 시가) / 결정 시점 가격(결정일 종가) − 1.
    불리갭 = 방향(매수 +1/매도 −1) × 갭 — 양수면 실측이 가정보다 불리했다.
    방향은 결정일 직전 기록 대비 목표 비중의 변화로 판정하고, 비중 변화가
    없으면(리밸런스 밴드로 주문이 안 나감) 표본에서 뺀다.
    """
    out: list[tuple[str, float, float]] = []
    by_date = {str(r.get("date", "")): i for i, r in enumerate(hist)}
    for r in hist:
        fill = r.get("fill")
        if not fill or not fill.get("decided_bar"):
            continue
        dec_date = str(fill["decided_bar"])[:10]
        j = by_date.get(dec_date)
        if j is None:
            continue
        try:
            dec_price = float(hist[j]["price"])
            fill_price = float(fill["price"])
            target = float(fill.get("weight", 0.0))
            prev_w = float(hist[j - 1].get("weight", 0.0)) if j > 0 else 0.0
        except (KeyError, TypeError, ValueError):
            continue
        if dec_price <= 0 or fill_price <= 0:
            continue
        dirn = 1.0 if target > prev_w + 1e-9 else (
            -1.0 if target < prev_w - 1e-9 else 0.0)
        if dirn == 0.0:
            continue
        gap = fill_price / dec_price - 1.0
        out.append((str(r.get("date", "")), abs(gap) * 1e4, dirn * gap * 1e4))
    return out


def fill_gap_report(state_dir: str = "state", window: int = 90) -> dict | None:
    """시장별 실측 개장 갭 통계 vs 백테스트 가정(수수료+슬리피지)을 만든다.

    반환: {"window", "total_fills", "markets": {market: {n, mean_abs_gap_bp,
    mean_adverse_bp, worst_adverse_bp, assumed_bp, optimistic}}} 또는
    표본이 하나도 없으면 None. optimistic=True 는 '실측 불리 갭 평균이
    가정을 넘는다'는 뜻 — 백테스트가 낙관적일 수 있다는 자기 고발 플래그.
    """
    from quant.backtest.costs import CostModel

    paper_dir = os.path.join(state_dir, "paper")
    if not os.path.isdir(paper_dir):
        return None
    per_market: dict[str, list[tuple[float, float]]] = {}
    for name in sorted(os.listdir(paper_dir)):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(paper_dir, name), encoding="utf-8") as f:
                st = json.load(f)
        except (OSError, ValueError):
            continue
        market = str(st.get("market", ""))
        if not market or market.startswith("portfolio"):
            continue                      # 통합 계좌 fills는 종목 계좌와 중복
        gaps = _iter_fill_gaps((st.get("history") or [])[-window:])
        if gaps:
            per_market.setdefault(market, []).extend(
                (a, s) for _, a, s in gaps)
    if not per_market:
        return None
    markets: dict[str, dict] = {}
    total = 0
    for market, rows in sorted(per_market.items()):
        n = len(rows)
        total += n
        mean_abs = sum(a for a, _ in rows) / n
        mean_adv = sum(s for _, s in rows) / n
        worst = max(s for _, s in rows)
        cm = CostModel.for_market(market)
        assumed = float(cm.fee + cm.slippage) * 1e4
        markets[market] = {
            "n": n,
            "mean_abs_gap_bp": round(mean_abs, 1),
            "mean_adverse_bp": round(mean_adv, 1),
            "worst_adverse_bp": round(worst, 1),
            "assumed_bp": round(assumed, 1),
            "optimistic": mean_adv > assumed,
        }
    return {"window": window, "total_fills": total, "markets": markets}
