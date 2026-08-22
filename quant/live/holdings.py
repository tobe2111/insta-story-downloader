"""종목마다 지금 얼마 벌고 있나 — 실험 트랙 세 곳이 **같은 한 곳**을 쓴다.

사장님 지시(2026-08-22): *"각 페이지들의 결과값들이 종목마다 각 얼마 현재
손해 혹은 이익인지 알려줘야 해."*

맞는 지적이었다. 본 계좌(100만 챌린지)의 잔고 표에는 종목마다 평균매입가·
현재가·평가금액·손익이 다 있었는데, **실험 세 트랙(코인·미국주식·선물)의
화면에는 수량밖에 없었다.** "BTC 0.0022개 들고 있음"은 읽는 사람에게
아무것도 말해 주지 않는다 — 그래서 벌고 있나 잃고 있나.

■ 왜 트랙마다 따로 안 쓰고 여기 모으나

FROZEN_IDEAS ①: 같은 판단을 두 곳에 두면 언젠가 갈라진다. 손익 계산은
세 트랙이 완전히 같고, 다른 것은 통화 이름뿐이다. 갈라지면 같은 날 세
페이지가 서로 다른 셈법으로 손익을 말하게 된다.

■ 평균매입가를 어디서 얻나

트랙들은 체결 기록을 회차마다 남긴다. 그것을 처음부터 따라가면 매 시점의
평균매입가가 나온다 — 본 계좌에서 쓴 것과 같은 방법이다(감사 303).
기록을 고치지 않고 **계산만** 한다.

⚠️ **숏(음수 수량)도 다룬다.** 선물 트랙은 수량이 음수일 수 있고, 그때
   손익의 부호는 반대다 — 값이 내리면 번다. 롱 전용 계산을 그대로 쓰면
   선물 페이지의 손익이 통째로 뒤집힌다.

■ 모르는 것은 모른다고 한다

시세를 못 받은 종목, 살 때 값이 기록에 없는 종목은 손익을 **지어내지
않는다.** 그 칸은 비어 있고(``None``), 화면이 '—'로 그린다. 0으로 적으면
'본전'이라는 뜻이 되고, 그건 거짓말이다.
"""
from __future__ import annotations

_EPS = 1e-12


def avg_cost_from_rounds(rounds: list) -> dict:
    """회차 기록의 체결을 처음부터 따라가 종목별 평균매입가를 복원한다.

    롱은 양수 수량, 숏은 음수 수량으로 다룬다. 방향이 뒤집히면(롱→숏)
    **뒤집힌 뒤의 값**이 새 진입가다 — 옛 방향의 평단을 들고 가면 그 뒤
    손익이 전부 틀린다.
    """
    qty: dict = {}
    avg: dict = {}
    for r in (rounds or []):
        if not isinstance(r, dict):
            continue
        for t in (r.get("trades") or []):
            if not isinstance(t, dict):
                continue
            sym = str(t.get("symbol") or "")
            try:
                px = float(t.get("price"))
                notional = float(t.get("notional"))
            except (TypeError, ValueError):
                continue
            if not sym or not (px > 0) or abs(notional) < _EPS:
                continue
            dq = notional / px                      # 부호 그대로(매도는 음수)
            held = float(qty.get(sym) or 0.0)
            prev = float(avg.get(sym) or 0.0)
            new = held + dq
            if abs(new) <= _EPS:                    # 전량 청산
                qty.pop(sym, None)
                avg.pop(sym, None)
                continue
            if held == 0.0 or (held > 0) == (dq > 0):
                # 같은 방향으로 늘린다 — 가중평균
                avg[sym] = (abs(held) * prev + abs(dq) * px) / abs(new)
            elif (new > 0) != (held > 0):
                avg[sym] = px                       # 방향이 뒤집혔다
            # 같은 방향으로 줄인다(부분 청산) → 평단은 그대로
            qty[sym] = new
    return avg


def holdings_view(positions: dict, prices: dict, avg_cost: dict,
                  currency: str = "USDT") -> list:
    """종목마다 한 줄 — 방향·수량·평단·현재가·평가금액·손익·수익률.

    돌려주는 줄의 ``pnl``·``pnl_pct``는 **못 재면 None**이다. 시세가 없거나
    살 때 값이 기록에 없으면 지어내지 않는다.
    """
    out = []
    for sym, q in sorted((positions or {}).items()):
        try:
            qty = float(q)
        except (TypeError, ValueError):
            continue
        if abs(qty) <= _EPS:
            continue
        px = prices.get(sym) if prices else None
        entry = (avg_cost or {}).get(sym)
        try:
            px = float(px) if px else None
        except (TypeError, ValueError):
            px = None
        try:
            entry = float(entry) if entry else None
        except (TypeError, ValueError):
            entry = None
        row = {
            "symbol": sym,
            "direction": "short" if qty < 0 else "long",
            "quantity": round(qty, 10),
            "avg_cost": (round(entry, 8) if entry and entry > 0 else None),
            "last_price": (round(px, 8) if px and px > 0 else None),
            "currency": currency,
            # ⚠️ 칸은 **언제나 있고**, 못 잰 것은 None이다. 표는 줄마다
            #    같은 칸을 가져야 하고, "칸이 없다"와 "값을 모른다"를
            #    화면이 구별할 필요도 없어야 한다. 0으로 채우지 않는
            #    것만이 중요하다 — 0은 '본전'이라는 뜻이다.
            "value": None,
            "cost": None,
            "pnl": None,
            "pnl_pct": None,
        }
        if px and px > 0:
            row["value"] = round(qty * px, 4)      # 숏이면 음수 — 부채다
        if px and px > 0 and entry and entry > 0:
            # ⚠️ 숏은 부호가 반대다. 값이 내리면 번다.
            row["cost"] = round(abs(qty) * entry, 4)
            row["pnl"] = round(abs(qty) * (px - entry) *
                               (1.0 if qty > 0 else -1.0), 4)
            row["pnl_pct"] = round(
                (px / entry - 1.0) * 100 * (1.0 if qty > 0 else -1.0), 4)
        out.append(row)
    return out


def totals(rows: list) -> dict:
    """합계 — **잴 수 있는 줄만** 더하고, 몇 줄을 못 쟀는지 함께 말한다.

    못 잰 줄을 0으로 치고 더하면 합계가 조용히 틀린다. 그리고 그 사실을
    아무도 모른다 — 이 저장소가 가장 싫어하는 모양이다.
    """
    pnl = 0.0
    counted = unknown = 0
    for r in (rows or []):
        if r.get("pnl") is None:
            unknown += 1
            continue
        pnl += float(r["pnl"])
        counted += 1
    return {"pnl": round(pnl, 4), "counted": counted, "unknown": unknown}
