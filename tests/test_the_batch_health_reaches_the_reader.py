"""배치가 반쯤 마비된 날에도 첫 화면은 평소와 같다 (감사 245).

새벽 배치의 부분 실패는 감사 226 이후 장부(`run_health.json`)에 남고,
`status.json`에 실려 브라우저까지 갑니다. 그런데 **화면이 한 번도 읽지
않았습니다.** 경보는 디스코드로만 갔고, 공개 장부를 보러 온 사람은 오늘
20종목 중 몇 개가 실제로 돌았는지 알 방법이 없었습니다.

    quant/live/daily.py    status["run_health"] = ...   실어 보낸다 ✅
    docs/index.html        (읽는 곳 없음)                        ❌

이 제품은 "판단·장부·코드 전부 공개"를 내걸고 있습니다. 그 화면에서
**절반이 마비된 날과 멀쩡한 날이 똑같이 보이면** 공개의 뜻이 없습니다.
감사 229(값을 계산만 하고 칸에 안 넣으면 화면에는 안 나온다)와 같은 계열
이고, 감사 139·243(만들어 놓고 배선하지 않은 장치)의 화면판입니다.

조용해야 할 때는 조용합니다 — 주말·휴장으로 전 종목이 건너뛴 날은 말하지
않습니다. 정체(stale)는 그 자체가 주말·휴장을 빼고 센 값이라(감사 243),
그것과 '실패'만 말합니다. 매일 울리는 경보는 꺼진 경보와 같습니다(감사 99).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

IDX = (ROOT / "docs" / "index.html").read_text("utf-8")


def test_the_page_reads_the_batch_health():
    """읽는 곳이 없으면 실어 보내는 일 전체가 헛수고다."""
    assert "st.run_health" in IDX, (
        "화면이 배치 건강 기록을 안 읽는다 — 절반 마비가 평범한 하루로 보인다")


def test_it_lands_in_the_warning_panel():
    """어딘가에 있는 것과 **읽는 사람 눈에 있는 것**은 다르다."""
    panel = IDX.split("const flags=[]", 1)[1].split("side-flags", 1)[0]
    assert "st.run_health" in panel, (
        "배치 건강이 '지금 켜진 경고'가 아닌 곳에 있다 — 아무도 안 본다")


def test_the_batch_still_ships_the_field():
    """화면이 읽어도 **배치가 안 실으면** 영영 빈칸이다(감사 229)."""
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert 'status["run_health"]' in src, "배치가 건강 기록을 안 실어 보낸다"


def test_the_warning_behaviour_actually_runs():
    """계약을 **실행해서** 확인한다 — 문자열 검사는 동작을 못 본다.

    값(실패 수·정체 단위·주말 침묵·이스케이프)은 전부
    `tests/run_health_flags_check.mjs`가 그 블록을 잘라 진짜로 돌려 본다.
    """
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not Path(node).exists():
        pytest.skip("node 없음 — 화면 경고 실행 검사 생략")
    r = subprocess.run([node, str(ROOT / "tests" / "run_health_flags_check.mjs")],
                       capture_output=True, text=True, cwd=str(ROOT))
    assert r.returncode == 0, (r.stdout + r.stderr)
