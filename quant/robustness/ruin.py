"""파산확률 — **분포가 좋아도 도중에 한 번 죽으면 끝이다.**

⚠️ 왜 이게 따로 필요한가 (2026-08-14).

    이 저장소의 검증 3종은 전부 **수익률의 분포**를 본다.
      · DSR  — 시도 횟수를 감안해도 샤프가 살아남는가
      · PBO  — 과거 1등이 새 구간에서도 상위인가
      · CPCV — 기간을 여러 갈래로 잘라도 계속 잘하는가

    셋 다 "평균적으로 좋은가"를 묻는다. 그런데 **레버리지가 붙으면 평균이
    아무 의미가 없어지는 순간**이 생긴다 — 도중에 계좌가 0이 되면 그 뒤의
    좋은 수익률은 나에게 오지 않는다. 경로 의존(path dependence)이다.

    예: 매일 51% 확률로 +10%, 49% 확률로 -10%. 기댓값은 양수고 샤프도
    괜찮다. 그런데 10배 레버리지면 -10%짜리 하루에 계좌가 사라진다.
    DSR·PBO·CPCV는 셋 다 **통과**시킨다 — 그들이 보는 것은 수익률 분포지
    '언제 죽는가'가 아니기 때문이다.

    그래서 레버리지를 열기 전에 이 계산을 먼저 만든다. 순서를 바꾸면
    "검증 3종을 통과했으니 안전합니다"가 거짓말이 된다.

⚠️ **이건 예측이 아니다.** 과거 수익률을 다시 뽑아(부트스트랩) "이 성질의
   수익률이 계속됐다면 얼마나 자주 죽었을까"를 세는 것이다. 미래가 과거와
   같다는 보장은 없고, 특히 **꼬리는 과거 표본에 안 들어 있을 수 있다** —
   그래서 이 숫자는 낙관 쪽으로 틀린다. 그만큼 문턱을 낮게 잡는다.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# 이 밑으로 떨어지면 '파산'으로 센다. 0%가 아니라 20%인 이유:
# 계좌가 정확히 0이 되기 전에 이미 게임이 끝난다 — 최소 주문 금액에 걸려
# 매매를 못 하고, 사람은 그 전에 그만둔다. 실질적 파산선을 쓴다.
RUIN_LEVEL = 0.20

# 통과 문턱 — 이 확률을 넘으면 그 설정으로는 레버리지를 쓸 수 없다.
# 1%는 "100번 살면 한 번 죽는다"이고, 이 계산이 낙관 쪽으로 틀린다는 것을
# 감안하면 실제로는 더 자주다.
RUIN_PASS = 0.01

DEFAULT_PATHS = 2000
DEFAULT_HORIZON = 252          # 1년(거래일)


@dataclass(frozen=True)
class RuinResult:
    probability: float         # 지평 안에 파산선을 밟은 경로의 비율
    median_final: float        # 최종 자산 배수의 중앙값(1.0 = 본전)
    worst_final: float         # 가장 나쁜 경로의 최종 자산 배수
    n_paths: int
    horizon: int
    leverage: float
    ok: bool
    reason: str

    def describe(self) -> str:
        return (f"파산확률 {self.probability:.2%}(기준 {RUIN_PASS:.0%} 미만) · "
                f"{self.horizon}일 · {self.leverage:g}배 · "
                f"중앙값 {self.median_final:.2f}배 · 최악 {self.worst_final:.2f}배 "
                f"— {self.reason}")


def probability_of_ruin(returns, *, leverage: float = 1.0,
                        horizon: int = DEFAULT_HORIZON,
                        paths: int = DEFAULT_PATHS,
                        ruin_level: float = RUIN_LEVEL,
                        seed: int = 0) -> RuinResult:
    """과거 수익률을 다시 뽑아 '얼마나 자주 죽는가'를 센다.

    returns  : 하루치 수익률 배열(비율. 0.01 = +1%). 전략의 실제 기록.
    leverage : 배수. 1.0이면 지금 이 시스템의 상태.

    ⚠️ **블록 부트스트랩을 쓴다.** 하루씩 무작위로 섞으면 연속된 하락(진짜로
       죽이는 것)이 흩어져 파산확률이 실제보다 **낮게** 나온다. 나쁜 날은
       뭉쳐서 온다 — 그 성질을 유지해야 이 계산에 뜻이 있다.

    ⚠️ 파산은 **경로**로 판정한다. 최종 자산만 보면 도중에 -95%까지 갔다가
       돌아온 경로가 '무사'로 세어진다 — 실제로는 그 시점에 청산돼 돌아올
       기회 자체가 없다.
    """
    r = np.asarray(list(returns), dtype=float)
    r = r[np.isfinite(r)]
    if r.size < 30:
        return RuinResult(
            float("nan"), float("nan"), float("nan"), 0, horizon, leverage,
            False,
            f"표본이 {r.size}일뿐이라 파산확률을 잴 수 없습니다 — 모르는 것을 "
            f"'안전'으로 읽지 않습니다(레버리지를 쓰려면 기록이 더 필요합니다).")

    rng = np.random.default_rng(seed)
    block = max(5, min(20, r.size // 10))          # 연속 하락을 살리는 블록 길이
    n_blocks = int(np.ceil(horizon / block))

    starts = rng.integers(0, r.size - block + 1, size=(paths, n_blocks))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :])
    sim = r[idx].reshape(paths, -1)[:, :horizon]   # (경로, 지평)

    lev = float(leverage)
    step = 1.0 + lev * sim
    # 한 스텝에 -100% 이하가 되면 그 경로는 그 자리에서 끝난다(음수 자산 금지).
    step = np.maximum(step, 0.0)
    equity = np.cumprod(step, axis=1)

    ruined = (equity <= ruin_level).any(axis=1)    # **경로 어느 지점에서든**
    prob = float(ruined.mean())
    final = equity[:, -1]
    ok = prob < RUIN_PASS
    return RuinResult(
        prob, float(np.median(final)), float(final.min()), paths, horizon, lev,
        ok,
        ("파산 위험이 기준 아래입니다" if ok else
         f"**{paths:,}번 중 {int(ruined.sum()):,}번 계좌가 사라졌습니다.** "
         f"평균이 좋아도 도중에 한 번 죽으면 그 뒤의 수익은 나에게 오지 "
         f"않습니다 — 배수를 낮추거나 레버리지를 쓰지 마세요."))


def max_leverage_by_ruin(returns, *, horizon: int = DEFAULT_HORIZON,
                         paths: int = DEFAULT_PATHS, seed: int = 0,
                         cap: float = 20.0) -> float:
    """파산확률 기준을 통과하는 **가장 큰 배수**. 없으면 1.0(레버리지 금지).

    ⚠️ 파산확률은 배수에 단조 증가한다(배수가 크면 더 자주 죽는다). 그래서
       이분법이 쓸 수 있다. 같은 seed를 써야 단조가 유지된다 — 경로가
       달라지면 잡음 때문에 뒤집힐 수 있다.
    """
    kw = dict(horizon=horizon, paths=paths, seed=seed)
    if not probability_of_ruin(returns, leverage=1.0, **kw).ok:
        return 1.0
    lo, hi = 1.0, float(cap)
    if probability_of_ruin(returns, leverage=hi, **kw).ok:
        return round(hi, 2)
    for _ in range(24):
        mid = (lo + hi) / 2
        if probability_of_ruin(returns, leverage=mid, **kw).ok:
            lo = mid
        else:
            hi = mid
    return round(lo, 2)
