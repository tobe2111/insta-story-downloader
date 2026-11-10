"""검사는 **진짜 장부·공개 화면을 건드리지 않는다** (2026-11-10 감사 377).

감사 376에서 실측: 검사 하나가 상태 빌더를 실제 `state/`로 돌려, 검사를 돌릴
때마다 진짜 장부에 부수 기록(`prereg_coverage.json`)이 생겼다. 판정일이 지난
뒤였다면 **확정 판정이 검사 실행으로 얼었을 것이다.** 한 자리를 고치는 것으로는
다음 자리를 못 막으므로 성질을 건다:

  · 검사 **파일 하나**가 끝날 때마다 `state/`·`docs/`의 파일 목록을 견줘, 내용이
    달라졌으면 그 파일의 마지막 검사를 실패시키고 바뀐 파일을 말한다.
  · 검사 세션 전체의 처음과 끝도 한 번 더 견준다(파일 단위가 놓친 것의 그물).

⚠️ 내용이 같으면 통과다 — 파일을 잠깐 바꿨다가 되돌리는 검사(변이 도구의 부분
   실행)는 수정 시각만 바뀐다. 그래서 크기·시각이 달라진 파일만 내용 지문을 다시 본다.
⚠️ 일꾼 넷이 나란히 돌면, 같은 때 돌던 **다른 파일**이 쓴 것을 이 파일 탓으로
   말할 수 있다. 그래서 문구가 "이 파일이거나 같은 때 돌던 파일"이라고 적는다.
⚠️ 검사 도중 사람이 그 폴더를 직접 고쳐도 걸린다 — 바뀐 파일 이름을 보고 판단한다.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent
_WATCHED = ("state", "docs")
_KEY = "_ledger_manifest"
_BIG = 4 * 1024 * 1024          # 이보다 큰 파일(시세 스냅샷)은 크기·시각만 본다


def _stat_manifest() -> dict:
    out = {}
    for name in _WATCHED:
        base = _ROOT / name
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if p.is_file() and "__pycache__" not in p.parts:
                try:
                    st = p.stat()
                except OSError:
                    continue
                out[str(p.relative_to(_ROOT))] = (st.st_size, st.st_mtime_ns)
    return out


def _digest(rel: str):
    p = _ROOT / rel
    try:
        if p.stat().st_size > _BIG:
            return None
        return hashlib.blake2b(p.read_bytes(), digest_size=12).hexdigest()
    except OSError:
        return None


def _manifest() -> dict:
    """경로 → (크기, 수정 시각, 내용 지문)."""
    return {k: (*v, _digest(k)) for k, v in _stat_manifest().items()}


def changed_files(before: dict, after_stat: dict | None = None) -> list[str]:
    """`before`(지문 포함)에 견줘 **내용이** 달라졌거나 새로 생겼거나 사라진 파일."""
    after_stat = _stat_manifest() if after_stat is None else after_stat
    out = []
    for name in sorted(set(before) | set(after_stat)):
        b, a = before.get(name), after_stat.get(name)
        if b is None or a is None:
            out.append(name)
        elif tuple(b[:2]) != tuple(a[:2]):
            if b[2] is None or _digest(name) != b[2]:
                out.append(name)
    return out


def _say(changed: list[str]) -> str:
    return ("검사가 진짜 장부·공개 화면을 바꿨다(감사 377) — 임시 폴더로 돌릴 것: "
            + ", ".join(changed[:10]) + (" …" if len(changed) > 10 else ""))


@pytest.fixture(scope="module", autouse=True)
def _real_ledger_is_untouched(request):
    before = _manifest()
    yield
    changed = changed_files(before)
    if changed:
        pytest.fail(f"{request.module.__name__}(이 파일이거나 같은 때 돌던 파일): "
                    + _say(changed), pytrace=False)


def pytest_sessionstart(session):
    if hasattr(session.config, "workerinput"):      # xdist 일꾼 — 지휘자만 잰다
        return
    setattr(session.config, _KEY, _manifest())


def pytest_sessionfinish(session, exitstatus):
    before = getattr(session.config, _KEY, None)
    if before is None:
        return
    changed = changed_files(before)
    if changed:
        tr = session.config.pluginmanager.get_plugin("terminalreporter")
        if tr is not None:
            tr.write_line("\n💥 " + _say(changed), red=True)
        session.exitstatus = 1
