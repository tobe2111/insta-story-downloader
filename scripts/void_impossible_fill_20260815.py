#!/usr/bin/env python3
"""2026-08-15 달러 시가로 체결된 미국주식 주문을 무효로 되돌린다 (감사 254).

일회성 복구 스크립트다. 지우지 않고 남기는 이유는 **무엇을 고쳤는지**가
저장소에 남아야 하기 때문이다 — 장부의 숫자가 하루아침에 달라졌는데
근거가 커밋 메시지 한 줄뿐이면, 그건 우리가 남에게 하지 말라고 적어 둔
바로 그 일이다.

무슨 일이 있었나
    통합 계좌는 원화 계좌다. 평가가격은 원화로 환산해 담는데, **대기 주문의
    체결가만 환산을 안 거치고 있었다**(감사 212가 한쪽만 고쳤다). 그래서
    2026-08-15에 META를 달러 시가 596.98로 사고, 그 포지션을 원화 종가
    832,868원으로 평가했다. 100만원 계좌가 7,154만원어치를 들고 있는 것으로
    기록됐고 자산은 7,249만원(+7,150%)이 됐다.

무엇을 하는가
    그 체결을 **없던 일로** 돌린다. 현실의 어떤 브로커도 100만원 계좌에
    7,154만원어치 주문을 채워 주지 않는다 — 실제로 같은 날 AMZN 주문
    24,017주는 현금 부족으로 거부됐다(cash_short). META만 달러 기준
    금액이 작아서 통과했을 뿐이다.

무엇을 하지 않는가
    "제대로 환산했다면 얼마였을까"를 계산해 넣지 않는다. 그건 일어나지
    않은 거래를 지어내는 일이다. 있었던 것으로 잘못 기록된 거래를 지울
    뿐이고, 지운 내용은 `_restated`에 원본 그대로 보관한다.
"""
from __future__ import annotations

import json
import pathlib

ACCOUNTS = ("state/paper/portfolio_ALL.json",
            "state/paper/portfolio_SHADOW.json")
DATE = "2026-08-15"
KEY = "us_stock:META"
FEE = 0.0006          # _fill_cost("us_stock") — 체결과 함께 나간 비용

WHY = ("2026-08-15 미국주식 대기 주문이 달러 시가로 체결됐습니다(감사 254). "
       "100만원 계좌가 META 85.9주(원화 7,154만원어치)를 산 것으로 기록됐고, "
       "그 결과 자산이 7,249만원(+7,150%)으로 찍혔습니다. 현실에서 낼 수 없는 "
       "주문이므로 체결을 무효로 되돌리고 쓴 돈을 현금으로 돌려놓습니다. "
       "없던 거래를 지어내지 않았습니다 — 있었던 것으로 기록된 불가능한 "
       "거래를 지웁니다.")


def repair(path: str) -> dict:
    p = pathlib.Path(path)
    st = json.loads(p.read_text("utf-8"))
    rec = next(r for r in st["history"] if r["date"] == DATE)

    voided, cash = [], float(st["cash"])
    for fill in list(rec.get("fills") or []):
        if fill["key"] != KEY:
            continue
        cash += float(fill["amount"]) * (1.0 + FEE)   # 나간 돈을 되돌린다
        voided.append(fill)
        rec["fills"].remove(fill)
    if not voided:
        return {"path": path, "already": True}

    st["cash"] = cash
    st["positions"].pop(KEY, None)
    (st.get("pending") or {}).pop(KEY, None)
    (st.get("last_trade") or {}).pop(KEY, None)

    equity = cash + sum(float(v["quantity"]) * float(v["last_price"])
                        for v in st["positions"].values())
    before = {k: rec.get(k) for k in
              ("equity", "pnl", "day_pct", "return_pct", "twr_pct")}
    rec["equity"] = round(equity, 2)
    start = float(st.get("start_cash") or 0.0)
    if rec.get("principal") is not None:
        rec["pnl"] = round(equity - float(rec["principal"]), 2)
    rec["return_pct"] = round((equity / start - 1.0) * 100.0, 2) if start else None
    prev = [r for r in st["history"] if r["date"] < DATE]
    if prev and prev[-1].get("equity"):
        rec["day_pct"] = round(
            (equity / float(prev[-1]["equity"]) - 1.0) * 100.0, 2)
    rec["twr_pct"] = rec["return_pct"]      # 입금이 없으므로 누적과 같다
    # 고친 사실을 기록 안에 남긴다 — 고친 흔적 없는 정정은 정정이 아니다.
    rec["_restated"] = {"why": WHY, "before": before, "voided_fills": voided}

    p.write_text(json.dumps(st, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return {"path": path, "cash": round(cash, 2), "equity": round(equity, 2),
            "voided": [(f["key"], f["quantity"]) for f in voided]}


if __name__ == "__main__":
    for acct in ACCOUNTS:
        print(repair(acct))
