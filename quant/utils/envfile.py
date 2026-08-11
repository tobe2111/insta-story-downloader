""".env 파일 로더 — API 키를 매번 export하지 않아도 되게 한다 (순수 stdlib).

프로그램 폴더의 .env 파일에서 KEY=VALUE 를 읽어 환경변수로 넣는다.
이미 설정된 환경변수는 덮어쓰지 않는다(셸에서 직접 지정한 값이 항상 우선).

⚠️ 보안 원칙:
    · .env 는 .gitignore 에 포함되어 절대 커밋되지 않는다.
    · 키는 로그에 출력하지 않는다. 이 모듈도 값(value)을 어디에도 남기지 않는다.
    · 파일은 **처음부터** 0o600(본인만 읽기)으로 만든다. 예전에는 평범하게
      쓰고(umask대로 0o644) 나서 chmod로 조였는데, 그 사이 짧은 순간 키가
      같은 기계의 다른 사용자에게 읽혔다. 더 나쁜 건 chmod가 실패해도
      `except OSError: pass`로 삼켜 놓고, 마법사는 "권한 600"이라고
      단언했다는 점이다 — 지켜지지 않은 약속을 지켜졌다고 말하는 쪽이
      권한이 느슨한 것보다 위험하다(2026-08-11 감사 ㊾).
    · 윈도우의 os.chmod는 POSIX 권한 비트를 흉내만 낸다(읽기전용 토글).
      그래서 '본인만 읽기'가 보장되지 않으며, `is_private()`는 그 사실을
      숨기지 않고 False를 돌려준다.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path


def parse_env_text(text: str) -> dict[str, str]:
    """KEY=VALUE 형식 텍스트를 dict로 파싱한다 (#주석·빈 줄 무시, 따옴표 제거)."""
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or not key.replace("_", "").isalnum():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key] = value
    return out


def load_env_file(path: str | Path = ".env", override: bool = False) -> int:
    """path의 .env를 환경변수로 로드한다. 넣은 변수 개수를 반환(파일 없으면 0).

    override=False(기본)면 이미 있는 환경변수는 건드리지 않는다 —
    셸에서 직접 export한 값이 파일보다 우선한다는 관례를 따른다.
    """
    fp = Path(path)
    if not fp.exists():
        return 0
    try:
        pairs = parse_env_text(fp.read_text(encoding="utf-8"))
    except OSError:
        return 0
    n = 0
    for k, v in pairs.items():
        if override or k not in os.environ:
            os.environ[k] = v
            n += 1
    return n


def is_private(path: str | Path) -> bool:
    """파일이 '본인만 읽기'인지 실제로 확인한다(그룹·기타 권한 0인가).

    윈도우에서는 POSIX 권한 비트가 의미를 갖지 않으므로 항상 False —
    '확인할 수 없다'를 '안전하다'로 반올림하지 않는다.
    """
    if os.name != "posix":
        return False
    try:
        mode = os.stat(path).st_mode
    except OSError:
        return False
    return not (mode & (stat.S_IRWXG | stat.S_IRWXO))


def _write_private(fp: Path, text: str) -> None:
    """0o600으로 '먼저' 만든 뒤 내용을 쓴다 — 노출되는 순간을 없앤다."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(fp, flags, 0o600)
    try:
        f = os.fdopen(fd, "w", encoding="utf-8")
    except BaseException:        # fdopen이 실패했을 때만 fd 소유권이 남는다
        os.close(fd)
        raise
    with f:                      # 성공했으면 파일 객체가 fd를 닫는다(이중 close 금지)
        f.write(text)


def update_env_file(path: str | Path, updates: dict[str, str]) -> bool:
    """기존 .env의 다른 키·주석을 보존하면서 updates만 추가/갱신한다.

    파일을 0o600으로 만든 뒤 내용을 쓴다(쓰고 나서 조이지 않는다).
    빈 값은 건너뛴다.

    반환값은 '저장 후 파일이 실제로 본인만 읽기인가'다. 호출자는 이 값을
    보고 사용자에게 사실대로 말해야 한다 — 예전처럼 무조건 "권한 600"이라
    출력하면 안 된다. 업데이트할 값이 없으면 파일을 건드리지 않았으므로
    현재 상태를 그대로 확인해 돌려준다.
    """
    fp = Path(path)
    updates = {k: v for k, v in updates.items() if v}
    if not updates:
        return is_private(fp) if fp.exists() else True
    lines: list[str] = []
    seen: set[str] = set()
    if fp.exists():
        for raw in fp.read_text(encoding="utf-8").splitlines():
            stripped = raw.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.partition("=")[0].strip()
                if key in updates:
                    lines.append(f"{key}={updates[key]}")
                    seen.add(key)
                    continue
            lines.append(raw)
    for k, v in updates.items():
        if k not in seen:
            lines.append(f"{k}={v}")
    existed = fp.exists()
    _write_private(fp, "\n".join(lines) + "\n")
    if existed:
        # 이미 있던 파일은 os.open이 권한을 바꾸지 않는다(O_CREAT의 mode는
        # 새로 만들 때만 적용). 예전 버전이 0o644로 남겨둔 파일을 조인다.
        try:
            os.chmod(fp, 0o600)
        except OSError:
            pass                 # 삼키되 숨기지 않는다 — 아래 반환값이 말한다
    return is_private(fp)
