"""같은 날을 **다시 기록할 수 있게** 하는 되돌림 지점 (2026-08-19 실측 사고).

⚠️ 무슨 일이 있었나. 2026-08-19, 사흘 멈췄던 배치를 살리려고 04:18 UTC에
   수동으로 한 번 돌렸다. 그날의 정규 밤 배치는 22:15/22:30이고, 과최적화
   검증 결과는 그 사이인 20:59에 도착했다. 그런데 밤 배치 두 번은 **정상
   성공했는데도 아무것도 바꾸지 못했다** — 멱등 가드가 "오늘 봉은 이미
   기록됨"이라며 통째로 건너뛴 것이다.

   결과: 그날 계좌는 **오후 1시의 낡은 검증**으로 비중을 정한 채 봉인됐다.
   같은 이유로 그날 머지된 유니버스 확대(20→45종목)도 반영되지 않았다.
   즉 **먼저 기록한 쪽이 이긴다** — 그게 더 나쁜 자료를 봤더라도.

   멱등 가드 자체는 옳다. 하루 두 번 도는 크론이 같은 봉을 두 줄로 적으면
   장부가 망가지고, 다시 돌리면 그날 매매가 **두 번** 일어나 비용이 두 배가
   된다. 그래서 "그냥 다시 돌리자"는 답이 아니다.

   답은 **되돌림 지점**이다. 새 봉의 계산을 시작하기 전에 계좌 상태(현금·
   보유·직전 비중 등)를 통째로 복사해 둔다. 나중에 같은 봉을 다시 돌려야
   하면 그 지점으로 되돌린 뒤 처음부터 계산한다 — 매매도 비용도 한 번이다.

   그리고 **아무 때나 다시 돌리지 않는다.** 다시 돌리는 유일한 조건은
   "판단의 재료가 실제로 새로 왔을 때"다(지금은 과최적화 검증 장부의 날짜).
   재료가 그대로면 예전처럼 조용히 건너뛴다.

원칙:
  · 되돌림 지목이 없거나 **다른 봉의 것**이면 되돌리지 않는다 — 추측하지
    않는다. 그때는 예전처럼 건너뛴다(안전한 쪽으로 실패).
  · 복사는 화이트리스트가 아니라 **history를 뺀 전체**다. 항목을 하나씩
    고르면 언젠가 새 필드가 빠지고, 그 빠짐은 돈이 틀리는 방식으로 드러난다.
  · 지난 날짜의 기록은 손대지 않는다. 되돌림은 **오늘 봉 한 줄**에만 쓴다.
"""
from __future__ import annotations

import copy
import json
import os

from quant.utils.logging import get_logger

log = get_logger("redo")

RESTORE_KEY = "_redo_point"
SKIP_KEYS = ("history", RESTORE_KEY)


def mark_restore_point(st: dict, bar) -> None:
    """이 봉의 계산을 시작하기 전 상태를 통째로 복사해 둔다."""
    snap = {k: copy.deepcopy(v) for k, v in st.items() if k not in SKIP_KEYS}
    st[RESTORE_KEY] = {"bar": str(bar), "state": snap}


def validation_stamp(state_dir: str) -> str:
    """검증 장부가 '언제 것'인가 — 가장 최근 asof + 종목 수.

    날짜만 보면 같은 날 2종목 → 20종목으로 늘어난 경우를 못 잡는다. 실제로
    2026-08-19이 그랬다(아침엔 2종목, 밤엔 20종목·같은 날짜).
    """
    try:
        path = os.path.join(state_dir, "validation.json")
        if not os.path.exists(path):
            return ""
        with open(path, encoding="utf-8") as f:
            val = json.load(f)
        if not isinstance(val, dict) or not val:
            return ""
        asof = max((str(v.get("asof") or "") for v in val.values()
                    if isinstance(v, dict)), default="")
        return f"{asof}/{len(val)}"
    except (OSError, ValueError) as exc:
        log.warning("검증 장부 지문을 읽지 못했다: %s", exc)
        return ""


def should_redo(st: dict, bar, state_dir: str) -> tuple[bool, str]:
    """같은 봉을 다시 기록해야 하는가 — (해야 하나, 사람이 읽을 이유).

    "그래야 한다"는 세 가지가 동시에 참일 때만이다:
      ① 되돌림 지점이 있고 **바로 이 봉**의 것이다
      ② 그때 쓴 검증 장부 지문이 기록돼 있다
      ③ 지금 장부 지문이 그것과 **다르다**(재료가 새로 왔다)
    """
    point = st.get(RESTORE_KEY) or {}
    if str(point.get("bar") or "") != str(bar) or not point.get("state"):
        return False, "되돌림 지점이 없다 — 다시 돌리지 않는다(추측 금지)"
    hist = st.get("history") or []
    used = str((hist[-1] or {}).get("validation_stamp") or "") if hist else ""
    if not used:
        return False, "오늘 기록이 어떤 검증 장부를 썼는지 남아 있지 않다"
    now = validation_stamp(state_dir)
    if not now or now == used:
        return False, "검증 장부가 그대로다 — 다시 돌릴 이유가 없다"
    return True, f"검증 장부가 바뀌었다({used} → {now}) — 오늘 기록을 다시 만든다"


def rewind(st: dict, bar) -> bool:
    """되돌림 지점으로 계좌를 되돌리고 오늘 기록 한 줄을 걷어낸다.

    되돌릴 수 없으면 **아무것도 건드리지 않고** False. 반쯤 되돌린 상태로
    계산을 시작하는 것이 가장 나쁘다.
    """
    point = st.get(RESTORE_KEY) or {}
    if str(point.get("bar") or "") != str(bar) or not point.get("state"):
        return False
    hist = list(st.get("history") or [])
    if hist and str((hist[-1] or {}).get("date") or "")[:10] == str(bar)[:10]:
        hist.pop()
    for k in list(st):
        if k not in SKIP_KEYS:
            del st[k]
    st.update(copy.deepcopy(point["state"]))
    st["history"] = hist
    st[RESTORE_KEY] = point
    return True
