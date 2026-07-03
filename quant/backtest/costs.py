"""거래 비용 모델 — 백테스트를 실전에 가깝게.

고정 수수료+슬리피지만 반영하면 백테스트가 실전보다 낙관적이다. 현실에는:
    - 변동성 비례 슬리피지: 요동칠수록 체결이 불리해진다
    - 공매도 차입 비용: 숏 포지션 보유에 드는 비용
    - 펀딩비: 무기한 선물(perp) 보유에 주기적으로 드는 비용
이들을 반영하면 '백테스트에서만 좋은' 고회전·고레버리지 전략의 환상이 걷힌다.

기본값은 모두 0(또는 기존 수수료·슬리피지)이라, 지정하지 않으면 기존과 동일하게 동작한다.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CostModel:
    fee: float = 0.001          # 편도 수수료 (회전율 대비)
    slippage: float = 0.0005    # 기본 슬리피지 (회전율 대비)
    impact_coef: float = 0.0    # 변동성 비례 슬리피지 계수 (× 최근 변동성)
    short_borrow: float = 0.0   # 숏 보유 비용 (봉당, |비중| 대비)
    funding: float = 0.0        # 펀딩비 (봉당, |비중| 대비)

    def turnover_cost(self, turnover: float, vol: float = 0.0) -> float:
        """회전율(포지션 변경량)에 따른 거래 비용 비율."""
        return (self.fee + self.slippage + self.impact_coef * vol) * turnover

    def holding_cost(self, position: float, vol: float = 0.0) -> float:
        """봉당 포지션 보유 비용 비율 (펀딩 + 숏 차입)."""
        cost = self.funding * abs(position)
        if position < 0:
            cost += self.short_borrow * abs(position)
        return cost
