"""판정이 나면 **사람 없이** 적용한다 — 채택 원장.

사장님 지시(2026-08-25): *"판정을 하면 이제 너가 조정을 하는게 아니라
머신러닝측에서 하게끔 해줘. 가능할까?"*

가능하다. 다만 먼저 **손잡이**가 있어야 했다.

■ 지금까지 무엇이 빠져 있었나

이 저장소에는 이미 셋이 다 있었다:

    사전 등록 원장(prereg)   — 무엇을 언제 어떤 통계로 판정할지
    판정 엔진(sequential)     — 경계를 넘으면 조기 판정까지
    화면                      — 진도와 판정을 그대로 공개

그런데 **판정이 나도 아무것도 안 바뀐다.** `sequential_status()`는
`status["sequential"]`에 실려 화면에 그려질 뿐이고, 실제 조정은 사람이
코드를 고쳐서 했다. 배분 방식만 해도 `hrp or erc or equal`이라는 고정
순서가 코드에 박혀 있어, "ERC가 이겼다"는 판정이 나도 손댈 곳이 없었다.

그래서 이 파일이 하는 일은 둘이다:

  ① **손잡이를 만든다** — 채택된 선택을 장부(state/adopted.json)에 두고
     운영 코드가 그것을 읽게 한다. 기본값은 **오늘의 동작 그대로**라,
     아무 판정도 없으면 아무것도 안 바뀐다.
  ② **판정을 그 손잡이에 연결한다** — 판정이 나면 사전에 등록해 둔 조치가
     자동으로 걸린다.

■ 조치는 **판정 전에** 등록한다 (이게 전부다)

`ACTIONS`는 "이기면 무엇을 할지"를 미리 적어 둔 표다. 결과를 보고 나서
정하면 그건 사전 등록이 아니라 사후 합리화다 — 우리가 그토록 걸러낸
'운 좋은 승자'를 만드는 방식이고, 이 제품의 정체성을 무너뜨린다.

기존 원장에는 `on_fail`("지면 현행 유지")만 있고 `on_win`이 없었다. 없는
쪽이 바로 사람이 끼어들던 자리다.

■ 자동으로 하지 않는 것

되돌리기 어려운 것은 자동으로 안 한다. 이건 소심함이 아니라 경계다:

    실거래 개시 · 원금 변경 · 판매 상태 변경

CLAUDE.md가 이 셋에 사용자 확인을 요구한다(법률 검토와 얽혀 있다). 판정이
나면 **적용 대신 알린다.** 조용히 넘기지 않는다 — 판정이 났는데 아무 말도
없으면 아무도 모른다.

■ 지키는 것

  · **한 번만 적용한다.** 같은 판정이 매일 다시 걸리면 장부가 뒤집힌다.
  · **과거는 고치지 않는다.** 채택은 그 시점부터 유효하고, 그 이전 기록은
    옛 규칙으로 남는다. 채택 사실과 근거를 원장에 적어 공개한다.
  · **적용 못 한 판정도 남긴다.** 이유와 함께.
"""
from __future__ import annotations

import json
import os

LEDGER = "adopted.json"

# ── 사전 등록된 조치 ─────────────────────────────────────────────
#
# key      : 판정 엔진이 쓰는 비교 이름(sequential_status의 pairs 키)
# knob     : 이 판정이 돌릴 손잡이 이름
# on_win   : 그 비교에서 **도전 쪽이 이겼을 때** 손잡이에 넣을 값
# on_lose  : 졌을 때(= 현행이 이겼을 때). 보통 현행 유지라 None이다.
# why      : 사람이 읽을 한 줄
# manual   : True면 자동 적용 금지 — 판정만 알리고 사람이 결정한다
ACTIONS = {
    "alloc:hrp-erc": {
        "knob": "alloc_method", "on_win": "erc", "on_lose": None,
        "why": "자본을 나누는 방식을 ERC(위험 균등)로 바꿉니다",
    },
    "alloc:hrp-equal": {
        "knob": "alloc_method", "on_win": "equal", "on_lose": None,
        "why": "자본을 나누는 방식을 균등 분할로 바꿉니다",
    },
    "alloc:hrp-inv_vol": {
        "knob": "alloc_method", "on_win": "inv_vol", "on_lose": None,
        "why": "자본을 나누는 방식을 변동성 역가중으로 바꿉니다",
    },
}

# 손잡이의 기본값 — **오늘의 동작 그대로**다. 판정이 없으면 아무것도
# 안 바뀐다. 이 표가 없으면 "채택 원장이 비었다"가 "설정이 없다"가 되고,
# 그 순간 운영 코드가 무엇을 해야 할지 모르게 된다.
DEFAULTS = {
    "alloc_method": "hrp",
}

# 자동으로 절대 하지 않는 일 — CLAUDE.md가 사용자 확인을 요구한다.
NEVER_AUTOMATIC = ("실거래 개시", "원금 변경", "판매 상태 변경")


def _path(state_dir: str) -> str:
    return os.path.join(state_dir, LEDGER)


