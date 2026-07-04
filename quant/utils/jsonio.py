"""상태 저장용 JSON 헬퍼 — NaN/inf 안전 + 원자적 쓰기 + history 상한.

라이브 러너(autolearn·multi·engine)가 state.json을 매 사이클 저장할 때의 문제 방지:

  1) NaN 오염: hit_rate 등이 float('nan')이면 json.dumps가 기본(allow_nan=True)으로
     유효하지 않은 토큰 `NaN`을 쓴다. 파이썬은 다시 읽을 수 있지만, 대시보드의
     브라우저 JSON.parse는 SyntaxError를 내고 catch{}로 삼켜져 화면이 '조용히'
     영구 정지한다. → 비유한 float를 null로 치환한다.
     (allow_nan=False로 raise시키면 cycle의 except가 삼켜 저장이 아예 멈춘다.)

  2) 비원자적 쓰기: write_text는 '자르고-쓰기'라, 읽는 중이거나 크래시 시 파일이
     부분/손상 상태가 된다. → 임시파일에 쓰고 fsync 후 os.replace로 원자 교체.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

# 라이브 러너 history 상한. 무한 실행 시 리스트가 무한 성장하고 매 사이클 전체를
# 재직렬화(O(N)→누적 O(N²))하는 것을 막는다. 시간당 1회면 약 208일치.
HISTORY_CAP = 5000


def sanitize(obj: Any) -> Any:
    """NaN/inf float를 None으로 바꾼 직렬화 안전 사본을 반환한다(재귀)."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize(v) for v in obj]
    return obj


def atomic_write_json(path: str | os.PathLike, obj: Any, indent: int = 2) -> None:
    """obj를 NaN 안전하게 직렬화해 원자적으로 저장한다(임시파일 + os.replace)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(sanitize(obj), ensure_ascii=False, indent=indent)
    tmp = p.with_name(p.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)   # 같은 파일시스템에서 원자적 교체(부분 파일 노출 없음)


def cap_history(history: list) -> list:
    """history를 HISTORY_CAP 최근 항목으로 잘라 반환한다(제자리 축소 아님)."""
    if len(history) > HISTORY_CAP:
        return history[-HISTORY_CAP:]
    return history
