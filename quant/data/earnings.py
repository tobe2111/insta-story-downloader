"""실적 발표 캘린더 가드 — 예고된 종목별 이벤트 창에서 비중을 줄인다.

FOMC 가드(quant/events)와 같은 원리를 종목 단위로: 실적 발표일 전후는
갭 위험이 평소의 몇 배라, 하루짜리 방향 모델의 엣지가 가장 약한 날이다.
발표 ±pad_days 창에서는 비중을 절반으로 줄인다(관망이 아니라 절반 —
발표가 좋은 쪽일 확률도 절반이므로 전면 회피는 과잉 반응이다).

재현성: 조회한 발표일은 state/earnings.json에 캐시되어 그날의 판단 근거가
파일로 남고, 일별 기록에도 어떤 날짜로 가드가 발동했는지 함께 적힌다 —
"그날 왜 비중이 절반이었나"를 장부만으로 답할 수 있다.

야후(yfinance) 캘린더는 미국 주식만 안정적이다 — 한국 주식·코인은 조회가
비어 그냥 가드 미발동(무해). 조회 실패도 미발동(실패가 매매를 막으면 안 됨).
"""
from __future__ import annotations

import datetime as _dt
import json
import os

from quant.utils.logging import get_logger

log = get_logger("data.earnings")

CACHE_FILE = "earnings.json"
REFRESH_DAYS = 7          # 캐시 신선도 — 발표일은 주 단위로만 움직인다
GUARD_FACTOR = 0.5        # 가드 발동 시 비중 배수
PAD_DAYS = 1              # 발표일 ±N일 창


def _fetch_dates(symbol: str) -> list[str]:
    """야후에서 (미래 포함) 실적 발표일 목록을 ISO 문자열로 받는다."""
    import yfinance as yf
    df = yf.Ticker(symbol).get_earnings_dates(limit=8)
    if df is None or df.empty:
        return []
    out = []
    for ts in df.index:
        try:
            out.append(ts.date().isoformat())
        except AttributeError:
            continue
    return sorted(set(out))


def next_earnings_date(symbol: str, today: _dt.date,
                       state_dir: str = "state",
                       fetch=_fetch_dates) -> _dt.date | None:
    """오늘 이후(오늘 포함) 가장 가까운 실적 발표일. 모르면 None.

    state/earnings.json에 심볼별 {dates, fetched}로 캐시하고 REFRESH_DAYS마다
    갱신한다 — 하루 20종목 순회가 야후를 반복 호출하지 않게, 그리고 그날
    판단에 쓴 캘린더가 파일로 남게(재현성).
    """
    path = os.path.join(state_dir, CACHE_FILE)
    cache: dict = {}
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                cache = json.load(f)
    except (OSError, ValueError):
        cache = {}
    entry = cache.get(symbol)
    fresh = False
    if entry and entry.get("fetched"):
        try:
            age = (today - _dt.date.fromisoformat(entry["fetched"])).days
            fresh = 0 <= age <= REFRESH_DAYS
        except ValueError:
            fresh = False
    if not fresh:
        try:
            dates = fetch(symbol)
        except Exception as exc:  # noqa: BLE001 — 조회 실패 = 가드 미발동(무해)
            log.warning("실적 캘린더 조회 실패 %s: %s", symbol, exc)
            dates = (entry or {}).get("dates", [])   # 옛 캐시라도 쓴다
        entry = {"dates": dates, "fetched": today.isoformat()}
        cache[symbol] = entry
        try:
            from quant.utils.jsonio import atomic_write_json
            atomic_write_json(path, cache)
        except Exception:  # noqa: BLE001 — 캐시 실패가 판단을 막으면 안 된다
            pass
    for iso in entry.get("dates", []):
        try:
            d = _dt.date.fromisoformat(iso)
        except ValueError:
            continue
        if d >= today:
            return d
    return None


def earnings_guard_factor(symbol: str, asof: _dt.date,
                          state_dir: str = "state",
                          pad_days: int = PAD_DAYS,
                          fetch=_fetch_dates) -> tuple[float, str | None]:
    """(비중 배수, 발동 사유 날짜) — 발표 ±pad_days 창이면 (0.5, 날짜)."""
    try:
        d = next_earnings_date(symbol, asof, state_dir, fetch=fetch)
    except Exception as exc:  # noqa: BLE001
        log.warning("실적 가드 판단 실패 %s: %s", symbol, exc)
        return 1.0, None
    if d is not None and abs((d - asof).days) <= pad_days:
        return GUARD_FACTOR, d.isoformat()
    return 1.0, None
