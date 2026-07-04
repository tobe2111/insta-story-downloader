"""챔피언-챌린저 — 새 전략을 바로 투입하지 않고 '가상 대결'로 검증한다.

새로 만든/학습한 전략(챌린저)이 백테스트에서 좋아 보여도 실전에 바로 넣는 건
위험하다. 현재 쓰는 전략(챔피언)과 챌린저를 같은 데이터에 나란히 돌려 성과를
비교하고, 챌린저가 '통계적으로 유의하게' 앞설 때만 교체(swap)를 권고한다.

⚠️ 정직한 한계: 여기서 쓰는 유의성 검정은 봉별 수익 차이의 단순 t-통계다.
같은 구간을 비교하므로 '미래 성과 보장'이 아니라 '섣부른 교체 방지' 가드레일일
뿐이다. 진짜 검증은 워크포워드 OOS로 해야 한다. 그래도 '좋아 보인다고 바로
바꾸는' 실수를 줄여준다.
"""
from __future__ import annotations

import math

import pandas as pd

from quant.strategies.base import Strategy
from quant.utils.logging import get_logger, log_event

log = get_logger("champion_challenger")


class ChampionChallenger:
    def __init__(self, champion: Strategy, challenger: Strategy,
                 min_obs: int = 60, edge: float = 0.0, t_threshold: float = 2.0):
        """champion을 challenger로 교체할지 판단한다.

        min_obs     : 판단에 필요한 최소 봉 수(표본이 적으면 교체 보류)
        edge        : 챌린저 평균 초과수익이 이 값보다 커야 함(거래비용 여유 등)
        t_threshold : t-통계 임계(≈2.0 → 약 95% 신뢰). 넘어야 교체 권고.
        """
        self.champion = champion
        self.challenger = challenger
        self.min_obs = min_obs
        self.edge = edge
        self.t_threshold = t_threshold

    def evaluate(self, df: pd.DataFrame) -> dict:
        """두 전략을 같은 데이터에 백테스트해 성과를 비교한다."""
        from quant.backtest import Backtester

        rc = Backtester(self.champion).run(df).returns
        rh = Backtester(self.challenger).run(df).returns
        diff = (rh - rc).dropna()
        n = int(len(diff))
        mean = float(diff.mean()) if n else 0.0
        std = float(diff.std(ddof=1)) if n > 1 else 0.0
        t_stat = mean / (std / math.sqrt(n)) if (std > 0 and n > 1) else 0.0

        swap = bool(n >= self.min_obs and mean > self.edge and t_stat > self.t_threshold)
        result = {
            "n": n,
            "champion_return": float((1 + rc).prod() - 1),
            "challenger_return": float((1 + rh).prod() - 1),
            "mean_diff": mean,
            "t_stat": t_stat,
            "swap": swap,
        }
        log_event(log, "champion_challenger_eval", level="info",
                  strategy_champion=getattr(self.champion, "name", "?"),
                  strategy_challenger=getattr(self.challenger, "name", "?"),
                  **result)
        return result

    def active(self, df: pd.DataFrame) -> Strategy:
        """평가 결과에 따라 실제로 쓸 전략(챔피언 또는 챌린저)을 반환한다."""
        return self.challenger if self.evaluate(df)["swap"] else self.champion