def _load(state_dir: str) -> dict:
    try:
        with open(_path(state_dir), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def current(state_dir: str = "state") -> dict:
    """지금 유효한 손잡이 값들. 채택된 적 없으면 **기본값**(= 오늘의 동작).

    ⚠️ 못 읽어도 기본값을 준다. 장부가 깨졌다고 운영이 멈추면 안 되고,
       무엇보다 **알 수 없는 상태로 돌면 안 된다** — 모를 때는 원래
       하던 대로 하는 것이 맞다.
    """
    out = dict(DEFAULTS)
    for knob, rec in (_load(state_dir).get("knobs") or {}).items():
        if knob not in DEFAULTS:
            continue        # 모르는 손잡이는 무시한다 — 넘겨짚지 않는다
        v = (rec or {}).get("value") if isinstance(rec, dict) else rec
        if v is not None:
            out[knob] = v
    return out


def history(state_dir: str = "state") -> list:
    """채택 이력 — 언제 무엇을 왜 바꿨나. 화면이 그대로 읽는다."""
    h = _load(state_dir).get("history")
    return list(h) if isinstance(h, list) else []


def _won(v: dict) -> bool | None:
    """이 판정이 도전 쪽의 승리인가. 아직이면 None.

    ⚠️ 진행 중·표본 부족은 **패배가 아니다.** 둘을 같게 다루면 아직 안 끝난
       실험을 진 것으로 치고 현행을 굳혀 버린다.
    """
    s = str((v or {}).get("state") or "")
    if s.startswith("조기 판정: 우세"):
        return True
    if s.startswith("조기 판정: 열세"):
        return False
    return None


def pending(state_dir: str = "state", status: dict | None = None) -> list:
    """지금 적용해야 할 판정들 — 이미 적용한 것은 빠진다."""
    if status is None:
        from quant.live.sequential import sequential_status
        status = sequential_status(state_dir) or {}
    done = {r.get("key") for r in history(state_dir)}
    out = []
    for key, v in sorted((status.get("pairs") or {}).items()):
        act = ACTIONS.get(key)
        if not act or key in done:
            continue
        won = _won(v)
        if won is None:
            continue            # 아직 판정 안 났다
        value = act["on_win"] if won else act["on_lose"]
        out.append({"key": key, "won": won, "knob": act["knob"],
                    "value": value, "why": act["why"],
                    "manual": bool(act.get("manual")),
                    "evidence": {k: v.get(k) for k in
                                 ("state", "n", "sum", "boundary",
                                  "mean_daily_pct")}})
    return out


def apply_verdicts(state_dir: str = "state", *, now: str,
                   status: dict | None = None) -> dict:
    """판정을 손잡이에 **실제로** 건다. 돌려주는 것은 무엇을 했는지.

    ⚠️ `now`를 받는다 — 시계를 직접 읽지 않는다. 그래야 검사가 시점을
       고정할 수 있고, 기록이 재현된다.
    """
    todo = pending(state_dir, status)
    d = _load(state_dir)
    knobs = dict(d.get("knobs") or {})
    hist = list(d.get("history") or [])
    applied, held = [], []
    for item in todo:
        rec = {"key": item["key"], "at": str(now), "won": item["won"],
               "knob": item["knob"], "why": item["why"],
               "evidence": item["evidence"]}
        if item["manual"]:
            # 되돌리기 어려운 일 — 판정만 알리고 사람이 결정한다.
            rec["applied"] = False
            rec["reason"] = ("자동 적용 대상이 아닙니다 — "
                             + " · ".join(NEVER_AUTOMATIC)
                             + "은 사람이 확인합니다")
            held.append(rec)
        elif item["value"] is None:
            # 도전이 졌다 — 현행 유지. **그래도 기록은 남긴다.**
            rec["applied"] = False
            rec["reason"] = "도전이 졌습니다 — 현행을 유지합니다"
            applied.append(rec)
        else:
            knobs[item["knob"]] = {"value": item["value"], "since": str(now),
                                   "by": item["key"]}
            rec["applied"] = True
            rec["value"] = item["value"]
            applied.append(rec)
        hist.append(rec)
    if todo:
        from quant.utils.jsonio import atomic_write_json
        os.makedirs(state_dir, exist_ok=True)
        atomic_write_json(_path(state_dir),
                          {"knobs": knobs, "history": hist})
    return {"applied": applied, "held": held, "knobs": current(state_dir)}


def public(state_dir: str = "state") -> dict:
    """화면이 읽을 재료 — 지금 값, 이력, 그리고 **자동으로 안 하는 것**."""
    return {
        "knobs": current(state_dir),
        "defaults": dict(DEFAULTS),
        "history": history(state_dir)[-20:],
        "never_automatic": list(NEVER_AUTOMATIC),
        "note": ("판정이 나면 사전에 등록해 둔 조치가 **사람 없이** "
                 "걸립니다. 조치는 결과를 보기 전에 정해 둔 것이며, "
                 "되돌리기 어려운 일은 자동으로 하지 않습니다."),
    }
