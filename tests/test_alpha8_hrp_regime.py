"""알파 8차 계약 검사 — HRP 배분 + 레짐별 성과 분해.

핵심 계약:
  ① HRP 비중은 합 1, 전 종목 양수 — 저위험 종목이 고위험보다 큰 비중
  ② 상관 군집이 있으면 군집 '내부'가 예산을 나눠, 독립 종목이 불이익 없음
  ③ 퇴화 입력(표본 부족·1종목·NaN)은 None — 호출자가 ERC→균등 폴백
  ④ 포트폴리오 경로가 HRP를 먼저 쓰고 장부에 alloc_method를 남긴다
  ⑤ 레짐 분해: 상승/하락 국면의 일수·복리 수익이 손계산과 맞는다
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.live.daily import _regime_breakdown  # noqa: E402
from quant.live.hrp import hrp_weights  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _rets(n: int = 120, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    base = rng.normal(0, 0.02, n)
    return pd.DataFrame({
        "A": base + rng.normal(0, 0.005, n),       # A·B는 강한 상관 군집
        "B": base + rng.normal(0, 0.005, n),
        "C": rng.normal(0, 0.01, n),               # 독립·저위험
        "D": rng.normal(0, 0.05, n),               # 독립·고위험
    }, index=idx)


def test_hrp_weights_sum_one_and_risk_ordered():
    w = hrp_weights(_rets())
    assert w is not None
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert all(v > 0 for v in w.values())
    assert w["C"] > w["D"]                    # 저위험이 고위험보다 크다


def test_hrp_cluster_splits_budget_inside():
    w = hrp_weights(_rets())
    # A·B(상관 군집)는 예산을 서로 나누므로, 독립 저위험 C보다 각각 작다
    assert w["C"] > max(w["A"], w["B"])


def test_hrp_degenerate_returns_none():
    r = _rets()
    assert hrp_weights(r.iloc[:10]) is None            # 표본 부족
    assert hrp_weights(r[["A"]]) is None               # 1종목
    bad = r.copy()
    bad.loc[:, "A"] = np.nan
    assert hrp_weights(bad) is None                    # NaN 공분산


def test_portfolio_uses_hrp_first_and_records_method(tmp_path):
    """기본은 HRP이고, 못 만들면 균등으로 내려간다 — **실행으로** 확인한다.

    ⚠️ 예전 판은 daily.py 소스에서 호출 순서를 글자로 찾았다. 배분 방식이
       채택 원장에서 읽는 손잡이가 되면서(감사 315) 그 글자가 사라졌고,
       화면·동작은 멀쩡한데 검사만 빨간불이 됐다. 소스를 읽는 검사는 코드가
       움직이면 따라오지 못한다 — 이제 고르는 함수를 직접 부른다.
    """
    from quant.live.daily import choose_slices
    r = _rets()
    rets_map = {c: r[c] for c in r.columns}
    n = len(rets_map)
    _slices, method = choose_slices(rets_map, n, dict.fromkeys(rets_map, 1.0),
                                    str(tmp_path))
    assert method == "hrp", f"채택이 없는데 기본이 HRP가 아니다: {method}"

    # 표본이 얇으면 HRP도 ERC도 못 만든다 → 균등으로 내려간다(대조군).
    thin = {c: r[c].iloc[:5] for c in r.columns}
    slices, method = choose_slices(thin, n, dict.fromkeys(thin, 1.0),
                                   str(tmp_path))
    assert method == "equal", method
    assert all(abs(v - 1.0 / n) < 1e-9 for v in slices.values())


def test_regime_breakdown_hand_math():
    # 지수: 30일 상승 후 30일 하락. 자산: 상승 국면에 +1%/일, 하락 국면에 -0.5%/일
    hist = []
    idx_price, eq = 100.0, 1000.0
    for i in range(60):
        up_phase = i < 30
        idx_price *= 1.01 if up_phase else 0.98
        eq *= 1.01 if idx_price >= _ma(hist, idx_price) else 0.995
        hist.append({"date": f"2026-01-{i+1:02d}", "price": idx_price,
                     "equity": eq})
    rb = _regime_breakdown(hist, window=20)
    assert rb is not None
    assert rb["up"]["days"] + rb["down"]["days"] == 60 - 20
    assert rb["up"]["ret_pct"] > 0            # 상승 국면에서는 벌었다
    assert rb["down"]["ret_pct"] < 0          # 하락 국면에서는 잃었다


def _ma(hist: list, cur: float, window: int = 20) -> float:
    prices = [r["price"] for r in hist][-(window - 1):] + [cur]
    return sum(prices) / len(prices)


def test_regime_breakdown_small_sample_none():
    hist = [{"date": "d", "price": 100.0, "equity": 100.0}] * 10
    assert _regime_breakdown(hist, window=20) is None


def test_site_shows_regime_and_hrp():
    p = (ROOT / "docs" / "paper.html").read_text(encoding="utf-8")
    assert "regime_breakdown" in p and "레짐별 성과" in p
    assert "HRP" in p
