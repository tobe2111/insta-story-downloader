"""화면 계약 검사가 **정말로 도는가** (감사 278).

⚠️ 이 저장소가 이미 두 번 걸린 병이다.

  · `verify` 명령은 처음부터 있었지만 **어떤 워크플로도 실행하지 않았다.**
    사이트가 "누구든 검증할 수 있다"고 말하는 동안 그 검증은 한 번도
    돌아본 적이 없었다.
  · `scripts/mutation_check.py`는 121개 항목을 쌓을 때까지 **아무도 안
    돌렸다.** 다른 모든 안전장치를 지키는 도구가 정작 무방비였다.

2026-08-17에 세 번째가 나왔다. 공개 페이지가 진짜로 그려지는가를 보는
검사가 일곱 파일에 있었는데, 브라우저를 받는 워크플로가 하나도 없었다.
그래서 그 검사들은 CI에서 매번 **조용히 건너뛰었고**, 야간 변이 전수가
놓친 21건 중 **16건**이 그 자리였다 — 첫 화면·잔고·금액·보유 대비 성적,
전부 사장님이 직접 지적해서 고친 자리다.

돌지 않는 검사는 깨져도 아무도 모르고, 깨진 줄 모르는 검사는 장식이다.
그래서 여기서는 검사가 아니라 **검사가 도는 조건**을 지킨다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _browser import chrome_exe  # noqa: E402

WF = ROOT / ".github" / "workflows"
TESTS = ROOT / "tests"

# 브라우저를 띄우는 검사가 도는 워크플로 — 여기에 브라우저가 없으면
# 그 계약은 아무도 안 지킨다.
BROWSER_JOBS = ("ci.yml", "mutation-sweep.yml")


def _browser_tests() -> list[Path]:
    return sorted(p for p in TESTS.glob("test_*.py")
                  if "sync_playwright" in p.read_text("utf-8"))


def test_there_really_are_browser_tests_to_protect():
    """전제 고정 — 대상이 사라지면 아래 검사는 아무것도 안 지킨다."""
    got = _browser_tests()
    assert len(got) >= 5, (
        f"브라우저를 띄우는 검사가 {len(got)}개뿐이다 — 공개 페이지 계약이 "
        "줄었거나 이 검사가 낡았다")


@pytest.mark.parametrize("name", BROWSER_JOBS)
def test_the_workflow_downloads_a_browser(name):
    """패키지만 깔면 안 된다 — 브라우저 본체는 따로 받아야 한다."""
    src = (WF / name).read_text("utf-8")
    assert re.search(r"playwright install[^\n]*chromium", src), (
        f"{name}이 크로미움을 안 받는다 — 화면 계약 검사가 통째로 "
        "건너뛰어지고, 그 사실은 초록 체크마크 뒤에 숨는다")


@pytest.mark.parametrize("name", BROWSER_JOBS)
def test_the_workflow_installs_the_python_package_too(name):
    """`playwright install`은 파이썬 패키지가 있어야 돈다."""
    src = (WF / name).read_text("utf-8")
    assert "-r requirements-extra.txt" in src, (
        f"{name}이 선택 의존성을 안 설치한다 — playwright가 없으면 "
        "`playwright install` 단계 자체가 죽는다")


def test_the_extra_file_pins_playwright():
    extra = (ROOT / "requirements-extra.txt").read_text("utf-8")
    assert re.search(r"^playwright\s*[<>=]", extra, re.M), (
        "playwright가 버전 범위와 함께 선언돼 있지 않다 — 워크플로가 그날 "
        "PyPI 최신을 받게 된다(감사 130)")


@pytest.mark.parametrize("name", BROWSER_JOBS)
def test_the_browser_arrives_before_the_tests_run(name):
    """받기 전에 돌면 받은 적 없는 것과 같다."""
    wf = yaml.safe_load((WF / name).read_text("utf-8"))
    for job in (wf.get("jobs") or {}).values():
        steps = job.get("steps") or []
        install = use = None
        for i, st in enumerate(steps):
            run = str(st.get("run") or "")
            if install is None and "playwright install" in run:
                install = i
            if use is None and ("pytest" in run or "mutation_check.py" in run):
                use = i
        if use is None:                      # 검사를 안 돌리는 잡
            continue
        assert install is not None and install < use, (
            f"{name}: 브라우저 설치({install})가 검사 실행({use})보다 "
            "뒤에 있거나 없다")


def test_no_test_file_hardcodes_a_container_only_browser_path():
    """경로를 파일마다 적으면 한 환경에서만 도는 검사가 다시 생긴다.

    `/opt/pw-browsers/chromium-1194/...`는 이 개발 컨테이너에만 있는 경로다.
    일곱 파일이 그 경로를 각자 적고 있었고, 그래서 GitHub 러너에서는 전부
    건너뛰었다. 찾는 규칙은 `tests/_browser.py` 한 곳에만 둔다.
    """
    bad = []
    for p in sorted(TESTS.glob("test_*.py")):
        if p.name == Path(__file__).name:    # 규칙을 설명하는 자기 자신
            continue
        for i, ln in enumerate(p.read_text("utf-8").splitlines(), 1):
            if "chromium-" in ln and "chrome-linux" in ln:
                bad.append(f"{p.name}:{i}")
    assert not bad, (
        f"브라우저 경로를 직접 적은 검사: {bad} — _browser.chrome_exe()를 쓸 것")


def test_the_resolver_finds_the_browser_here():
    """이 환경에서는 실제로 찾아야 한다 — 못 찾으면 여기서도 다 건너뛴다.

    ⚠️ 브라우저가 없는 환경(가벼운 로컬 설치)에서는 이 검사만 건너뛴다.
       그 경우에도 위의 워크플로 검사들은 그대로 돌아, **CI에서는** 반드시
       브라우저가 있다는 사실을 지킨다.
    """
    pytest.importorskip("playwright.sync_api",
                        reason="playwright 없음 — 이 환경엔 화면 검사가 없다")
    exe = chrome_exe()
    if not exe:
        pytest.skip("크로미움 없음 — 이 환경엔 화면 검사가 없다")
    assert Path(exe).exists(), f"찾았다는 경로가 없다: {exe}"


def test_the_resolver_does_not_invent_a_path(tmp_path, monkeypatch):
    """대조군 — 없는데 있다고 하면 그 검사는 launch에서 죽는다."""
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    import _browser
    monkeypatch.setattr(_browser, "_roots", lambda: [tmp_path])
    assert _browser.chrome_exe() == ""
    d = tmp_path / "chromium-9999" / "chrome-linux"
    d.mkdir(parents=True)
    (d / "chrome").write_text("#!/bin/sh\n", encoding="utf-8")
    assert _browser.chrome_exe() == str(d / "chrome")


# ── 다음번엔 원인을 함께 말하게 한다 ────────────────────────────

def _extract(func: str):
    """`scripts/mutation_check.py`에서 함수 하나만 떼어 온다.

    ⚠️ **이 파일은 절대 임포트하지 않는다.** 임포트가 곧 실행이고, 실행은
       소스를 잠깐 변조한다(FROZEN_IDEAS ㊿+㉜-b). 그래서 ast로 그 함수의
       본문만 잘라 따로 컴파일한다.
    """
    import ast

    src = (ROOT / "scripts" / "mutation_check.py").read_text("utf-8")
    tree = ast.parse(src)
    node = next((n for n in tree.body
                 if isinstance(n, ast.FunctionDef) and n.name == func), None)
    assert node is not None, f"{func}를 못 찾았다 — 검사가 낡았다"
    ns: dict = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]),
                 "<mutation_check>", "exec"), {"re": re}, ns)
    return ns[func]


def test_a_missed_mutation_reports_whether_the_test_even_ran():
    """'헐거운 검사'와 '안 돈 검사'는 고치는 방법이 전혀 다르다.

    2026-08-17 전수는 21건을 똑같이 "못 잡음"이라고만 적었다. 그중 16건은
    검사가 헐거워서가 아니라 **아예 안 돌아서** 못 잡은 것이었다. 건너뛴
    검사의 종료코드는 0이라 도구에는 '통과'와 구별되지 않았다. 이제 놓친
    항목 옆에 그 검사가 기준선에서 몇 개를 건너뛰었는지를 함께 적는다.
    """
    n = _extract("_skip_count")
    assert n("38 passed, 6 skipped in 12.3s") == 6
    assert n("38 passed in 12.3s") == 0
    assert n("") == 0 and n(None) == 0
    # 여러 줄이면 **마지막** 요약이 그 실행의 결과다.
    assert n("2 skipped in 1s\n...\n40 passed, 9 skipped in 5s") == 9


def test_the_report_actually_prints_that_reason():
    """세어 놓고 안 적으면 세지 않은 것과 같다(부품은 있는데 배선이 없다)."""
    src = (ROOT / "scripts" / "mutation_check.py").read_text("utf-8")
    assert "_skipped_in" in src and "환경부터 볼 것" in src, (
        "건너뛴 개수를 세기만 하고 보고서에 안 적는다 — 다음 실패도 원인 "
        "없이 '못 잡음'만 21줄 나온다")


def test_every_browser_test_cuts_the_outside_world():
    """검사가 **어느 컴퓨터에서 도느냐에 따라 다른 페이지**를 보면 안 된다.

    이 개발 컨테이너는 바깥으로 못 나가고 CI 러너는 나간다. 그러면 같은
    검사가 한쪽에서는 "시세를 못 받은 화면"을, 다른 쪽에서는 "시세가 들어온
    화면"을 본다 — 한쪽에만 있는 결함은 다른 쪽에서 영영 안 보인다
    (감사 130이 pandas로 겪은 것과 같은 병이다).
    """
    bad = []
    for p in sorted(TESTS.glob("test_*.py")):
        if p.name == Path(__file__).name:
            continue
        src = p.read_text("utf-8")
        # `.new_page(` — 함수 이름에 들어간 new_page와 구별한다.
        if ".new_page(" in src and "block_external(" not in src:
            bad.append(p.name)
    assert not bad, (
        f"바깥 네트워크를 안 끊는 화면 검사: {bad} — _browser.block_external()을 "
        "부를 것(시세가 필요한 검사는 그 뒤에 page.route로 자기 응답을 심는다)")


# ── 브라우저가 **없는** 기계에서도 안전한가 (감사 280) ──────────
#
# ⚠️ 감사 278의 수리가 그날 밤 배치를 죽였다. 경로 찾기를 한 곳으로 모으면서
#    '못 찾음'을 빈 문자열로 돌려줬고, 부르는 쪽은 이렇게 확인했다.
#
#        if not Path(CHROME).exists():   # CHROME == ""
#            pytest.skip(...)
#
#    **`Path("")`는 `PosixPath('.')`이고 현재 디렉터리는 언제나 존재한다.**
#    그래서 브라우저 없는 러너에서 관문이 통과했고, playwright에
#    `executable_path="."`가 넘어가 `spawn . EACCES`로 죽었다. 하필 그 검사
#    파일이 배치의 장부 관문 목록에 있어서, 2026-08-17 밤 페이퍼·재학습
#    배치가 **기록을 한 줄도 남기지 못하고** 멈췄다.

def test_no_test_guards_the_browser_with_a_bare_path_check():
    """빈 문자열을 경로로 다루는 확인이 남아 있으면 같은 사고가 반복된다."""
    bad = []
    for p in sorted(TESTS.glob("test_*.py")):
        if p.name == Path(__file__).name:
            continue
        for i, ln in enumerate(p.read_text("utf-8").splitlines(), 1):
            if "Path(CHROME)" in ln or "Path(chrome_exe())" in ln:
                bad.append(f"{p.name}:{i}")
    assert not bad, (
        f"빈 문자열이 '.'가 되는 확인이 남아 있다: {bad} — "
        "_browser.chromium_or_skip()을 쓸 것")


def test_every_browser_test_asks_the_shared_guard():
    """launch에 넘기는 경로는 반드시 그 관문을 통과한 값이어야 한다."""
    bad = []
    for p in sorted(TESTS.glob("test_*.py")):
        src = p.read_text("utf-8")
        if "sync_playwright" not in src:
            continue
        if "executable_path=chromium_or_skip()" not in src:
            bad.append(p.name)
    assert not bad, (
        f"공용 관문을 안 거치고 브라우저를 띄우는 검사: {bad}")


def test_the_guard_skips_instead_of_handing_over_a_bogus_path(monkeypatch):
    """대조군 — 아무것도 못 찾으면 **건너뛰어야** 한다(통과가 아니라).

    ⚠️ `pytest.skip()`이 던지는 Skipped는 `Exception`이 아니라
       `BaseException`을 상속한다. `pytest.raises(Exception)`으로 잡으면
       **이 검사 자신이 건너뛰어지고**, 그러면 아무것도 안 지킨다 —
       오늘 하루 종일 잡은 바로 그 모양이라 여기서 못 박는다.
    """
    from _pytest.outcomes import Skipped

    import _browser
    monkeypatch.setattr(_browser, "_roots", lambda: [])
    with pytest.raises(Skipped):
        _browser.chromium_or_skip()


def test_the_ledger_gate_does_not_need_a_browser():
    """배치가 커밋 직전에 돌리는 관문은 **가볍고 장부만** 봐야 한다.

    화면 검사가 이 목록에 섞이면, 브라우저가 없는 배치 러너에서 화면과
    아무 상관 없는 이유로 그날 기록이 통째로 사라진다. 2026-08-17 밤에
    실제로 그랬다 — 조용히 틀리는 것보다는 낫지만, 멈출 이유가 아니었다.
    """
    import ast

    src = (ROOT / "scripts" / "ledger_gate.py").read_text("utf-8")
    tree = ast.parse(src)
    checks = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(
                node.targets[0], "id", "") == "LEDGER_CHECKS":
            checks = [c.value for c in node.value.elts]
    assert checks, "LEDGER_CHECKS를 못 찾았다 — 검사가 낡았다"
    heavy = []
    for rel in checks:
        f = ROOT / rel
        if not f.exists():
            continue
        s = f.read_text("utf-8")
        if "sync_playwright" in s or "_browser" in s or "playwright" in s:
            heavy.append(rel)
    assert not heavy, (
        f"장부 관문이 브라우저에 의존한다: {heavy} — 화면 검사는 별도 파일로 "
        "빼고 관문은 장부만 볼 것")
