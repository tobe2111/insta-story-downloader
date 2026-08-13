"""바깥에서 오는 거시 숫자의 계약 (감사 196).

`quant/data/macro.py` — FRED에서 받은 값이 ML 피처와 사이트 카드로 흘러간다.

**사이트가 깨지는 결함은 없었다.** 처음에 `"nan"`·`"inf"`가 `status.json`에
실려 브라우저의 `JSON.parse`를 깨뜨린다고 봤는데, 확인해 보니 실제 writer인
`jsonio.atomic_write_json`이 `sanitize()`로 비유한값을 `null`로 바꾼다 —
이미 검사와 변이로 지켜지고 있었다. **내 첫 실험이 `json.dumps`를 직접 불러
실제 경로를 건너뛴 것**이었다.

다만 원천에서도 막아 둔다: `float("nan")`·`float("1e400")`은 통과하므로,
그 값이 ML 피처로 흘러가면 학습·예측이 오염된다. 공개 JSON은 아래층이
막아 주지만 모델은 안 막아 준다.

곁들여 확인: `fred_frame`은 **어디서도 안 불린다**(정의·재export만). 실제
거시 피처는 `data/crossasset.py`가 만든다. 배선 안 된 부품 목록에 하나 더다
(`compare_sources`·`MultiTimeframeFilter`·`ADXFilter`…와 같은 계열).
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from quant.data.macro import (  # noqa: E402
    PUBLICATION_LAG_DAYS, _parse_fred, fred_frame, fred_series,
)


def _obs(*pairs):
    return {"observations": [{"date": d, "value": v} for d, v in pairs]}


# ── 못 쓰는 값이 통과하지 않는가 ──────────────────────────────


def test_non_finite_values_never_become_features():
    """float()는 'nan'·'inf'·'1e400'을 받아 준다 — 모델을 오염시킨다."""
    for bad in ("nan", "NaN", "inf", "-inf", "1e400"):
        s = _parse_fred(_obs(("2026-08-12", bad)))
        assert s.empty, f"{bad!r}가 피처로 흘러갔다"


def test_missing_and_malformed_rows_are_skipped():
    s = _parse_fred(_obs(("2026-08-10", "."), ("2026-08-11", ""),
                         ("나쁜날짜", "1.0"), ("2026-08-12", "글자"),
                         ("2026-08-13", "2.5")))
    assert list(s.values) == [2.5], f"망가진 행 하나가 전체를 버렸다: {list(s)}"


def test_good_values_still_get_through():
    """대조군 — 전부 걸러내면 거시 피처가 통째로 사라진다."""
    s = _parse_fred(_obs(("2026-08-11", "1.5"), ("2026-08-12", "-0.25")))
    assert list(s.values) == [1.5, -0.25]
    assert all(math.isfinite(v) for v in s.values)


def test_rows_are_sorted_by_date():
    s = _parse_fred(_obs(("2026-08-13", "3"), ("2026-08-11", "1"),
                         ("2026-08-12", "2")))
    assert list(s.values) == [1.0, 2.0, 3.0]


def test_an_empty_payload_is_an_empty_series():
    assert _parse_fred({}).empty and _parse_fred({"observations": []}).empty


# ── 룩어헤드 방지가 살아 있는가 ───────────────────────────────


def test_the_publication_lag_pushes_dates_forward(monkeypatch):
    """'그 시점에 알 수 있던 값'만 쓰게 하는 장치다(감사 181에서 확인)."""
    import quant.data.macro as M

    monkeypatch.setenv("FRED_API_KEY", "dummy")
    monkeypatch.setattr(M, "get_json",
                        lambda *a, **k: _obs(("2026-08-12", "1.5")))
    shifted = fred_series("T10Y2Y")
    raw = fred_series("T10Y2Y", lag_days=0)
    lag = PUBLICATION_LAG_DAYS["T10Y2Y"]
    assert shifted.index[-1] == raw.index[-1] + pd.Timedelta(days=lag)
    assert raw.index[-1] == pd.Timestamp("2026-08-12")


def test_no_key_means_an_empty_series_not_a_crash(monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    assert fred_series("T10Y2Y").empty


def test_a_network_failure_is_an_empty_series(monkeypatch):
    import quant.data.macro as M

    monkeypatch.setenv("FRED_API_KEY", "dummy")

    def _boom(*a, **k):
        raise RuntimeError("down")

    monkeypatch.setattr(M, "get_json", _boom)
    assert fred_series("T10Y2Y").empty


# ── 여러 시리즈를 합칠 때 미래를 끌어오지 않는가 ──────────────


def test_the_frame_only_fills_forward(monkeypatch):
    """뒤에서 앞으로 채우면(bfill) 아직 발표되지 않은 값이 과거로 샌다."""
    import quant.data.macro as M

    monkeypatch.setenv("FRED_API_KEY", "dummy")

    def _fake(url, *a, **k):
        if "AAA" in url:
            return _obs(("2026-08-10", "1"), ("2026-08-12", "3"))
        return _obs(("2026-08-11", "9"))

    monkeypatch.setattr(M, "get_json", _fake)
    df = fred_frame({"a": "AAA", "b": "BBB"}, lag_days=0)
    assert list(df.columns) == ["a", "b"]
    # b는 08-11에 처음 나온다 → 그 이전은 NaN으로 남아야 한다(뒤채움 금지)
    assert math.isnan(df.loc[pd.Timestamp("2026-08-10"), "b"]), (
        f"발표 전 날짜에 미래 값이 채워졌다:\n{df}")
    assert df.loc[pd.Timestamp("2026-08-12"), "b"] == 9.0, "전진충전이 안 된다"


def test_an_all_empty_frame_is_empty_not_an_exception(monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    assert fred_frame(["AAA", "BBB"]).empty


# ── 공개 JSON은 이미 아래층이 막는가 (확인) ───────────────────


def test_the_published_json_layer_already_neutralises_non_finite(tmp_path):
    """`_parse_fred`가 막기 전에도 사이트는 안 깨졌다 — 그 사실을 못 박는다."""
    from quant.utils.jsonio import atomic_write_json

    fp = tmp_path / "s.json"
    atomic_write_json(fp, {"v": float("nan"), "w": float("inf"), "ok": 1.5})
    text = fp.read_text(encoding="utf-8")
    assert "NaN" not in text and "Infinity" not in text, text
    assert json.loads(text) == {"v": None, "w": None, "ok": 1.5}
