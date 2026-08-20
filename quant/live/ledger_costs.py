"""이 계좌가 비용으로 얼마를 냈나 — 세는 자리 하나 (2026-08-19 사장님 지시).

수수료·슬리피지는 예전부터 현금에서 제대로 빠지고 있었다. 자산도 수익률도
전부 비용을 뺀 뒤의 값이다. 빠진 것은 **얼마를 뺐는지 아무도 세지 않았다**는
것이다. 그래서 "지금까지 비용으로 얼마 냈어?"라는 질문에 답하려면 체결
기록을 되짚어 추정해야 했다.

되짚기는 위험하다. 2026-08-15 장부에는 **현금이 모자라 거부된 주문이
체결처럼 남아 있다**(감사 273에서 고쳤지만 그날 기록은 고치지 않는다 —
이 저장소는 과거를 고치지 않는다). 그 가짜 체결을 그대로 세면 없던 비용
6백만원어치가 생긴다.

그래서 두 갈래로 나눈다.

  · **앞으로** — 돈을 실제로 빼는 자리(가짜 브로커)가 직접 센다. 되짚지
    않으므로 틀릴 수 없다.
  · **지금까지** — 여기서 한 번만 되짚어 시작 잔액을 만든다. 그 되짚기는
    **같은 날 기록이 스스로 부인한 체결은 세지 않는다** — 현금 부족으로
    거부됐다고 그 기록이 적어 둔 종목이 그렇다. 날짜를 손으로 박아 넣지
    않고 기록이 남긴 표식만 본다.

되짚은 값은 추정이고, 화면에도 추정이라고 적는다.
"""
from __future__ import annotations


def _rate(market: str) -> float:
    from quant.live.daily import _fill_cost
    return _fill_cost(market)


def denied_keys(record: dict) -> set[str]:
    """그 기록이 **스스로 "못 샀다"고 적어 둔** 종목들.

    `cash_short`(현금 부족)와 `fill_refused`(체결가 이상)가 그 표식이다.
    같은 기록의 체결 목록에 남아 있어도, 그 종목은 실제로 사지 않았으므로
    비용도 내지 않았다.
    """
    out: set[str] = set()
    for row in (record.get("cash_short") or []):
        if isinstance(row, dict) and row.get("key"):
            out.add(str(row["key"]))
    ref = record.get("fill_refused")
    if isinstance(ref, dict):
        out.update(str(k) for k in ref)
    return out


def record_cost(record: dict) -> float:
    """한 기록이 실제로 낸 비용(원). 기록이 부인한 체결은 빼고 센다."""
    denied = denied_keys(record)
    total = 0.0
    for f in (record.get("fills") or []):
        key = str(f.get("key") or "")
        if key in denied:
            continue
        total += abs(float(f.get("amount") or 0.0)) * _rate(key.split(":")[0])
    return total


def reconstruct_cost_paid(history: list) -> dict:
    """지난 기록 전체를 되짚어 만든 시작 잔액과, 그 과정의 정직한 부작용.

    돌려주는 값:
        amount   — 되짚은 누적 비용(원)
        records  — 몇 개의 기록을 봤나
        denied   — 기록이 부인해서 세지 않은 체결 수
        upto     — 어느 날짜까지 되짚었나
    """
    amount, denied_n, upto = 0.0, 0, ""
    for rec in (history or []):
        if not isinstance(rec, dict):
            continue
        d = denied_keys(rec)
        denied_n += sum(1 for f in (rec.get("fills") or [])
                        if str(f.get("key") or "") in d)
        amount += record_cost(rec)
        upto = str(rec.get("date") or upto)
    return {"amount": round(amount, 2), "records": len(history or []),
            "denied": denied_n, "upto": upto}


def seed_cost_paid(st: dict) -> dict:
    """장부에 누적 비용 칸이 아직 없으면 한 번만 되짚어 채운다.

    이미 있으면 **손대지 않는다** — 실제로 센 값이 추정보다 언제나 옳다.
    """
    if st.get("cost_paid") is not None:
        return {}
    seed = reconstruct_cost_paid(st.get("history") or [])
    st["cost_paid"] = seed["amount"]
    st["cost_paid_seed"] = {
        **seed,
        "why": ("이 칸이 생기기 전의 비용은 체결 기록을 되짚어 채웠습니다 — "
                "추정입니다. 이후로는 돈을 뺄 때마다 실제로 셉니다."),
    }
    return st["cost_paid_seed"]
