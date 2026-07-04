"""목적함수(objective)의 방향 정의 — grid_search와 히트맵이 공유한다.

값이 '작을수록 좋은' 지표 집합이다. 이 집합으로 탐색·시각화할 때 부호/색·최고값
방향을 뒤집어야 한다. (max_drawdown은 음수로 저장돼 클수록=0에 가까울수록 좋으므로
여기에 넣지 않는다.)

grid.py와 heatmap.py가 각자 하드코딩하면 새 지표를 추가할 때 한쪽만 고쳐 드리프트가
난다(색·★가 실제 최적과 어긋남). 단일 출처로 두어 이를 막는다. 이 모듈은 의존성 0을
유지해(pandas/numpy 미임포트) 순수 stdlib인 heatmap.py도 안전하게 임포트할 수 있다.
"""
from __future__ import annotations

LOWER_IS_BETTER = frozenset({"volatility"})
