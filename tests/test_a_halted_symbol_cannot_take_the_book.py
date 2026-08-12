"""거래정지 종목이 **포트폴리오를 통째로 가져가면 안 된다** (감사 149).

역분산·ERC·HRP는 전부 "분모(변동성)가 작을수록 많이 산다". 그러면 분모가
사실상 0인 종목이 나타났을 때 무슨 일이 생기는가.

    s0~s3  분산 1.0e-04  → 역분산 1.2e+04
    HALT   분산 1.2e-38  → 역분산 8.5e+37     ← 정확히 0이 아니다
    ────────────────────────────────────────
    HALT 비중 1.000                            포트폴리오 전부

`np.isfinite`로 막고 있었는데 **8.5e37은 유한하다.** 감사 146(샤프의 분모)과
같은 병이 이번엔 **배분의 분모**에 있었다. 거래정지, 고정 시세, 상장 직후,
휴장일로 채워진 계열 — 전부 이 모양이 된다.

두 겹으로 막는다.

    ① 퇴화 판정   그 패널 최대 분산에 견주어 무시할 만큼 작은 열은 뺀다.
                  ⚠️ 키를 지우면 안 된다 — 호출 쪽이 `slices.get(key, 1/n)`
                     이라 **빠진 키가 오히려 기본 슬라이스를 받는다.** 0으로 남긴다.
    ② 과집중 상한 균등가중의 3배. 실거래 경로(_erc_slices·_hrp_slices)는
                  이미 이 상한을 쓰고 있었는데 **오디션이 쓰는
                  portfolio/allocation.py에만 없었다.**

②가 필요한 이유: 30일에 딱 한 번 1틱 움직이는 저유동 종목은 부동소수
문제가 아니라 **진짜로 분산이 작다.** 퇴화 판정으로는 안 걸리고, 걸려서도
안 된다. 그건 상한이 막을 일이다(실측 0.997 → 0.600).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import quant.portfolio.allocation as A  # noqa: E402
from quant.live.daily import _erc_slices, _hrp_slices  # noqa: E402
from quant.live.hrp import hrp_weights  # noqa: E402

N = 200
IDX = pd.date_range("2025-01-01", periods=N, freq="D")
NORMAL = ["s0", "s1", "s2", "s3"]


def _panel(halt: np.ndarray | None) -> pd.DataFrame:
    """정상 4종 + 문제 종목 하나."""
    rng = np.random.default_rng(1)
    df = pd.DataFrame({c: rng.normal(0, 0.01, N) for c in NORMAL}, index=IDX)
    if halt is not None:
        df["HALT"] = halt
    return df


def _mmf() -> np.ndarray:
    """매일 정확히 +0.005%씩 오르는 상품(예금형·MMF형 ETF)의 일간 수익률.

    ⚠️ 처음엔 `np.zeros(N)`(수익률 전부 0)으로 검사를 썼는데 **잡히지 않았다.**
       전부 정확히 0이면 분산도 정확히 0이라 옛 가드(`isfinite`)가 이미 막는다.
       진짜 위험한 건 **0이 아닌 상수**다 — 부동소수 상쇄로 분산이 0이 아니라
       1e-41 언저리로 나오고, 그건 유한해서 가드를 그대로 통과한다.

       그리고 이건 가공의 입력이 아니다. 가격이 매일 같은 비율로 오르는
       상품의 pct_change가 정확히 이 모양이다 — 고유값 3개, 표준편차 9.2e-17.
       예금형 ETF·MMF·고정 배당 상품이 전부 여기 해당한다.

           역분산   1 / 4.6e-41 = 2.2e+40   → 비중 1.000 (상한 없으면)
           역변동성 1 / 9.2e-17 = 1.1e+16   → 비중 1.000 (상한 없으면)
    """
    price = 100.0 * (1.00005 ** np.arange(N + 1))
    return (price[1:] / price[:-1] - 1.0)


FROZEN = _mmf()                                        # 상수 수익 (분산 1e-41)
ILLIQUID = np.where(np.arange(N) % 30 == 0, 5e-5, 0.0)  # 30일에 1틱


def _sig(df):
    return pd.DataFrame(1.0, index=df.index, columns=df.columns)


# ── ① 완전히 고정된 종목은 예산을 못 받는다 ───────────────────


def test_a_frozen_symbol_gets_nothing_from_inverse_variance():
    df = _panel(FROZEN)
    got = float(A._inv_var_weights(df.cov())["HALT"])
    assert got == 0.0, (
        f"거래정지 종목이 역분산 비중 {got:.4f}를 받는다 — 분산 1e-38을 "
        "'가장 안전한 자산'으로 읽고 있다")


def test_a_frozen_symbol_gets_nothing_from_any_allocator():
    df = _panel(FROZEN)
    rets = {c: df[c] for c in df.columns}
    checks = {
        "inverse_vol": float(A.inverse_vol(df, _sig(df), window=30)["HALT"].max()),
        "allocation.hrp": float(A.hrp(df, _sig(df), window=60).iloc[-1]["HALT"]),
        "live _hrp_slices": float((_hrp_slices(rets, 5) or {}).get("HALT", 0.0)),
        "live _erc_slices": float((_erc_slices(rets, 5) or {}).get("HALT", 0.0)),
        "live hrp_weights": float((hrp_weights(df) or {}).get("HALT", 0.0)),
    }
    bad = {k: v for k, v in checks.items() if v > 1e-9}
    assert not bad, f"거래정지 종목에 예산을 주는 배분기: {bad}"

    # 대조군 — 위 검사만 있으면 '전 종목 비중 0'인 코드로도 통과한다(0 == 0).
    # 실제로 변이 시험에서 그 상태가 나왔고 이 검사가 없어서 놓쳤다.
    normal = {
        "inverse_vol": A.inverse_vol(df, _sig(df), window=30).iloc[-1],
        "allocation.hrp": A.hrp(df, _sig(df), window=60).iloc[-1],
    }
    for name, row in normal.items():
        assert abs(float(row[NORMAL].sum()) - 1.0) < 1e-9, (
            f"{name}: 정상 4종의 비중 합이 {float(row[NORMAL].sum()):.6f} — "
            "퇴화 종목을 빼면서 나머지까지 지웠다")
    for name, out in (("live _hrp_slices", _hrp_slices(rets, 5)),
                      ("live _erc_slices", _erc_slices(rets, 5)),
                      ("live hrp_weights", hrp_weights(df))):
        assert out is not None, f"{name}: 배분이 통째로 실패했다"
        assert sum(out[c] for c in NORMAL) > 0.5, (
            f"{name}: 정상 종목 몫이 {sum(out[c] for c in NORMAL):.4f}뿐이다")


def test_the_dropped_symbol_keeps_its_key():
    """⚠️ 키를 지우면 **더 나빠진다.**

    호출 쪽은 `slices.get(key, 1.0 / n)`이다 — 키가 없으면 기본 슬라이스를
    준다. 즉 '빼는 것'이 '균등 배분해 주는 것'이 된다. 반드시 0으로 남긴다.
    """
    df = _panel(FROZEN)
    rets = {c: df[c] for c in df.columns}
    for name, out in (("_hrp_slices", _hrp_slices(rets, 5)),
                      ("_erc_slices", _erc_slices(rets, 5)),
                      ("hrp_weights", hrp_weights(df))):
        assert out is not None, f"{name}이 통째로 실패했다 — 전제가 깨졌다"
        assert "HALT" in out, (
            f"{name}이 퇴화 종목의 키를 지웠다 — 호출자가 기본 1/n을 준다")


# ── ② 진짜로 변동성이 낮은 종목은 상한이 막는다 ───────────────


def test_a_genuinely_quiet_symbol_is_capped_not_erased():
    """저유동 종목은 퇴화가 아니다 — 많이 받되 전부는 못 받는다."""
    df = _panel(ILLIQUID)
    rets = {c: df[c] for c in df.columns}
    cap = A.MAX_CONCENTRATION / 5          # 5종목 → 0.6
    got = {
        "inverse_vol": float(A.inverse_vol(df, _sig(df), window=30)["HALT"].max()),
        "allocation.hrp": float(A.hrp(df, _sig(df), window=60).iloc[-1]["HALT"]),
        "live _hrp_slices": float((_hrp_slices(rets, 5) or {})["HALT"]),
        "live _erc_slices": float((_erc_slices(rets, 5) or {})["HALT"]),
    }
    for name, v in got.items():
        assert v <= cap + 1e-9, (
            f"{name}: 저유동 종목이 {v:.4f} — 상한 {cap:.2f}를 넘는다")
        assert v > 0.05, (
            f"{name}: 저유동 종목이 {v:.4f}로 사실상 지워졌다 — 가드가 덫이 됐다")


def test_the_cap_matches_the_live_path():
    """오디션과 실거래가 다른 상한을 쓰면 승격된 전략이 실전에서 다르게 돈다."""
    assert A.MAX_CONCENTRATION == 3.0, (
        "실거래 경로(_erc_slices·_hrp_slices)가 쓰는 3/n과 어긋났다")


def test_capping_redistributes_instead_of_shrinking():
    """잘라낸 몫은 버리지 않고 나눠 준다 — 버리면 총 노출이 조용히 준다."""
    w = A._cap_concentration(np.array([0.90, 0.04, 0.03, 0.03]))
    assert abs(w.sum() - 1.0) < 1e-9, f"합이 {w.sum():.6f} — 노출이 새어 나갔다"
    assert w[0] <= 3.0 / 4 + 1e-9
    assert w[1] > 0.04, "잘라낸 몫이 나머지에게 가지 않았다"


# ── 대조군 — 정상 패널을 망가뜨리지 않았는가 ──────────────────


def test_a_normal_panel_is_unchanged():
    df = _panel(None)
    w = A.inverse_vol(df, _sig(df), window=30).iloc[-1]
    assert abs(w.sum() - 1.0) < 1e-9, f"정상 패널의 비중 합이 {w.sum():.6f}"
    assert w.min() > 0.15 and w.max() < 0.35, (
        f"정상 4종의 배분이 흔들렸다: {w.round(4).to_dict()}")

    rets = {c: df[c] for c in df.columns}
    for name, out in (("_erc_slices", _erc_slices(rets, 4)),
                      ("_hrp_slices", _hrp_slices(rets, 4))):
        assert out and len(out) == 4, f"{name}: {out}"
        assert all(v > 0.1 for v in out.values()), f"{name}: {out}"
