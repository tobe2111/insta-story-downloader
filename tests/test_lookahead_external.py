"""외부 데이터 룩어헤드 계약 검사 — 그날 알 수 없던 값을 쓰지 않는다.

퀀트에서 가장 위험한 결함은 룩어헤드다: 백테스트는 훌륭한데 실전은
무너진다. 가격 유도 피처는 기존 누수 테스트가 지키므로, 여기서는 **외부에서
받아오는 값**(FRED 거시·크로스에셋)이 발표 시점을 지키는지 본다.

2026-08-11 감사 결과: 이 부분은 이미 옳게 돼 있었다(발표 시차를 인덱스에
반영, 미상 시리즈는 45일 보수 폴백, 김치 프리미엄은 진짜 이력 계산).
결함이 없었으므로 **그 상태를 계약으로 고정**한다 — 새 시리즈를 추가하면서
시차를 빠뜨리는 것이 이 계열의 전형적 재발 경로다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.data import crossasset as ca  # noqa: E402
from quant.data.macro import (  # noqa: E402
    _DEFAULT_LAG_DAYS,
    PUBLICATION_LAG_DAYS,
    fred_series,
)

ROOT = Path(__file__).resolve().parent.parent


# ── ① 발표 시차가 인덱스에 반영된다 ───────────────────────────


def test_publication_lag_shifts_the_index(monkeypatch):
    payload = {"observations": [
        {"date": "2026-08-03", "value": "4.10"},
        {"date": "2026-08-04", "value": "4.15"},
    ]}
    monkeypatch.setenv("FRED_API_KEY", "dummy")
    monkeypatch.setattr("quant.data.macro.get_json", lambda url: payload)
    s = fred_series("DGS10")
    # 기준일 08-03 값은 '발표일' 08-04에 알 수 있다
    assert s.index[0] == pd.Timestamp("2026-08-04")
    assert float(s.iloc[0]) == 4.10


def test_zero_lag_must_be_explicit(monkeypatch):
    """시차 0은 명시할 때만 — 기본값이 0이면 조용히 룩어헤드가 된다."""
    payload = {"observations": [{"date": "2026-08-03", "value": "1.0"}]}
    monkeypatch.setenv("FRED_API_KEY", "dummy")
    monkeypatch.setattr("quant.data.macro.get_json", lambda url: payload)
    assert fred_series("DGS10", lag_days=0).index[0] == pd.Timestamp("2026-08-03")
    assert fred_series("DGS10").index[0] == pd.Timestamp("2026-08-04")


def test_unknown_series_falls_back_conservatively():
    """모르는 시리즈는 보수적으로 — 늦게 쓰는 것은 안전, 일찍 쓰면 조작."""
    assert _DEFAULT_LAG_DAYS >= 30
    assert PUBLICATION_LAG_DAYS.get("__nonexistent__") is None


def test_every_used_series_has_an_explicit_lag():
    """실제로 쓰는 시리즈는 전부 표에 있어야 한다 — 45일 폴백은 정보 낭비다."""
    src = (ROOT / "quant" / "data" / "crossasset.py").read_text("utf-8")
    used = set(re.findall(r'_fred\("([A-Z0-9]+)"\)', src))
    assert used, "탐지기가 시리즈를 하나도 못 찾았다"
    missing = used - set(PUBLICATION_LAG_DAYS)
    assert not missing, f"발표 시차가 명시되지 않은 시리즈: {sorted(missing)}"


# ── ② 정렬은 과거로만 채운다 ──────────────────────────────────


def test_align_never_pulls_a_future_value():
    feature = pd.Series([1.0, 2.0],
                        index=pd.to_datetime(["2026-08-03", "2026-08-06"]))
    target = pd.to_datetime(["2026-08-03", "2026-08-04", "2026-08-05",
                             "2026-08-06"])
    out = ca._align(feature, target)
    # 08-04·08-05는 아직 08-06 값을 알 수 없다 → 08-03 값이 유지돼야 한다
    assert list(out) == [1.0, 1.0, 1.0, 2.0]


def test_align_leaves_nan_before_the_first_observation():
    feature = pd.Series([5.0], index=pd.to_datetime(["2026-08-05"]))
    out = ca._align(feature, pd.to_datetime(["2026-08-03", "2026-08-05"]))
    assert pd.isna(out.iloc[0]) and out.iloc[1] == 5.0


# ── ③ 크로스에셋은 진짜 이력이어야 한다 ───────────────────────


def test_kimchi_premium_is_a_real_series_not_a_constant(monkeypatch):
    """오늘 값 하나를 전 구간에 뿌리면 전 역사가 오염된다."""
    idx = pd.to_datetime(["2026-08-03", "2026-08-04", "2026-08-05"])

    def fake(market, symbol, limit=200, **kw):
        base = {"upbit": [1400.0, 1420.0, 1450.0],
                "crypto": [1.0, 1.0, 1.0],
                "us_stock": [1400.0, 1400.0, 1400.0]}[market]
        return pd.DataFrame({"close": base}, index=idx)

    ca._MEMO.clear()
    monkeypatch.setattr(ca, "_bench_close",
                        lambda m, s, limit=500, fetch=None: fake(m, s)["close"])
    prem = ca._kimchi_series()
    assert prem is not None and len(prem) == 3
    assert prem.nunique() > 1, "전 구간이 같은 값 — 상수 브로드캐스트 의심"
    ca._MEMO.clear()
