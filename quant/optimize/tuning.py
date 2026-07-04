"""하이퍼파라미터 튜닝의 '정직한' 진입점 — 워크포워드 래퍼.

새 최적화 알고리즘이 아니다. 이 모듈의 존재 이유는 단 하나의 규칙을
코드로 못 박는 것이다:

    튜닝은 반드시 워크포워드 루프 '안'에서 해야 한다.

전체 데이터로 파라미터를 고른 뒤 같은 데이터로 성과를 재면(전형적 실수)
그 성과는 미래를 훔쳐본 숫자다 — 실전에서 재현되지 않는다. 여기서는 각
학습(IS) 구간 안에서만 grid_search가 돌고, 성과는 보지 않은 OOS 구간으로만
측정된다. 즉 grid_search를 직접 쓰고 싶어질 때 대신 쓰는 안전한 문이다.

⚠️ 워크포워드를 통과해도 수익은 보장되지 않는다. 과최적화 위험을 '줄일'
   뿐이며, OOS 성과가 나쁘면 그 전략은 버리는 것이 정직한 결론이다.
"""
from __future__ import annotations

from typing import Any, Sequence, Type

import pandas as pd

from quant.optimize.walkforward import walk_forward
from quant.strategies.base import Strategy

HONESTY_NOTE = (
    "하이퍼파라미터 튜닝은 각 워크포워드 학습(IS) 구간 안에서만 수행되었고, "
    "성과는 보지 않은 OOS 구간으로만 측정되었습니다. 전체 데이터로 튜닝한 뒤 "
    "같은 데이터로 성과를 재는 것은 룩어헤드이며, 이 함수는 그것을 허용하지 "
    "않습니다. OOS 성과가 나쁘면 파라미터를 더 뒤지지 말고 전략을 의심하세요."
)


def tune_and_validate(
    df: pd.DataFrame,
    strategy_cls: Type[Strategy],
    param_grid: dict[str, Sequence[Any]],
    is_window: int,
    oos_window: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """워크포워드 방식으로 튜닝+검증을 한 번에 수행한다 (walk_forward의 얇은 래퍼).

    인자와 반환은 quant.optimize.walk_forward와 동일하며(step/objective/risk/
    embargo 등은 **kwargs로 전달), 반환 dict에 'note' 키(정직성 안내문)만
    추가된다. 새 수학은 없다 — 문서화된 안전한 진입점일 뿐이다.

    반환: {oos_metrics, segments[], equity, note}
    """
    result = walk_forward(df, strategy_cls, param_grid, is_window, oos_window, **kwargs)
    return {**result, "note": HONESTY_NOTE}
