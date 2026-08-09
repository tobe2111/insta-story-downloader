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


def test_build_workflow_has_e2e_smoke_steps():
    """빌드 로그 echo가 아니라 '실행'으로 잠금을 검증하는 스모크 2단계."""
    y = (ROOT / ".github" / "workflows" / "build-app.yml").read_text("utf-8")
    # ① 소스+표식: 실거래 경로 3곳을 진짜 실행해 비정상 종료를 요구
    assert "expect_block python -m quant live-daily --real" in y
    assert "expect_block python -m quant live --real" in y
    assert "expect_block python -m quant webhook --live" in y
    # ② 빌드 산출물: 실행파일을 QUANT_SMOKE 모드로 돌려 표식·잠금 확인
    assert "QUANT_SMOKE" in y
    assert "dist_marker=1" in y and "live_block=1" in y
    s = (ROOT / "start.py").read_text("utf-8")
    assert "QUANT_SMOKE" in s and "_smoke_check" in s


def test_e2e_marker_blocks_cli_subprocess():
    """임시 표식을 굽고 실제 CLI 서브프로세스가 죽는지 — 로컬판 E2E."""
    import subprocess
    marker = ROOT / "quant" / "_dist_build.py"
    assert not marker.exists()      # 소스 설치가 오염돼 있으면 그 자체가 사고
    try:
        marker.write_text("DISTRIBUTION = True\n", "utf-8")
        r = subprocess.run(
            [sys.executable, "-m", "quant", "live-daily", "--real"],
            capture_output=True, text=True, cwd=ROOT, timeout=120)
        assert r.returncode != 0
        assert "실거래 기능이 없습니다" in (r.stdout + r.stderr)
    finally:
        marker.unlink(missing_ok=True)
        for pyc in (ROOT / "quant" / "__pycache__").glob("_dist_build*"):
            pyc.unlink(missing_ok=True)


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


def test_generation_archive_splits_prev_and_current():
    """세대 경계로 기록을 갈라 구간별 일수·TWR을 분리한다(착시 제거)."""
    from quant.live.daily import _generation_archive
    state = {
        "start_cash": 100.0,
        "deposits": [{"date": "2026-08-02", "amount": 50.0},
                     {"date": "2026-08-06", "amount": 30.0}],
        "history": [
            {"date": "2026-08-01", "equity": 100.0},
            {"date": "2026-08-02", "equity": 160.0},   # +50 입금 → 운용 +10%
            {"date": "2026-08-04", "equity": 160.0},   # 이전 세대 끝
            {"date": "2026-08-05", "equity": 168.0},   # 현 세대 시작 +5%
            {"date": "2026-08-06", "equity": 198.0},   # +30 입금 → 운용 0%
        ],
    }
    a = _generation_archive(state, "2026-08-05")
    assert a["prev_days"] == 3 and a["cur_days"] == 2
    assert a["prev_twr_pct"] == pytest.approx(10.0, abs=0.1)
    assert a["cur_twr_pct"] == pytest.approx(5.0, abs=0.1)


def test_generation_archive_none_when_all_current():
    from quant.live.daily import _generation_archive
    state = {"start_cash": 100.0, "deposits": [],
             "history": [{"date": "2026-08-05", "equity": 101.0}]}
    assert _generation_archive(state, "2026-08-01") is None


def test_wired_into_status_and_site():
    dl = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert "_generation_info" in dl and '"generation"' in dl
    assert "_generation_archive" in dl and '"archive"' in dl
    p = (ROOT / "docs" / "paper.html").read_text("utf-8")
    assert "판정 시계" in p and "st.generation" in p
    assert "0일부터 다시" in p                  # 리셋 사실의 명시(착시 방지)
    assert "이전 구조" in p and "g.archive" in p  # 세대별 아카이브 분리 표시
    assert "구조 교체" in p                     # 차트의 세대 경계 마커
