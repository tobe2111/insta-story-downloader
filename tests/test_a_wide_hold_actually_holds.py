"""'넓은 목록 그냥 보유'가 실제로 산다 (2026-10-12 감사 353).

추세 엔진의 무거래 밴드(2%)를 그대로 물려받아, 73종목 균등(종목당 ~1.4%)
보유는 처음 진입부터 밴드에 막혀 영영 현금이었다 — 그림자 장부 실측 10/11:
`holdw`만 투자 비중 0. 검증 시뮬레이션도 같은 규칙이라 그 후보는 '현금'으로
평가돼 선택기에 올라갔다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant.live import engine_shadow as S
from quant.portfolio import engine_select as E
from quant.portfolio import trend_core as T


def _closes(n_assets=73, days=300):
    idx = pd.bdate_range("2025-01-01", periods=days)
    rng = np.random.default_rng(1)
    data = {f"us_stock:A{i}": 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, days)))
            for i in range(n_assets)}
    return pd.DataFrame(data, index=idx)


def test_hold_band_is_smaller_than_one_equal_slice():
    closes = _closes()
    for name in ("holdw", "hold40"):
        t = E.targets_today(closes, name)
        per = max(t["weights"].values())
        assert t["band"] < per, f"{name}: 밴드 {t['band']}가 종목당 목표 {per:.4f}보다 크다 — 영영 못 산다"


def test_the_shadow_actually_buys_a_wide_hold():
    closes = _closes()
    t = E.targets_today(closes, "holdw")
    target = {k: v for k, v in t["weights"].items() if v}
    new = S.rebalance({}, target, band=t["band"])
    assert abs(sum(new.values()) - 1.0) < 1e-6, f"보유형 그림자가 안 샀다: 투자 비중 {sum(new.values())}"
    # 대조군 — 옛 밴드(2%)면 정말로 아무것도 안 산다(결함의 재현).
    assert S.rebalance({}, target, band=0.02) == {}


def test_trend_candidates_keep_their_band():
    """추세·상대 강세 후보의 밴드는 그대로다 — 검증된 회전 가정을 안 바꾼다."""
    assert E.candidate_config("xs12").band == T.BAND
    assert E.candidate_config("risk12").band == T.BAND
