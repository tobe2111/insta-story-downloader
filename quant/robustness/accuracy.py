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
        hit_rate : 전체 적중률(채점 가능한 봉들 중) — 표본 없으면 NaN.
        n        : 채점에 쓰인 봉 수 — 비중이 0이 아니고, 다음 봉이 있고,
                   **그 다음 봉이 실제로 움직인** 봉.
        n_flat   : 포지션은 있었지만 다음 봉이 보합(수익률 0)이라 채점에서
                   뺀 봉 수. 분모에서 빼되 숨기지 않는다(감사 168).
        rolling  : (window 지정 시) 최근 window봉 이동 적중률 Series.

    적중 판정은 sign(비중_t) == sign(수익률_{t+1}) 이며, 미래 수익률을
    쓰지만 '평가용'일 뿐 신호 생성에는 관여하지 않는다(룩어헤드 아님).

    ⚠️ 수익률은 **종가 대비 종가**다. 이 시스템은 실제로 다음 봉 시가에
       체결하므로, 이 지표는 "모델이 방향을 맞혔는가"를 재는 것이지
       "우리가 그 방향을 먹었는가"가 아니다. 후자는 장부의 실현 손익이
       답한다 — 둘을 같은 것으로 읽지 말 것.
    """
    ret_next = df["close"].pct_change().shift(-1)      # r_{t+1} 를 index t 에 정렬
    sig = signals.reindex(df.index).fillna(0.0)

    held = (sig.abs() > 1e-9) & ret_next.notna()
    # ⚠️ **방향이 없던 봉은 방향 예측을 채점할 수 없다**(감사 168).
    #    예전에는 `held`를 그대로 분모로 썼다. 그런데 `np.sign(0.0)`은 0이라
    #    보합 봉(수익률이 정확히 0)은 롱이든 숏이든 `sign(sig) != 0` →
    #    **무조건 '틀림'**으로 채점됐다.
    #
    #    실측(롱 고정, 상승 6 · 하락 2 · 보합 2):
    #        보고된 적중률 60.0%   ← 보합 2봉이 오답으로 들어갔다
    #        방향이 있던 봉만  75.0%  (6/8)
    #
    #    자기 자신에게 불리한 쪽이라 '정직'해 보이지만 그냥 틀린 숫자다.
    #    게다가 보합 봉 비율은 종목마다 다르다(거래정지·상하한가·저유동
    #    국내주식이 많다) — 그래서 종목 간 비교가 조용히 왜곡된다.
    #
    #    분모에서 빼되 **숨기지는 않는다**. 몇 봉을 뺐는지 n_flat으로 함께
    #    돌려준다 — 안 보이면 '보합이 없었다'와 구별되지 않는다.
    moved = ret_next != 0
    active = held & moved
    correct = active & (np.sign(sig) == np.sign(ret_next))

    n = int(active.sum())
    hit_rate = float(correct.sum() / n) if n > 0 else float("nan")
    out: dict = {"hit_rate": hit_rate, "n": n,
                 "n_flat": int((held & ~moved).sum())}

    if window:
        num = correct.astype(float).rolling(window).sum()
        den = active.astype(float).rolling(window).sum()
        out["rolling"] = (num / den.replace(0.0, np.nan)).rename("hit_rate")
    return out
