"""13F 오버레이 세기를 **증거로** 정한다 — 사람이 손으로 크게 잡지 않는다.

사장님 지시(2026-09-23): *"13F의 영향을 상당히 크게 비중을 두는게 좋을듯."*
방침(2026-08-27): *"투자 로직은 기계가 개선한다 — 너가 수동으로 고치는 방향
말고."* 그래서 세기의 상한만 크게 열고(quant.live.thirteenf_overlay), **얼마를
쓸지는 여기서 과거 기록의 실제 성적으로 정한다.**

무엇을 재나 — point-in-time 겹쳐 담기 앞선 성적:
  각 13F 제출일(공개된 날) 시점에, 그 날 공개돼 있던 겹쳐 담긴 종목들이
  그 뒤 horizon일 동안 **나머지 유니버스보다 더 올랐나**를 잰다. 제출일을
  기준으로 삼아 미래를 훔쳐보지 않는다(보고 기준일이 아니라 제출일).

정직한 한계:
  · 과거 13F 시계열과 일봉이 있어야 잰다. 이 컨테이너는 EDGAR·시세가 막혀
    있어 **프로덕션(야간)에서만** 실측하고, 여기·검사에서는 주입 데이터로 돈다.
  · 재료가 모자라면(관측 < 문턱) choose_strength가 **중립(0.15)**을 돌려준다 —
    못 잰 것을 큰 확신으로 읽지 않는다. 낡은 참고에 믿음만으로 크게 걸지 않는다.
  · 여기서 잰 것은 '오버레이가 트랙 수익을 얼마 올렸나'가 아니라 '겹쳐 담기에
    앞선 성적이 있나'다 — 후자가 있어야 전자를 걸 자격이 생긴다.
"""
from __future__ import annotations

import json
import math
import os

from quant.live.thirteenf_overlay import NEUTRAL_BONUS, choose_strength
from quant.utils.logging import get_logger

log = get_logger("live.thirteenf_tune")

STRENGTH_FILE = "thirteenf_strength.json"
HORIZON_DAYS = 21          # 약 한 달(거래일) — 분기 신호에 맞는 보유 지평
CLUSTER_MIN = 1            # 저명 투자자 1명 이상이 든 종목을 '겹쳐 담김'으로


def _forward_return(bars: list, as_of: str, horizon: int) -> float | None:
    """제출일 이후 첫 봉에 들어가 horizon봉 뒤에 나왔을 때의 수익률.

    bars = [(date_str, close)] 오름차순. 미래 봉이 모자라면 None(못 잰다).
    """
    d = str(as_of)[:10]
    entry_i = None
    for i, (bd, _px) in enumerate(bars):
        if str(bd)[:10] >= d:
            entry_i = i
            break
    if entry_i is None or entry_i + horizon >= len(bars):
        return None
    p0 = bars[entry_i][1]
    p1 = bars[entry_i + horizon][1]
    if not (p0 and p1) or p0 <= 0:
        return None
    return p1 / p0 - 1.0


def measure_edge(history: list, price_lookup, universe: list, *,
                 horizon: int = HORIZON_DAYS, cluster_min: int = CLUSTER_MIN) -> dict:
    """겹쳐 담긴 종목이 그 뒤 나머지보다 더 올랐나 — {mean_diff, t, n}.

    price_lookup(sym) -> [(date, close)] 오름차순 또는 None(시세 없음).

    ⚠️ **관측 단위는 날짜(제출일)다** — 패널 관문과 같은 원칙(quant/live/
       panel_gate: "종목 수로 날짜 수를 대신할 수 없다"). 한 제출일에서 겹쳐
       담긴 종목들의 평균 앞선 성적에서 나머지의 평균을 뺀 값이 **관측 하나**다.
       종목 하나하나를 관측으로 세면, 같은 날 같은 시장에 있는 종목들이
       서로 얽혀 t가 거짓으로 커진다. 그리고 분기 제출은 서로 겹치지 않는
       창이라 날짜끼리는 대체로 독립이다. n은 두 그룹이 모두 있는 **날짜 수**다.
    """
    prices = {}
    for sym in universe:
        try:
            bars = price_lookup(sym)
        except Exception:  # noqa: BLE001 — 한 종목 실패가 측정을 못 죽인다
            bars = None
        if bars:
            prices[sym] = list(bars)

    per_date: list[float] = []
    for row in (history or []):
        as_of = row.get("as_of")
        cl = row.get("cluster") or {}
        c_rets, o_rets = [], []
        for sym in universe:
            bars = prices.get(sym)
            if not bars:
                continue
            r = _forward_return(bars, as_of, horizon)
            if r is None:
                continue
            info = cl.get(sym)
            held = isinstance(info, dict) and int(info.get("count") or 0) >= cluster_min
            (c_rets if held else o_rets).append(r)
        if c_rets and o_rets:               # 두 그룹이 모두 있어야 그날 잰다
            per_date.append(sum(c_rets) / len(c_rets) - sum(o_rets) / len(o_rets))

    k = len(per_date)
    if k == 0:
        return {"mean_diff": 0.0, "t": 0.0, "n": 0}
    mean_diff = sum(per_date) / k
    if k < 2:
        return {"mean_diff": mean_diff, "t": 0.0, "n": k}
    var = sum((x - mean_diff) ** 2 for x in per_date) / (k - 1)
    se = math.sqrt(var / k)
    t = mean_diff / se if se > 0 else 0.0
    return {"mean_diff": mean_diff, "t": t, "n": k, "horizon": horizon}


