"""선언한 의존성이 **실제로 도는 환경**과 맞는가 (감사 130).

오늘 가장 비쌌던 두 결함(127 풀링 사망 · 128 학습 상한 무력화)은 둘 다
pandas 3.0의 동작 변화가 원인이었다. 그런데 `requirements.txt`는 이렇게
적혀 있었다.

    # 의존성 버전은 '보수적 범위'로 고정한다 — 어느 날 갑자기 메이저
    # 업데이트가 설치돼 동작이 바뀌는 사고를 막는다(설치 재현성).
    pandas>=2.0,<3

**막겠다고 적어 놓고 아무것도 막지 않았다.**

  · 이 파일을 설치에 쓰는 워크플로는 `ci.yml`의 audit 잡 하나뿐이었다.
    돈을 굴리는 daily-paper·nightly-retrain·kr-live는 전부
    `pip install pandas numpy …` — **버전 없이** 그날 PyPI 최신을 받았다.
  · 그래서 검사(pandas 3.0.5)와 실전(장부 지문 기준 pandas 2.3.3)이
    **서로 다른 세계**에서 돌았다. 한쪽에만 있는 결함은 다른 쪽에서
    영원히 안 보인다 — 감사 127이 정확히 그랬다(pandas 3에서만 죽었다).
  · 게다가 장부에는 매일 `lock:3e29b4dc…`가 찍힌다. 읽는 사람은 의존성이
    고정돼 있다고 믿는다. 그 해시는 **파일 내용의 해시일 뿐** 설치된
    버전과는 아무 관계가 없었다.

이 검사는 그 간극을 못 박는다: **지금 이 검사를 돌리는 환경이
requirements.txt가 허용하는 범위 안이어야 한다.** 메이저가 올라온 날
조용히 동작이 바뀌는 대신 검사가 빨개진다.

판정 규칙(파서·비교기)은 `quant/utils/repro.py`에만 둔다 — 검사가 자기
파서를 따로 쓰면 둘이 어긋나고, 그러면 '검사는 초록인데 현실은 다르다'가
또 생긴다(FROZEN_IDEAS ①: 같은 규칙을 두 곳에 적으면 반드시 어긋난다).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.utils.repro import (  # noqa: E402
    _CORE_MODULES,
    declared_requirements,
    env_fingerprint,
    lock_violations,
    version_satisfies,
)

REQ = str(ROOT / "requirements.txt")


# ── 비교기 자체 시험 — 이것이 틀리면 아래가 전부 헛것이다 ──────


def test_the_comparator_actually_compares():
    assert version_satisfies("2.3.3", [(">=", "2.0"), ("<", "3")])
    assert not version_satisfies("3.0.5", [(">=", "2.0"), ("<", "3")])
    assert not version_satisfies("1.9.0", [(">=", "2.0")])
    assert version_satisfies("9.1.1", [(">=", "7.0"), ("<", "10")])
    assert not version_satisfies("9.1.1", [(">=", "7.0"), ("<", "9")])
    # 자릿수가 다른 비교(2 vs 2.0.0)에서 무너지지 않는가
    assert version_satisfies("2", [(">=", "2.0.0")])
    assert version_satisfies("2.0.0", [(">=", "2")])
    # 숫자가 아닌 꼬리(rc·post)를 만나도 죽지 않는가
    assert version_satisfies("3.0.5rc1", [(">=", "3.0")])


def test_the_parser_finds_the_core_pins():
    d = declared_requirements(REQ)
    for name in _CORE_MODULES:
        assert name in d, f"requirements.txt에서 {name}을 못 찾았다 — 파서가 낡았다"
        assert d[name], f"{name}에 버전 범위가 없다 — 고정이 아니다"


def test_the_detector_notices_a_planted_mismatch(tmp_path):
    """탐지기가 살아 있는가 — 일부러 어긋난 범위를 넣으면 잡아야 한다."""
    fake = tmp_path / "requirements.txt"
    fake.write_text("pandas>=0.1,<0.2\n", encoding="utf-8")
    assert lock_violations(str(fake)), "명백히 어긋난 범위를 못 잡는다"
    ok = tmp_path / "ok.txt"
    ok.write_text("pandas>=0.1,<99\n", encoding="utf-8")
    assert not lock_violations(str(ok))


# ── 본론 — 선언과 현실 ─────────────────────────────────────────


@pytest.mark.parametrize("name,mod", sorted(_CORE_MODULES.items()))
def test_the_running_environment_is_inside_the_declared_range(name, mod):
    m = pytest.importorskip(mod)
    got = getattr(m, "__version__", None) or getattr(m, "version", None)
    assert got, f"{name} 버전을 읽을 수 없다"
    specs = declared_requirements(REQ).get(name)
    assert specs, f"{name}이 requirements.txt에 없다"
    assert version_satisfies(str(got), specs), (
        f"{name} {got}이(가) 선언 범위 {specs} 밖이다.\n"
        "  선언과 현실이 다르면 '고정했다'는 말이 거짓이 된다. 둘 중 하나다:\n"
        "   ① 새 메이저를 실제로 지원하기로 했다면 requirements.txt를 넓힐 것\n"
        "   ② 아직 검증 못 했다면 워크플로에서 그 버전을 설치하지 말 것\n"
        "  (2026-08-12 감사 130: pandas 3.0이 조용히 들어와 풀링 학습을\n"
        "   통째로 죽이고 학습 상한 필터를 무력화했다 — 검사 환경에서만\n"
        "   일어난 일이라 실전 장부로는 몇 주 동안 보이지 않았다.)")


def test_every_workflow_installs_from_the_one_file():
    """검사와 실전이 **같은 파일**로 설치되는가.

    두 환경이 갈라지면 한쪽에만 있는 결함은 다른 쪽에서 영원히 안 보인다.
    장부에 매일 `lock:…` 해시를 찍으면서 정작 설치는 고정하지 않으면,
    그 해시는 고정돼 있다는 **인상만** 준다.
    """
    wf = ROOT / ".github" / "workflows"
    bad = []
    for p in sorted(wf.glob("*.yml")):
        src = p.read_text("utf-8")
        for ln in src.splitlines():
            s = ln.strip()
            if not s.startswith("pip install") or "--upgrade pip" in s:
                continue
            if "pip-audit" in s:            # 감사 도구 자신은 예외
                continue
            if "-r requirements.txt" not in s:
                bad.append(f"{p.name}: {s}")
                continue
            # ⚠️ **`-r`이 있는지만 보면 반쪽이다**(2026-08-15에 드러남).
            #    이 검사가 붙은 뒤에도 이렇게 남아 있었다:
            #        pip install -r requirements.txt pykrx        ← 버전 없음
            #        pip install -r requirements.txt cryptography ← 버전 없음
            #    감사 130이 막겠다고 적은 바로 그 형태가 세 패키지에 그대로
            #    있었다. 하필 pykrx는 **돈을 굴리는 워크플로**가 설치하고,
            #    한국주식 수급 피처의 유일한 소스다.
            #    그래서 `-r` 뒤에 덧붙은 **맨 패키지 이름**도 잡는다.
            rest = s.split("pip install", 1)[1].split()
            skip = False
            for tok in rest:
                if skip:                       # -r 다음 토큰은 파일 이름
                    skip = False
                    continue
                if tok == "-r":
                    skip = True
                    continue
                if tok.startswith("-"):        # 그 밖의 옵션
                    continue
                bad.append(f"{p.name}: {s}  ← '{tok}'에 버전이 없다")
    assert not bad, (
        "버전 고정 없이 설치하는 워크플로가 있다 — 어느 날 메이저가 올라오면\n"
        "조용히 동작이 바뀐다(감사 130):\n  " + "\n  ".join(bad))


def test_the_fingerprint_tells_when_the_lock_is_not_actually_honored():
    """지문의 lock 해시가 '고정됐다'는 오해를 만들지 않는가.

    해시는 파일 내용의 해시일 뿐이다. 설치된 버전이 그 범위 밖이면
    지문이 그 사실을 말해야 한다 — 안 그러면 verify 불일치를 '환경 차이'로
    설명할 때 어느 환경인지 알 수 없다.
    """
    fp = env_fingerprint()
    assert "lock:" in fp
    if lock_violations():
        assert "deps!" in fp, (
            f"설치 버전이 선언 범위 밖인데 지문이 조용하다: {fp}")
    else:
        assert "deps!" not in fp


def test_the_extra_file_exists_and_pins_what_workflows_add():
    """워크플로가 덧붙이던 패키지가 **파일에 버전과 함께** 있는가.

    ⚠️ 배선만 바꾸고 파일이 비어 있으면 그 패키지는 아예 설치되지 않는다 —
       조용히 없어지는 쪽이 버전이 흔들리는 것보다 더 나쁘다(pykrx가 빠지면
       한국주식 수급 피처가 통째로 사라진다).
    """
    import re

    extra = (ROOT / "requirements-extra.txt")
    assert extra.exists(), "requirements-extra.txt가 없다"
    pins = {}
    for ln in extra.read_text("utf-8").splitlines():
        s = ln.split("#")[0].strip()
        if not s:
            continue
        m = re.match(r"^([A-Za-z0-9_.-]+)\s*([<>=!].+)$", s)
        assert m, f"버전 범위가 없는 줄: {s!r}"
        pins[m.group(1).lower()] = m.group(2)
    for need in ("pykrx", "cryptography", "pyinstaller"):
        assert need in pins, f"{need}가 requirements-extra.txt에 없다"


def test_workflows_that_need_the_extras_actually_install_them():
    """돈을 굴리는 워크플로가 선택 의존성을 **실제로** 설치하는가."""
    wf = ROOT / ".github" / "workflows"
    for name in ("daily-paper.yml", "nightly-retrain.yml", "kr-live.yml",
                 "build-app.yml"):
        src = (wf / name).read_text("utf-8")
        assert "-r requirements-extra.txt" in src, (
            f"{name}이 선택 의존성을 안 설치한다 — 전에는 맨 이름으로 "
            f"덧붙이고 있었다(버전 없이 그날 최신)")
