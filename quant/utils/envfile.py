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


def write_private(fp: str | Path, text: str) -> bool:
    """비밀을 담은 파일을 0o600으로 '먼저' 만든 뒤 내용을 쓴다.

    쓰고 나서 조이면 그 사이 짧은 순간 같은 기계의 다른 사용자가 읽는다.
    0o600 임시 파일에 쓴 뒤 원자적으로 갈아 끼우므로, 이미 있던 파일이
    느슨한 권한이었더라도 교체와 함께 조여진다(감사 190).

    반환값은 **'저장 후 실제로 본인만 읽기인가'** 다 — 호출자는 이 값을 보고
    사용자에게 사실대로 말해야 한다. 확인하지 않은 보안을 약속하면 안 된다
    (감사 ㊾).

    ⚠️ 비밀을 파일로 쓰는 곳은 전부 이 함수를 거친다. .env는 처음부터 이렇게
    했는데 **정작 팔아서 돈을 받은 라이선스 키(license.key)는 평범한
    write_text로 0o644에 저장되고 있었다**(감사 76). 같은 기계의 다른
    사용자가 읽어 그대로 쓸 수 있다 — 그게 곧 무단 복제다.
    """
    fp = Path(fp)
    # 예전에는 '이미 있던 파일은 O_CREAT의 mode가 안 먹으니' 뒤에서 chmod로
    # 조였다. 지금은 0o600 임시 파일을 만들어 `os.replace`로 갈아 끼우므로
    # 결과 파일이 처음부터 0o600이다 — 뒤에서 조일 자리가 없다(감사 190).
    _write_private(fp, text)
    return is_private(fp)


def _write_private(fp: Path, text: str) -> None:
    """0o600 임시 파일에 먼저 쓰고 **원자적으로 갈아 끼운다**.

    두 가지를 동시에 지킨다.

    ① **노출되는 순간을 없앤다** — 파일을 처음부터 0o600으로 만든다.
       평범하게 쓰고 나서 chmod로 조이면 그 사이 짧은 순간 같은 기계의
       다른 사용자가 키를 읽는다(감사 ㊾).

    ② **실패해도 원본을 잃지 않는다**(감사 190). 예전에는 대상 파일을
       `O_TRUNC`로 **제자리에서 잘랐다.** 쓰기가 중간에 실패하면
       (디스크 가득·중단) 그 자리에 빈 파일만 남는다. 실측:

           원본 .env : BINANCE_KEY=... · KIS_APP_SECRET=...
           쓰기 실패 후: ''            ← 실거래 키가 통째로 사라진다

       감사 162에서 **캐시**에는 원자적 쓰기를 넣었는데, 정작 실거래
       API 키가 든 이 파일은 제자리 자르기였다. 형제를 안 찾은 자리다(⑭).
       임시 파일에 다 쓰고 `os.replace`로 바꾸면, 실패했을 때 원본이
       그대로 남는다. 갈아 끼운 파일은 이미 0o600이라 뒤에서 조일 필요도
       없어진다.

    ⚠️ `os.replace`는 심볼릭 링크를 **따라가지 않고 링크 자체를 바꾼다.**
       예전(O_TRUNC)은 링크가 가리키는 파일에 썼다. 비밀 파일이 링크를
       통해 다른 곳을 가리키게 만드는 공격을 막는 쪽이라 이 차이는 의도된
       것이다.
    """
    tmp = fp.with_name(fp.name + f".tmp{os.getpid()}")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            f = os.fdopen(fd, "w", encoding="utf-8")
        except BaseException:    # fdopen이 실패했을 때만 fd 소유권이 남는다
            os.close(fd)
            raise
        with f:                  # 성공했으면 파일 객체가 fd를 닫는다(이중 close 금지)
            f.write(text)
            f.flush()
            os.fsync(f.fileno())  # 갈아 끼우기 전에 내용이 디스크에 닿게
        os.replace(tmp, fp)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


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
    # 0o600 임시 파일 → os.replace 이므로 결과 파일이 처음부터 0o600이다.
    # 예전 버전이 0o644로 남겨 둔 파일도 이 교체로 함께 조여진다(감사 190).
    _write_private(fp, "\n".join(lines) + "\n")
    return is_private(fp)
