"""상태 저장 JSON 헬퍼 테스트 — NaN 안전 + 원자적 쓰기 + history 상한 (순수 stdlib)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_spec = importlib.util.spec_from_file_location(
    "jsonio", str(Path(__file__).resolve().parent.parent / "quant" / "utils" / "jsonio.py"))
jio = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(jio)


def test_sanitize_replaces_non_finite():
    out = jio.sanitize({"a": float("nan"), "b": [1.0, float("inf"), -float("inf")],
                        "c": "x", "d": 3, "e": {"f": float("nan")}})
    assert out == {"a": None, "b": [1.0, None, None], "c": "x", "d": 3, "e": {"f": None}}


def test_sanitized_dumps_is_valid_json():
    text = json.dumps(jio.sanitize({"hit": float("nan"), "e": 1.5}))
    assert "NaN" not in text and "Infinity" not in text
    assert json.loads(text) == {"hit": None, "e": 1.5}


def test_atomic_write_creates_dirs_and_is_nan_safe(tmp_path):
    p = tmp_path / "sub" / "deep" / "state.json"
    jio.atomic_write_json(p, {"hit_rate": float("nan"), "equity": 10_000.0})
    raw = p.read_text(encoding="utf-8")
    assert "NaN" not in raw                       # 브라우저 JSON.parse가 멈추지 않게
    loaded = json.loads(raw)                       # 표준 파서로 파싱 가능
    assert loaded["hit_rate"] is None and loaded["equity"] == 10_000.0
    # 임시 파일이 남지 않는다(원자적 교체)
    assert not (tmp_path / "sub" / "deep" / "state.json.tmp").exists()


def test_atomic_write_overwrites_existing(tmp_path):
    p = tmp_path / "s.json"
    jio.atomic_write_json(p, {"v": 1})
    jio.atomic_write_json(p, {"v": 2})
    assert json.loads(p.read_text())["v"] == 2


def test_cap_history():
    assert len(jio.cap_history(list(range(jio.HISTORY_CAP + 100)))) == jio.HISTORY_CAP
    short = list(range(10))
    assert jio.cap_history(short) is short        # 상한 이하는 그대로
