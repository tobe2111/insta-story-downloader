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

import math
from typing import Any, Mapping


def _num(v, unit: str = "") -> str:
    """사람이 읽을 숫자 — 측정이 안 됐으면 'nan'이 아니라 그렇게 말한다.

    ⚠️ 예전에는 `f"{v:.2f}"`라 화면에 **"샤프 nan · 총수익 nan%"**가 그대로
    나갔다(감사 202). 읽는 사람은 그것이 '0'인지 '측정 실패'인지 '버그'인지
    알 수 없다. 숫자가 없으면 없다고 적는 편이 정직하다.
    """
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "측정 불가"
    if not math.isfinite(f):
        return "측정 불가"
    return f"{f:.2%}" if unit == "%" else f"{f:.2f}"


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
    # ⚠️ **망가진 전략 하나가 나머지의 힌트까지 지우면 안 된다**(감사 202).
    #    `max(nan, 0.0)`은 `nan`이다(파이썬에서 nan과의 비교는 모두 False).
    #    그래서 전략 하나의 샤프가 NaN이면 합계가 NaN이 되고, `total > 0`이
    #    거짓이라 **전 전략의 기여도 힌트가 사라졌다.** 실측:
    #
    #        좋은전략 1.50 · 망가진전략 nan · 보통전략 0.40  →  힌트 전부 없음
    #
    #    측정이 안 되는 전략은 기여 0으로 두고 나머지는 정상적으로 나눈다.
    #    '모르는 하나' 때문에 '아는 둘'까지 잃을 이유가 없다.
    #
    # ⚠️ **다만 이 분기는 지금 도달 불가다.** 실측으로 확인했다 — 관망·NaN
    #    신호·한 봉짜리 신호를 실제 `Backtester`에 태워도 샤프는 0.0이나
    #    유한값으로 나온다(엔진이 위쪽에서 이미 막는다). 그래서 변이 항목을
    #    붙이지 않았다: **잡을 수 없는 항목은 안전장치가 아니라 소음이다.**
    #    감사 183에서 `hrp.py`의 합계 검사가 정규화 뒤라 어떤 입력으로도
    #    안 걸렸던 것과 같은 자리다 — 그때 배운 대로, 방어는 위험이 실제로
    #    도착하는 쪽(아래 `attribution_report`)에 두었고 그쪽은 변이로 지킨다.
    #    여기 남긴 것은 엔진이 바뀌었을 때를 위한 값싼 보험이다.
    positive = {n: (max(float(r["sharpe"]), 0.0)
                    if math.isfinite(float(r["sharpe"])) else 0.0)
                for n, r in out.items()}
    total = sum(positive.values())
    if total > 0:
        for name in out:
            out[name]["contribution_hint"] = positive[name] / total
    return out


def attribution_report(attribution: dict[str, dict[str, float | None]]) -> str:
    """strategy_attribution 결과를 한국어 요약 문자열로 (표준 라이브러리만)."""
    lines = ["전략별 단독 성과 (기여도 근사):"]

    def _rank(kv):
        # ⚠️ NaN이 섞이면 정렬이 뒤죽박죽이 된다(nan과의 비교가 전부 False).
        #    측정 불가는 **맨 뒤로** 보내고, 같은 값이면 이름 순 — 같은 입력이
        #    같은 순서를 내야 리포트를 대조할 수 있다(재현성).
        s = kv[1].get("sharpe")
        try:
            f = float(s)
        except (TypeError, ValueError):
            f = float("nan")
        return (0, -f, kv[0]) if math.isfinite(f) else (1, 0.0, kv[0])

    for name, row in sorted(attribution.items(), key=_rank):
        hint = row.get("contribution_hint")
        hint_txt = (f" · 기여 힌트 {hint:.0%}"
                    if isinstance(hint, (int, float)) and math.isfinite(hint)
                    else "")
        lines.append(f"  {name}: 샤프 {_num(row.get('sharpe'))} · "
                     f"총수익 {_num(row.get('total_return'), '%')}{hint_txt}")
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
    # `is None`만 보면 **빈 프레임에서 IndexError**가 난다(감사 202). 신호를
    # 한 번 돌렸는데 봉이 없었던 경우가 그렇다 — '아직 안 돌림'과 같은 상황이니
    # 같은 안내를 낸다. 리포트가 예외로 죽으면 그날 요약 전체가 사라진다.
    if weights is None or len(weights) == 0:
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
