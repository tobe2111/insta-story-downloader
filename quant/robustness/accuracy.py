"""방향 예측 정확도(hit rate) 측정 — 정직하게.

전략/모델이 '다음 봉 방향'을 얼마나 맞혔는지 계산한다. 매수(비중>0)했는데
다음 봉이 올랐으면 적중, 내렸으면 실패. 이 지표는 룩어헤드 없이 '과거 성과'를
사후 평가할 뿐, 매매에 쓰이지 않는다.

⚠️ 왜 이걸 만드는가: "학습할수록 정확도가 100%로 올라간다"는 것은 불가능하다.
시장은 적응하는 상대가 있는 게임이라, 최고 수준의 모델도 방향 정확도가 대개
52~55%에 그친다. 이 지표는 그 현실을 '숨기지 않고 보여주기' 위한 것이다.
정확도가 오르내리는 것을 눈으로 확인하고, 나빠지면 나빠졌다고 알기 위함이다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def directional_accuracy(
    df: pd.DataFrame,
    signals: pd.Series,
    window: int | None = None,
) -> dict:
    """포지션 방향이 다음 봉 방향과 일치한 비율(적중률)을 계산한다.

    반환:
        hit_rate : 전체 적중률(포지션을 잡은 봉들 중) — 표본 없으면 NaN.
        n        : 평가에 쓰인 봉 수(비중 0이 아닌, 다음 봉이 존재하는 봉).
        rolling  : (window 지정 시) 최근 window봉 이동 적중률 Series.

    적중 판정은 sign(비중_t) == sign(수익률_{t+1}) 이며, 미래 수익률을
    쓰지만 '평가용'일 뿐 신호 생성에는 관여하지 않는다(룩어헤드 아님).
    """
    ret_next = df["close"].pct_change().shift(-1)      # r_{t+1} 를 index t 에 정렬
    sig = signals.reindex(df.index).fillna(0.0)

    active = (sig.abs() > 1e-9) & ret_next.notna()
    correct = active & (np.sign(sig) == np.sign(ret_next))

    n = int(active.sum())
    hit_rate = float(correct.sum() / n) if n > 0 else float("nan")
    out: dict = {"hit_rate": hit_rate, "n": n}

    if window:
        num = correct.astype(float).rolling(window).sum()
        den = active.astype(float).rolling(window).sum()
        out["rolling"] = (num / den.replace(0.0, np.nan)).rename("hit_rate")
    return out
