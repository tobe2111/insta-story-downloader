"""야간 실데이터 회귀 워크플로의 핵심 계약을 검사한다 (표준 라이브러리만).

YAML 파서(외부 의존성) 없이 텍스트 수준에서 확인한다 — 스케줄·수동 실행·
합성 폴백 가드·양 시장 검증·아티팩트 업로드가 빠지면 야간 회귀가 조용히
무의미해지므로, 그 조건들을 테스트로 고정한다.
"""
from __future__ import annotations

from pathlib import Path

_WF = (Path(__file__).resolve().parent.parent
       / ".github" / "workflows" / "nightly-validate.yml")


def _text() -> str:
    return _WF.read_text(encoding="utf-8")


def test_workflow_exists_with_schedule_and_dispatch():
    text = _text()
    assert "schedule:" in text
    assert 'cron: "0 19 * * *"' in text          # 19:00 UTC = 새벽 4시 KST
    assert "workflow_dispatch:" in text          # 수동 실행 가능


def test_workflow_guards_against_synthetic_fallback():
    """합성 폴백 가드 — 실데이터가 아니면 validate 전에 잡을 실패시킨다."""
    text = _text()
    assert "synthetic_fallback" in text
    assert "무의미" in text                       # 실데이터 없이 검증은 무의미
    # 실데이터 소스 의존성 설치
    assert "yfinance" in text and "ccxt" in text


def test_workflow_validates_both_markets_and_uploads_artifact():
    text = _text()
    assert "--market crypto" in text and "BTC/USDT" in text
    assert "--market us_stock" in text and "SPY" in text
    assert "--strategy ma_cross" in text and "--limit 800" in text
    assert "upload-artifact" in text
    assert "validate-${{ github.run_id }}" in text


def test_build_app_workflow_creates_release():
    """빌드 워크플로가 Release에 고정 이름 zip을 첨부한다(다운로드 버튼 페이지의 전제)."""
    import yaml

    w = yaml.safe_load(
        (Path(__file__).resolve().parent.parent
         / ".github" / "workflows" / "build-app.yml").read_text(encoding="utf-8"))
    on = w.get("on") or w.get(True)
    assert on["workflow_dispatch"]["inputs"]["version"]["required"]
    assert w["permissions"]["contents"] == "write"
    steps = {s.get("name"): s for s in w["jobs"]["build"]["steps"]}
    assert "Package (zip)" in steps
    rel = steps["Attach to GitHub Release"]
    assert rel["uses"].startswith("softprops/action-gh-release@")
    # 자산 이름 고정 → releases/latest/download/<asset>.zip 고정 주소 성립
    assert rel["with"]["files"] == "${{ matrix.asset }}.zip"
    assets = [m["asset"] for m in w["jobs"]["build"]["strategy"]["matrix"]["include"]]
    assert set(assets) == {"quant-cockpit-linux", "quant-cockpit-windows",
                           "quant-cockpit-macos"}


def test_download_page_uses_stable_release_urls():
    """랜딩 페이지의 버튼이 '항상 최신'을 가리키는 고정 주소를 쓴다."""
    html_text = (Path(__file__).resolve().parent.parent
                 / "docs" / "index.html").read_text(encoding="utf-8")
    for asset in ("windows", "macos", "linux"):
        assert (f"releases/latest/download/quant-cockpit-{asset}.zip"
                in html_text), asset
    assert "수익을 보장하지 않습니다" in html_text   # 정직성 고지 필수
