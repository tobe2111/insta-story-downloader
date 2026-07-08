"""손익분기 비용 분석 — '수수료를 못 이기는' 전략을 폭로한다.

백테스트가 0.1%짜리 엣지를 보여줘도, 그 엣지를 얻으려 매 봉 회전한다면
편도 수수료 0.1%짜리 거래소에서는 남는 게 없다. 고회전 전략의 흔한 환상이다:
비용을 0으로 두면 근사해 보이지만, 현실 비용을 넣는 순간 마이너스가 된다.

이 모듈은 두 가지를 계산한다:
    1) cost_sweep      — 수수료 수준별로 총수익·샤프·거래횟수가 어떻게 무너지는지
    2) break_even_cost — 총수익이 0으로 꺼지는 '손익분기 수수료'가 얼마인지

손익분기 수수료가 실제 거래 비용보다 낮으면, 그 전략은 실전에서 비용을 못 이긴다.
이 도구는 엣지를 만들어 주지 않는다 — 엣지가 비용 앞에서 얼마나 얇은지 드러낼 뿐이다.
수익을 보장하지 않는다.
"""
from __future__ import annotations

from typing import Callable

import pandas as pd

from quant.backtest.costs import MARKET_COST_PRESETS
from quant.backtest.engine import Backtester
from quant.strategies.base import Strategy


def _run_at_fee(
    df: pd.DataFrame,
    strategy_factory: Callable[[], Strategy],
    fee: float,
    slippage_ratio: float,
    periods_per_year: int,
):
    """지정 수수료로 백테스트 1회 실행. 전략은 상태를 가지므로 매번 새로 만든다."""
    strat = strategy_factory()
    slippage = fee * slippage_ratio
    return Backtester(
        strat, fee=fee, slippage=slippage, periods_per_year=periods_per_year
    ).run(df)


def cost_sweep(
    df: pd.DataFrame,
    strategy_factory: Callable[[], Strategy],
    fees,
    periods_per_year: int = 365,
    slippage_ratio: float = 0.5,
) -> list[dict]:
    """수수료 수준별로 백테스트를 돌려 성과가 어떻게 무너지는지 표를 만든다.

    각 수수료마다 슬리피지 = 수수료 × slippage_ratio로 함께 올린다(실전에서
    수수료가 높은 시장·자산은 대개 스프레드/슬리피지도 크기 때문).

    반환: [{'fee', 'total_return', 'sharpe', 'num_trades'}, ...] (fees 순서대로)
    """
    rows: list[dict] = []
    for fee in fees:
        res = _run_at_fee(df, strategy_factory, float(fee), slippage_ratio,
                          periods_per_year)
        rows.append({
            "fee": float(fee),
            "total_return": float(res.metrics.total_return),
            "sharpe": float(res.metrics.sharpe),
            "num_trades": int(res.metrics.num_trades),
        })
    return rows


def _turnover_per_bar(result) -> float:
    """봉당 평균 회전율(|포지션 변화|의 평균). 고회전일수록 비용에 취약하다."""
    pos = result.positions
    if len(pos) == 0:
        return 0.0
    changes = pos.diff().fillna(pos).abs()
    return float(changes.sum() / len(pos))


def break_even_cost(
    df: pd.DataFrame,
    strategy_factory: Callable[[], Strategy],
    periods_per_year: int = 365,
    hi: float = 0.02,
    tol: float = 1e-4,
    slippage_ratio: float = 0.5,
) -> dict:
    """총수익이 0으로 꺼지는 '편도 손익분기 수수료'를 이분탐색한다.

    수수료가 오르면 회전 비용이 커져 총수익은 단조 감소한다(거래하는 전략 기준).
    이 성질을 이용해 total_return이 0을 통과하는 수수료를 좁혀 나간다.

    반환: {
        'break_even_fee'       : 손익분기 편도 수수료,
        'base_return_at_zero_fee': 수수료 0에서의 총수익률,
        'turnover_per_bar'     : 봉당 평균 회전율,
        'unprofitable_at_zero' : 수수료 0에서도 손실이면 True(엣지 자체가 없음),
        'capped'               : hi에서도 여전히 이익이면 True(hi로 상한 처리),
    }
    특이 케이스:
        · 수수료 0에서도 손실 → break_even_fee=0.0, unprofitable_at_zero=True
        · hi에서도 이익      → break_even_fee=hi, capped=True (상한에서 잘림)
    """
    base = _run_at_fee(df, strategy_factory, 0.0, slippage_ratio, periods_per_year)
    base_ret = float(base.metrics.total_return)
    turnover = _turnover_per_bar(base)

    result = {
        "break_even_fee": 0.0,
        "base_return_at_zero_fee": base_ret,
        "turnover_per_bar": turnover,
        "unprofitable_at_zero": False,
        "capped": False,
    }

    # 수수료 0에서도 못 벌면 손익분기랄 게 없다 — 엣지 자체가 없는 전략.
    if base_ret <= 0.0:
        result["unprofitable_at_zero"] = True
        return result

    def ret_at(fee: float) -> float:
        return float(_run_at_fee(
            df, strategy_factory, fee, slippage_ratio, periods_per_year
        ).metrics.total_return)

    # hi에서도 여전히 이익이면 손익분기가 hi 밖 → 상한으로 잘라 보고한다.
    if ret_at(hi) > 0.0:
        result["break_even_fee"] = hi
        result["capped"] = True
        return result

    # lo(이익) ~ hi(손실) 사이에서 total_return=0 지점을 이분탐색
    lo, hi_b = 0.0, hi
    while hi_b - lo > tol:
        mid = 0.5 * (lo + hi_b)
        if ret_at(mid) > 0.0:
            lo = mid
        else:
            hi_b = mid
    result["break_even_fee"] = 0.5 * (lo + hi_b)
    return result


