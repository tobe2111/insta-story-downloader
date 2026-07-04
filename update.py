#!/usr/bin/env python3
"""더블클릭 업데이트 — 최신 버전으로 안전하게 갱신한다.

이 파일을 실행하면:
    1) (git 설치본이면) 최신 코드를 내려받고
    2) 새로 필요해진 라이브러리를 맞춰 설치하고
    3) 무엇이 바뀌었는지 간단히 알려줍니다.

터미널을 몰라도 됩니다. 윈도우는 update.bat, 맥/리눅스는 update.sh 를
더블클릭하거나, 어디서든  python update.py  로 실행하세요.

⚠️ 정직한 안내:
    - 업데이트는 '코드'를 최신으로 맞출 뿐, 수익을 높여주지 않습니다.
      방향 예측 정확도 천장(대개 52~55%)은 어떤 업데이트로도 뚫리지 않습니다.
    - 내가 직접 고친 파일(로컬 수정)이 있으면 자동 병합이 막힐 수 있습니다.
      그럴 땐 아래 안내대로 처리하세요(데이터·설정은 건드리지 않습니다).
"""
from __future__ import annotations

import os
import subprocess
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))


def _run(cmd: list[str]) -> tuple[int, str]:
    """명령을 실행하고 (종료코드, 출력)을 반환한다(예외 대신 코드로 판단)."""
    try:
        out = subprocess.run(cmd, cwd=_ROOT, capture_output=True, text=True)
        return out.returncode, (out.stdout or "") + (out.stderr or "")
    except FileNotFoundError as exc:
        return 127, str(exc)


def _is_git_checkout() -> bool:
    return os.path.isdir(os.path.join(_ROOT, ".git"))


def _git_update() -> bool:
    """git으로 최신 코드를 받는다. 성공하면 True."""
    code, _ = _run(["git", "--version"])
    if code != 0:
        print("ℹ️ git 이 설치되어 있지 않아 코드 자동 업데이트를 건너뜁니다.")
        print("   최신 버전은 배포처(GitHub)에서 폴더를 다시 내려받아 덮어쓰면 됩니다.")
        print("   (data_cache·state 등 결과 파일은 그대로 두세요.)")
        return False

    # 현재 브랜치 확인(없으면 main 가정)
    code, branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    branch = branch.strip() or "main"

    print(f"⬇️ 최신 코드를 확인합니다… (브랜치: {branch})")
    code, out = _run(["git", "pull", "--ff-only", "origin", branch])
    if code == 0:
        if "Already up to date" in out or "이미 최신" in out:
            print("✅ 이미 최신 버전입니다.")
        else:
            print("✅ 코드 업데이트 완료.")
            print(_summarize(out))
        return True

    # 로컬 수정 등으로 fast-forward 실패
    print("⚠️ 자동 업데이트가 막혔습니다. 보통 로컬에서 직접 고친 파일이 있을 때입니다.")
    print("   해결: 아래 중 하나를 선택하세요(결과·설정 파일은 안전합니다).")
    print("     · 내 수정을 유지하고 싶다: 수정한 파일을 백업 후 다시 실행")
    print("     · 최신으로 깔끔히 맞추고 싶다: 터미널에서")
    print("         git stash  &&  git pull --ff-only  &&  git stash pop")
    print("\n   (자세한 원인)")
    print(_indent(out))
    return False


def _summarize(pull_output: str) -> str:
    """git pull 출력에서 사람이 읽기 좋은 요약만 추린다."""
    lines = [ln for ln in pull_output.splitlines()
             if ln.strip() and not ln.startswith("From ")]
    tail = lines[-6:] if len(lines) > 6 else lines
    return _indent("\n".join(tail))


def _indent(text: str, prefix: str = "   | ") -> str:
    return "\n".join(prefix + ln for ln in text.splitlines() if ln.strip())


def _refresh_deps() -> None:
    """requirements.txt 기준으로 라이브러리를 최신 상태로 맞춘다."""
    req = os.path.join(_ROOT, "requirements.txt")
    if not os.path.exists(req):
        return
    print("\n📦 라이브러리를 최신 요구사항에 맞춰 확인합니다…")
    code, out = _run([sys.executable, "-m", "pip", "install", "-r", req, "--upgrade"])
    if code == 0:
        print("✅ 라이브러리 확인 완료.")
    else:
        print("⚠️ 라이브러리 설치 중 문제가 있었습니다(인터넷/권한 확인). 상세:")
        print(_indent(out[-800:]))


def main() -> None:
    print("━" * 60)
    print(" 업데이트를 시작합니다")
    print("━" * 60)
    if not _is_git_checkout():
        print("ℹ️ 이 폴더는 git 설치본이 아닙니다.")
        print("   최신 버전은 배포처에서 폴더를 다시 내려받아 덮어쓰면 됩니다.")
        print("   (data_cache·state 등 결과 파일은 그대로 두세요.)")
        _refresh_deps()
    else:
        updated = _git_update()
        if updated:
            _refresh_deps()
    print("\n완료. 이제 start(웹 조종석) 또는 learn(자동 학습)을 실행하세요.")


if __name__ == "__main__":
    main()
