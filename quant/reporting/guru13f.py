"""저명 투자자 13F — 모든 공개 페이지가 같은 칸을 읽도록 한 곳에서 모은다.

사장님 지시(2026-10-01): *"13F 관련 내용도 홈페이지 각 페이지들에 보여야 해."*

그때까지 13F는 미국 장중 페이지 하나에만 떠 있었고, 그마저 **비어 있었다**
— EDGAR가 429(요청 과다)로 막아 이력이 0점이었는데 화면은 그 사실을 말하지
않았다(감사 331). 그래서 이 블록은 내용만큼 **수집 상태**를 함께 싣는다.
빈 칸이 "아무도 안 샀다"인지 "못 받았다"인지 읽는 사람이 구별해야 한다.

페이지마다 따로 계산하지 않는다 — 배치가 status.json의 `guru13f` 한 칸에
싣고, 화면(assets/guru13f.js)은 읽기만 한다.
"""
from __future__ import annotations

import json
import os

# 13F가 이 제품에서 실제로 쓰이는 자리 — 코드와 같은 말을 한다.
USES = [
    {"where": "미국주식 ML 모델",
     "how": "입력 재료 하나로 들어간다(겹친 투자자 수). 쓸지 뺄지는 밤 "
            "오디션이 성적으로 정한다 — 사람이 '꼭 써라'라고 정하지 않는다."},
    {"where": "미국주식 장중 실험",
     "how": "모델이 이미 사겠다고 한 종목만 비중을 키운다. 관망을 매수로 "
            "바꾸지 않는다. 키우는 폭은 기계가 과거 기록으로 정한다."},
]


def _read(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, ValueError):
        return {}


def guru13f_public(state_dir: str = "state") -> dict:
    from quant.data.thirteenf import CACHE_FILE, FILERS, load_fetch_report
    from quant.live.thirteenf_overlay import NEUTRAL_BONUS, cluster_public
    from quant.live.thirteenf_tune import STRENGTH_FILE

    snap = _read(os.path.join(state_dir, CACHE_FILE))
    block = cluster_public(snap)
    rep = load_fetch_report(state_dir)
    st = _read(os.path.join(state_dir, STRENGTH_FILE))
    try:
        strength = float(st.get("strength", NEUTRAL_BONUS))
    except (TypeError, ValueError):
        strength = NEUTRAL_BONUS
    filers = rep["filers"] or [{"cik": c, "name": n, "filings": 0, "filed": None,
                                "report": None, "holds": []}
                               for c, n in FILERS.items()]
    return {
        **block,
        "filers": filers,
        "fetch": rep["fetch"],
        "history_points": rep["points"],
        "strength_pct": round(strength * 100),
        "strength_why": ((st.get("evidence") or {}).get("why")),
        "uses": USES,
    }
