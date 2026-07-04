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
