"""재현성 도구 — "이 결과가 이 코드·이 데이터에서 나왔다"를 증명 가능하게.

결과 커밋만으로는 조작 불가를 증명하지 못한다. 매일 기록에
  ① 코드 커밋 해시  ② 입력 데이터 SHA256  ③ 결정적 시드
를 함께 박고, 입력 스냅샷을 저장해 누구나 재실행 → 같은 결정이 나오는지
검증할 수 있게 한다 (python -m quant verify --date YYYY-MM-DD).
"""
from __future__ import annotations

import gzip
import hashlib
import os
import re

SNAP_DIR = "snapshots"


def data_sha256(df) -> str:
    """OHLCV 데이터프레임의 정규화 해시 — 부동소수 표현 차이에 안정적."""
    cols = [c for c in ("open", "high", "low", "close", "volume") if c in df]
    body = "\n".join(
        f"{ix},{','.join(format(float(r[c]), '.10g') for c in cols)}"
        for ix, r in df[cols].iterrows())
    return hashlib.sha256(body.encode()).hexdigest()


def code_sha() -> str:
    """실행 중인 코드의 커밋 해시 (Actions는 GITHUB_SHA, 로컬은 git)."""
    sha = os.getenv("GITHUB_SHA", "")
    if sha:
        return sha[:12]
    try:
        import subprocess
        return subprocess.run(["git", "rev-parse", "--short=12", "HEAD"],
                              capture_output=True, text=True,
                              timeout=5).stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def env_fingerprint() -> str:
    """실행 환경 지문 — 파이썬·핵심 라이브러리 버전 + 의존성 잠금 해시.

    코드·데이터·시드가 같아도 numpy/pandas 버전이 다르면 부동소수점 결과가
    미세하게 달라질 수 있다. 기록에 환경 지문을 함께 박아, verify 불일치가
    '조작'인지 '환경 차이'인지 구분할 수 있게 한다.
    """
    import platform
    parts = [f"py{platform.python_version()}"]
    for mod, name in (("numpy", "np"), ("pandas", "pd"), ("sklearn", "sk")):
        try:
            m = __import__(mod)
            parts.append(f"{name}{m.__version__}")
        except Exception:  # noqa: BLE001
            parts.append(f"{name}?")
    lock = _lock_sha()
    if lock:
        parts.append(f"lock:{lock}")
    return "|".join(parts)


def _lock_sha() -> str:
    """requirements.txt(의존성 잠금)의 짧은 해시 — 없으면 빈 문자열."""
    for cand in ("requirements.txt",):
        try:
            with open(cand, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()[:12]
        except OSError:
            continue
    return ""


def _snap_path(state_dir: str, asof: str, market: str, symbol: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", f"{market}_{symbol}")
    return os.path.join(state_dir, SNAP_DIR, asof, f"{safe}.csv.gz")


def save_snapshot(df, state_dir: str, asof: str,
                  market: str, symbol: str) -> str:
    """입력 데이터를 csv.gz로 보존한다(이미 있으면 덮어쓰지 않음 — 불변)."""
    path = _snap_path(state_dir, asof, market, symbol)
    if os.path.exists(path):
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        df.to_csv(f)
    return path


def load_snapshot(state_dir: str, asof: str, market: str, symbol: str):
    """저장된 스냅샷을 데이터프레임으로 복원한다. 없으면 None."""
    import pandas as pd
    path = _snap_path(state_dir, asof, market, symbol)
    if not os.path.exists(path):
        return None
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return pd.read_csv(f, index_col=0, parse_dates=True)
