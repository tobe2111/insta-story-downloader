"""일일 요약 알림 — UTC 날짜가 바뀔 때 하루 한 번 상태를 한 문단으로 통지한다.

알림기(notifier)가 설정된 경우에만 동작하며, 없으면 아무 동작도 하지 않는다
(기본 동작 무변화). 순수 stdlib — 상태 dict만 읽으므로 pandas가 필요 없다.

⚠️ 정직한 안내: 이 요약은 '기록의 보고'일 뿐 수익 보장이 아니다. 적중률과
자산은 오르내리는 게 정상이며, 요약이 좋아 보인다고 미래 수익이 보장되지 않는다.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from quant.robustness.accuracy import hit_rate_text


def _today_utc() -> str:
    """오늘의 UTC 날짜 문자열(YYYY-MM-DD)."""
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


def _fmt_pct(v) -> str:
    """적중률 등 비율을 퍼센트 문자열로(숫자가 아니면 'N/A')."""
    try:
        f = float(v)
        if f != f:                      # NaN
            return "N/A"
        return f"{f:.1%}"
    except (TypeError, ValueError):
        return "N/A"


def _fmt_num(v) -> str:
    try:
        return f"{float(v):,.2f}"
    except (TypeError, ValueError):
        return "N/A"


def _positions_text(state: dict) -> str:
    """단일(position) / 다중(positions) 상태 모두에서 보유 요약을 만든다."""
    items = []
    multi = state.get("positions")
    if isinstance(multi, list):
        items = [p for p in multi if isinstance(p, dict)]
    else:
        single = state.get("position")
        if isinstance(single, dict):
            items = [single]
    parts = []
    for p in items:
        qty = p.get("quantity") or 0
        try:
            if abs(float(qty)) < 1e-12:
                continue
        except (TypeError, ValueError):
            continue
        parts.append(f"{p.get('symbol', '?')} {float(qty):.6f}")
    return ", ".join(parts) if parts else "없음"


def build_daily_summary(state: dict, today: str | None = None) -> str:
    """상태 dict에서 한국어 한 문단 일일 요약을 만든다(누락 키에 안전).

    today: **요약 대상 날짜**(보내는 날이 아니라). 롤오버 알림은 끝난 날을
    넘긴다 — 감사 193 참고.

    포함: 그 날의 사이클 수 · 최근 적중률 · 자산 · 포지션 · 마지막 에러.
    어떤 키가 없어도 예외 없이 'N/A' 등으로 대체한다.
    """
    state = state if isinstance(state, dict) else {}
    day = today or _today_utc()
    history = state.get("history")
    history = history if isinstance(history, list) else []
    same_day = [h for h in history
                if isinstance(h, dict) and str(h.get("time", "")).startswith(day)]
    cycles = len(same_day)
    # ⚠️ **그 날의 마지막 기록을 쓴다**(감사 193). 예전에는 `history[-1]`,
    #    즉 **전체에서 가장 최근** 기록을 썼다. 요약은 날짜가 바뀐 직후에
    #    보내지므로 그 시점의 마지막 기록은 이미 **다음 날 것**이다 —
    #    "07-04 요약"이라고 적어 놓고 07-05의 자산·적중률을 실었다.
    #    그 날에 기록이 하나도 없으면 전체 마지막으로 폴백한다(없는 것보다 낫다).
    last = same_day[-1] if same_day else (
        history[-1] if history and isinstance(history[-1], dict) else {})
    # 적중률은 **표본이 감당하는 만큼만** 말한다 — 구간이 50%를 품으면
    # "판정 불가"로 나간다. 서식 규칙은 robustness/accuracy.py 한 곳에 있다.
    _r = last.get("recent_hit_rate")
    hit_txt = (hit_rate_text(last, key="recent_hit_rate", n_key="recent_n")
               if isinstance(_r, (int, float)) and _r == _r
               else hit_rate_text(last, key="hit_rate", n_key="n"))
    err = state.get("last_error")
    return (
        f"📋 일일 요약({day} UTC) [{state.get('symbol', '?')}"
        f" · {state.get('strategy', '?')} · {state.get('mode', '?')}]: "
        f"오늘 사이클 {cycles}회 · 최근 적중률 {hit_txt} · "
        f"자산 {_fmt_num(last.get('equity'))} · 포지션 {_positions_text(state)} · "
        f"마지막 에러 {err if err else '없음'}"
    )


def maybe_daily_summary(state: dict, last_date: str | None,
                        today: str | None = None) -> tuple[str, str | None]:
    """UTC 날짜가 롤오버됐으면 (오늘날짜, 요약문)을, 아니면 (오늘날짜, None)을 반환.

    last_date가 None이면(첫 사이클/재시작 직후 상태 없음) 보내지 않고 날짜만
    기록한다 — 재시작할 때마다 요약이 중복 전송되는 것을 막는다.
    """
    t = today or _today_utc()
    if last_date is None or last_date == t:
        return t, None
    # ⚠️ **끝난 날을 요약한다**(감사 193). 예전에는 `today=t`를 넘겨 **막 시작한
    #    날**을 요약했다. 이 함수는 날짜가 바뀐 **직후** 불리므로 새 날에는
    #    기록이 0~1건뿐이다 — 실측: 08-12에 3사이클을 돌고 롤오버했는데
    #    "일일 요약(2026-08-13): 오늘 사이클 1회"가 나갔다.
    #
    #    하루를 마감하는 보고인데 **아직 시작도 안 한 날**을 보고한 셈이다.
    #    어제가 아무리 바빴어도 늘 0~1회로 찍혀, 이 알림을 받는 사람은
    #    "봇이 거의 안 돌았다"고 읽는다.
    return t, build_daily_summary(state, today=last_date)


def load_last_summary_date(state_path: str | None) -> str | None:
    """기존 state 파일에서 last_summary_date를 읽는다(없거나 손상돼도 None).

    파일이 손상됐어도(크래시 중 등) 예외 없이 None으로 폴백해 러너 시작을
    막지 않는다 — 최악의 경우 요약이 하루 건너뛸 뿐이다.
    """
    if not state_path:
        return None
    try:
        data = json.loads(Path(state_path).read_text(encoding="utf-8"))
        v = data.get("last_summary_date") if isinstance(data, dict) else None
        return v if isinstance(v, str) else None
    except Exception:  # noqa: BLE001 - 누락·손상 모두 조용히 폴백
        return None


def notify_daily_summary(trader) -> None:
    """러너 루프에서 매 사이클 호출 — 알림기가 있고 UTC 날짜가 바뀌었으면 전송.

    trader에 notifier가 없으면 즉시 반환한다(기본 동작 무변화). 요약 관련
    오류는 모두 삼켜 매매 루프를 절대 멈추지 않는다.
    """
    if getattr(trader, "notifier", None) is None:
        return
    try:
        state = trader.snapshot() if hasattr(trader, "snapshot") else {}
        new_date, text = maybe_daily_summary(
            state, getattr(trader, "_last_summary_date", None))
        trader._last_summary_date = new_date
        if text:
            trader.notifier.send(text)
            if getattr(trader, "state_path", None):
                trader._persist()          # last_summary_date를 즉시 저장
    except Exception:  # noqa: BLE001 - 요약 실패가 매매를 멈추면 안 된다
        pass
