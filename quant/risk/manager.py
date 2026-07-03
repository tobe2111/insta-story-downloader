"""리스크 관리 — 이 프레임워크에서 가장 중요한 부분.

전략이 "얼마나 확신하는가(목표 비중)"를 말하면, 리스크 관리자가
"실제로 얼마를 걸 것인가"를 결정한다. 좋은 전략보다 좋은 리스크 관리가
장기 생존을 좌우한다.

제공 기능:
    - 포지션 사이징: 고정 비율 / 변동성 타겟팅
    - 손절(stop-loss) / 익절(take-profit)
    - 종목당 최대 노출 한도
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class RiskConfig:
    # 종목당 최대 노출 (자본 대비 비율). 1.0 = 100%
    max_position: float = 1.0
    # 손절선: 진입가 대비 -x. 예) 0.1 = -10%에서 청산. None이면 미사용
    stop_loss: float | None = 0.15
    # 익절선: 진입가 대비 +x. None이면 미사용
    take_profit: float | None = None
    # 트레일링 스톱: 유리한 방향 고점 대비 x만큼 되돌리면 청산 (이익 보호). None이면 미사용
    trailing_stop: float | None = None
    # 사이징 방식: 'fixed' | 'vol_target'
    sizing: str = "vol_target"
    # 변동성 타겟팅 시 목표 연율 변동성 (예: 0.2 = 20%)
    target_vol: float = 0.20
    # 변동성 추정 윈도우
    vol_window: int = 30
    # 연율화 계수 (일봉=365 for crypto, 252 for stock 권장)
    periods_per_year: int = 365


class RiskManager:
    """전략 신호(목표 비중)를 실제 포지션 비중으로 변환한다."""

    def __init__(self, config: RiskConfig | None = None):
        self.config = config or RiskConfig()

    def size_positions(self, df: pd.DataFrame, target: pd.Series) -> pd.Series:
        """목표 비중을 리스크 조정된 실제 비중으로 스케일링한다.

        손절/익절은 경로 의존적이라 백테스트 엔진에서 별도로 처리한다.
        여기서는 사이징(스케일)과 최대 노출 한도만 적용한다.
        """
        cfg = self.config
        if cfg.sizing == "fixed":
            scale = pd.Series(1.0, index=df.index)
        elif cfg.sizing == "vol_target":
            returns = df["close"].pct_change()
            realized = returns.rolling(cfg.vol_window).std() * np.sqrt(
                cfg.periods_per_year
            )
            # 목표변동성 / 실현변동성 = 레버리지 배수 (과도한 값은 캡)
            scale = (cfg.target_vol / realized).clip(upper=3.0).fillna(0.0)
        else:
            raise ValueError(f"알 수 없는 sizing: {cfg.sizing}")

        sized = (target * scale).clip(-cfg.max_position, cfg.max_position)
        return sized.fillna(0.0).rename("position")

    def apply_stops(
        self, position: float, entry_price: float, current_price: float
    ) -> float:
        """단일 시점에서 손절/익절 여부를 판단해 조정된 포지션을 반환한다.

        롱 포지션 기준. position이 0이거나 진입가가 없으면 그대로 반환.
        """
        cfg = self.config
        if position == 0 or entry_price <= 0:
            return position
        pnl = (current_price - entry_price) / entry_price * np.sign(position)
        if cfg.stop_loss is not None and pnl <= -cfg.stop_loss:
            return 0.0  # 손절 청산
        if cfg.take_profit is not None and pnl >= cfg.take_profit:
            return 0.0  # 익절 청산
        return position

    def apply_trailing_stop(
        self, position: float, extreme_price: float, current_price: float
    ) -> float:
        """유리한 방향의 극값(extreme) 대비 되돌림을 확인해 청산 여부를 결정한다.

        롱: 보유 중 최고가(extreme) 대비 trailing_stop 만큼 하락하면 청산.
        숏: 보유 중 최저가(extreme) 대비 trailing_stop 만큼 상승하면 청산.
        이익을 낸 뒤 되돌림으로 이익을 반납하는 것을 막아준다.
        """
        cfg = self.config
        if position == 0 or cfg.trailing_stop is None or extreme_price <= 0:
            return position
        if position > 0:
            giveback = (current_price - extreme_price) / extreme_price
            if giveback <= -cfg.trailing_stop:
                return 0.0
        else:
            giveback = (current_price - extreme_price) / extreme_price
            if giveback >= cfg.trailing_stop:
                return 0.0
        return position
