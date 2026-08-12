"""붙이는 피처가 미래를 보면 백테스트가 통째로 거짓말이 된다 (감사 173).

가격 말고도 외부 맥락을 컬럼으로 붙인다 — 펀딩비(코인 포지셔닝 과열),
미결제약정, KRX 외국인·기관 수급, 공포탐욕지수. 전부 ML 피처가 되고,
스냅샷·`data_sha256`에 함께 보존돼 그날의 결정을 재현하는 근거가 된다.

이 가족에서 돈이 걸린 성질은 하나다 — **붙는 값이 그 봉 시점에 알 수
있었는가.** 하루 뒤에야 공표되는 수급을 그날 봉에 붙이면, 백테스트는
빛나는데 실전에서는 재현되지 않는다.

전수조사에서 여섯 파일을 같은 눈으로 훑었다. **결함은 못 찾았다.**

    funding.py       정산 이벤트를 '정산시각 이후 첫 봉'에 합산 — 올바르다
    openinterest.py  전진충전(ffill) 정렬만 — 과거값만 흘러온다
    krx.py           같은 방식 + z점수 클립(±4)
    sentiment.py     일자 인덱스 정렬
    synthetic.py     난수 생성기 — 시드 고정 재현성
    crosscheck.py    두 소스 비교기(현재 두 번째 소스가 없어 미사용)

다만 `attach_funding`만 **fetch 주입 인자가 없어 네트워크 없이는 검사할 수
없었다.** 형제인 `attach_open_interest`·`attach_krx_flows`는 처음부터 받고
있었다. 검사할 수 없는 코드는 검사되지 않는다 — 인자를 맞춰 두었다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.data.funding import align_funding_to_bars, attach_funding  # noqa: E402
from quant.data.krx import attach_krx_flows  # noqa: E402
from quant.data.openinterest import attach_open_interest  # noqa: E402

N = 120
IDX = pd.date_range("2024-01-01", periods=N, freq="D")
PRICE_COLS = ("open", "high", "low", "close", "volume")


def _frame(n: int = N) -> pd.DataFrame:
    c = pd.Series(100.0 + np.arange(n), index=IDX[:n])
    return pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99,
                         "close": c, "volume": 1e6}, index=c.index)


@pytest.fixture(scope="module")
def sources():
    rng = np.random.default_rng(1)
    return {
        "oi": pd.Series(rng.uniform(1e6, 2e6, N), index=IDX, name="oi"),
        "flows": pd.DataFrame({"frgn": rng.normal(0, 1e5, N),
                               "inst": rng.normal(0, 1e5, N)}, index=IDX),
        "funding": pd.Series(rng.normal(0.0, 1e-4, N * 3),
                             index=pd.date_range("2024-01-01", periods=N * 3,
                                                 freq="8h")),
    }


def _attachers(src):
    return {
        "funding": lambda d: attach_funding(d, "BTC/USDT",
                                            fetch=lambda s: src["funding"]),
        "open_interest": lambda d: attach_open_interest(
            d, "BTC/USDT", fetch=lambda s: src["oi"]),
        "krx_flows": lambda d: attach_krx_flows(
            d, "005930.KS", fetch=lambda s: src["flows"]),
    }


# ── 절단 검사: 미래가 도착해도 과거 값이 안 바뀌는가 ──────────


@pytest.mark.parametrize("name", ["funding", "open_interest", "krx_flows"])
def test_an_attached_feature_does_not_change_when_the_future_arrives(name, sources):
    fn = _attachers(sources)[name]
    full = fn(_frame())
    added = [c for c in full.columns if c not in PRICE_COLS]
    assert added, f"{name}: 붙은 컬럼이 없다 — 이 검사가 헛돈다"

    for k in (60, 90, 110):
        part = fn(_frame(k))
        for col in added:
            a = full[col].iloc[:k].to_numpy(dtype=float)
            b = part[col].to_numpy(dtype=float)
            both_nan = np.isnan(a) & np.isnan(b)
            diff = np.where(both_nan, 0.0, np.abs(a - b))
            assert np.nanmax(diff) < 1e-12, (
                f"{name}.{col}: {k}봉까지만 주면 앞부분이 달라진다 — 미래를 봤다")


@pytest.mark.parametrize("name", ["funding", "open_interest", "krx_flows"])
def test_a_failed_source_leaves_the_price_data_untouched(name, sources):
    """외부 소스가 죽어도 시세는 그대로여야 한다 — 맥락은 '있으면 쓰는' 것이다."""
    def _boom(*a, **kw):
        raise RuntimeError("소스 다운")

    broken = {
        "funding": lambda d: attach_funding(d, "X", fetch=_boom),
        "open_interest": lambda d: attach_open_interest(d, "X", fetch=_boom),
        "krx_flows": lambda d: attach_krx_flows(d, "X", fetch=_boom),
    }[name]
    df = _frame()
    out = broken(df)
    assert list(out.columns) == list(df.columns), f"{name}: 실패했는데 컬럼이 생겼다"
    assert out.equals(df), f"{name}: 실패가 시세를 건드렸다"


@pytest.mark.parametrize("name", ["funding", "open_interest", "krx_flows"])
def test_an_empty_source_is_not_an_error(name, sources):
    """빈 응답은 흔하다(신규 상장·주말) — 조용히 컬럼 없이 넘어가야 한다."""
    empty = {"funding": pd.Series(dtype=float),
             "open_interest": pd.Series(dtype=float),
             "krx_flows": pd.DataFrame()}[name]
    fn = {
        "funding": lambda d: attach_funding(d, "X", fetch=lambda s: empty),
        "open_interest": lambda d: attach_open_interest(d, "X",
                                                        fetch=lambda s: empty),
        "krx_flows": lambda d: attach_krx_flows(d, "X", fetch=lambda s: empty),
    }[name]
    df = _frame()
    assert fn(df).equals(df)


# ── 펀딩 정렬: 손으로 아는 정답 ───────────────────────────────


BARS = pd.date_range("2024-01-01", periods=4, freq="D")   # 00:00 라벨 일봉


def test_a_settlement_lands_on_the_bar_after_it_happened():
    """d0 장중에 일어난 정산이 d0 봉에 실리면 룩어헤드다."""
    ev = pd.Series([0.001, 0.002], index=[pd.Timestamp("2024-01-01 08:00"),
                                          pd.Timestamp("2024-01-01 16:00")])
    out = align_funding_to_bars(ev, BARS)
    assert float(out.iloc[0]) == 0.0, (
        "그날 장중 정산이 그날 봉에 실렸다 — 결정 시점엔 아직 모르는 값이다")
    assert float(out.iloc[1]) == pytest.approx(0.003), "다음 봉에 합산돼야 한다"


def test_settlements_in_the_same_window_are_summed():
    ev = pd.Series([0.001, 0.002, 0.004],
                   index=[pd.Timestamp("2024-01-01 08:00"),
                          pd.Timestamp("2024-01-01 16:00"),
                          pd.Timestamp("2024-01-02 00:00")])
    assert float(align_funding_to_bars(ev, BARS).iloc[1]) == pytest.approx(0.007)


def test_events_after_the_last_bar_are_dropped():
    """마지막 봉 뒤의 정산을 어딘가에 밀어 넣으면 없는 비용이 생긴다."""
    ev = pd.Series([9.9], index=[pd.Timestamp("2024-01-09")])
    assert float(align_funding_to_bars(ev, BARS).sum()) == 0.0


def test_a_broken_settlement_value_is_ignored():
    """NaN·inf가 섞여도 비용 계열을 오염시키면 안 된다."""
    ev = pd.Series([float("nan"), float("inf"), 0.002],
                   index=[pd.Timestamp("2024-01-01 08:00"),
                          pd.Timestamp("2024-01-01 09:00"),
                          pd.Timestamp("2024-01-01 10:00")])
    out = align_funding_to_bars(ev, BARS)
    assert np.isfinite(out.to_numpy()).all()
    assert float(out.iloc[1]) == pytest.approx(0.002)


def test_no_events_gives_a_zero_series_not_an_error():
    """대조군 — 현물 심볼은 펀딩이 없다. 0으로 채운 계열이어야 한다."""
    out = align_funding_to_bars(pd.Series(dtype=float), BARS)
    assert len(out) == len(BARS) and float(out.abs().sum()) == 0.0


# ── 붙은 값이 실제로 원본과 같은가 ────────────────────────────


def test_the_open_interest_uses_the_last_known_value_not_the_next_one():
    """⚠️ 촘촘한 소스로는 방향을 못 가린다.

    처음엔 봉마다 값이 있는 소스로 검사했는데, 그러면 **전진충전과 후진충전이
    같은 답**을 낸다(모든 날짜가 소스에 있으니까). 그래서 ffill을 bfill로
    바꾸는 변이가 그대로 통과했다.

    소스가 드문드문 들어올 때 비로소 갈린다. 빈 날은 **직전에 알던 값**을
    써야 하고, 다음 보고치를 끌어오면 아직 없는 정보를 쓰는 것이다.
    """
    sparse = pd.Series([10.0, 20.0, 30.0],
                       index=[IDX[0], IDX[3], IDX[6]], name="oi")
    out = attach_open_interest(_frame(9), "X", fetch=lambda s: sparse)
    got = [float(v) for v in out["oi"]]
    assert got == [10, 10, 10, 20, 20, 20, 30, 30, 30], (
        f"빈 날에 다음 보고치를 끌어왔다: {got}")


def test_the_open_interest_column_carries_the_source_values(sources):
    out = attach_open_interest(_frame(), "X", fetch=lambda s: sources["oi"])
    assert "oi" in out.columns
    assert float(out["oi"].iloc[-1]) == pytest.approx(
        float(sources["oi"].iloc[-1])), "마지막 값이 원본과 다르다"


def test_the_krx_zscore_is_clipped(sources):
    """수급 z점수가 튀면 사이징까지 흔든다 — ±4로 묶여 있어야 한다."""
    wild = pd.DataFrame({"frgn": [0.0] * 100 + [1e12] * 20,
                         "inst": [0.0] * 100 + [-1e12] * 20}, index=IDX)
    out = attach_krx_flows(_frame(), "X", fetch=lambda s: wild)
    for col in ("x_frgn5", "x_inst5"):
        v = out[col].to_numpy(dtype=float)
        v = v[np.isfinite(v)]
        assert v.size and np.abs(v).max() <= 4.0 + 1e-9, (col, np.abs(v).max())
