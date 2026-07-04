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

    포함: 오늘 사이클 수 · 최근 적중률 · 자산 · 포지션 · 마지막 에러.
    어떤 키가 없어도 예외 없이 'N/A' 등으로 대체한다.
    """
    state = state if isinstance(state, dict) else {}
    day = today or _today_utc()
    history = state.get("history")
    history = history if isinstance(history, list) else []
    cycles = sum(1 for h in history
                 if isinstance(h, dict) and str(h.get("time", "")).startswith(day))
    last = history[-1] if history and isinstance(history[-1], dict) else {}
    hit = last.get("recent_hit_rate", last.get("hit_rate"))
    err = state.get("last_error")
    return (
        f"📋 일일 요약({day} UTC) [{state.get('symbol', '?')}"
        f" · {state.get('strategy', '?')} · {state.get('mode', '?')}]: "
        f"오늘 사이클 {cycles}회 · 최근 적중률 {_fmt_pct(hit)} · "
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
    return t, build_daily_summary(state, today=t)


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