def cost_sensitivity_report(sweep: list[dict], break_even: dict) -> str:
    """손익분기 비용 분석을 사람이 읽을 한국어 요약으로.

    핵심 프레이밍: 손익분기 수수료가 실전 거래 비용보다 낮으면 그 전략은
    비용을 못 이긴다 — 고회전 전략의 환상. MARKET_COST_PRESETS와 대조해
    "이 시장에선 마이너스"를 구체적으로 짚어 준다.
    """
    lines: list[str] = []
    be = break_even["break_even_fee"]
    base_ret = break_even["base_return_at_zero_fee"]
    turnover = break_even["turnover_per_bar"]

    lines.append("=== 손익분기 비용 분석 ===")
    lines.append(f"수수료 0에서의 총수익률 : {base_ret:>10.2%}")
    lines.append(f"봉당 평균 회전율       : {turnover:>10.4f}")

    if break_even["unprofitable_at_zero"]:
        lines.append(
            "손익분기 수수료        :   해당 없음 — 수수료 0에서도 손실"
        )
        lines.append(
            "⚠️ 비용을 한 푼도 안 내도 마이너스다. 이건 비용 문제가 아니라 "
            "엣지가 없는 것이다."
        )
    elif break_even["capped"]:
        lines.append(f"손익분기 수수료        : >{be:>9.4%} (상한에서 잘림)")
        lines.append(
            "비교적 비용에 견고한 편이다. 그래도 이는 과거 데이터 위의 얘기이며 "
            "미래 수익을 보장하지 않는다."
        )
    else:
        lines.append(f"손익분기 편도 수수료   : {be:>10.4%}")
        lines.append(
            "이 수수료를 넘으면 백테스트상의 엣지가 사라진다(총수익 0 이하). "
            "손익분기가 실전 비용보다 낮다면 고회전 전략의 환상일 뿐이다."
        )
        # 실제 시장 프리셋과 대조 — 어느 시장에서 마이너스가 되는지 구체화.
        losers: list[str] = []
        for name, preset in MARKET_COST_PRESETS.items():
            if preset["fee"] > be:
                losers.append(f"{name}(편도 {preset['fee']:.4%})")
        if losers:
            lines.append(
                "실전에선 마이너스가 되는 시장: " + ", ".join(losers)
                + f" > 손익분기 {be:.4%}"
            )
        else:
            lines.append(
                "주요 시장 프리셋의 편도 수수료보다는 손익분기가 높다 — "
                "다만 슬리피지·시장충격·펀딩까지 더하면 얘기가 달라진다."
            )

    if sweep:
        lines.append("")
        lines.append("수수료      총수익률     샤프    거래횟수")
        lines.append("-" * 42)
        for row in sweep:
            lines.append(
                f"{row['fee']:>8.4%}  {row['total_return']:>10.2%}  "
                f"{row['sharpe']:>6.2f}  {row['num_trades']:>7d}"
            )

    lines.append("")
    lines.append(
        "⚠️ 이 분석은 엣지를 만들어 주지 않는다. 엣지가 비용 앞에서 얼마나 얇은지 "
        "드러낼 뿐이며, 미래 수익을 보장하지 않는다."
    )
    return "\n".join(lines)
