"""배포판 실거래 잠금 + 판정 시계 계약 검사.

핵심 계약:
  ① 배포판 표식(_dist_build)이 있으면 실거래 진입이 SystemExit — 소스
     설치(표식 없음)에서는 아무 것도 잠기지 않는다
  ② 빌드 워크플로가 표식을 굽고, CLI 실거래 경로 3곳(live --real,
     live-daily --real, webhook --live)이 잠금을 통과한다
  ③ 판정 시계: 현재 피처셋 세대의 첫 재학습 날짜부터 관찰 일수를 세고,
     기록이 없으면 오늘=0일차 — status.json과 사이트에 표시
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.utils.dist import (  # noqa: E402
    block_live_in_distribution,
    is_distribution_build,
)

ROOT = Path(__file__).resolve().parent.parent


# ── ① 잠금 동작 ────────────────────────────────────────────────


def test_source_install_not_blocked():
    assert not is_distribution_build()         # 소스 설치에는 표식이 없다
    block_live_in_distribution()               # 예외 없이 통과


def test_distribution_build_blocks_live(monkeypatch):
    fake = types.ModuleType("quant._dist_build")
    fake.DISTRIBUTION = True
    monkeypatch.setitem(sys.modules, "quant._dist_build", fake)
    assert is_distribution_build()
    with pytest.raises(SystemExit, match="실거래 기능이 없습니다"):
        block_live_in_distribution()


# ── ② 배선 ─────────────────────────────────────────────────────


def test_build_workflow_bakes_marker_and_cli_gates():
    y = (ROOT / ".github" / "workflows" / "build-app.yml").read_text("utf-8")
    assert "_dist_build.py" in y and "DISTRIBUTION = True" in y
    c = (ROOT / "quant" / "cli.py").read_text("utf-8")
    assert c.count("block_live_in_distribution()") >= 3   # 실거래 경로 3곳


# ── ③ 판정 시계 ────────────────────────────────────────────────


def test_generation_info_from_ledger(tmp_path):
    from quant.live.daily import _generation_info
    from quant.strategies.ml import FEATURE_SET
    ledger = tmp_path / "retrain_history.jsonl"
    rows = [
        {"asof": "2026-08-01", "feature_set": "fs7:+krxflow"},   # 이전 세대
        {"asof": "2026-08-05", "feature_set": FEATURE_SET},      # 현 세대 시작
        {"asof": "2026-08-07", "feature_set": FEATURE_SET},
    ]
    ledger.write_text("\n".join(json.dumps(r) for r in rows) + "\n", "utf-8")
    g = _generation_info(str(tmp_path))
    assert g["feature_set"] == FEATURE_SET
    assert g["since"] == "2026-08-05"          # 이전 세대 날짜는 무시
    assert g["days"] >= 0 and g["target_days"] == 90


def test_generation_info_empty_ledger_is_day_zero(tmp_path):
    from quant.live.daily import _generation_info
    g = _generation_info(str(tmp_path))        # 장부 없음 → 오늘부터 0일차
    assert g is not None and g["days"] == 0


def test_wired_into_status_and_site():
    dl = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert "_generation_info" in dl and '"generation"' in dl
    p = (ROOT / "docs" / "paper.html").read_text("utf-8")
    assert "판정 시계" in p and "st.generation" in p
    assert "0일부터 다시" in p                  # 리셋 사실의 명시(착시 방지)
