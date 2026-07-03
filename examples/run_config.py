"""설정파일(config.yaml) 기반 통합 실행기.

하나의 명령으로: 데이터 로드 → 백테스트 → HTML 리포트 → 몬테카를로 신뢰구간.

사용법:
    cp config/config.example.yaml config/config.yaml   # 값 수정
    python examples/run_config.py --config config/config.yaml
    python examples/run_config.py                        # 기본값(합성)으로 데모
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.backtest import Backtester
from quant.data import get_provider
from quant.reporting import generate_report
from quant.risk import RiskConfig, RiskManager
from quant.robustness import bootstrap_metrics, summarize
from quant.strategies import default_ensemble, get_strategy

DEFAULTS = {
    "market": "synthetic",
    "symbol": "DEMO",
    "timeframe": "1d",
    "strategy": {"name": "ensemble", "params": {}},
    "risk": {"sizing": "vol_target", "target_vol": 0.20, "stop_loss": 0.15,
             "max_position": 1.0},
    "backtest": {"initial_capital": 10_000, "fee": 0.001, "slippage": 0.0005},
}


def _load_config(path: str | None) -> dict:
    if not path:
        return DEFAULTS
    import yaml

    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    merged = {**DEFAULTS, **cfg}
    return merged


def _build_strategy(spec: dict):
    if isinstance(spec, str):
        spec = {"name": spec, "params": {}}
    name = spec.get("name", "ensemble")
    params = spec.get("params", {}) or {}
    if name == "ensemble":
        return default_ensemble()
    return get_strategy(name, **params)


def main() -> None:
    p = argparse.ArgumentParser(description="설정파일 기반 통합 백테스트")
    p.add_argument("--config", default=None)
    p.add_argument("--limit", type=int, default=800)
    p.add_argument("--report", default="results/report.html")
    args = p.parse_args()

    cfg = _load_config(args.config)
    ppy = 365 if cfg["market"] in ("crypto", "synthetic") else 252

    df = get_provider(cfg["market"]).get_ohlcv(
        cfg["symbol"], cfg["timeframe"], limit=args.limit
    )
    strategy = _build_strategy(cfg["strategy"])

    rc = cfg["risk"]
    risk = RiskManager(RiskConfig(
        sizing=rc.get("sizing", "vol_target"),
        target_vol=rc.get("target_vol", 0.20),
        stop_loss=rc.get("stop_loss", 0.15),
        take_profit=rc.get("take_profit"),
        trailing_stop=rc.get("trailing_stop"),
        max_position=rc.get("max_position", 1.0),
        periods_per_year=ppy,
    ))
    bc = cfg["backtest"]
    result = Backtester(
        strategy, risk,
        initial_capital=bc.get("initial_capital", 10_000),
        fee=bc.get("fee", 0.001), slippage=bc.get("slippage", 0.0005),
        periods_per_year=ppy,
    ).run(df)

    print(f"\n=== 백테스트: {getattr(strategy, 'name', '?')} / {cfg['symbol']} ===")
    print(result.summary())

    # 몬테카를로 신뢰구간
    print("\n=== 몬테카를로 신뢰구간 (1000회 부트스트랩) ===")
    dist = bootstrap_metrics(result.returns, n_sims=1000, periods_per_year=ppy)
    print(summarize(dist))

    # HTML 리포트
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    out = generate_report(result, args.report,
                          title=f"{getattr(strategy, 'name', '전략')} · {cfg['symbol']}")
    print(f"\n📄 리포트 저장: {out}")
    print("⚠️ 신뢰구간 하단(5%)이 0 근처면 운일 가능성이 큽니다.")


if __name__ == "__main__":
    main()
