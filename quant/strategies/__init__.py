"""전략 계층."""
from __future__ import annotations

from quant.strategies.adx import ADXFilter
from quant.strategies.base import Strategy
from quant.strategies.breakout import Breakout
from quant.strategies.buy_hold import BuyHold
from quant.strategies.cross_rank import CrossRank
from quant.strategies.ensemble import AdaptiveEnsemble, StrategyEnsemble
from quant.strategies.event_guard import EventGuard
from quant.strategies.keltner import KeltnerBreakout
from quant.strategies.liquidity import LiquidityFilter
from quant.strategies.multitimeframe import MultiTimeframeFilter
from quant.strategies.macd import MACD
from quant.strategies.mean_reversion import MeanReversion
from quant.strategies.momentum import Momentum
from quant.strategies.ml import MLStrategy
from quant.strategies.moving_average import MovingAverageCross
from quant.strategies.regime import RegimeFilter
from quant.strategies.rsi import RSIReversion
from quant.strategies.stochastic import Stochastic
from quant.strategies.stop_guard import TrailingStopGuard
from quant.strategies.turtle import TurtleStrategy
from quant.strategies.bollinger import BollingerStrategy
from quant.strategies.psar import ParabolicSAR
from quant.strategies.ichimoku import IchimokuStrategy
from quant.strategies.dualthrust import DualThrustStrategy
from quant.strategies.connors import ConnorsRSI2
from quant.strategies.ibs import IBSStrategy
from quant.strategies.turn_of_month import TurnOfMonth
from quant.strategies.pead import PEADStrategy
from quant.strategies.expiry_week import ExpiryWeek
from quant.strategies.fomc_drift import FOMCDrift
from quant.strategies.supertrend import SuperTrendStrategy
from quant.strategies.supplysom import SupplyDemandSOM
from quant.strategies.valueanchor import ValueAnchor

# 파라미터만으로 생성 가능한 단순 전략 (앙상블/레짐/ADX는 다른 전략을 인자로 받아 별도 취급)
_REGISTRY = {
    "ma_cross": MovingAverageCross,
    "momentum": Momentum,
    "mean_reversion": MeanReversion,
    "rsi": RSIReversion,
    "breakout": Breakout,
    "turtle": TurtleStrategy,
    "bollinger": BollingerStrategy,
    "psar": ParabolicSAR,
    "ichimoku": IchimokuStrategy,
    "dual_thrust": DualThrustStrategy,
    "supply_som": SupplyDemandSOM,
    "supertrend": SuperTrendStrategy,
    "connors_rsi2": ConnorsRSI2,
    "ibs": IBSStrategy,
    "turn_of_month": TurnOfMonth,
    "pead": PEADStrategy,
    "expiry_week": ExpiryWeek,
    "fomc_drift": FOMCDrift,
    "value_anchor": ValueAnchor,
    "macd": MACD,
    "keltner": KeltnerBreakout,
    "stochastic": Stochastic,
    "ml": MLStrategy,
    # 벤치마크를 링에 세운다 — 사이트가 그리는 "그냥 보유"가 후보로
    # 없으면, 시스템은 "들고 있는 게 낫다"를 영원히 발견하지 못한다.
    "buy_hold": BuyHold,
    "cross_rank": CrossRank,
}

__all__ = [
    "Strategy",
    "MovingAverageCross",
    "BuyHold",
    "CrossRank",
    "Momentum",
    "MeanReversion",
    "RSIReversion",
    "Breakout",
    "DualThrustStrategy",
    "SupplyDemandSOM",
    "SuperTrendStrategy",
    "ConnorsRSI2",
    "ValueAnchor",
    "TurtleStrategy",
    "BollingerStrategy",
    "ParabolicSAR",
    "IchimokuStrategy",
    "MACD",
    "KeltnerBreakout",
    "Stochastic",
    "MLStrategy",
    "StrategyEnsemble",
    "AdaptiveEnsemble",
    "RegimeFilter",
    "EventGuard",
    "TrailingStopGuard",
    "ADXFilter",
    "MultiTimeframeFilter",
    "LiquidityFilter",
    "get_strategy",
    "list_strategies",
    "register_strategy",
    "load_user_strategies",
    "default_ensemble",
    "adaptive_ensemble",
]


