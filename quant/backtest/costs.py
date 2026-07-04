"""거래 비용 모델 — 백테스트를 실전에 가깝게.

고정 수수료+슬리피지만 반영하면 백테스트가 실전보다 낙관적이다. 현실에는:
    - 변동성 비례 슬리피지: 요동칠수록 체결이 불리해진다
    - 시장충격(market impact): 주문이 그 봉 거래대금에서 차지하는 비중이
      클수록 체결가가 불리해진다 (제곱근 법칙 근사)
    - 공매도 차입 비용: 숏 포지션 보유에 드는 비용
    - 펀딩비: 무기한 선물(perp) 보유에 주기적으로 드는 비용
이들을 반영하면 '백테스트에서만 좋은' 고회전·고레버리지 전략의 환상이 걷힌다.

기본값은 모두 0(또는 기존 수수료·슬리피지)이라, 지정하지 않으면 기존과 동일하게 동작한다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CostModel:
    fee: float = 0.001          # 편도 수수료 (회전율 대비)
    slippage: float = 0.0005    # 기본 슬리피지 (회전율 대비)
    impact_coef: float = 0.0    # 변동성 비례 슬리피지 계수 (× 최근 변동성)
    short_borrow: float = 0.0   # 숏 보유 비용 (봉당, |비중| 대비)
    funding: float = 0.0        # 펀딩비 (봉당, |비중| 대비, 롱·숏 모두 부과하는 보수적 고정치)
    # 시장충격(제곱근 법칙): 체결비용률 = market_impact_coef × √participation.
    # participation = (주문 명목금액 / 그 봉 거래대금). 기본 0 = 미사용(기존과 동일).
    # ⚠️ 근사 모델이며 실제 호가창 깊이·유동성 공백을 대체하지 못한다.
    #    소형주·저유동 코인에서 실제 충격은 이보다 훨씬 클 수 있다.
    market_impact_coef: float = 0.0
    participation_cap: float = 1.0   # participation 상한(거래대금보다 큰 주문의 폭주 방지)
    # 봉 타임스탬프→펀딩률 실데이터 시리즈(pd.Series). 지정 시 고정 funding 대신
    # 그 봉 타임스탬프에 '정확히 일치'하는 정산액만 부과한다(룩어헤드 없음).
    # 봉 인덱스와 맞추려면 quant.data.funding.align_funding_to_bars 를 쓸 것.
    # 부호 규약: 양수=롱이 지불(숏은 수취). None(기본)=기존 고정 funding 사용.
    funding_series: Any = field(default=None, repr=False)

    def turnover_cost(self, turnover: float, vol: float = 0.0) -> float:
        """회전율(포지션 변경량)에 따른 거래 비용 비율."""
        return (self.fee + self.slippage + self.impact_coef * vol) * turnover

    def market_impact_cost(
        self, turnover: float, equity: float, dollar_volume: float | None
    ) -> float:
        """제곱근 법칙 시장충격 비용 비율 (자본 대비).

        participation = (turnover × equity) / 봉 거래대금.
        자본 대비 비용 = market_impact_coef × √participation × turnover.
        거래대금 정보가 없으면 0을 반환한다(과소추정임을 인지할 것).
        """
        if self.market_impact_coef <= 0.0 or turnover <= 0.0 or equity <= 0.0:
            return 0.0
        if dollar_volume is None or not (dollar_volume > 0.0) \
                or not math.isfinite(dollar_volume):
            return 0.0
        participation = min((turnover * equity) / dollar_volume,
                            self.participation_cap)
        return self.market_impact_coef * math.sqrt(participation) * turnover

    # 봉당 펀딩률 절대값 상한. 실제 펀딩은 극단 시장에서도 8시간당 ±0.75% 수준이라
    # 이 값을 넘는 데이터는 오염(단위 오류·API 이상)으로 보고 잘라낸다. 클램프가
    # 없으면 |rate|>=1 인 오염 값 하나가 cash_equity *= 1-hold 에서 자본 부호를
    # 뒤집어 백테스트 전체를 조용히 망가뜨린다.
    _FUNDING_RATE_CAP = 0.05

    def _funding_rate_at(self, ts) -> float:
        """funding_series에서 ts 시점의 펀딩률을 읽는다(없거나 비유한이면 0)."""
        try:
            v = float(self.funding_series.get(ts, 0.0))
        except (TypeError, ValueError, AttributeError):
            return 0.0
        if not math.isfinite(v):
            return 0.0
        return max(-self._FUNDING_RATE_CAP, min(self._FUNDING_RATE_CAP, v))

    def holding_cost(self, position: float, vol: float = 0.0, ts=None) -> float:
        """봉당 포지션 보유 비용 비율 (펀딩 + 숏 차입). 음수 = 수취(펀딩 크레딧).

        funding_series 지정 시 실데이터 부호를 따른다(양수 rate → 롱 지불·숏 수취).
        미지정 시 기존처럼 |비중|에 고정 funding을 보수적으로 부과한다.
        """
        if self.funding_series is not None and ts is not None:
            cost = self._funding_rate_at(ts) * position
        else:
            cost = self.funding * abs(position)
        if position < 0:
            cost += self.short_borrow * abs(position)
        return cost
