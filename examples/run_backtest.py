"""전략 백테스트 실행 예제.

사용법:
    python examples/run_backtest.py                                  # 합성 데이터
    python examples/run_backtest.py --market crypto --symbol BTC/USDT
    python examples/run_backtest.py --market us_stock --symbol AAPL --strategy momentum
    python examples/run_backtest.py --market kr_stock --symbol 005930.KS
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.backtest import Backtester
from quant.data import get_provider
from quant.risk import RiskConfig, RiskManager
from quant.strategies import get_strategy, list_strategies


def main() -> None:
    p = argparse.ArgumentParser(description="퀀트 전략 백테스트")
    p.add_argument("--market", default="synthetic",
                   help="synthetic | crypto | us_stock | kr_stock")
    p.add_argument("--symbol", default="DEMO")
    p.add_argument("--timeframe", default="1d")
    p.add_argument("--limit", type=int, default=500)
    p.add_argument("--strategy", default="ma_cross",
                   help=f"{list_strategies()}")
    p.add_argument("--capital", type=float, default=10_000.0)
    p.add_argument("--fee", type=float, default=0.001)
    args = p.parse_args()

    # 시장별 연율화 계수 (주식 거래일 ≈ 252, 코인 ≈ 365)
    ppy = 365 if args.market in ("crypto", "synthetic") else 252

    provider = get_provider(args.market)
    df = provider.get_ohlcv(args.symbol, args.timeframe, limit=args.limit)
    print(f"데이터: {len(df)}개 봉  ({df.index[0]} ~ {df.index[-1]})")

    strategy = get_strategy(args.strategy)
    risk = RiskManager(RiskConfig(periods_per_year=ppy, stop_loss=0.15))
    bt = Backtester(
        strategy, risk, initial_capital=args.capital,
        fee=args.fee, periods_per_year=ppy,
    )
    result = bt.run(df)

    print("\n=== 백테스트 결과 ===")
    print(f"전략: {strategy.name} | 시장: {args.market} | 종목: {args.symbol}")
    print("-" * 32)
    print(result.summary())
    print("-" * 32)
    print("⚠️ 과거 성과는 미래 수익을 보장하지 않습니다.")


if __name__ == "__main__":
    main()
