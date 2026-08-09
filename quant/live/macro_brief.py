"""오늘의 거시(FRED) — 사이트 표시 전용 요약.

판단(ML 피처)과 같은 원천(FRED, 발표 시차 보정)을 쓰되, 이 요약 자체는
표시 전용이다 — 매매를 바꾸지 않는다. FRED_API_KEY 없으면 None(사이트에
칸이 안 뜬다). 조회 실패도 None — 브리핑 실패가 기록을 막으면 안 된다.
"""
from __future__ import annotations

import os

from quant.utils.logging import get_logger

log = get_logger("macro_brief")

# (키, FRED id, 한글명, 단위) — 사이트가 그대로 렌더링한다
_ITEMS = [
    ("t10y2y", "T10Y2Y", "장단기 금리차", "%p"),
    ("hy_spread", "BAMLH0A0HYM2", "하이일드 스프레드", "%p"),
    ("usd_idx", "DTWEXBGS", "달러인덱스", ""),
    ("t10yie", "T10YIE", "10년 기대인플레", "%"),
]


def _interpret(vals: dict) -> str:
    """숫자를 한 줄 한국어로 — 해석이지 예측이 아니다."""
    parts = []
    t = vals.get("t10y2y", {}).get("value")
    if t is not None:
        parts.append("장단기 금리 역전(경기침체 신호)" if t < 0
                     else "금리 곡선 정상")
    hy = vals.get("hy_spread", {}).get("value")
    if hy is not None:
        parts.append("신용 경색 경보" if hy > 5.0
                     else "신용시장 안정" if hy < 3.5 else "신용 스트레스 보통")
    u = vals.get("usd_idx", {}).get("chg5_pct")
    if u is not None:
        parts.append("달러 강세(위험자산 역풍)" if u > 0.5
                     else "달러 약세(위험자산 순풍)" if u < -0.5 else "달러 보합")
    return " · ".join(parts)


def macro_summary() -> dict | None:
    """{"items": [{key,name,value,unit,date,chg5_pct?}...], "note": 해석} 또는 None."""
    if not os.getenv("FRED_API_KEY"):
        return None
    try:
        from quant.data.macro import fred_series
        vals: dict = {}
        items = []
        for key, sid, name, unit in _ITEMS:
            s = fred_series(sid)
            if s is None or s.empty:
                continue
            entry = {"key": key, "name": name, "unit": unit,
                     "value": round(float(s.iloc[-1]), 3),
                     "date": str(s.index[-1].date())}
            if key == "usd_idx" and len(s) > 5:
                entry["chg5_pct"] = round(
                    float(s.pct_change(5).iloc[-1]) * 100, 2)
            vals[key] = entry
            items.append(entry)
        if not items:
            return None
        return {"items": items, "note": _interpret(vals),
                "source": "FRED(세인트루이스 연준) · 발표 시차 보정"}
    except Exception as exc:  # noqa: BLE001
        log.warning("거시 요약 실패: %s", exc)
        return None