def _strength_path(state_dir: str) -> str:
    return os.path.join(state_dir, STRENGTH_FILE)


def load_strength(state_dir: str = "state") -> float:
    """트랙이 쓸 오버레이 세기. 튜너가 안 돌았으면 중립(0.15)."""
    try:
        with open(_strength_path(state_dir), encoding="utf-8") as f:
            v = float((json.load(f) or {}).get("strength"))
        return v if v >= 0.0 else NEUTRAL_BONUS
    except (OSError, ValueError, TypeError):
        return NEUTRAL_BONUS


def _default_price_lookup(limit: int = 800):
    """프로덕션 일봉 조회기 — 합성 폴백이면 None(가짜로 재지 않는다)."""
    from quant.data.stock import StockDataProvider

    def lookup(sym: str):
        df = StockDataProvider("us_stock").get_ohlcv(sym, timeframe="1d",
                                                     limit=limit)
        if (df is None or len(df) == 0 or not df.attrs.get("source")
                or df.attrs.get("synthetic_fallback")):
            return None
        return [(str(idx)[:10], float(c))
                for idx, c in zip(df.index, df["close"])]
    return lookup


def run_tune(state_dir: str = "state", *, fetch=None, price_lookup=None,
             filers: dict | None = None, universe: list | None = None,
             history: list | None = None) -> dict:
    """이력 새로고침 → 앞선 성적 측정 → 세기 결정 → 상태에 기록.

    주입(fetch/price_lookup/history)은 검사용. 실전 기본값은 EDGAR·일봉이다.
    어떤 실패도 중립으로 떨어진다 — 재료가 없다고 매매가 멈추면 안 된다.
    """
    from quant.data.thirteenf import (SYMBOL_ISSUERS, load_history,
                                       refresh_history)

    if universe is None:
        universe = list(SYMBOL_ISSUERS)
    if history is None:
        if fetch is not None:
            history = refresh_history(state_dir, fetch=fetch, filers=filers)
        else:
            try:
                history = refresh_history(state_dir, filers=filers)
            except Exception as exc:  # noqa: BLE001
                log.info("13F 이력 새로고침 실패(무해): %s", exc)
                history = load_history(state_dir)
    lookup = price_lookup or _default_price_lookup()
    try:
        edge = measure_edge(history, lookup, universe)
    except Exception as exc:  # noqa: BLE001
        log.info("13F 앞선 성적 측정 실패(무해): %s", exc)
        edge = {"mean_diff": 0.0, "t": 0.0, "n": 0}
    chosen = choose_strength(edge)
    out = {"strength": chosen["bonus"], "evidence": chosen,
           "history_points": len(history or [])}
    try:
        os.makedirs(state_dir, exist_ok=True)
        from quant.utils.jsonio import atomic_write_json
        atomic_write_json(_strength_path(state_dir), out)
    except Exception as exc:  # noqa: BLE001
        log.info("13F 세기 저장 실패(무해): %s", exc)
    log.info("🇺🇸 13F 오버레이 세기 = %.2f (%s)", chosen["bonus"], chosen["why"])
    return out
