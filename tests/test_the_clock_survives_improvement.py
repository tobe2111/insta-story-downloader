"""판정 시계 수정 공지(2026-08-18) — 개선해도 시계는 리셋되지 않는다.

사장님 결정: "앞으로는 리셋하지 말고 모두 개선해줘. 개선하는 것도 과정이니까."
측정 대상을 '얼어붙은 전략'에서 '개선하는 과정 전체'로 재선언했다.

지켜야 할 약속(리셋을 대신하는 정직 장치):
- 시계는 계좌 탄생일(STRUCTURE_EPOCH)부터 **연속**으로 흐른다.
- 시계가 도는 동안의 구조 변경은 **버전 이력(versions)**으로 날짜와 함께
  공개된다 — 조용히 사라지면 리셋보다 나쁘다.
- 수정 공지(amended)가 날짜·내용·이유와 함께 실린다.
- 엣지 입증 관문(90일 + 윌슨 하한)은 그대로다 — 시계가 연속이 됐다고
  판정이 후해지는 것이 아니다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.daily import (                     # noqa: E402
    JUDGEMENT_AMENDED, STRUCTURE_EPOCH, _generation_info)


def _history(tmp_path, rows):
    (tmp_path / "retrain_history.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", "utf-8")


def test_a_later_feature_declaration_becomes_a_version_not_a_reset(tmp_path):
    """피처 선언이 계좌 탄생 뒤에 바뀌면 — 시계는 그대로, 이력에 남는다."""
    from quant.strategies.ml import FEATURE_SET
    _history(tmp_path, [
        {"asof": "2026-08-16", "feature_set": FEATURE_SET},
        {"asof": "2026-08-17", "feature_set": FEATURE_SET},
    ])
    g = _generation_info(str(tmp_path))
    assert g["since"] == STRUCTURE_EPOCH, (
        f"시계가 리셋됐다 — since={g['since']} (탄생일 {STRUCTURE_EPOCH}이어야)")
    axes = [v["axis"] for v in g["versions"]]
    assert "피처 선언" in axes, "변경이 이력에서 사라졌다 — 리셋보다 나쁘다"
    ver = next(v for v in g["versions"] if v["axis"] == "피처 선언")
    assert ver["on"] == "2026-08-16", "이력의 날짜가 실제 변경일이 아니다"


def test_the_amendment_notice_travels_with_the_clock(tmp_path):
    _history(tmp_path, [])
    g = _generation_info(str(tmp_path))
    assert g["amended"] is JUDGEMENT_AMENDED
    assert g["amended"]["on"] == "2026-08-18"
    assert "리셋" in g["amended"]["what"] and "과정" in g["amended"]["why"]


def test_days_count_from_inception_continuously(tmp_path):
    import datetime as dt
    _history(tmp_path, [])
    g = _generation_info(str(tmp_path))
    expect = (dt.date.today() - dt.date.fromisoformat(STRUCTURE_EPOCH)).days
    assert g["days"] == expect, (
        f"연속 시계가 아니다 — {g['days']}일 (탄생 후 {expect}일이어야)")


def test_the_edge_gate_is_not_loosened():
    """시계가 연속이 됐어도 '90일 + 윌슨 하한' 관문은 그대로다."""
    src = (ROOT / "quant" / "risk" / "portfolio_vol.py").read_text("utf-8")
    assert 'gen["days"] < gen["target_days"]' in src, "90일 관문이 사라졌다"
    assert "_wilson_ci" in src, "윌슨 신뢰구간 관문이 사라졌다"
    assert "개선" in src, "진행 중 문구가 개선 이력을 말하지 않는다"


def test_the_site_shows_the_amendment_and_history():
    html = (ROOT / "docs" / "index.html").read_text("utf-8")
    assert "리셋하지 않습니다" in html, "첫 화면 판정 시계에 수정 공지가 없다"
    assert "g.versions" in html, "변경 이력이 화면에 연결되지 않았다"
    trust = (ROOT / "docs" / "trust.html").read_text("utf-8")
    assert "판정 시계의 규칙을 바꿨습니다" in trust, (
        "신뢰 페이지에 수정 공지가 없다 — 조용한 규칙 변경은 골대 이동으로 "
        "읽힌다")


def test_status_json_carries_versions(tmp_path):
    """사이트 재료(status.json)에 연속 시계·이력·공지가 실린다."""
    from quant.live.daily import write_docs_status
    _history(tmp_path, [])
    docs = tmp_path / "status.json"
    st = write_docs_status(str(tmp_path), docs_path=str(docs))
    g = st.get("generation")
    assert g and "versions" in g and g["amended"]["on"] == "2026-08-18"
