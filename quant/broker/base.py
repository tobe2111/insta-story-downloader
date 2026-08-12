"""브로커 공통 인터페이스.

페이퍼 트레이딩과 실거래가 동일한 인터페이스를 구현하므로,
실행 코드를 바꾸지 않고 --paper / --live 만 전환할 수 있다.
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass


def safe_amount(value, default: float = 0.0, allow_negative: bool = False) -> float:
    """거래소/API 응답에서 읽은 금액·수량을 안전하게 float로 변환한다.

    inf·nan·(기본적으로) 음수는 거부하고 default를 반환한다. 잘못되거나 악의적인
    잔고·체결·가격 값이 자금 계산(equity=cash+수량*가격 → 주문 수량)을 오염시켜
    'inf 수량 주문'이나 NaN 비교 오류를 일으키는 것을 막는다.
    allow_negative=True 는 숏 포지션 수량처럼 음수가 정상인 경우에만 쓴다.
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(v):
        return default
    if v < 0 and not allow_negative:
        return default
    return v


def normalize_side(side) -> str:
    """주문 방향을 'buy'/'sell'로 정규화한다. 아는 방향이 아니면 거절.

    ⚠️ **모르는 방향의 기본값이 '매도'였다**(감사 182·192). 브로커마다

        signed = quantity if side == "buy" else -quantity
        api_id = TR_BUY   if side == "buy" else TR_SELL

    처럼 적혀 있어서, 정확히 `"buy"`가 아닌 **무엇이든** — `"BUY"`·`"Buy"`·
    `"long"`·오타 — 조용히 매도가 된다. 사는 줄 알고 팔린다.

    감사 182에서 국내 실거래 브로커 둘(kiwoom·KIS)에 검사를 넣었는데,
    **같은 모양이 `paper.py`와 `retry.py`에도 있었다**(감사 192). 파일마다
    복사해 넣으면 다음에 또 한 곳을 빠뜨린다 — 판정을 여기 하나로 모으고
    모두가 이걸 부른다(㉞ '같은 판정을 두 곳에서 쓰면 언젠가 갈라진다').

    `paper.py`는 8마일 챌린지의 **모든 기록이 나오는 브로커**다. 여기서
    방향이 뒤집히면 장부·사이트·방송이 전부 그 위에 쌓인다.

    대소문자와 앞뒤 공백은 받아 준다 — 기본값이 파괴적인 쪽이면 안 될 뿐,
    사람이 흔히 치는 표기까지 막을 이유는 없다.
    """
    s = str(side).strip().lower()
    if s not in ("buy", "sell"):
        raise ValueError(f"알 수 없는 주문 방향: {side!r} (buy/sell만 허용)")
    return s


@dataclass
class Order:
    symbol: str
    side: str        # 'buy' | 'sell'
    quantity: float
    price: float     # 체결가(추정)
    status: str = "filled"
    filled_quantity: float = 0.0  # 실제 체결 수량 (부분체결 추적용)
    order_id: str = ""            # 브로커 주문번호 (체결 조회·감사 추적용)


@dataclass
class Position:
    symbol: str
    quantity: float
    avg_price: float


