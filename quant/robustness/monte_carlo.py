"""몬테카를로 부트스트랩 — 성과의 '신뢰구간'을 구한다.

백테스트가 내놓는 샤프지수 하나는 착시일 수 있다. 같은 전략이라도 수익률의
순서를 뒤섞거나 재추출하면 결과가 크게 흔들린다. 부트스트랩으로 수천 번
가상의 경로를 만들어 보면 '진짜 실력'의 분포가 보인다.

    샤프 1.5 (단일값)  →  샤프 90% 신뢰구간 [0.3, 2.6]  처럼.

구간 하단이 0 근처거나 음수라면, 그 전략은 운이었을 가능성이 크다.
블록 부트스트랩(block bootstrap)을 기본으로 써서 수익률의 자기상관을
어느 정도 보존한다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _block_bootstrap(r: np.ndarray, rng: np.random.Generator, block: int) -> np.ndarray:
    n = len(r)
    out: list[float] = []
    while len(out) < n:
        start = int(rng.integers(0, n))
        out.extend(r[start : start + block])
    return np.asarray(out[:n])


def bootstrap_metrics(
    returns: pd.Series,
    n_sims: int = 1000,
    block: int | None = None,
    periods_per_year: int = 365,
    seed: int = 42,
) -> dict[str, np.ndarray]:
    """전략 수익률을 재추출해 지표들의 분포를 만든다.

    반환: {'sharpe': array, 'total_return': array, 'max_drawdown': array, 'cagr': array}
    """
    r = returns.dropna().to_numpy()
    r = r[np.isfinite(r)]
    if len(r) < 2:
        raise ValueError("수익률 데이터가 부족합니다.")
    block = block or max(1, int(np.sqrt(len(r))))
    rng = np.random.default_rng(seed)
    years = len(r) / periods_per_year

    sharpe = np.empty(n_sims)
    total_ret = np.empty(n_sims)
    max_dd = np.empty(n_sims)
    cagr = np.empty(n_sims)

    for i in range(n_sims):
        sample = _block_bootstrap(r, rng, block)
        std = sample.std()
        sharpe[i] = sample.mean() / std * np.sqrt(periods_per_year) if std > 0 else 0.0
        equity = np.cumprod(1.0 + sample)
        total_ret[i] = equity[-1] - 1.0
        peak = np.maximum.accumulate(equity)
        max_dd[i] = (equity / peak - 1.0).min()
        cagr[i] = equity[-1] ** (1 / years) - 1.0 if years > 0 else 0.0

    return {
        "sharpe": sharpe,
        "total_return": total_ret,
        "max_drawdown": max_dd,
        "cagr": cagr,
    }


def summarize(dist: dict[str, np.ndarray]) -> str:
    """분포를 사람이 읽기 좋은 신뢰구간 표로 요약한다."""
    labels = {
        "sharpe": "샤프지수",
        "cagr": "연수익(CAGR)",
        "total_return": "총수익률",
        "max_drawdown": "최대낙폭",
    }
    lines = ["지표          중앙값     [ 5% ~ 95% 신뢰구간 ]"]
    lines.append("-" * 48)
    for key, label in labels.items():
        arr = dist[key]
        p5, p50, p95 = np.percentile(arr, [5, 50, 95])
        pct = key != "sharpe"
        fmt = (lambda x: f"{x:>8.2%}") if pct else (lambda x: f"{x:>8.2f}")
        lines.append(f"{label:<10} {fmt(p50)}   [{fmt(p5)} ~ {fmt(p95)} ]")
    return "\n".join(lines)
