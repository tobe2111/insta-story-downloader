"""검사는 **진짜 장부·공개 화면을 건드리지 않는다** (2026-11-10 감사 377).

감사 376에서 실측: 검사 하나가 상태 빌더를 실제 `state/`로 돌려, 검사를 돌릴
때마다 진짜 장부에 부수 기록(`prereg_coverage.json`)이 생겼다. 판정일이 지난
뒤였다면 **확정 판정이 검사 실행으로 얼었을 것이다.** 한 자리를 고치는 것으로는
다음 자리를 못 막으므로 성질을 건다:

  검사 세션의 처음과 끝에 `state/`·`docs/`의 파일 목록(크기·수정 시각)을 견줘,
  달라졌으면 그 세션을 **실패**시키고 바뀐 파일을 말한다.

⚠️ 검사를 도는 동안 사람이 그 폴더를 직접 고치면 거짓 경보가 난다 — 그때는
   바뀐 파일 이름을 보고 판단한다(이름을 말하는 이유다).
"""
from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_WATCHED = ("state", "docs")
_KEY = "_ledger_manifest"


def _manifest() -> dict:
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


def changed_files(before: dict, after: dict) -> list[str]:
    names = set(before) | set(after)
    return sorted(n for n in names if before.get(n) != after.get(n))


def pytest_sessionstart(session):
    if hasattr(session.config, "workerinput"):      # xdist 일꾼 — 지휘자만 잰다
        return
    setattr(session.config, _KEY, _manifest())


def pytest_sessionfinish(session, exitstatus):
    before = getattr(session.config, _KEY, None)
    if before is None:
        return
    changed = changed_files(before, _manifest())
    if changed:
        tr = session.config.pluginmanager.get_plugin("terminalreporter")
        msg = ("검사가 진짜 장부·공개 화면을 바꿨다(감사 377) — 임시 폴더로 돌릴 것: "
               + ", ".join(changed[:10]) + (" …" if len(changed) > 10 else ""))
        if tr is not None:
            tr.write_line("\n💥 " + msg, red=True)
        session.exitstatus = 1
