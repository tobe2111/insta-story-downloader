"""판 시점에 얼마를 벌었나 — 장부를 되짚어 계산한다 (2026-08-22 사장님 요청).

사장님 요청: *"매도 시점 손익을 써 달라."*

거래내역 표에는 "언제 얼마에 얼마어치를 사고팔았나"만 있었다. 그래서 표를
봐도 **그 매도가 이익 실현인지 손절인지 알 수가 없다.** 판 금액만으로는
답이 안 나온다 — 얼마에 샀는지를 같이 알아야 한다.

    실현 손익 = 판 수량 × (판 가격 − 평균 매입가) − 그 거래 비용

⚠️ **비용을 뺀 뒤**의 값이다. "팔아서 100 벌었는데 수수료로 120을 냈다"면
   그 매도는 이익이 아니다.

■ 왜 장부에 적지 않고 되짚는가

장중 실험 트랙은 파는 그 자리에서 평균 단가를 들고 다니며 손익을 확정해
기록에 적는다(그쪽은 오늘 새로 시작한 계좌라 처음부터 셀 수 있었다).

이 계좌는 다르다. 이미 **지난 매도가 여럿 쌓여 있고**, 그 기록에는 평균
매입가가 없다. 앞으로 것만 적으면 지난 매도는 영영 '—'로 남는다.

그런데 이 값은 **되짚어서 정확히 복원할 수 있다.** 매수와 매도가 전부
기록에 있으므로, 처음부터 순서대로 따라가면 매 시점의 평균 매입가가
나온다. 기록을 한 글자도 고치지 않고 계산만 하는 것이다 —
**과거를 고치지 않는다**는 규칙 그대로다.

■ 되짚기의 함정 하나 (감사 273·290이 이미 만난 자리)

2026-08-15 장부에는 **현금이 모자라 거부된 주문이 체결처럼 남아 있다.**
그걸 매수로 세면 없던 재고 6백만원어치가 생기고, 그 뒤의 모든 평균 단가와
실현 손익이 통째로 틀린다. 그래서 **그 기록이 스스로 "못 샀다"고 적어 둔
종목은 세지 않는다** — 날짜를 손으로 박지 않고 기록이 남긴 표식만 본다
(`ledger_costs.denied_keys`와 같은 판단을 재사용한다. 같은 판단을 두 곳에
따로 두면 언젠가 갈라진다).

■ 모르는 것은 모른다고 한다

장부가 시작되기 전부터 들고 있던 종목을 팔면 살 때 값이 기록에 없다.
그때 실현 손익은 **0이 아니라 '모른다'**이다. 0으로 적으면 본전이라는
뜻이 되고, 그건 거짓말이다. 이런 매도는 ``None``을 돌려준다.
"""
from __future__ import annotations

_EPS = 1e-12


def _fee_rate(key: str) -> float:
    """그 시장의 편도 비용률 — 장부가 비용을 셀 때 쓰는 값과 같은 것."""
    from quant.live.ledger_costs import _rate
    return _rate(str(key).split(":")[0])


def realized_by_fill(history: list) -> dict:
    """기록을 처음부터 따라가며 매도마다 실현 손익을 계산한다.

    반환: {(날짜, 그 기록 안에서의 체결 순번): {"realized_pnl": float,
                                              "avg_cost": float}}
    매수와 '모르는' 매도는 아예 넣지 않는다 — 없는 칸이 '모른다'를 뜻한다.
    """
    qty: dict = {}
    avg: dict = {}
    out: dict = {}
    for rec in (history or []):
        if not isinstance(rec, dict):
            continue
        date = str(rec.get("date") or "")
        denied = _denied(rec)
        for i, f in enumerate(rec.get("fills") or []):
            if not isinstance(f, dict):
                continue
            key = str(f.get("key") or "")
            # 기록이 스스로 부인한 체결 — 돈이 안 움직였으므로 재고도 없다.
            if not key or key in denied:
                continue
            try:
                price = float(f.get("price"))
                q = abs(float(f.get("quantity")))
                amount = abs(float(f.get("amount") or 0.0))
            except (TypeError, ValueError):
                continue          # 수량·금액이 없던 옛 기록 — 셀 수 없다
            if not (price > 0) or not (q > _EPS):
                continue
            held = float(qty.get(key) or 0.0)
            prev = float(avg.get(key) or 0.0)
            if str(f.get("side") or "").lower() == "sell":
                # 장부가 모르는 재고를 판 매도 — 살 때 값이 없으니 잴 수 없다.
                if held <= _EPS or prev <= 0.0:
                    continue
                sold = min(q, held)
                fee = amount * _fee_rate(key)
                out[(date, i)] = {
                    "realized_pnl": round(sold * (price - prev) - fee, 2),
                    "avg_cost": round(prev, 6),
                }
                left = held - sold
                if left <= _EPS:
                    # ⚠️ 재고만 지운다. 평균 단가는 **일부러 남긴다** —
                    #    다음 매수가 `held == 0`에서 시작하므로 옛 값은
                    #    가중평균에 0으로 곱해져 사라진다. 여기서 avg까지
                    #    지우는 줄을 뒀었는데, 변이 시험이 "그 줄을 없애도
                    #    아무 검사가 안 깨진다"고 알려 줬다 — 지워도 결과가
                    #    같은 줄은 안전장치가 아니라 장식이다(감사 303).
                    qty.pop(key, None)
                else:
                    qty[key] = left      # 평균 단가는 그대로(부분 매도)
            else:
                new_q = held + q
                if new_q > _EPS:
                    avg[key] = (held * prev + q * price) / new_q
                qty[key] = new_q
    return out


def _denied(record: dict) -> set:
    from quant.live.ledger_costs import denied_keys
    return denied_keys(record)


def attach_realized(trades: list, history: list) -> list:
    """거래내역 줄마다 실현 손익을 붙여 돌려준다(원본은 안 고친다).

    ``trades``의 각 줄은 ``date``와 ``fill_index``로 자기 자리를 안다.
    """
    table = realized_by_fill(history)
    out = []
    for t in (trades or []):
        got = table.get((str(t.get("date") or ""), t.get("fill_index")))
        out.append({**t, **got} if got else dict(t))
    return out