def register_strategy(name: str, cls: type, *, overwrite: bool = False) -> None:
    """사용자 전략을 이름으로 등록한다(소스 수정 없이). 이후 CLI·웹·validate에서
    그 이름으로 바로 쓸 수 있다.

    name : `--strategy <name>` 및 웹 드롭다운에 나타날 이름
    cls  : Strategy 하위 클래스 (파라미터만으로 생성 가능해야 함 — get_strategy가
           kwargs 없이도 인스턴스화한다)
    overwrite=False 면 기존 이름을 덮어쓰려 할 때 막는다(실수 방지).
    """
    if not (isinstance(cls, type) and issubclass(cls, Strategy)):
        raise TypeError(f"{cls!r} 는 Strategy 하위 클래스가 아닙니다.")
    if name in _REGISTRY and not overwrite:
        raise ValueError(f"이미 등록된 전략 이름: {name!r} (덮어쓰려면 overwrite=True)")
    _REGISTRY[name] = cls


def load_user_strategies(path: str | None = None) -> list[str]:
    """사용자 전략 폴더의 *.py 를 불러와 자동 등록한다. 등록된 이름 목록을 반환.

    폴더 경로: 인자 path → 환경변수 QUANT_STRATEGY_DIR → ./strategies_user.
    각 .py 파일에서:
        · `register_strategy(...)`를 직접 호출하거나,
        · Strategy 하위 클래스를 정의하면 클래스의 `name` 속성(없으면 파일명)으로
          자동 등록한다.
    한 파일이 실패해도 나머지는 계속 불러온다(경고만). 오프라인·격리 실행 안전.
    """
    import importlib.util
    import os
    from pathlib import Path

    from quant.utils.logging import get_logger

    log = get_logger("strategies.user")
    root = Path(path or os.getenv("QUANT_STRATEGY_DIR") or "strategies_user")
    if not root.exists():
        return []
    registered: list[str] = []
    for fp in sorted(root.glob("*.py")):
        if fp.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"user_strat_{fp.stem}", fp)
            mod = importlib.util.module_from_spec(spec)
            before = set(_REGISTRY)
            spec.loader.exec_module(mod)          # register_strategy 직접 호출 지원
            new_names = set(_REGISTRY) - before
            if not new_names:
                # 파일이 직접 등록하지 않았다면, 정의된 Strategy 하위 클래스 자동 등록
                for attr in vars(mod).values():
                    if (isinstance(attr, type) and issubclass(attr, Strategy)
                            and attr.__module__ == mod.__name__):
                        nm = getattr(attr, "name", None) or fp.stem
                        register_strategy(str(nm), attr, overwrite=True)
                        registered.append(str(nm))
                        break
            else:
                registered.extend(sorted(new_names))
        except Exception as exc:  # noqa: BLE001
            log.warning("사용자 전략 로드 실패(%s): %s", fp.name, exc)
    if registered:
        log.info("사용자 전략 %d개 등록: %s", len(registered), ", ".join(registered))
    return registered


def get_strategy(name: str, **kwargs) -> Strategy:
    """이름으로 전략 인스턴스를 생성한다."""
    if name not in _REGISTRY:
        raise ValueError(f"알 수 없는 전략: {name}. 사용 가능: {list(_REGISTRY)}")
    return _REGISTRY[name](**kwargs)


def list_strategies() -> list[str]:
    return list(_REGISTRY)


def _diversified_book(allow_short: bool = False):
    """추세추종 2 + 평균회귀 2로 균형 잡은 전략 묶음 (상관이 낮아 분산 효과가 크다).

    allow_short 를 각 하위 전략에 전달해야 앙상블도 실제로 숏을 낼 수 있다.
    """
    return [
        MovingAverageCross(fast=20, slow=60, allow_short=allow_short),   # 추세추종
        Breakout(window=55, exit_window=20, allow_short=allow_short),    # 추세추종(돌파)
        RSIReversion(period=14, allow_short=allow_short),                # 평균회귀(단기)
        MeanReversion(window=20, z=2.0, allow_short=allow_short),        # 평균회귀(밴드)
    ]


def default_ensemble(allow_short: bool = False,
                     weighting: str = "fixed") -> StrategyEnsemble:
    """추세추종 + 평균회귀를 균형 있게 섞은 기본 앙상블.

    weighting="inverse_vol" 이면 리스크 패리티(역변동성 가중)로 결합해 변동성이
    큰 전략이 포트폴리오 위험을 독점하지 못하게 균형을 맞춘다.
    """
    return StrategyEnsemble(
        strategies=_diversified_book(allow_short),
        allow_short=allow_short,
        weighting=weighting,
    )


def adaptive_ensemble(lookback: int = 60, allow_short: bool = False,
                      score: str = "sharpe", risk_parity: bool = True) -> AdaptiveEnsemble:
    """최근 위험조정 성과에 따라 소프트맥스로 가중치를 조정하는 적응형 앙상블."""
    return AdaptiveEnsemble(
        strategies=_diversified_book(allow_short),
        lookback=lookback,
        allow_short=allow_short,
        score=score,
        risk_parity=risk_parity,
    )
