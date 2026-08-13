"""차트 축 범위 계산 — **한 곳에서만** (감사 213).

무엇이 있었나: 곡선을 그리는 코드가 전부 이렇게 시작했다.

    lo, hi = float(vals.min()), float(vals.max())
    rng = hi - lo or 1.0

`or 1.0`은 "위아래가 같으면(평평하면) 0으로 나누지 말자"는 가드다. 그
의도는 맞다. 그런데 **NaN은 참이라서 그대로 통과한다** — numpy의 `min`은
NaN을 만나면 NaN을 내므로, 값 하나만 결측이면 lo·hi·rng가 전부 NaN이 되고
좌표가 이렇게 찍힌다:

    <polygon points="0,200 0.0,nan 266.7,nan 533.3,nan 800.0,nan 800,200"

차트가 **조용히 사라진다.** 오류도 없고 빈 그림도 아니다 — 브라우저가
말이 안 되는 좌표를 그냥 무시할 뿐이라, 보는 사람은 "오늘은 데이터가
없나 보다"라고 생각한다. 이 저장소에서 반복해 나온 두 교훈이 겹친 자리다:

  · 가드가 있다는 것이 막힌다는 뜻은 아니다 (감사 183·198·209)
  · `A or B`에서 A가 숫자면 0·NaN에서 뜻이 달라진다 (감사 183·195·205)

같은 두 줄이 **일곱 곳**에 복사돼 있었다(html_report 3 · validation_report 2
· dashboard 1 · heatmap 1). 그래서 한 곳을 고쳐도 나머지가 계속 무너진다.
계산을 여기 하나로 모은다.
"""

from __future__ import annotations

import math
from collections.abc import Iterable


def finite(values: Iterable) -> list[float]:
    """그릴 수 있는 값만 — NaN·inf는 뺀다."""
    out = []
    for v in values:
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if math.isfinite(f):
            out.append(f)
    return out


def plot_points(values: Iterable, width: float, height: float,
                lo: float, rng: float) -> list[tuple[float, float]]:
    """(x, y) 좌표 — **결측 봉은 건너뛴다.**

    범위(lo·rng)만 고쳐서는 부족하다. 좌표를 만드는 자리가 결측값을 그대로
    계산하면 그 점 하나가 `nan,nan`이 되고, 브라우저는 그 폴리라인을 통째로
    버린다 — 결국 차트가 사라지는 것은 똑같다. 실측으로 확인한 자리다.

    건너뛴 점은 선이 이어져 지나간다. 없는 값을 0이나 직전 값으로 채우지
    않는다 — 채우면 '그날 폭락' 또는 '그날 변화 없음'이라는 없던 사실이
    그림에 생긴다.
    """
    vals = list(values)
    n = len(vals)
    if n < 2:
        return []
    out = []
    for i, v in enumerate(vals):
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(f):
            continue
        out.append((i / (n - 1) * width, height - (f - lo) / rng * height))
    return out


def axis_span(values: Iterable) -> tuple[float, float, float] | None:
    """(lo, hi, rng) — 그릴 값이 없으면 **None**.

    None은 "그릴 수 없다"는 뜻이고, 부르는 쪽은 빈 그림을 내야 한다.
    억지로 0이나 1을 돌려주면 평평한 가짜 선이 그려지는데, 그건 없는
    데이터를 있는 것처럼 보이게 하는 것이라 더 나쁘다.

    rng은 항상 유한하고 0보다 크다 — 평평한 계열(hi == lo)은 1.0으로 둔다.
    """
    vals = finite(values)
    if not vals:
        return None
    lo, hi = min(vals), max(vals)
    rng = hi - lo
    if not math.isfinite(rng) or rng <= 0:
        rng = 1.0
    return lo, hi, rng
