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

import numpy as np
import pandas as pd

from quant.strategies.base import Strategy
from quant.utils.logging import get_logger, log_event

log = get_logger("champion_challenger")


class ChampionChallenger:
    def __init__(self, champion: Strategy, challenger: Strategy,
                 min_obs: int = 60, edge: float = 0.0, t_threshold: float = 2.0,
                 cost_model=None, next_open_fill: bool = False,
                 rebalance_band: float = 0.0):
        """champion을 challenger로 교체할지 판단한다.

        min_obs     : 판단에 필요한 최소 봉 수(표본이 적으면 교체 보류)
        edge        : 챌린저 평균 초과수익이 이 값보다 커야 함(거래비용 여유 등)
        t_threshold : t-통계 임계(≈2.0 → 약 95% 신뢰). 넘어야 교체 권고.
        cost_model  : 시장별 거래비용 프리셋(CostModel). 없으면 백테스터 기본
                      비용(편도 0.1%+슬리피지 0.05%)이 적용된다 — 비용 없는
                      대결은 회전율 높은 전략에 유리하게 왜곡되므로 금지.
        next_open_fill / rebalance_band :
            '챔피언을 뽑는 세계'를 '돈이 도는 세계'와 맞추는 두 손잡이.
            실제 운용은 다음 세션 시가에 체결하고(개장 갭 실측 79bp) 리밸런스
            밴드로 잔조정을 거른다. 오디션이 종가 체결·밴드 0으로 평가하면
            고회전 전략이 부당하게 유리해져, 실제로는 낼 수 없는 성과를 근거로
            챔피언이 선발된다(2026-08-11 발견). 호출자가 시장에 맞는 값을 넣는다.
        """
        self.champion = champion
        self.challenger = challenger
        self.min_obs = min_obs
        self.edge = edge
        self.t_threshold = t_threshold
        self.cost_model = cost_model
        self.next_open_fill = bool(next_open_fill)
        self.rebalance_band = max(0.0, float(rebalance_band))

    def evaluate(self, df: pd.DataFrame, tail: int | None = None,
                 folds: int = 0) -> dict:
        """두 전략을 같은 데이터에 백테스트해 성과를 비교한다.

        tail이 주어지면 백테스트는 전체 구간으로 하되(워크포워드 워밍업 확보)
        '마지막 tail봉'의 수익만 비교한다 — 재학습 파이프라인의 확인(홀드아웃)
        단계처럼 최근 구간만으로 공정하게 판정할 때 쓴다.

        folds ≥ 2면 수익 차이 시계열을 연속 구간 folds개로 나눠 각 구간의
        평균 차이가 양수인 구간 수(fold_wins)를 함께 반환한다 — 전체 t-통계
        하나는 한 구간의 대박이 만든 착시일 수 있어, '기간 전반에 걸쳐
        이겼는가'를 따로 본다(CPCV의 경량판). 판정(swap)은 바꾸지 않고
        정보만 제공한다 — 게이트 적용은 호출자(재학습 선발전)의 몫.
        """
        from quant.backtest import Backtester

        bt = dict(cost_model=self.cost_model,
                  next_open_fill=self.next_open_fill,
                  rebalance_band=self.rebalance_band)
        res_c = Backtester(self.champion, **bt).run(df)
        res_h = Backtester(self.challenger, **bt).run(df)
        rc, rh = res_c.returns, res_h.returns
        if tail is not None and tail > 0:
            rc, rh = rc.iloc[-tail:], rh.iloc[-tail:]
        # 두 전략 모두 관망(무포지션)인 봉은 수익 차이가 0이라 정보가 없다.
        # 워밍업·무거래 구간의 0들을 t-검정에 넣으면 표본만 부풀려 t-통계를
        # 인위적으로 0쪽으로 눌러 판단을 왜곡한다. 적어도 한쪽이 '직전 봉에
        # 포지션을 보유'해 이번 봉 수익을 실현한 구간만 비교한다(1봉 지연 규약).
        active = (
            (res_c.positions.shift(1).fillna(0.0) != 0)
            | (res_h.positions.shift(1).fillna(0.0) != 0)
        )
        # 챌린저가 챔피언과 **한 봉도 다르지 않은 포지션**을 내는 경우 —
        # 후보가 아니라 사본이다. 설정만 다르고 실제로는 아무 일도 하지 않는
        # 장치(예: 재료가 없어 조용히 꺼진 옵션)가 여기로 들어온다.
        # t=0.00으로 어차피 탈락하지만, 그냥 두면 세 가지 해를 끼친다:
        #   ① 매일 백테스트 두 번을 헛돌린다
        #   ② 장부의 후보 수를 부풀려 **다중검정 문턱을 올린다** — 아무것도
        #      안 하는 후보가 진짜 후보의 승격을 방해한다
        #   ③ 오디션 링에 '그 기능을 시험 중'이라는 인상만 남긴다
        # 그래서 판정에 쓰지 않고 **사실로 보고한다**(감사 127의 교훈 —
        # 죽은 장치를 조용히 두지 않는다).
        pos_c, pos_h = res_c.positions, res_h.positions
        if tail is not None and tail > 0:
            pos_c, pos_h = pos_c.iloc[-tail:], pos_h.iloc[-tail:]
        identical = bool(
            len(pos_c) == len(pos_h) and len(pos_c) > 0
            and np.allclose(pos_c.fillna(0.0).to_numpy(dtype=float),
                            pos_h.fillna(0.0).to_numpy(dtype=float),
                            rtol=0.0, atol=1e-12))
        diff = (rh - rc)[active].dropna()
        n = int(len(diff))
        mean = float(diff.mean()) if n else 0.0
        std = float(diff.std(ddof=1)) if n > 1 else 0.0
        # ⚠️ `std > 0`은 부동소수에서 믿을 수 없는 판정이다(감사 146·149·159).
        #    여기서는 **도달 경로를 만들지 못했다** — 차이가 상수가 되려면
        #    두 전략이 보유한 봉에서 수익이 상수여야 하는데, 그런 계열은
        #    사이저가 비중을 0으로 만들어 active 표본이 비어 버린다(n=0).
        #    그래도 이 t 통계량이 **챔피언 승격을 결정하는 자리**라, 같은
        #    병이 다른 경로로 들어올 여지를 남기지 않는다. 재현 못 한 결함에
        #    대한 예방이지 고친 결함이 아니라는 점을 분명히 적어 둔다.
        from quant.utils.numerics import degenerate_spread
        degenerate = degenerate_spread(std, float(diff.abs().mean()) if n else 0.0)
        t_stat = (0.0 if (degenerate or n <= 1)
                  else mean / (std / math.sqrt(n)))

        swap = bool(n >= self.min_obs and mean > self.edge and t_stat > self.t_threshold)
        result = {
            "n": n,
            "champion_return": float((1 + rc).prod() - 1),
            "challenger_return": float((1 + rh).prod() - 1),
            "mean_diff": mean,
            "t_stat": t_stat,
            "swap": swap,
            "identical": identical,
        }
        if folds >= 2 and n >= folds:
            # 연속 등분 — 각 폴드에서 평균 차이 > 0이면 그 폴드 승리
            chunks = [diff.iloc[len(diff) * k // folds:
                                len(diff) * (k + 1) // folds] for k in range(folds)]
            result["n_folds"] = folds
            result["fold_wins"] = int(sum(
                1 for c in chunks if len(c) and float(c.mean()) > 0))
        log_event(log, "champion_challenger_eval", level="info",
                  strategy_champion=getattr(self.champion, "name", "?"),
                  strategy_challenger=getattr(self.challenger, "name", "?"),
                  **result)
        return result

    def active(self, df: pd.DataFrame) -> Strategy:
        """평가 결과에 따라 실제로 쓸 전략(챔피언 또는 챌린저)을 반환한다."""
        return self.challenger if self.evaluate(df)["swap"] else self.champion
