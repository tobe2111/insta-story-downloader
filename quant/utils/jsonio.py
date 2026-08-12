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
    # ⚠️ 임시 이름에 **프로세스 번호**를 붙인다(감사 170). 고정 이름 ".tmp"를
    #    쓰면 같은 파일을 동시에 쓰는 두 프로세스가 **같은 임시 파일**을 밟는다
    #    — A가 쓰는 중에 B가 덮어쓰고, A가 os.replace를 하면 반쪽이 섞인 내용이
    #    원자적으로 '완성본'이 된다. 원자성이 지켜지는데 내용이 깨지는,
    #    가장 알아채기 어려운 형태다.
    #    (오늘 배치는 깃허브 액션에서 한 번에 하나씩 도니 지금 새는 곳은
    #     아니다. 학습 루프를 로컬에서 함께 돌리면 바로 닿는다.)
    tmp = p.with_name(f"{p.name}.{os.getpid()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)   # 같은 파일시스템에서 원자적 교체(부분 파일 노출 없음)
    except BaseException:
        # 쓰기/교체가 중간에 실패해도 원본은 그대로다(교체 전이므로).
        # 부분 임시파일만 치우고 예외는 그대로 올린다 — 손상 파일을 남기지 않는다.
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def cap_history(history: list) -> list:
    """history를 HISTORY_CAP 최근 항목으로 잘라 반환한다(제자리 축소 아님).

    ⚠️ 이것만 쓰면 잘려나간 과거가 통계에서도 사라진다. 요약 지표(총손익·
    최대낙폭)를 함께 쓰는 곳은 fold_history를 쓸 것.
    """
    if len(history) > HISTORY_CAP:
        return history[-HISTORY_CAP:]
    return history


def fold_history(history: list, summary: dict | None = None,
                 key: str = "equity", cap: int = HISTORY_CAP) -> tuple[list, dict]:
    """history를 자르되, **잘려나가는 구간을 요약에 접어 넣어** 함께 반환한다.

    왜 필요한가(2026-08-11 감사 ㊿): 감시 대시보드는 총손익을
    `equity[-1]/equity[0]-1`로, 최대낙폭을 남아 있는 equity 배열만 훑어
    계산했다. cap_history가 앞을 잘라내는 순간 이 두 숫자의 뜻이 조용히
    바뀐다 — 총손익은 '잘린 시점 이후 손익'이 되고, 최대낙폭은 **가장
    아팠던 구간이 밀려나면 저절로 좋아진다.** 위험 지표가 시간이 지나면
    스스로 개선되는 것은 지표가 아니라 위안이다.

    낙폭은 '지금까지의 최고점 대비'라는 누적 계산이라, 버리는 구간의
    (최초값·최고점·그때까지의 최저 낙폭) 셋만 들고 가면 전 구간 값을
    정확히 복원할 수 있다 — 근사가 아니라 등가다.

    반환: (잘린 history, 갱신된 요약)
      요약 = {"start": 최초 자산, "peak": 버린 구간까지의 최고 자산,
              "max_drawdown": 버린 구간까지의 최대 낙폭(≤0), "dropped": 버린 개수}
    """
    s: dict = dict(summary or {})
    if len(history) <= cap:
        return history, s
    n_drop = len(history) - cap
    start = s.get("start")
    peak = s.get("peak")
    max_dd = float(s.get("max_drawdown") or 0.0)
    for rec in history[:n_drop]:
        try:
            e = float(rec.get(key))
        except (AttributeError, TypeError, ValueError):
            continue
        if not math.isfinite(e):
            continue
        if start is None:
            start = e
        peak = e if peak is None else max(peak, e)
        if peak:
            max_dd = min(max_dd, e / peak - 1.0)
    s.update({"start": start, "peak": peak, "max_drawdown": max_dd,
              "dropped": int(s.get("dropped") or 0) + n_drop})
    return history[n_drop:], s
