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
    assert 'cron: "15 20 * * *"' in text        # 20:15 UTC = 05:15 KST (감사 221)
    assert "workflow_dispatch:" in text          # 수동 실행 가능


def test_workflow_guards_against_synthetic_fallback():
    """합성 폴백 가드 — 실데이터가 아니면 validate 전에 잡을 실패시킨다."""
    text = _text()
    assert "synthetic_fallback" in text
    assert "무의미" in text                       # 실데이터 없이 검증은 무의미
    # 실데이터 소스 의존성 설치
    assert "yfinance" in text and "ccxt" in text


def test_workflow_validates_the_whole_traded_universe_and_uploads_artifact():
    """검증 범위가 운용 범위를 따라가는가.

    ⚠️ 2026-08-14 이전 이 검사는 `--market crypto`·`BTC/USDT`·`--market
    us_stock`·`SPY`가 파일 안에 있는지만 봤다. 그래서 운용이 8 → 20종목으로
    늘어도 초록이었고, 나머지 18종목은 PBO·DSR이 **한 번도 계산되지 않았다.**
    더 나쁜 건 `--strategy ma_cross`도 통과했다는 것이다 — 워크플로는 이미
    `--strategy ml`을 쓰고 있었고, 그 문자열은 "예전에는 ma_cross를 검증했다"는
    **주석**에만 남아 있었다. 주석을 읽고 초록을 준 검사였다.

    이제 실행 명령(주석이 아니라)만 보고, 목록이 코드에 있는지를 확인한다.
    """
    text = _text()
    # 셸 줄바꿈(\)으로 이어진 명령을 한 줄로 복원한다 — 안 하면 첫 줄만 보고
    # "옵션이 없다"고 오판한다.
    flat, buf = [], ""
    for ln in text.splitlines():
        stripped = ln.strip()
        if buf or stripped.startswith("python -m quant validate"):
            buf += " " + stripped.rstrip("\\").strip()
            if not stripped.endswith("\\"):
                flat.append(buf.strip())
                buf = ""
    cmds = flat
    assert cmds, "검증 실행 명령이 없다"
    joined = " ".join(cmds)
    assert "--all" in joined, (
        f"전 종목 모드가 아니다 — 일부만 검증한다: {cmds}")
    assert "--symbol" not in joined, (
        f"종목이 워크플로에 손으로 박혀 있다(다시 갈라진다): {cmds}")
    assert "--strategy ml" in joined, (
        f"실제로 굴리는 전략이 아닌 것을 검증한다: {cmds}")
    assert "--limit 800" in joined
    # 목록은 코드가 갖는다 — 운용 종목을 늘리면 검증도 따라온다
    assert "AUTO_TARGETS" in text
    assert "upload-artifact" in text
    assert "validate-${{ github.run_id }}" in text


def test_build_app_workflow_creates_release():
    """빌드 워크플로가 Release에 고정 이름 자산을 첨부한다(다운로드 버튼 페이지의 전제)."""
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
    assert "${{ matrix.asset }}.zip" in rel["with"]["files"]
    assets = [m["asset"] for m in w["jobs"]["build"]["strategy"]["matrix"]["include"]]
    assert set(assets) == {"quant-cockpit-linux", "quant-cockpit-windows",
                           "quant-cockpit-macos"}


def test_build_app_auto_releases_on_version_bump():
    """VERSION 파일이 바뀌어 main에 들어오면 자동으로 릴리스가 빌드된다."""
    import yaml

    root = Path(__file__).resolve().parent.parent
    w = yaml.safe_load(
        (root / ".github" / "workflows" / "build-app.yml").read_text(encoding="utf-8"))
    on = w.get("on") or w.get(True)
    push = on["push"]
    assert "main" in push["branches"]              # main 브랜치 푸시에서
    assert "VERSION" in push["paths"]              # VERSION 변경 시 트리거
    steps = {s.get("name"): s for s in w["jobs"]["build"]["steps"]}
    assert "Resolve version" in steps              # 버전 자동 결정 단계
    # 릴리스 태그·이름은 결정된 버전(env.APP_VERSION)을 쓴다
    rel = steps["Attach to GitHub Release"]
    assert rel["with"]["tag_name"] == "${{ env.APP_VERSION }}"
    # VERSION 파일이 존재하고 vX.Y.Z 형태다
    ver = (root / "VERSION").read_text(encoding="utf-8").strip()
    assert ver.startswith("v") and ver.count(".") >= 1, ver


def test_build_app_attaches_windows_exe():
    """Windows는 원본 .exe도 첨부한다 — 받자마자 더블클릭(압축 해제 불필요)."""
    import yaml

    w = yaml.safe_load(
        (Path(__file__).resolve().parent.parent
         / ".github" / "workflows" / "build-app.yml").read_text(encoding="utf-8"))
    steps = {s.get("name"): s for s in w["jobs"]["build"]["steps"]}
    assert "Prepare raw binary" in steps           # 원본 바이너리 준비 단계
    rel = steps["Attach to GitHub Release"]
    assert "${{ env.RAW_ASSET }}" in rel["with"]["files"]   # 원본(.exe) 자산도 첨부


def test_download_page_uses_stable_release_urls():
    """랜딩 페이지의 버튼이 '항상 최신'을 가리키는 고정 주소를 쓴다."""
    html_text = (Path(__file__).resolve().parent.parent
                 / "docs" / "index.html").read_text(encoding="utf-8")
    # Windows는 원본 .exe 직접 실행, mac/Linux는 zip
    assert "releases/latest/download/quant-cockpit-windows.exe" in html_text
    for asset in ("macos", "linux"):
        assert (f"releases/latest/download/quant-cockpit-{asset}.zip"
                in html_text), asset
    assert "수익을 보장하지 않습니다" in html_text   # 정직성 고지 필수
