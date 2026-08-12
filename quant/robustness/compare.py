"""전략 A/B 비교 — '더 나아 보이는 것'이 노이즈인지 검정한다.

파라미터를 바꿨더니 샤프가 1.2에서 1.4로 올랐다 — 개선일까, 운일까?
단일 숫자 비교로는 알 수 없다. 두 전략의 샤프 '차이'를 부트스트랩으로 수천 번
재추출해 분포를 만들고, 그 95% 신뢰구간이 0을 포함하는지 본다.

    구간이 0을 포함  →  차이가 유의하지 않다 = 더 나아 보이는 건 노이즈일 수 있다.
    구간이 0을 배제  →  차이가 통계적으로 유의하다(그래도 미래 수익 보장은 아니다).

부트스트랩은 블록 재추출(block bootstrap)로 자기상관을 어느 정도 보존한다.
길이가 같으면 '짝지어(paired)' — 같은 봉 인덱스로 두 전략을 함께 재추출해
공통 시장 충격을 상쇄하고 차이의 분산을 더 정직하게 추정한다. 길이가 다르면
독립 재추출한다.

⚠️ 블록 부트스트랩도 자기상관을 완전히 제거하지 못한다. 남은 상관 때문에
   신뢰구간이 실제보다 약간 좁게(=과신하게) 나올 수 있음을 감안할 것.
"""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

from quant.utils.numerics import degenerate_spread


def _clean(returns) -> np.ndarray:
    r = np.asarray(returns, dtype=float)
    return r[np.isfinite(r)]


def _sharpe(r: np.ndarray, ppy: int) -> float:
    if len(r) < 2:
        return 0.0
    sd = r.std()
    if degenerate_spread(sd, float(np.abs(r).mean())):   # 감사 146
        return 0.0
    return float(r.mean() / sd * np.sqrt(ppy))


def _block_indices(n: int, rng: np.random.Generator, block: int) -> np.ndarray:
    """길이 n짜리 블록 부트스트랩 '인덱스'를 만든다.

    인덱스를 반환하므로, 짝지은(paired) 비교에서 두 전략에 '같은' 재추출을
    적용해 공통 시장 충격을 상쇄할 수 있다.

    ⚠️ **원형(circular) 블록이어야 한다**(감사 188). 예전에는 끝에서 잘랐다.

        idx.extend(range(start, min(start + block, n)))

    블록은 `start ≤ j`인 자리에서만 j를 담을 수 있으므로, **앞쪽 원소는
    들어갈 블록 자체가 적다.** 실측(n=100·block=10, 2만 회):

        index 0    표집 빈도 0.108×   (균등이면 1.00×)
        앞 10개    평균     0.584×
        중간·뒤    평균     1.05×

    즉 표본의 **앞부분이 조용히 절반 무게로 깎인다.** 이 함수는 챔피언을
    바꿀지 정하는 A/B 유의성 검정에 쓰인다 — 초반 구간이 다른 국면이었다면
    (워밍업·다른 레짐) 그 구간의 영향만 빠진 채로 판정이 난다.

    끝을 자르지 않고 **앞으로 감으면**(modulo) 모든 인덱스의 포함 확률이
    정확히 같아진다. 자기상관 보존이라는 목적도 그대로다.
    """
    idx: list[int] = []
    while len(idx) < n:
        start = int(rng.integers(0, n))
        idx.extend((start + k) % n for k in range(block))
    return np.asarray(idx[:n])


