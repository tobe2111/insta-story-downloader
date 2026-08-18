"""수동 킬스위치 — 사장님이 조종석에서 전체 매매를 즉시 멈추는 스위치.

사장님이 공유한 구축 사례(2026-08-18)에서 채택한 안전장치다. 지금 있는
브레이크(킬스위치·서킷브레이커)는 전부 **자동**이라, 자동 장치가 못 보는
이상 — 뉴스로만 알 수 있는 사고, 데이터가 이상하다는 직감 — 을 사람이
먼저 봤을 때 누를 것이 없었다.

동작 원칙:
- **정지는 한 번에, 해제는 확인을 거쳐** — 급할 때 바로 눌러야 하는 건
  정지 쪽이고, 실수로 눌러도 큰일 나는 건 해제 쪽이다.
- 정지 상태에서 매매 배치(일일 페이퍼·통합 계좌·장중 실험)는 **아무 주문도
  내지 않고, 장부도 건드리지 않는다.** 기록이 없는 날이 아니라 "사장님이
  멈춘 날"임을 status.json에 남긴다 — 조용한 공백은 고장과 구별이 안 된다.
- 모든 켜고 끔은 시각·사유와 함께 이력에 남는다. 스위치가 언제 왜
  눌렸는지는 나중에 성적을 읽을 때 반드시 필요한 각주다.

⚠️ 이 스위치는 **멈추기만** 한다 — 보유 포지션을 강제 청산하지 않는다.
   청산 여부는 사람이 판단할 문제이고, 자동 청산은 그 자체가 새 위험이다
   (폭락장 바닥에서 다 팔아 버리는 스위치가 된다).
"""
from __future__ import annotations

import datetime as dt
import json
import os

FILE = "manual_halt.json"
# 해제는 이 단어를 정확히 타이핑해야 한다 — 클릭 실수로 재개되지 않게.
RESUME_WORD = "재개"


def _path(state_dir: str) -> str:
    return os.path.join(state_dir, FILE)


def status(state_dir: str = "state") -> dict | None:
    """켜져 있으면 {"on": True, "at": ..., "who": ..., "reason": ...}, 꺼져 있으면 None.

    파일이 없거나 깨져 있으면 **꺼짐**으로 본다 — 이 스위치는 사람이 의도를
    갖고 켜는 장치라, 애매함이 매매를 멈추면 고장이 정지로 위장하게 된다.
    """
    try:
        with open(_path(state_dir), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict) or not d.get("on"):
        return None
    return {"on": True, "at": d.get("at"), "who": d.get("who"),
            "reason": d.get("reason")}


def set_halt(state_dir: str, on: bool, *, who: str = "cockpit",
             reason: str = "") -> dict:
    """스위치를 켜거나 끈다. 매번 이력에 남는다."""
    from quant.utils.jsonio import atomic_write_json
    path = _path(state_dir)
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        if not isinstance(d, dict):
            d = {}
    except (OSError, ValueError):
        d = {}
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    d.update({"on": bool(on), "at": now, "who": str(who),
              "reason": str(reason or "")})
    hist = d.get("history")
    if not isinstance(hist, list):
        hist = []
    hist.append({"on": bool(on), "at": now, "who": str(who),
                 "reason": str(reason or "")})
    d["history"] = hist[-200:]
    os.makedirs(state_dir, exist_ok=True)
    atomic_write_json(path, d)
    return d


def gate_message(state_dir: str = "state") -> str | None:
    """정지 중이면 배치가 찍을 한 줄, 아니면 None — CLI 관문이 부른다."""
    st = status(state_dir)
    if not st:
        return None
    why = f" · 사유: {st['reason']}" if st.get("reason") else ""
    return (f"🛑 수동 킬스위치가 켜져 있습니다({st.get('at')}, "
            f"{st.get('who')}{why}) — 오늘 매매를 건너뜁니다. "
            f"해제는 조종석의 긴급 정지 화면에서.")
