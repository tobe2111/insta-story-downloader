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
    """닫혀 있는가 — 닫은 적이 있어도 다시 열었으면(`REOPENED`) 아니다."""
    return track in TRACKS and track not in REOPENED


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


# ─────────────────────────────────────────────────────────────────────────────
# 2기 — 닫은 트랙을 다시 연다 (2026-11-10 감사 366)
#
# 사장님: *"트랙들 다시 시작하자."*
#
# ■ 무엇을 이어받나
#
#   · **닫을 때의 최종 자산**(마지막 시세로 다 판 것으로 보고 정리 비용을 뺀 값)을
#     **현금으로** 들고 2기를 연다. 1기 손실을 지우지 않는다 — 누적 수익률은 처음
#     시작 자산(`start_cash`)에서 끊김 없이 이어진다. 2기만의 성적은 따로 센다.
#   · 닫을 때 이미 정리 비용을 뺐으므로 포지션도 비운다. 포지션을 그대로 두면
#     **이미 뺀 정리 비용이 공짜로 되돌아온다**(냈다고 적은 돈을 안 낸 셈이 된다).
#     2기는 다시 담을 때 진입 비용을 정직하게 문다.
#   · 운용 계좌(기계가 단타·주기·보유 / 엔진·보유·현금을 고르는 계좌)도 같은 규칙.
#     방식은 닫을 때 고른 것에서 이어 간다 — 갈아타기 규칙(문턱·최소 유지)은 그대로다.
#   · 지정가 그림자는 본 실험의 **복제**라 본 실험이 현금이 되면 비교가 깨진다 —
#     그림자의 1기 요약을 남기고 비운다(다음 회차가 2기 계좌를 다시 복제한다).
#   · 1기 기록(`closed`)은 `seasons`로 옮겨 **얼린다.** 회차 기록은 지우지 않는다.
#
# ■ 왜 같은 것을 다시 여는가 — 정직하게
#
#   1기에서 진 이유는 수수료였다(코인 단타 비용 전 −3.9% → 비용 후 −12.0%).
#   2기의 차이는 전략이 아니라 **고르는 쪽**이다: 운용 계좌가 처음부터 '그냥 보유'와
#   (선물은) '현금'을 후보로 들고 있어, 단타가 수수료에 지는 동안에는 기계가 매매를
#   멈출 수 있다. 1기 중반(10/11)에야 생긴 장치라 1기 성적에는 반만 들어 있다.
#   2기는 그 장치가 첫날부터 도는 실험이고, 판정은 새로 등록했다
#   (`prereg["*_s2"]` — 본 계좌보다 나은가).
# ─────────────────────────────────────────────────────────────────────────────

#: 다시 연 트랙 → 2기 시작일(한국 날짜). 다시 닫으려면 여기서 뺀다.
REOPENED = {"intraday": "2026-11-10", "intraday_us": "2026-11-10", "futures": "2026-11-10"}
REOPEN_APPROVED = "2026-11-10 사장님 — \"트랙들 다시 시작하자\""


def _liquidate_book(book: dict, final: float) -> None:
    book["cash"] = round(float(final), 6)
    book["positions"] = {}
    if "avg_cost" in book:
        book["avg_cost"] = {}


def reopen(track: str, st: dict) -> bool:
    """닫힌 1기를 `seasons`에 얼리고 그 최종 자산을 현금으로 2기를 연다(멱등)."""
    c = st.get("closed")
    if track not in REOPENED or not c:
        return False
    seasons = st.setdefault("seasons", [])
    sh = st.pop("limit_shadow", None)
    seasons.append({"n": len(seasons) + 1, **c, "rounds": len(st.get("rounds") or []),
                    "limit_shadow_final": ({k: sh.get(k) for k in
                                            ("since", "start_equity", "cost_paid",
                                             "filled_total", "unfilled_total")}
                                           if isinstance(sh, dict) else None)})
    del st["closed"]
    _liquidate_book(st, c["final_equity"])
    # 닫을 때 뺀 정리 비용은 실제로 낸 비용으로 센다 — 안 세면 '낸 비용' 칸이
    # 자산 변화보다 작아 그 차이가 어디로 갔는지 아무도 모른다.
    st["cost_paid"] = round(float(st.get("cost_paid") or 0.0) + float(c.get("exit_cost") or 0.0), 6)
    op, opc = st.get("operated"), c.get("operated")
    if isinstance(op, dict) and opc:
        op["cost_paid"] = round(float(op.get("cost_paid") or 0.0)
                                + float(opc.get("exit_cost") or 0.0), 6)
        if "positions" in op:            # 체결 장부(단타 운용 계좌)
            _liquidate_book(op, opc["final_equity"])
        else:                            # 배분 장부(선물 운용 계좌)
            op["equity"] = round(float(opc["final_equity"]), 4)
            op["peak"] = max(float(op.get("peak") or 0.0), op["equity"])
    st["season"] = {"n": len(seasons) + 1, "since": REOPENED[track],
                    "approved": REOPEN_APPROVED,
                    "start_equity": round(float(c["final_equity"]), 2),
                    "operated_start_equity": (round(float(opc["final_equity"]), 2)
                                              if opc else None)}
    return True


def _operated_equity(op) -> float | None:
    if not isinstance(op, dict):
        return None
    if "positions" in op:
        px = op.get("last_prices") or {}
        return float(op.get("cash") or 0.0) + sum(
            float(q) * float(px.get(k) or 0.0) for k, q in (op.get("positions") or {}).items())
    return float(op["equity"]) if op.get("equity") is not None else None


def season_public(st: dict, equity: float | None = None) -> dict | None:
    """공개 자료의 `season` 칸 — 지금 몇 기인가, 그 기의 성적, 지난 기의 최종 성적."""
    s = st.get("season")
    if not s:
        return None
    operated_equity = _operated_equity(st.get("operated"))
    def _ret(now, base):
        return (round((float(now) / float(base) - 1) * 100, 2)
                if now is not None and base else None)
    return {"n": s.get("n"), "since": s.get("since"), "approved": s.get("approved"),
            "start_equity": s.get("start_equity"),
            "return_pct": _ret(equity, s.get("start_equity")),
            "operated_start_equity": s.get("operated_start_equity"),
            "operated_return_pct": _ret(operated_equity, s.get("operated_start_equity")),
            "previous": [{k: p.get(k) for k in ("n", "on", "return_pct", "final_equity",
                                                 "start_cash", "exit_cost", "last_round")}
                         | {"operated_return_pct": (p.get("operated") or {}).get("return_pct")}
                         for p in st.get("seasons") or []]}


def reopen_track(track: str, state_dir: str = "state", say=print) -> bool:
    """장부 파일에서 한 트랙을 다시 연다(멱등). 연 날만 True."""
    meta = TRACKS.get(track)
    if not meta or track not in REOPENED:
        return False
    sp = os.path.join(state_dir, *meta["state"])
    try:
        with open(sp, encoding="utf-8") as f:
            st = json.load(f)
    except (OSError, ValueError):
        return False
    if not reopen(track, st):
        return False
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    say(f"🔓 {meta['label']} — {st['season']['n']}기 시작 "
        f"(이어받은 현금 {st['season']['start_equity']:,.2f})")
    return True