def compare_strategies(
    returns_a,
    returns_b,
    n_sims: int = 2000,
    periods_per_year: int = 365,
    block: int | None = None,
    seed: int = 42,
    rng: np.random.Generator | None = None,
) -> dict:
    """두 전략 수익률의 샤프 '차이'를 부트스트랩해 유의성을 검정한다.

    길이가 같으면 짝지어(paired) 재추출(같은 인덱스로 A·B 동시 표집),
    다르면 독립 재추출한다. 결정론적이다 — 같은 seed면 같은 결과.

    반환: {
        'sharpe_a', 'sharpe_b', 'sharpe_diff'(=a-b),
        'ci_low', 'ci_high'   : 차이의 95% 신뢰구간,
        'prob_a_better'       : A가 B보다 나은 재추출 비율(0~1),
        'significant'         : 신뢰구간이 0을 배제하면 True,
        'paired'              : 짝지어 재추출했는지,
    }
    """
    a = _clean(returns_a)
    b = _clean(returns_b)
    if len(a) < 2 or len(b) < 2:
        raise ValueError("두 전략 모두 최소 2개 이상의 수익률이 필요합니다.")

    ppy = periods_per_year
    sharpe_a = _sharpe(a, ppy)
    sharpe_b = _sharpe(b, ppy)

    if rng is None:
        rng = np.random.default_rng(seed)

    paired = len(a) == len(b)
    # 블록 길이: 미지정 시 √n (monte_carlo와 동일한 관례) — 자기상관 보존용.
    n_a, n_b = len(a), len(b)
    blk_a = block if (block and block > 0) else max(1, int(np.sqrt(n_a)))
    blk_b = block if (block and block > 0) else max(1, int(np.sqrt(n_b)))

    diffs = np.empty(n_sims)
    for i in range(n_sims):
        if paired:
            # 같은 블록 인덱스를 두 전략에 함께 적용 — 공통 충격 상쇄
            idx = _block_indices(n_a, rng, blk_a)
            da = _sharpe(a[idx], ppy)
            db = _sharpe(b[idx], ppy)
        else:
            da = _sharpe(a[_block_indices(n_a, rng, blk_a)], ppy)
            db = _sharpe(b[_block_indices(n_b, rng, blk_b)], ppy)
        diffs[i] = da - db

    ci_low, ci_high = (float(x) for x in np.percentile(diffs, [2.5, 97.5]))
    significant = ci_low > 0.0 or ci_high < 0.0

    return {
        "sharpe_a": sharpe_a,
        "sharpe_b": sharpe_b,
        "sharpe_diff": sharpe_a - sharpe_b,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "prob_a_better": float((diffs > 0.0).mean()),
        "significant": bool(significant),
        "paired": bool(paired),
    }


def compare_report(result: dict) -> str:
    """A/B 비교 결과를 사람이 읽을 한국어 요약으로.

    정직한 프레이밍: 차이가 유의하지 않으면(신뢰구간이 0을 포함) '더 나아
    보이는 건 노이즈일 수 있다 — 파라미터를 바꿨다고 개선된 게 아니다'.
    """
    lines = ["=== 전략 A/B 비교 (샤프 차이 유의성) ==="]
    lines.append(
        f"샤프 A : {result['sharpe_a']:>7.2f}    샤프 B : {result['sharpe_b']:>7.2f}"
    )
    lines.append(
        f"샤프 차이(A-B) : {result['sharpe_diff']:>7.2f}  "
        f"95% 신뢰구간 [{result['ci_low']:.2f} ~ {result['ci_high']:.2f}]"
    )
    lines.append(
        f"A가 B보다 나을 확률 : {result['prob_a_better']:.1%}"
        + ("  (짝지은 부트스트랩)" if result.get("paired") else "  (독립 부트스트랩)")
    )

    if result["significant"]:
        better = "A" if result["sharpe_diff"] > 0 else "B"
        lines.append(
            f"✅ 차이가 통계적으로 유의하다(신뢰구간이 0을 배제) — {better}가 낫다고 "
            "볼 근거가 있다. 다만 이는 과거 표본 안의 얘기이며 미래 수익을 "
            "보장하지 않는다."
        )
    else:
        lines.append(
            "⚠️ 차이가 유의하지 않다(신뢰구간이 0을 포함). 더 나아 보이는 건 "
            "노이즈일 수 있다 — 파라미터를 바꿨다고 개선된 게 아니다."
        )
    lines.append(
        "※ 블록 부트스트랩도 자기상관을 완전히 제거하지 못해, 신뢰구간이 실제보다 "
        "약간 좁게(과신하게) 나올 수 있다."
    )
    return "\n".join(lines)


def ab_test(
    df: pd.DataFrame,
    factory_a: Callable[[], "object"],
    factory_b: Callable[[], "object"],
    n_sims: int = 2000,
    periods_per_year: int = 365,
    seed: int = 42,
    **bt_kwargs,
) -> dict:
    """두 전략을 같은 데이터로 백테스트한 뒤 샤프 차이를 검정한다(편의 함수).

    factory_a/factory_b는 인자 없는 호출로 '새' Strategy를 반환해야 한다
    (전략은 상태를 가지므로 재사용하지 말 것). bt_kwargs는 Backtester에 전달된다.
    """
    from quant.backtest.engine import Backtester

    res_a = Backtester(factory_a(), periods_per_year=periods_per_year,
                       **bt_kwargs).run(df)
    res_b = Backtester(factory_b(), periods_per_year=periods_per_year,
                       **bt_kwargs).run(df)
    return compare_strategies(
        res_a.returns, res_b.returns,
        n_sims=n_sims, periods_per_year=periods_per_year, seed=seed,
    )
