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
    """입력 데이터프레임의 정규화 해시 — 부동소수 표현 차이에 안정적.

    funding 등 부가 피처 컬럼도 포함한다 — 판단에 쓰인 모든 입력이 해시에
    묶여야 '입력이 같았다'는 검증이 성립한다(OHLCV만 있던 과거 기록과는
    컬럼 교집합이 같으므로 하위 호환).
    """
    cols = [c for c in ("open", "high", "low", "close", "volume", "funding")
            if c in df]
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
    # ⚠️ lock 해시는 **파일 내용**의 해시일 뿐이다(감사 130). 그 파일대로
    #    설치됐다는 뜻이 아니다 — 실제로 돈을 굴리는 배치들은 버전 없이
    #    `pip install pandas …`로 그날 최신을 받고 있었고, 그래서 검사
    #    환경(pandas 3)과 실전(pandas 2.3)이 서로 다른 세계였다.
    #    해시만 찍으면 읽는 사람이 '고정돼 있다'고 오해한다. 어긋나면 말한다.
    bad = lock_violations()
    if bad:
        parts.append(f"deps!{len(bad)}")
    return "|".join(parts)


# ── 선언한 의존성 vs 실제로 설치된 것 (감사 130) ──────────────
#
# 규칙을 여기 한 곳에만 둔다 — 검사가 자기 파서를 따로 쓰면 둘이 어긋나고,
# 그러면 '검사는 초록인데 현실은 다르다'가 또 생긴다(FROZEN_IDEAS ①).

_CORE_MODULES = {"pandas": "pandas", "numpy": "numpy",
                 "scikit-learn": "sklearn", "pytest": "pytest",
                 "pyyaml": "yaml"}


def _ver_tuple(text: str) -> tuple:
    """'2.3.3rc1' → (2, 3, 3). 숫자가 아닌 꼬리는 버린다."""
    out = []
    for part in str(text).split("."):
        m = re.match(r"\d+", part)
        if not m:
            break
        out.append(int(m.group()))
    return tuple(out) or (0,)


def version_satisfies(version: str, specs) -> bool:
    """'2.3.3'이 [('>=', '2.0'), ('<', '3')] 범위 안인가."""
    v = _ver_tuple(version)
    for op, bound in specs:
        b = _ver_tuple(bound)
        n = max(len(v), len(b))
        a, c = v + (0,) * (n - len(v)), b + (0,) * (n - len(b))
        if op == ">=" and not a >= c:
            return False
        if op == ">" and not a > c:
            return False
        if op == "<=" and not a <= c:
            return False
        if op == "<" and not a < c:
            return False
        if op == "==" and a != c:
            return False
        if op == "!=" and a == c:
            return False
    return True


def declared_requirements(path: str = "requirements.txt") -> dict:
    """requirements.txt → {이름(소문자): [(연산자, 버전), …]}."""
    out: dict = {}
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return out
    for raw in lines:
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        m = re.match(r"^([A-Za-z0-9_.\-]+)\s*(.*)$", line)
        if not m:
            continue
        out[m.group(1).lower()] = re.findall(
            r"(>=|<=|==|!=|>|<)\s*([0-9][0-9A-Za-z.\-]*)", m.group(2))
    return out


def lock_violations(path: str = "requirements.txt") -> list:
    """설치된 핵심 라이브러리 중 선언 범위를 벗어난 것들의 설명 목록."""
    declared = declared_requirements(path)
    bad = []
    for name, mod in _CORE_MODULES.items():
        specs = declared.get(name)
        if not specs:
            continue
        try:
            m = __import__(mod)
            got = getattr(m, "__version__", None) or getattr(m, "version", None)
        except Exception:  # noqa: BLE001 — 없는 선택 의존성은 위반이 아니다
            continue
        if got and not version_satisfies(str(got), specs):
            spec_txt = ",".join(f"{o}{v}" for o, v in specs)
            bad.append(f"{name} {got} ∉ {spec_txt}")
    return bad


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


def snapshot_pool_day(state_dir: str, cutoff: str) -> str | None:
    """cutoff보다 **엄격히 이전**인 최신 스냅샷 폴더명(없으면 None).

    폴더 고르는 규칙을 한 곳에 둔다 — 호출자가 '어느 날의 풀인가'를 알아야
    같은 폴더를 두 번 읽지 않고 캐시할 수 있다(감사 129에서 학습 블록마다
    풀을 다시 고르게 바꾸면서 필요해졌다).
    """
    base = os.path.join(state_dir, SNAP_DIR)
    if not os.path.isdir(base):
        return None
    days = sorted(d for d in os.listdir(base) if d < cutoff[:10])
    return days[-1] if days else None


def load_snapshot_pool(state_dir: str, cutoff: str) -> list:
    """cutoff(YYYY-MM-DD)보다 '이전' 날짜 중 최신 스냅샷 폴더의 전 종목 df 목록.

    풀링(패널) 학습의 재현 가능한 데이터 소스: 스냅샷은 날짜 폴더로 불변
    보존되므로, '엄격히 이전 날짜의 최신 폴더'라는 규칙은 언제 다시 실행해도
    같은 답을 준다. 당일 폴더를 제외하는 이유 — 야간 재학습이 종목을 순회하며
    당일 스냅샷을 하나씩 채우는 중이라, 당일 폴더는 실행 시점마다 내용물이
    달라 verify 재현이 깨진다(하루 지연은 학습 풀에 무해).
    """
    import pandas as pd
    day = snapshot_pool_day(state_dir, cutoff)
    if day is None:
        return []
    day_dir = os.path.join(state_dir, SNAP_DIR, day)
    out = []
    for name in sorted(os.listdir(day_dir)):
        if not name.endswith(".csv.gz"):
            continue
        try:
            with gzip.open(os.path.join(day_dir, name), "rt",
                           encoding="utf-8") as f:
                out.append(pd.read_csv(f, index_col=0, parse_dates=True))
        except Exception:  # noqa: BLE001 — 파일 하나의 손상이 풀을 막으면 안 된다
            continue
    return out
