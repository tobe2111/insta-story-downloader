""".env 파일 로더 — API 키를 매번 export하지 않아도 되게 한다 (순수 stdlib).

프로그램 폴더의 .env 파일에서 KEY=VALUE 를 읽어 환경변수로 넣는다.
이미 설정된 환경변수는 덮어쓰지 않는다(셸에서 직접 지정한 값이 항상 우선).

⚠️ 보안 원칙:
    · .env 는 .gitignore 에 포함되어 절대 커밋되지 않는다.
    · 키는 로그에 출력하지 않는다. 이 모듈도 값(value)을 어디에도 남기지 않는다.
    · 파일 권한은 setup 마법사가 0o600(본인만 읽기)으로 만든다.
"""
from __future__ import annotations

import os
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


def update_env_file(path: str | Path, updates: dict[str, str]) -> None:
    """기존 .env의 다른 키·주석을 보존하면서 updates만 추가/갱신한다.

    새 파일은 0o600(본인만 읽기) 권한으로 만든다. 빈 값은 건너뛴다.
    """
    fp = Path(path)
    updates = {k: v for k, v in updates.items() if v}
    if not updates:
        return
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
    fp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(fp, 0o600)      # 본인만 읽기 — 키 유출 방지
    except OSError:
        pass
