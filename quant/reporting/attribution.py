"""전략별 기여도 분석 (attribution) — 앙상블 안 각 전략이 얼마나 값을 하는지.

두 가지 시각을 제공한다:

  1) strategy_attribution: 각 하위 전략을 **단독** 백테스트해 샤프·총수익을 구하고,
     양(+)의 샤프의 상대 비중을 '기여도 힌트'로 제시한다.
  2) ensemble_weight_report: 실행된 앙상블의 last_weights_(마지막 봉 가중치)를
     읽어 '앙상블이 지금 어떤 전략을 신뢰하는가'를 한국어로 요약한다.

⚠️ 정직한 한계: 단독 백테스트 성과는 앙상블 '내부'에서의 실제 기여와 다를 수
있다. 앙상블의 가치는 전략 간 상호작용(낮은 상관 → 분산 효과)에서 오는데,
단독 성과는 그 상호작용을 보지 못한다 — 예컨대 단독으로 부진한 전략이 앙상블
낙폭을 줄이는 핵심일 수 있다. 여기 숫자는 근사적 힌트일 뿐이며, 어떤 수치도
미래 수익을 보장하지 않는다.
"""
from __future__ import annotations

from typing import Any, Mapping


def strategy_attribution(
    df,
    strategies: Mapping[str, Any],
    periods_per_year: int = 365,
    fee: float = 0.001,
    initial_capital: float = 10_000.0,
) -> dict[str, dict[str, float | None]]:
    """전략별 단독 백테스트 성과 + 기여도 힌트를 계산한다 (pandas 필요).

    strategies: {이름: Strategy 인스턴스}. 각 전략을 같은 데이터·비용으로 단독
    백테스트한다(Backtester 재사용).

    반환: {이름: {sharpe, total_return, contribution_hint}}.
    contribution_hint는 max(샤프, 0)의 상대 비중(합=1)이다. 모든 전략의 샤프가
    0 이하이면 힌트를 만들 근거가 없으므로 전부 None — 억지 숫자를 만들지 않는다.

    ⚠️ 단독 기여는 앙상블 내 실제 기여와 상호작용(상관 구조) 때문에 다를 수
    있는 '근사'다. 수익 보장이 아니다.
    """
    from quant.backtest.engine import Backtester   # 지연 임포트 (pandas)

    out: dict[str, dict[str, float | None]] = {}
    for name, strat in strategies.items():
        res = Backtester(strat, fee=fee, initial_capital=initial_capital,
                         periods_per_year=periods_per_year).run(df)
        out[name] = {
            "sharpe": float(res.metrics.sharpe),
            "total_return": float(res.metrics.total_return),
            "contribution_hint": None,
        }
    positive = {n: max(float(r["sharpe"]), 0.0) for n, r in out.items()}
    total = sum(positive.values())
    if total > 0:
        for name in out:
            out[name]["contribution_hint"] = positive[name] / total
    return out


def attribution_report(attribution: dict[str, dict[str, float | None]]) -> str:
    """strategy_attribution 결과를 한국어 요약 문자열로 (표준 라이브러리만)."""
    lines = ["전략별 단독 성과 (기여도 근사):"]
    ranked = sorted(attribution.items(),
                    key=lambda kv: -(kv[1].get("sharpe") or 0.0))
    for name, row in ranked:
        hint = row.get("contribution_hint")
        hint_txt = f" · 기여 힌트 {hint:.0%}" if hint is not None else ""
        lines.append(f"  {name}: 샤프 {row['sharpe']:.2f} · "
                     f"총수익 {row['total_return']:.2%}{hint_txt}")
    lines.append("⚠️ 단독 성과는 앙상블 내 실제 기여(상호작용·분산 효과)와 다를 수 "
                 "있는 근사이며, 미래 수익을 보장하지 않습니다.")
    return "\n".join(lines)


def ensemble_weight_report(ensemble) -> str:
    """앙상블의 현재 가중치(last_weights_ 마지막 봉)를 한국어로 요약한다.

    StrategyEnsemble/AdaptiveEnsemble은 generate_signals 실행 후 진단용으로
    last_weights_(봉별 결합 가중치)를 남긴다. 그 마지막 행 = '앙상블이 지금
    어떤 전략을 얼마나 신뢰하는가'다. 아직 실행 전이면 안내 문구를 반환한다.
    """
    weights = getattr(ensemble, "last_weights_", None)
    if weights is None:
        return ("앙상블 가중치 정보가 없습니다 — generate_signals()를 먼저 "
                "실행하세요 (백테스트/라이브 1사이클 이후 확인 가능).")
    last = weights.iloc[-1]
    strategies = list(getattr(ensemble, "strategies", []))

    def _label(i: int) -> str:
        name = getattr(strategies[i], "name", "") if i < len(strategies) else ""
        return f"{name or '전략'}#{i}"   # 같은 전략이 두 번 들어가도 구분되게 순번 부착

    order = sorted(range(len(last)), key=lambda i: -float(last.iloc[i]))
    lines = ["현재 앙상블 가중치 (마지막 봉 기준):"]
    lines += [f"  {_label(i)}: {float(last.iloc[i]):.1%}" for i in order]
    lines.append("⚠️ 가중치는 과거 성과·변동성 기반 배분일 뿐입니다. 가중치가 "
                 "크다고 그 전략의 미래 수익이 보장되지 않습니다.")
    return "\n".join(lines)
