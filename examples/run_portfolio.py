"""다중 종목 포트폴리오 백테스트 예제.

사용법:
    python examples/run_portfolio.py
    python examples/run_portfolio.py --market crypto --symbols BTC/USDT ETH/USDT SOL/USDT
    python examples/run_portfolio.py --market us_stock --symbols AAPL MSFT GOOGL NVDA --allocation equal
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.data import get_provider
from quant.portfolio import PortfolioBacktester, list_schemes
from quant.strategies import get_strategy


def main() -> None:
    p = argparse.ArgumentParser(description="포트폴리오 백테스트")
    p.add_argument("--market", default="synthetic")
    p.add_argument("--symbols", nargs="+", default=["A", "B", "C", "D"])
    p.add_argument("--timeframe", default="1d")
    p.add_argument("--limit", type=int, default=500)
    p.add_argument("--strategy", default="momentum")
    p.add_argument("--allocation", default="inverse_vol", help=str(list_schemes()))
    p.add_argument("--capital", type=float, default=10_000.0)
    args = p.parse_args()

    ppy = 365 if args.market in ("crypto", "synthetic") else 252
    provider = get_provider(args.market)
    data = {
        s: provider.get_ohlcv(s, args.timeframe, limit=args.limit) for s in args.symbols
    }

    bt = PortfolioBacktester(
        strategy=get_strategy(args.strategy),
        allocation=args.allocation,
        initial_capital=args.capital,
        periods_per_year=ppy,
    )
    result = bt.run(data)

    print(f"\n=== 포트폴리오 백테스트 ({len(args.symbols)}종목) ===")
    print(f"종목: {', '.join(args.symbols)}")
    print(f"전략: {args.strategy} | 배분: {args.allocation}")
    print("-" * 32)
    print(result.summary())
    print("-" * 32)
    print("⚠️ 과거 성과는 미래 수익을 보장하지 않습니다.")


if __name__ == "__main__":
    main()
