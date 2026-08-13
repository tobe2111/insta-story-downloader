"""재현성 매니페스트 테스트.

매니페스트 모듈 자체는 표준 라이브러리만 쓰므로 pandas 없이 실행 가능하다.
generate_report 통합 테스트만 pandas가 필요해 CI에서 실행된다(로컬에선 skip).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.utils.manifest import build_manifest, data_checksum, save_manifest


def test_data_checksum_stable_and_sensitive():
    """같은 입력 → 같은 지문, 한 값만 달라져도 다른 지문 (sha256 hex 64자)."""
    a = data_checksum("2024-01-01", "2024-12-31", 365, 100.0, 123.45)
    b = data_checksum("2024-01-01", "2024-12-31", 365, 100.0, 123.45)
    c = data_checksum("2024-01-01", "2024-12-31", 365, 100.0, 123.46)
    d = data_checksum("2024-01-01", "2024-12-31", 364, 100.0, 123.45)
    assert a == b
    assert a != c and a != d
    assert len(a) == 64 and all(ch in "0123456789abcdef" for ch in a)


def test_build_manifest_fields():
    m = build_manifest(
        {"strategy": "ma_cross", "fee": 0.001},
        {"rows": 500, "start": "2024-01-01", "end": "2025-05-15",
         "checksum": "abc123"},
        {"sharpe": 1.2, "total_return": 0.34},
        created_utc="2026-07-04T00:00:00+00:00",
    )
    assert m["created_utc"] == "2026-07-04T00:00:00+00:00"
    from quant import __version__
    assert m["quant_version"] == __version__
    assert m["python_version"]                       # 예: '3.12.x'
    assert m["config"]["strategy"] == "ma_cross"
    assert m["data"] == {"rows": 500, "start": "2024-01-01",
                         "end": "2025-05-15", "checksum": "abc123"}
    assert m["results"]["sharpe"] == 1.2


def test_build_manifest_defaults():
    """created_utc 미지정 → 현재 UTC ISO. df_meta의 빠진 키는 None으로 정직하게."""
    m = build_manifest({}, {}, {})
    assert "T" in m["created_utc"]                   # ISO 형식
    assert m["data"] == {"rows": None, "start": None, "end": None,
                         "checksum": None}


def test_save_manifest_roundtrip(tmp_path):
    p = tmp_path / "r.html.manifest.json"
    manifest = build_manifest({"k": "v"}, {"rows": 3}, {"sharpe": 0.5},
                              created_utc="2026-01-01T00:00:00+00:00")
    out = save_manifest(p, manifest)
    assert out == p and p.exists()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["config"]["k"] == "v" and data["data"]["rows"] == 3


def test_generate_report_writes_manifest(tmp_path):
    """generate_report(manifest=...)가 리포트 옆에 .manifest.json을 쓴다 (pandas 필요 — CI)."""
    import pytest
    pytest.importorskip("pandas")

    from quant.backtest import Backtester
    from quant.data import SyntheticDataProvider
    from quant.reporting import generate_report
    from quant.strategies import get_strategy

    df = SyntheticDataProvider().get_ohlcv("X", "1d", limit=200)
    res = Backtester(get_strategy("ma_cross")).run(df)
    checksum = data_checksum(str(df.index[0]), str(df.index[-1]), len(df),
                             float(df["close"].iloc[0]),
                             float(df["close"].iloc[-1]))
    manifest = build_manifest(
        {"strategy": "ma_cross", "market": "synthetic"},
        {"rows": len(df), "start": str(df.index[0]), "end": str(df.index[-1]),
         "checksum": checksum},
        {"sharpe": res.metrics.sharpe},
    )
    out = generate_report(res, tmp_path / "r.html", manifest=manifest)
    mp = tmp_path / "r.html.manifest.json"
    assert out.exists() and mp.exists()
    saved = json.loads(mp.read_text(encoding="utf-8"))
    assert saved["config"]["strategy"] == "ma_cross"
    assert saved["data"]["rows"] == len(df)
    assert saved["data"]["checksum"] == checksum


def test_generate_report_without_manifest_writes_nothing_extra(tmp_path):
    """manifest 기본값(None)이면 기존 동작 그대로 — 추가 파일 없음 (pandas 필요 — CI)."""
    import pytest
    pytest.importorskip("pandas")

    from quant.backtest import Backtester
    from quant.data import SyntheticDataProvider
    from quant.reporting import generate_report
    from quant.strategies import get_strategy

    df = SyntheticDataProvider().get_ohlcv("X", "1d", limit=150)
    res = Backtester(get_strategy("rsi")).run(df)
    generate_report(res, tmp_path / "plain.html")
    assert not list(tmp_path.glob("*.manifest.json"))


# ── 지문이 라이브러리 버전에 흔들리지 않는가 (감사 207) ───────────
#
# `data_checksum`은 *"그때 그 샤프가 왜 지금 재현이 안 되지?"*를 추적하려고
# 있다. 그런데 값을 `repr(v)`로 적어서, **자기 지문이 numpy 버전에 따라
# 달라졌다**:
#
#     float      repr → '100.0'
#     np.float64 repr → 'np.float64(100.0)'      (numpy 1.x에서는 '100.0')
#
# pandas에서 꺼낸 종가는 `np.float64`다. 즉 numpy를 올리는 것만으로 같은
# 데이터의 지문이 바뀌고, 재현 실패를 추적하라고 만든 도구가 "데이터가
# 바뀌었다"는 거짓 신호를 낸다.
#
# 이 함수의 독스트링은 **인덱스에 대해서는 그 위험을 이미 알고 있었다**
# ("인덱스는 str()로 넘기면 라이브러리 버전에 따른 repr 차이를 피할 수
# 있다"). 같은 위험이 종가에도 있는데 거기만 적혀 있었다 — 감사 200과 같은
# 형태다: 무엇을 막는다고 적었으면 그 무엇이 지나는 문을 전부 셀 것.
#
# ⚠️ `data_checksum`은 지금 아무 데서도 안 불린다(배선 안 된 부품).
#    live 결함이 아니라 공개 API의 구멍으로 적는다.


def test_the_fingerprint_does_not_depend_on_the_numeric_type():
    import numpy as np
    import pandas as pd

    from quant.utils.manifest import data_checksum

    df = pd.DataFrame({"close": [100.0, 150.0]},
                      index=pd.to_datetime(["2025-01-01", "2025-12-31"]))
    raw = data_checksum(str(df.index[0]), str(df.index[-1]), len(df),
                        df["close"].iloc[0], df["close"].iloc[-1])
    wrapped = data_checksum(str(df.index[0]), str(df.index[-1]), len(df),
                            float(df["close"].iloc[0]),
                            float(df["close"].iloc[-1]))
    assert raw == wrapped, "pandas 값과 float()가 다른 지문을 낸다"

    as_int = data_checksum(str(df.index[0]), str(df.index[-1]), 2, 100, 150)
    assert raw == as_int, "100 과 100.0 이 다른 지문을 낸다"
    assert raw == data_checksum(str(df.index[0]), str(df.index[-1]), 2,
                                np.float32(100.0), np.float32(150.0))


def test_the_fingerprint_still_changes_when_the_data_changes():
    """대조군 — 값이 진짜 다르면 지문도 달라야 한다.

    이게 없으면 위 검사는 "무엇이든 같은 지문을 내는" 구현도 통과시키고,
    그러면 이 도구가 하는 일이 없어진다.
    """
    from quant.utils.manifest import data_checksum

    base = data_checksum("2025-01-01", "2025-12-31", 2, 100.0, 150.0)
    assert base != data_checksum("2025-01-01", "2025-12-31", 2, 100.0, 150.01)
    assert base != data_checksum("2025-01-01", "2025-12-31", 3, 100.0, 150.0)
    assert base != data_checksum("2025-01-02", "2025-12-31", 2, 100.0, 150.0)
    assert base != data_checksum("2025-01-01", "2025-12-30", 2, 100.0, 150.0)


def test_a_missing_value_is_stable_too():
    """경계 — None·NaN도 매번 같은 글자여야 한다(지문이 흔들리면 안 된다)."""
    from quant.utils.manifest import data_checksum

    nan = float("nan")
    a = data_checksum("s", "e", 1, nan, None)
    b = data_checksum("s", "e", 1, nan, None)
    assert a == b, "같은 입력인데 지문이 매번 달라진다"
    assert a != data_checksum("s", "e", 1, 0.0, None), "NaN과 0을 같게 봤다"
