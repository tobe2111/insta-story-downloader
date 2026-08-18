"""수급 SOM — 사장님이 주신 투자자별 수급 논문의 방식을 재현 가능하게 옮긴 도전자.

논문의 발상: 투자자별 순매수(외국인·기관·개인)가 만드는 '시장 상태'를
자기조직화지도(SOM, Self-Organizing Map)로 군집화하고, 각 군집에서 다음날
주가가 어땠는지를 학습해 매매에 쓴다.

이 틀에서 다른 점 (정직하게):
    · 논문과 같은 3주체(외국인·기관·개인)를 쓴다 — 단, 개인(flow_indi5)은
      2026-08-18부터 부착되는 **도전자 전용** 컬럼이라, 그 이전 데이터나
      부착이 실패한 날에는 외국인·기관 2주체로 동작한다(있으면 쓰고 없으면
      2주체 — 어느 쪽이었는지는 재료 자체가 말해 준다). 챔피언의 피처
      구성(동결)은 이 컬럼을 모르므로 아무 영향이 없다.
    · 논문의 신경망(NN) 예측 단계는 **군집별 다음날 수익 통계**로 대체한다.
      신경망 학습은 실행 환경에 따라 결과가 흔들려 "모든 판단은 재현
      가능해야 한다"는 이 저장소의 원칙과 충돌한다. 통계 판정은 같은
      데이터에서 언제나 같은 답을 준다.
    · SOM 학습도 고정 시드·고정 반복으로 결정적이다. A3C 논문처럼 "성능
      좋은 시드를 채택"하지 않는다 — 그건 우리가 다중검정 보정으로 막는
      바로 그 실수다. 시드는 42 하나, 바꾸지 않는다.

동작:
    ① 재료: 부착된 수급 z-점수 2개 + 5일 수익률(가격 맥락).
    ② 20봉마다 직전 250봉으로 3×3 SOM을 학습(그날 봉 제외 — 룩어헤드 금지).
    ③ 오늘 상태가 속한 군집의 '학습 구간 내 다음날 수익'이 표본 8개 이상
       이고 평균이 양수면 매수(1), 아니면 관망(0).

수급 피처가 없는 종목(코인·미국)은 언제나 관망 — 이 도전자는 수급 데이터가
있는 곳(한국 주식)에서만 의견을 낸다. 도전자로만 서고, 채택은 오디션이
결정한다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant.strategies.base import Strategy

FLOW_COLS = ("x_frgn5", "x_inst5")     # 필수 2주체 — 없으면 관망
# 개인(3주체째) — 있으면 함께 쓴다. 이름이 x_로 시작하지 않는 이유는
# quant/data/krx.py의 부착 주석 참조(챔피언 피처 빌더의 x_* 자동 포함을
# 피하는 동결 장치 — 이 컬럼은 도전자 전용이다).
OPT_FLOW = "flow_indi5"


def _train_som(feats: np.ndarray, grid: int, iters: int,
               seed: int) -> np.ndarray:
    """고정 시드 SOM 학습 → (grid*grid, dim) 코드북. 완전 결정적."""
    rng = np.random.RandomState(seed)
    n, dim = feats.shape
    codes = feats[rng.choice(n, grid * grid, replace=True)].astype(float)
    coords = np.array([(i // grid, i % grid) for i in range(grid * grid)],
                      dtype=float)
    order = rng.randint(0, n, size=iters)
    for it, i in enumerate(order):
        x = feats[i]
        bmu = int(np.argmin(((codes - x) ** 2).sum(axis=1)))
        frac = it / max(1, iters - 1)
        lr = 0.5 * (1.0 - frac) + 0.01 * frac          # 0.5 → 0.01
        sigma = grid * (1.0 - frac) + 0.5 * frac       # 넓게 → 좁게
        d2 = ((coords - coords[bmu]) ** 2).sum(axis=1)
        h = np.exp(-d2 / (2.0 * sigma * sigma))
        codes += (lr * h)[:, None] * (x - codes)
    return codes


def _bmu(codes: np.ndarray, x: np.ndarray) -> int:
    return int(np.argmin(((codes - x) ** 2).sum(axis=1)))


class SupplyDemandSOM(Strategy):
    name = "supply_som"

    def __init__(self, grid: int = 3, window: int = 250,
                 retrain_every: int = 20, iters: int = 400,
                 min_cluster: int = 8, seed: int = 42,
                 allow_short: bool = False):
        self.grid = int(grid)
        self.window = int(window)
        self.retrain_every = int(retrain_every)
        self.iters = int(iters)
        self.min_cluster = int(min_cluster)
        self.seed = int(seed)
        self.allow_short = allow_short

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        n = len(df)
        out = np.zeros(n)
        if not all(c in df.columns for c in FLOW_COLS):
            # 수급 데이터가 없는 시장 — 의견 없음(관망). 침묵이 아니라
            # "이 전략의 재료가 없는 곳"이라는 사실 그대로다.
            return self._finalize(pd.Series(out, index=df.index), df.index)

        close = df["close"].to_numpy(dtype=float)
        mom5 = pd.Series(close).pct_change(5).to_numpy()
        cols = [df[FLOW_COLS[0]].to_numpy(dtype=float),
                df[FLOW_COLS[1]].to_numpy(dtype=float)]
        if OPT_FLOW in df.columns:                     # 개인 — 논문의 3주체째
            cols.append(df[OPT_FLOW].to_numpy(dtype=float))
        cols.append(np.clip(mom5 * 10.0, -4.0, 4.0))   # 수급 z와 비슷한 스케일
        feats = np.column_stack(cols)
        fwd = np.empty(n)
        fwd[:] = np.nan
        fwd[:-1] = close[1:] / close[:-1] - 1.0        # 학습 구간 안에서만 사용

        codes = None
        stats: dict[int, tuple[int, float]] = {}
        for t in range(self.window, n):
            if codes is None or (t - self.window) % self.retrain_every == 0:
                lo, hi = t - self.window, t            # 오늘(t) 제외 — 룩어헤드 금지
                win = feats[lo:hi]
                ok = ~np.isnan(win).any(axis=1)
                train = win[ok]
                if len(train) < self.window // 2:
                    codes = None
                    out[t] = 0.0
                    continue
                # 블록마다 같은 시드 — 성능 좋은 시드 채택(선택 편향) 금지.
                codes = _train_som(train, self.grid, self.iters, self.seed)
                stats = {}
                idxs = np.arange(lo, hi)[ok]
                for i in idxs:
                    f = fwd[i]
                    # 학습 창의 마지막 표본(i == hi-1)의 다음날은 t다 —
                    # 오늘을 학습에 쓰면 룩어헤드이므로 뺀다.
                    if np.isnan(f) or i + 1 >= hi:
                        continue
                    c = _bmu(codes, feats[i])
                    cnt, s = stats.get(c, (0, 0.0))
                    stats[c] = (cnt + 1, s + f)
            if codes is None or np.isnan(feats[t]).any():
                out[t] = 0.0
                continue
            c = _bmu(codes, feats[t])
            cnt, s = stats.get(c, (0, 0.0))
            if cnt >= self.min_cluster and s / cnt > 0.0:
                out[t] = 1.0
            elif self.allow_short and cnt >= self.min_cluster and s / cnt < 0.0:
                out[t] = -1.0
        return self._finalize(pd.Series(out, index=df.index), df.index)
