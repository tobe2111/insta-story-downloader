"""횡단면 랭킹 — **"오를까?"가 아니라 "누가 더 셀까?"를 묻는다** (감사 259).

## 왜 만들었나

지금까지 이 시스템이 던진 질문은 하나뿐이었다: **"이 종목이 내일 오를까?"**
20종목에 20번 물었지만 19종목이 같은 챔피언을 써서 사실상 **한 개의 실험**이다.
그리고 실측(2026-08-16)이 그 한계를 그대로 보여준다:

    125구간 중 '그냥 보유'를 이긴 구간   **39개(31%)**
    오디션에서 실제로 이긴 전략          **buy_hold(그냥 보유)**

방향 예측 정확도의 현실적 상한은 52~55%다. 거기서 비용을 빼면 남는 것이
거의 없고, 실제로 남지 않았다. 이건 파라미터를 더 흔들어서 될 일이 아니라
**질문이 좁은** 것이다.

## 이 전략이 던지는 다른 질문

같은 날 20종목을 **나란히 세워** 순위를 매기고, 상위권일 때만 산다.
"시장이 오를까"가 아니라 "이 종목이 **다른 종목들보다** 나은가"를 본다.

    · 시장 전체가 오르는 날에도 하위권이면 안 산다
    · 시장이 빠지는 날에도 상위권이면 살 수 있다

즉 **시장 방향과 다른 축**이다. 기존 챔피언들이 서로 닮아 분산이 이름뿐이던
문제(19/20 동일 챔피언)에 실제로 다른 신호원을 하나 더한다.

## 정직한 한계

⚠️ **이것도 만병통치가 아니다.** 롱온리로 쓰면 여전히 시장 위험을 그대로
   진다 — 전 종목이 함께 빠지면 상위권도 빠진다. 진짜 시장 중립은 하위권을
   **공매도**해야 나오는데, 그건 체결·차입비용·제도(한국 개인 공매도)를
   따로 검증해야 하는 별개의 일이다. 그래서 여기서는 **롱온리가 기본**이고
   `allow_short`는 꺼져 있다.

⚠️ **비교 대상은 우리 유니버스 20종목뿐이다.** "시장에서 상위 30%"가 아니라
   "우리가 고른 20개 중 상위 30%"다. 그 20개가 이미 살아남은 종목이라
   생존 편향이 그대로 들어 있다(감사 256과 같은 주의).

⚠️ **스냅샷이 없으면 아무 말도 하지 않는다**(전 구간 0). 지어내지 않는다.
   그날은 '무효 후보'로 오디션에서 제외된다 — 그게 맞다.

## 룩어헤드를 어떻게 막았나 — 두 겹이다

**① 가격은 과거 방향으로만 채운다.** 또래 계열을 내 인덱스에 맞출 때
`ffill`만 쓴다. 뒤채움 한 줄이면 내일 가격이 오늘 순위에 실린다.

**② 폴더 선택이 데이터와 무관하다.** 첫 판은 넘겨받은 프레임의 마지막
봉으로 스냅샷 폴더를 골랐는데, 그러면 미래를 잘라낼 때 다른 폴더가 뽑혀
**과거 봉의 신호까지 바뀐다**(저장소의 인과성 검사가 절단 200에서 18봉이
바뀐 것을 잡았다). 지금은 `fullest_snapshot_day` — 언제 잘라도 같은 폴더다.

⚠️ 그 대가로 **생존 편향**을 감수한다(`MLStrategy(pool="universe")`와 똑같은
   맞바꿈). 폴더에 든 **종목 목록**은 '오늘까지 살아남아 유니버스에 있는'
   종목이다. 가격 값 자체는 봉 t 이전만 쓰므로 룩어헤드는 아니지만, 누구와
   비교하는지는 사후 정보다. 그래서 강제 적용하지 않고 후보로만 세우며,
   승격되면 그 사실이 장부의 전략 이름(cross_rank)에 그대로 남는다.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant.strategies.base import Strategy
from quant.utils.logging import get_logger

log = get_logger("strategies.cross_rank")

# 또래가 이보다 적으면 순위가 의미 없다 — 3종목 중 1등은 등수가 아니다.
MIN_PEERS = 4


class CrossRank(Strategy):
    """또래 대비 상대 강도가 상위 `top_frac`일 때만 보유한다."""

    name = "cross_rank"

    def __init__(self, lookback: int = 60, top_frac: float = 0.3,
                 state_dir: str = "state", min_peers: int = MIN_PEERS,
                 allow_short: bool = False):
        if not 0.0 < float(top_frac) <= 1.0:
            raise ValueError(f"top_frac은 (0,1] 이어야 합니다: {top_frac!r}")
        if int(lookback) < 2:
            raise ValueError(f"lookback은 2 이상이어야 합니다: {lookback!r}")
        self.lookback = int(lookback)
        self.top_frac = float(top_frac)
        self.state_dir = state_dir
        self.min_peers = int(min_peers)
        # ⚠️ 기본은 롱온리다. 하위권 공매도는 체결·차입비용·제도를 따로
        #    검증해야 하는 별개의 일이라 여기서 몰래 켜지 않는다.
        self.allow_short = bool(allow_short)

    # ── 또래 모멘텀 행렬 ──────────────────────────────────────

    def _peer_matrix(self, index: pd.Index) -> pd.DataFrame | None:
        """또래들의 lookback 수익률을 내 인덱스에 맞춘 행렬(없으면 None).

        ⚠️ `ffill`만 쓴다. 뒤채움(bfill/interpolate)을 한 줄이라도 넣으면
           **내일 가격이 오늘 순위에 실린다** — 이 파일에서 가장 조심할 곳.
        """
        from quant.utils.repro import fullest_snapshot_day, load_snapshot_pool_day

        try:
            # ⚠️ 폴더를 **넘겨받은 데이터의 마지막 봉**으로 고르면 안 된다.
            #    첫 판이 그렇게 했다가 저장소의 인과성 검사에 잡혔다: 미래를
            #    잘라내면 cutoff가 앞당겨져 **다른 폴더**가 뽑히고, 그러면
            #    과거 봉의 신호까지 바뀐다(절단 200에서 18봉이 바뀌었다).
            #    데이터와 무관한 규칙이어야 한다 — 그래야 언제 잘라도 같다.
            frames = load_snapshot_pool_day(
                self.state_dir, fullest_snapshot_day(self.state_dir))
        except Exception as exc:  # noqa: BLE001 — 풀 실패가 배치를 막지 않는다
            log.warning("횡단면 또래 로드 실패: %s", exc)
            return None
        cols = {}
        for i, f in enumerate(frames):
            if f is None or "close" not in getattr(f, "columns", ()):
                continue
            s = pd.Series(f["close"]).astype(float)
            if len(s) <= self.lookback:
                continue
            mom = s.pct_change(self.lookback)
            # 내 봉 시각으로 정렬 — 과거 방향으로만 채운다.
            cols[f"p{i}"] = mom.reindex(mom.index.union(index)).ffill().reindex(index)
        if len(cols) < self.min_peers:
            return None
        return pd.DataFrame(cols, index=index)

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        idx = df.index
        mine = df["close"].astype(float).pct_change(self.lookback)
        mat = self._peer_matrix(idx)
        if mat is None:
            # 또래를 못 구했다 — **지어내지 않는다.** 전 구간 관망이면
            # 챔피언과 신호가 같아 그날 오디션에서 '무효 후보'로 빠진다.
            log.info("횡단면: 또래 부족(최소 %d) — 신호 없음", self.min_peers)
            return self._finalize(pd.Series(0.0, index=idx), idx)

        # 나보다 낮은 또래의 비율 = 내 백분위.
        valid = mat.notna().sum(axis=1)
        below = mat.lt(mine, axis=0).sum(axis=1)

        # ⚠️ **순위가 성립하는 봉만 판단한다.** 내 모멘텀이 없거나(워밍업)
        #    비교할 또래가 하나도 없으면(또래가 나보다 늦게 시작한 구간)
        #    등수라는 것이 없다.
        #
        #    이 가드를 `pct` 계산 **뒤**의 비교식에만 맡기면 안 된다. 내
        #    모멘텀이 NaN일 때 `mat.lt(NaN)`은 전부 False라 백분위가 **0.0**
        #    으로 계산된다 — NaN이 아니라 0이다. 롱온리에서는 우연히 무해하지만
        #    (`0.0 >= 0.7`이 거짓), 숏을 켜는 순간 `0.0 <= 0.3`이 참이 되어
        #    **아무것도 모르는 구간에서 최대 숏을 잡는다.**
        known = mine.notna() & (valid > 0)
        pct = pd.Series(np.nan, index=idx, dtype=float)
        pct[known] = (below[known] / valid[known]).astype(float)

        w = pd.Series(0.0, index=idx)
        # 상위 top_frac — 백분위가 (1 - top_frac) 이상이면 상위권이다.
        w[known & (pct >= (1.0 - self.top_frac))] = 1.0
        if self.allow_short:
            w[known & (pct <= self.top_frac)] = -1.0
        return self._finalize(w, idx)
