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


def _last_resort(obj: Any) -> Any:
    """json이 모르는 값을 만났을 때 — **기록을 잃지 않는 쪽**으로 바꾼다.

    ⚠️ 왜 필요한가(감사 200). 이 모듈은 첫 줄부터 "NaN이 저장을 멈추는 것을
    막는다"고 적어 두고, 독스트링에 그 이유까지 남겼다 —
    *"allow_nan=False로 raise시키면 cycle의 except가 삼켜 저장이 아예 멈춘다."*

    그런데 **같은 except가 삼키는 다른 예외**는 막지 않고 있었다. 실측:

        float('nan')      → None      (설계대로 막힌다)
        np.float64('nan') → None      (float의 하위 클래스라 막힌다)
        np.float32(1.5)   → TypeError  ← 여기서 저장이 통째로 죽는다
        np.int64(7)       → TypeError
        np.bool_(True)    → TypeError
        pandas Timestamp  → TypeError
        datetime · Path   → TypeError

    `np.float64`가 통과하는 것이 특히 고약하다 — numpy 값이 들어와도 대개
    괜찮으니 안심하게 되는데, `float32`·`int64`·`bool_` 하나가 섞이는 날
    **그날 기록이 통째로 사라진다.** 지금은 `daily.py`가 필드마다 `float(...)`
    로 감싸 두어 실제로 새는 곳은 없다(2026-08-13 실제 실행으로 확인).
    하지만 그 방어는 필드를 추가하는 사람이 매번 기억해야 하는 종류다.

    막는 방향은 '거절'이 아니라 '보존'이다. 하루치 장부를 잃는 것보다
    값이 문자열로 남는 편이 낫다 — 다만 **조용히** 바뀌면 안 되므로 경고를
    남긴다. 숫자·시각은 뜻이 보존되게 바꾸고, 정말 모르는 것만 문자열로.
    """
    item = getattr(obj, "item", None)          # numpy 스칼라 → 파이썬 값
    if callable(item):
        try:
            return sanitize(item())
        except Exception:  # noqa: BLE001
            pass
    iso = getattr(obj, "isoformat", None)       # datetime · date · Timestamp
    if callable(iso):
        try:
            return iso()
        except Exception:  # noqa: BLE001
            pass
    if isinstance(obj, (set, frozenset)):
        return sorted(sanitize(v) for v in obj)
    from quant.utils.logging import get_logger
    get_logger("utils.jsonio").warning(
        "JSON으로 바꿀 수 없는 값을 문자열로 저장합니다(%s) — 기록을 잃지 "
        "않으려는 최후 수단입니다. 저장하는 쪽에서 형을 맞추세요: %.80r",
        type(obj).__name__, obj)
    return str(obj)


def atomic_write_json(path: str | os.PathLike, obj: Any, indent: int = 2) -> None:
    """obj를 NaN 안전하게 직렬화해 원자적으로 저장한다(임시파일 + os.replace)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    # default=_last_resort — sanitize가 못 거른 값에서 저장이 통째로 죽지
    # 않게 한다(감사 200). 이 모듈이 NaN을 막는 것과 같은 이유다: 예외는
    # 호출부의 except가 삼키고, 사라지는 것은 그날의 장부다.
    text = json.dumps(sanitize(obj), ensure_ascii=False, indent=indent,
                      default=_last_resort)
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
