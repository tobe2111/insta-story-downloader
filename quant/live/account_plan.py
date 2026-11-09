"""엔진을 온전히 따르려면 **계좌마다 얼마가 필요한가** (2026-11-09 감사 364).

사장님: *"모두 진행해"* — 개선 ①. 실거래 집행기(`daily_live`)는 국내 종목만 산다.
엔진 목표의 대부분은 미국 ETF·코인이라, 국내 계좌 하나로 실거래를 켜면 모의 장부와
**다른 전략**이 실제 돈으로 돈다(감사 340). 계좌를 여럿 쓰면 엔진을 따를 수 있지만,
그러려면 **돈을 계좌마다 미리 나눠 넣어야** 한다 — 그건 사람이 하는 일이다.

이 모듈은 주문을 내지 않는다. 본 계좌 장부의 마지막 목표(`applied`)를 시장별로 묶어
"국내 계좌 X원 · 미국 계좌 Y원 · 코인 계좌 Z원"을 계산하고, 실거래 전환 점검표가
그 숫자를 말한다. 실거래 전환 자체는 사장님 결정이다.

⚠️ 목표는 매주 바뀐다(엔진이 주 1회 고쳐 잡는다) — 이 숫자는 **오늘의 몫**이고, 계좌
간 비율이 움직이면 그만큼 돈을 옮기거나 그 차이를 받아들여야 한다. 그 사실도 적는다.
"""
from __future__ import annotations

import json
import os

MARKET_ACCOUNT = {"kr_stock": "국내 증권 계좌", "us_stock": "해외주식 계좌(달러)",
                  "crypto": "코인 거래소 계좌"}


def plan(state_dir: str = "state") -> dict | None:
    path = os.path.join(state_dir, "paper", "portfolio_ALL.json")
    try:
        with open(path, encoding="utf-8") as f:
            st = json.load(f)
    except (OSError, ValueError):
        return None
    hist = st.get("history") or []
    if not hist:
        return None
    rec = hist[-1]
    equity = float(rec.get("equity") or 0.0)
    applied = rec.get("applied") or {}
    if equity <= 0 or not applied:
        return None
    by: dict[str, float] = {}
    for key, w in applied.items():
        m = key.split(":", 1)[0]
        by[m] = by.get(m, 0.0) + abs(float(w or 0.0))
    invested = sum(by.values())
    rows = {m: {"account": MARKET_ACCOUNT.get(m, m), "weight": round(w, 4),
                "krw": round(w * equity)} for m, w in sorted(by.items())}
    return {"date": rec.get("date"), "equity": round(equity), "accounts": rows,
            "cash_weight": round(max(0.0, 1.0 - invested), 4),
            "domestic_only_covers": round(by.get("kr_stock", 0.0) / invested, 4)
            if invested > 0 else None}


def advisory(state_dir: str = "state") -> str | None:
    p = plan(state_dir)
    if not p:
        return None
    parts = [f"{r['account']} {r['krw']:,}원({r['weight'] * 100:.0f}%)"
             for r in p["accounts"].values()]
    cov = p["domestic_only_covers"]
    return (f"계좌 나누기({p['date']} 목표 기준, 자산 {p['equity']:,}원): "
            + " · ".join(parts)
            + f" · 현금 {p['cash_weight'] * 100:.0f}%. 국내 계좌 하나로 켜면 엔진의 "
            + (f"{cov * 100:.0f}%만" if cov is not None else "일부만")
            + " 따라갑니다. 목표는 매주 바뀌므로 계좌 간 비율도 움직입니다.")
