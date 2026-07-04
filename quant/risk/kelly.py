"""부분 켈리(fractional Kelly) 포지션 '상한' 헬퍼 — 순수 표준 라이브러리.

켈리 공식은 승률과 손익비가 '정확히 알려진' 반복 베팅에서 장기 복리 성장률을
최대화하는 베팅 비율을 준다. 그러나 트레이딩의 승률·평균손익은 전부 백테스트
'추정치'이고, 켈리는 추정 오차에 비대칭적으로 취약하다 — 과대 베팅의 벌칙이
과소 베팅보다 훨씬 크며, 풀 켈리의 2배를 걸면 장기 성장률이 0으로 무너진다.

따라서 이 모듈의 용도는 하나뿐이다: **max_position 상한을 정하는 참고치**.
    - 풀 켈리 금물 — 관행적으로 1/4~1/2 켈리를 쓴다(fraction 파라미터).
    - 계산값이 아무리 커도 cap(기본 1.0 = 무레버리지)을 넘기지 않는다.
    - 입력이 퇴화(표본 부족·손실 없음·NaN 등)하면 0.0 — 모르면 걸지 않는다.

⚠️ 켈리 값이 크다고 엣지가 실재하는 게 아니다. 인샘플(최적화에 쓴 구간)
거래 통계를 넣으면 켈리는 그 환상을 증폭할 뿐이다 — 반드시 OOS 통계로 쓸 것.

numpy 없이 동작한다(로컬 환경에서도 테스트 가능).
"""
from __future__ import annotations

import math


def kelly_fraction(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """표준 켈리 비율 f* = (p·b − q) / b,  b = 평균이익/|평균손실|, q = 1−p.

    win_rate : 승률 p ∈ [0, 1].
    avg_win  : 평균 이익 거래 수익률 (> 0).
    avg_loss : 평균 손실 거래 수익률 — trade_stats()처럼 음수로 줘도 되고
               양의 크기로 줘도 된다(절댓값 사용).

    퇴화 입력(NaN/무한대, 승률 범위 밖, avg_win≤0, avg_loss=0)은 전부 0.0을
    반환한다 — '추정 불가'를 베팅 근거로 위장하지 않는다. 음의 엣지(f*<0)도
    0.0으로 자른다(숏 켈리가 아니라 '걸지 말라'는 뜻이다).
    """
    try:
        p = float(win_rate)
        w = float(avg_win)
        l = abs(float(avg_loss))
    except (TypeError, ValueError):
        return 0.0
    if not (math.isfinite(p) and math.isfinite(w) and math.isfinite(l)):
        return 0.0
    if not 0.0 <= p <= 1.0 or w <= 0.0 or l <= 0.0:
        return 0.0
    b = w / l
    f = (p * b - (1.0 - p)) / b
    return max(0.0, f)


def fractional_kelly_cap(stats: dict, fraction: float = 0.25, cap: float = 1.0,
                         min_trades: int = 20) -> float:
    """trade_stats() 결과에서 부분 켈리 기반 max_position '상한 제안'을 만든다.

    stats      : quant.backtest.trades.trade_stats() 반환 dict
                 (win_rate·avg_win·avg_loss·num_trades 키 사용).
    fraction   : 켈리의 몇 배를 쓸지. 기본 1/4 켈리 — 풀 켈리 금물.
    cap        : 절대 상한. 기본 1.0(자본 100%) — 레버리지를 제안하지 않는다.
    min_trades : 거래 표본이 이보다 적으면 0.0. 거래 20번의 승률은 잡음이라
                 그 위에 세운 켈리는 수학의 탈을 쓴 도박이다.

    반환값은 상한 '제안'이지 사이징 명령이 아니다. 입력 통계가 인샘플에서
    나왔다면 이 값도 그만큼 부풀려져 있다 — OOS 거래 통계로만 쓸 것.
    """
    if not isinstance(stats, dict):
        return 0.0
    try:
        n = int(stats.get("num_trades", 0))
        frac = float(fraction)
        top = float(cap)
    except (TypeError, ValueError):
        return 0.0
    if not (math.isfinite(frac) and math.isfinite(top)):
        return 0.0
    if n < max(1, int(min_trades)) or frac <= 0.0 or top <= 0.0:
        return 0.0
    f = kelly_fraction(stats.get("win_rate", 0.0), stats.get("avg_win", 0.0),
                       stats.get("avg_loss", 0.0))
    return min(top, frac * f)
