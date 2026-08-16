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

import math

import numpy as np
import pandas as pd

# 이 비율과 구별되지 않으면 "맞힌다"고 말할 수 없다 — 동전던지기.
COIN_FLIP = 0.5


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """윌슨 신뢰구간(기본 95%) — 소표본·극단 비율에서도 [0,1]을 안 벗어난다.

    ⚠️ 이 규칙은 **여기 한 곳에만** 둔다. 같은 공식을 두 곳에 적으면 반드시
       어긋난다(FROZEN_IDEAS ①). explain.py가 자기 사본을 갖고 있었고,
       그쪽은 n=0에서 0으로 나눈다 — 이 함수는 그 경우 (nan, nan)을 준다.
    """
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, center - half), min(1.0, center + half)


def is_conclusive(k: int, n: int, z: float = 1.96) -> bool:
    """이 표본이 '동전던지기가 아니다'라고 말할 수 있는가.

    신뢰구간이 50%를 품고 있으면 **어느 쪽으로도 말할 수 없다.** 그런데도
    비율만 크게 써 두면 읽는 사람은 그것을 확립된 실력으로 읽는다.

    ⚠️ 표본 크기(n)만으로는 판정할 수 없다(2026-08-14 실측). 사장님이
       "솔라나 64% n=11"을 지적해 20종목을 전부 재 봤더니 **19개**의
       구간이 50%를 품고 있었다. n=81짜리 60%(구간 50~70%)도 그랬다 —
       그때까지 화면은 n<20일 때만 n을 흐리게 붙였으므로, n=81은 아무
       단서 없이 "60%"라는 단정으로 나가고 있었다.
       **n이 아니라 구간이 판정한다.**
    """
    lo, hi = wilson_ci(k, n)
    if lo != lo or hi != hi:            # NaN — 표본 없음
        return False
    return not (lo <= COIN_FLIP <= hi)


def hit_rate_text(rec: dict | None, *, key: str = "hit_rate",
                  n_key: str = "hit_n") -> str:
    """장부 기록 하나 → 사람이 읽을 적중률 문자열. **여기가 유일한 규칙이다.**

    화면(assets/hitrate.js)과 같은 판정을 파이썬 쪽에서도 쓴다 — 텔레그램
    요약·조종석 KPI가 각자 자기 서식을 만들면 같은 날 같은 종목이 화면에서는
    "판정 불가"인데 알림에서는 "60%"로 나간다.

        58% (판정 불가 32~81% · n=12)   구간이 50%를 품는다 — 아무 말도 못 한다
        67% (54~77% · n=63)             동전던지기와 구별된다
        60% (표본 미상)                  n이 기록되지 않은 옛 기록
        N/A                              채점 가능한 봉이 없다
    """
    rec = rec or {}
    r = rec.get(key)
    if not isinstance(r, (int, float)) or isinstance(r, bool) or r != r:
        return "N/A"
    n = rec.get(n_key)
    if not isinstance(n, int) or isinstance(n, bool) or n <= 0:
        return f"{r:.0%} (표본 미상)"
    lo, hi = wilson_ci(round(r * n), n)
    band = f"{lo * 100:.0f}~{hi * 100:.0f}%"   # 화면(hitrate.js)과 같은 서식
    if is_conclusive(round(r * n), n):
        return f"{r:.0%} ({band} · n={n})"
    return f"{r:.0%} (판정 불가 {band} · n={n})"


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
    k = int(correct.sum())
    hit_rate = float(k / n) if n > 0 else float("nan")
    # ⚠️ 적중률은 **혼자 다니지 않는다.** 비율만 내보내면 읽는 쪽이 표본을
    #    붙일 방법이 없고, 그러면 n=11짜리 64%가 확립된 실력처럼 읽힌다.
    #    구간과 판정을 같이 돌려주어 '숫자를 쓸 수 있는가'를 호출자가
    #    따로 계산하지 않게 한다(같은 규칙을 두 곳에 적지 않는다).
    lo, hi = wilson_ci(k, n)
    out: dict = {"hit_rate": hit_rate, "n": n,
                 "n_flat": int((held & ~moved).sum()),
                 "correct": k, "lo": lo, "hi": hi,
                 "conclusive": is_conclusive(k, n)}

    if window:
        num = correct.astype(float).rolling(window).sum()
        den = active.astype(float).rolling(window).sum()
        out["rolling"] = (num / den.replace(0.0, np.nan)).rename("hit_rate")
        # ⚠️ 롤링 비율에는 **분모가 따라다녀야 한다**(2026-08-14). 예전에는
        #    비율만 돌려줬고, 화면·알림은 그 비율을 표본 없이 "최근 적중률
        #    64%"로 내보냈다. window=20이어도 관망이 많은 종목은 실제
        #    채점된 봉이 서너 개뿐이라, 그 64%는 아무것도 말하지 않는다.
        #    비율을 주는 자리에서 분모도 같이 준다 — 그래야 받는 쪽이
        #    '이 숫자를 쓸 수 있는가'를 물을 수 있다.
        out["rolling_n"] = den.rename("n")
    return out