class Broker(ABC):
    @abstractmethod
    def get_cash(self) -> float:
        ...

    @abstractmethod
    def get_position(self, symbol: str) -> Position:
        ...

    @abstractmethod
    def market_order(self, symbol: str, side: str, quantity: float, price: float) -> Order:
        ...

    def target_weight(
        self, symbol: str, weight: float, price: float, equity: float,
        rebalance_band: float = 0.0, rebalance_band_rel: float = 0.0,
    ) -> Order | None:
        """현재 포지션을 목표 비중(weight)에 맞추도록 주문을 낸다.

        weight: -1.0 ~ 1.0 (자본 대비 목표 노출)
        price:  현재가
        equity: 총 자산 (현금 + 평가액)
        rebalance_band: |목표-현재| 비중 차가 이 값 미만이면 주문을 생략한다
            (자산 대비 절대 기준). 매 봉 미세하게 달라지는 목표(vol 가중·
            proba 사이징)의 잔조정은 기대수익 0에 왕복 수수료만 확정
            지불한다 — 밴드는 그 비용을 결정론적으로 아낀다.
        rebalance_band_rel: 같은 취지의 **상대** 밴드 — 변화액이 목표 포지션
            크기의 이 비율 미만이면 생략한다. 절대 밴드만 쓰면 포지션이
            커질수록 밴드가 상대적으로 촘촘해져 회전율이 폭증한다(총노출을
            20배로 올렸을 때 실제로 겪은 문제). 두 밴드 중 더 큰 문턱이
            적용된다.

        청산(weight=0)은 두 밴드와 무관하게 항상 실행한다 — 빠져나오는 길을
        막으면 리스크 관리가 아니라 덫이 된다. 0(기본)=기존 동작.
        """
        # ⚠️ **여기가 '숫자가 주문이 되는' 마지막 자리다**(감사 167).
        #    `price <= 0`만으로는 NaN을 못 막는다 — `NaN <= 0`은 False다.
        #    그대로 통과하면 아래 계산이 전부 NaN이 되고, 마지막 줄의
        #    `"buy" if delta > 0 else "sell"`에서 `NaN > 0`도 False라
        #    **조용히 '매도'로 떨어진다.** 실측:
        #
        #        price  = NaN  →  ('sell', nan, nan)
        #        equity = NaN  →  ('sell', nan)
        #        weight = NaN  →  ('sell', nan)
        #        equity = inf  →  ('buy',  inf)
        #
        #    이 파일 맨 위의 `safe_amount`가 정확히 이걸 막으라고 있는
        #    함수인데(독스트링에 "inf 수량 주문"이라고 적혀 있다), 정작
        #    주문을 만드는 이 함수는 쓰지 않고 있었다 — 부품은 있는데
        #    배선이 없던 자리다(감사 135와 같은 계열).
        if not all(math.isfinite(v) for v in
                   (float(weight), float(price), float(equity))):
            return None
        if price <= 0:
            return None
        fee = getattr(self, "fee", 0.0) or 0.0
        target_qty = (weight * equity) / price
        current = self.get_position(symbol).quantity
        delta = target_qty - current
        if weight != 0.0 and equity > 0:
            moved = abs(delta * price)
            thresh = rebalance_band * equity if rebalance_band > 0.0 else 0.0
            if rebalance_band_rel > 0.0:
                thresh = max(thresh, rebalance_band_rel * abs(weight * equity))
            if thresh > 0.0 and moved < thresh:
                return None  # 밴드 미만 잔조정 — 비용만 내는 거래 생략
        # 수수료 버퍼는 '롱 노출을 늘리는 매수'에만 적용한다: 풀 비중(weight≈1)에서
        # 비용+수수료가 현금을 초과해 '음수 현금'이 되는 것을 막는다. 숏(weight<0)이나
        # 포지션 축소(delta<0)에까지 (1+fee)로 나누면 목표만 왜곡돼(숏 과소진입·축소
        # 과다) 현금 문제도 없는데 사이징이 틀어진다. fee 속성이 있는 브로커(페이퍼)에만
        # 반영되고, 실거래 브로커는 fee=0으로 무영향(거래소가 잔고를 검증한다).
        if fee > 0 and weight > 0 and delta > 0:
            target_qty = (weight * equity) / (price * (1.0 + fee))
            delta = target_qty - current
        if abs(delta * price) < 1e-6:
            return None  # 조정 불필요
        # 입력이 유한해도 나눗셈이 넘칠 수 있다(equity 1e308 / price 1e-308).
        # 수량은 마지막에 한 번 더 본다.
        qty = abs(delta)
        if not math.isfinite(qty) or qty <= 0:
            return None
        side = "buy" if delta > 0 else "sell"
        return self.market_order(symbol, side, qty, price)
