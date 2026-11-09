"""단타 두 트랙과 선물 트랙을 **닫는다** (2026-11-09 감사 357).

사장님: 전체 리뉴얼 — 트랙 정리는 "지금 바로 정리"를 골랐다(판정일
11/16·11/17 전에). 사전 등록을 판정일 전에 어기는 것이라 수정 이력
(`prereg.AMENDMENTS`)과 trust 페이지에 그 사실을 남긴다.

■ 닫는다는 것

  · 회차를 더 돌리지 않는다 — 매매도, 운용 계좌의 방식 판정도 멈춘다.
  · 마지막 장부 그대로 **마지막 시세로 다 판 것**으로 보고, 그 정리 비용(편도
    실측 비용 × 들고 있던 금액)을 뺀 값을 최종 성적으로 적는다. 정리 비용을
    빼지 않으면 닫는 순간 성적이 실제보다 좋아 보인다.
  · 기록은 지우지 않는다. 장부·공개 자료는 그대로 남고 `closed`가 덧붙는다.

■ 닫은 이유(장부 실측, 2026-11-09)

  · 코인 단타 −12.0%(비용 전 −3.9%) — 같은 기간 코인 그냥 보유는 +13.4%.
  · 미국 단타 −2.1%(비용 전 −0.9%) — 보유 −4.8%보다는 덜 잃었지만 비용이
    손실의 절반 이상이다.
  · 코인 선물 −18.3%(비용 전 −8.6%) — 운용 계좌는 10/13부터 '현금'을 골랐다.
"""
from __future__ import annotations

import json
import os

CLOSED_ON = "2026-11-09"
APPROVED = "2026-11-09 사장님 — 전체 리뉴얼, 트랙 정리 '지금 바로 정리'"

#: 닫힌 트랙 → 공개 자료 파일. 새 트랙을 닫으려면 여기에 적는다.
TRACKS = {
    "intraday": {"label": "코인 단타(1시간봉)", "doc": "intraday.json",
                 "state": ("intraday", "challenger.json"), "market": "crypto"},
    "intraday_us": {"label": "미국 단타(1시간봉)", "doc": "intraday_us.json",
                    "state": ("intraday", "us_challenger.json"), "market": "us_stock"},
    "futures": {"label": "코인 선물", "doc": "futures.json",
                "state": ("futures", "futures.json"), "market": "crypto"},
}


def is_closed(track: str) -> bool:
    return track in TRACKS


def _book(st: dict) -> tuple[dict, dict]:
    """(수량, 가격) — 선물은 마지막 회차 기록에서, 현물은 장부의 마지막 시세에서."""
    last = (st.get("rounds") or [{}])[-1]
    if "prices" in last and "positions" in last:
        return dict(last.get("positions") or {}), dict(last.get("prices") or {})
    return dict(st.get("positions") or {}), dict(st.get("last_prices") or {})


def exit_cost(positions: dict, prices: dict, cost_of) -> tuple[float, float]:
    """(들고 있던 금액, 정리 비용). cost_of(종목) → 편도 비용."""
    held = cost = 0.0
    for sym, q in (positions or {}).items():
        v = abs(float(q) * float(prices.get(sym) or 0.0))
        held += v
        cost += v * float(cost_of(sym))
    return held, cost


def _operated_final(op: dict | None, cost_of) -> dict | None:
    if not op:
        return None
    base = float(op.get("start_cash") or 0.0) or 1.0
    if "positions" in op:            # 체결 장부(단타 운용 계좌)
        held, cost = exit_cost(op.get("positions"), op.get("last_prices") or {}, cost_of)
        eq = float(op.get("cash") or 0.0) + held
    else:                            # 배분 장부(선물 운용 계좌) — 현금이면 정리할 것이 없다
        eq = float(op.get("equity") or base)
        cost = 0.0 if op.get("mode") == "cash" else eq * float(cost_of(None))
    final = eq - cost
    return {"mode": op.get("mode"), "equity_before": round(eq, 2),
            "exit_cost": round(cost, 2), "final_equity": round(final, 2),
            "return_pct": round((final / base - 1) * 100, 2)}


def closure(track: str, st: dict, cost_of) -> dict:
    """그 트랙의 최종 성적 — 마지막 장부 + 정리 비용."""
    meta = TRACKS[track]
    last = (st.get("rounds") or [{}])[-1]
    base = float(st.get("start_cash") or 0.0) or 1.0
    eq = float(last.get("equity") or base)
    held, cost = exit_cost(*_book(st), cost_of)
    final = eq - cost
    return {"on": CLOSED_ON, "label": meta["label"], "approved": APPROVED,
            "last_round": last.get("time") or last.get("at"),
            "equity_before": round(eq, 2), "held_value": round(held, 2),
            "exit_cost": round(cost, 2), "final_equity": round(final, 2),
            "return_pct": round((final / base - 1) * 100, 2),
            "start_cash": base, "currency": st.get("currency"),
            "operated": _operated_final(st.get("operated"), cost_of),
            "prereg_amended": True}


def close_all(state_dir: str = "state", docs_dir: str = "docs", say=print) -> dict:
    """닫힌 트랙마다 한 번만 최종 성적을 장부·공개 자료에 남긴다(멱등)."""
    from quant.live.daily import measured_cost_model
    done = {}
    for track, meta in TRACKS.items():
        sp = os.path.join(state_dir, *meta["state"])
        dp = os.path.join(docs_dir, meta["doc"])
        try:
            with open(sp, encoding="utf-8") as f:
                st = json.load(f)
        except (OSError, ValueError):
            continue
        if not st.get("closed"):
            if track == "futures" and st.get("operated"):
                # 감사 355의 계산 오류를 먼저 바로잡는다 — 안 그러면 −578%가 최종 성적이 된다.
                from quant.live.futures_mode import repair_switch_costs
                repair_switch_costs(st["operated"])
            def cost_of(sym, _m=meta["market"]):
                return measured_cost_model(_m, state_dir, symbol=sym).total_one_way()
            st["closed"] = closure(track, st, cost_of)
            with open(sp, "w", encoding="utf-8") as f:
                json.dump(st, f, ensure_ascii=False, indent=1)
            if track == "futures":
                # 바로잡은 운용 계좌가 공개 자료에도 실리게 한 번 다시 쓴다.
                from quant.live.futures_challenger import write_public_report
                write_public_report(st, docs_dir=docs_dir)
            say(f"🔒 {meta['label']} 종료 — 최종 {st['closed']['return_pct']:+.2f}%")
        try:
            with open(dp, encoding="utf-8") as f:
                pub = json.load(f)
        except (OSError, ValueError):
            pub = {}
        if pub.get("closed") != st["closed"]:
            pub["closed"] = st["closed"]
            with open(dp, "w", encoding="utf-8") as f:
                json.dump(pub, f, ensure_ascii=False, indent=2)
        done[track] = st["closed"]
    return done
