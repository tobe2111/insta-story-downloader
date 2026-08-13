"""재현성 매니페스트 — '이 결과가 어떤 코드·설정·데이터에서 나왔는가'를 기록한다.

백테스트 숫자는 코드 버전·설정·데이터 어느 하나만 바뀌어도 조용히 달라진다.
리포트 옆에 매니페스트(JSON)를 남겨 두면 "그때 그 샤프가 왜 지금 재현이 안
되지?"를 추적할 근거가 생긴다. 표준 라이브러리만 사용한다(pandas 불필요).

⚠️ 매니페스트는 재현 '가능성'을 돕는 기록일 뿐이다. 기록된 성과가 미래에
재현된다는 보장이 아니며, 수익 보장은 더더욱 아니다.
"""
from __future__ import annotations

import hashlib
import os
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def data_checksum(index_first, index_last, n_rows, close_first, close_last) -> str:
    """데이터 지문(sha256 hex). pandas 없이 쓸 수 있게 스칼라만 받는다.

    전체 데이터를 해시하는 대신 (시작/끝 인덱스, 행 수, 시작/끝 종가)의 안정적
    repr 문자열을 해시한다 — '데이터가 바뀌었는가'를 싸게 감지하는 약식 지문이지,
    중간 행 변조까지 잡는 완전한 무결성 검증이 아니다. 인덱스는 str()로 넘기면
    (예: str(df.index[0])) 라이브러리 버전에 따른 repr 차이를 피할 수 있다.
    """
    payload = "|".join(_stable(v) for v in
                       (index_first, index_last, int(n_rows),
                        close_first, close_last))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _stable(v) -> str:
    """라이브러리 버전이 바뀌어도 같은 값이면 같은 글자 (감사 207).

    ⚠️ 예전에는 `repr(v)`를 그대로 썼다. 그런데 pandas에서 꺼낸 종가는
    `np.float64`이고, **numpy 2.x에서 그 repr이 바뀌었다**:

        float      repr → '100.0'
        np.float64 repr → 'np.float64(100.0)'      (numpy 1.x에서는 '100.0')

    즉 **numpy를 올리는 것만으로 같은 데이터의 지문이 달라진다.** 재현
    실패를 추적하라고 만든 도구가 "데이터가 바뀌었다"는 거짓 신호를 내는
    것이다 — 이 도구가 유일하게 하는 일이 그 판정인데.

    이 함수의 독스트링은 **인덱스에 대해서는 그 위험을 이미 알고 있었다**
    ("인덱스는 str()로 넘기면 라이브러리 버전에 따른 repr 차이를 피할 수
    있다"). 같은 위험이 종가에도 있는데 거기만 적혀 있었다 — 감사 200과
    같은 형태다: 무엇을 막는다고 적었으면 그 무엇이 지나는 문을 전부 셀 것.

    숫자는 파이썬 float로 정규화해 적고(`1`과 `1.0`도 같은 값으로 본다),
    나머지는 문자열로 적는다.
    """
    if isinstance(v, bool):
        return str(v)
    item = getattr(v, "item", None)          # numpy 스칼라 → 파이썬 값
    if callable(item):
        try:
            v = item()
        except Exception:  # noqa: BLE001
            pass
    if isinstance(v, (int, float)):
        f = float(v)
        return "nan" if f != f else repr(f)   # 1 과 1.0 을 같은 글자로
    return str(v)


def build_manifest(config: dict, df_meta: dict, results: dict,
                   created_utc: str | None = None) -> dict[str, Any]:
    """설정·데이터 메타·결과를 묶은 재현성 매니페스트 dict를 만든다.

    created_utc: ISO 문자열. 재현 검증 시 타임스탬프까지 고정하고 싶으면 호출자가
    직접 넘긴다. None이면 현재 UTC 시각을 쓴다.
    df_meta: {rows, start, end, checksum} — checksum은 data_checksum() 결과를
    넘기는 것을 권장한다. 없는 키는 None으로 기록해 '몰랐다'를 숨기지 않는다.
    """
    return {
        "created_utc": created_utc or datetime.now(timezone.utc)
                                              .isoformat(timespec="seconds"),
        "quant_version": _quant_version(),
        "python_version": platform.python_version(),
        "config": dict(config),
        "data": {
            "rows": df_meta.get("rows"),
            "start": df_meta.get("start"),
            "end": df_meta.get("end"),
            "checksum": df_meta.get("checksum"),
        },
        "results": dict(results),
    }


def _quant_version() -> str:
    from quant import __version__   # 순환 임포트 방지를 위해 지연 임포트

    return __version__


def save_manifest(path: str | os.PathLike, manifest: dict) -> Path:
    """매니페스트를 원자적으로 저장한다(atomic_write_json 재사용)."""
    from quant.utils.jsonio import atomic_write_json

    atomic_write_json(path, manifest)
    return Path(path)
