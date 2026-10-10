"""엔진 선택을 **기계가** 한다 — 수익률로, 규칙은 결과보다 먼저 (감사 341).

사장님(2026-10-10): *"어떤 엔진을 선택할 지는 수익률에 따라서 머신러닝이
결정하는거지 그걸 내가 결정하는건 아닌 것 같아."*

2026-08-27 방침("투자 로직은 기계가 개선한다")이 엔진 단위까지 올라온 것이다.
엔진 교체(감사 335)는 사람이 했고, 그 뒤 "더 공격적인 엔진으로 갈지"를 다시
사람에게 물었다 — 그 질문 자체를 기계에게 넘긴다.

■ 무엇을 고르나 — 후보 여섯(`CANDIDATES`)

  모두 **지금 매매하는 40종목** 위에서 돈다(매일 배치가 시세를 받는 목록이라
  고른 것을 그날 바로 체결할 수 있다). 넓은 ETF 목록(감사 336의 C)은 매일
  배치가 그 시세를 안 받으므로 여기 못 넣는다 — 재료라 사람이 붙인다.

  · risk12 · risk20      자산군마다 같은 **위험**(지금 엔진이 risk12)
  · notional30 · notional50  자산군마다 같은 **금액**(주식·코인 몫이 커진다)
  · xs12                 종목 간 상대 강세(월 1회)
  · blend12              추세와 상대 강세를 위험 기준 반반

■ 어떻게 고르나 — 사전 등록(2026-10-10, 이 파일을 커밋하는 시점 — 결과 보기 전)

  매주 금요일 종가 기준으로:
  ① 후보마다 **최근 3년(756영업일)** 의 수수료·환전 뺀 연수익을 잰다.
     (각 후보의 자산 곡선은 그날까지의 자료로만 정한 비중이라 미래를 안 본다.)
  ② 가장 높은 후보가 지금 엔진이 아니면, 두 곡선의 **일별 차이**로 t를 낸다.
     t ≥ `T_SWITCH`(1.35 — 승격 관문 `CONFIRM_T_CAP`에서 빌려 온다)일 때만
     갈아탄다. 수익률 순위만으로 바꾸면 3년 차이의 대부분이 우연이라 매달
     갈아타며 수수료만 낸다.
  ③ 갈아탄 뒤 **63영업일(3개월)** 은 다시 안 바꾼다(`MIN_HOLD`).
  ④ 최근 3년 최대낙폭이 `MDD_FLOOR`(−40%)보다 나쁜 후보는 고르지 않는다 —
     최적화한 손잡이가 아니라 **명백히 병적인 상태**의 문턱이다(SPY 보유의
     2016~ 최대낙폭이 −33.7%였다). 청산·레버리지 관문과 같은 종류다.

  ⚠️ 목표가 "수익률"이라 위험 대비 효율(샤프)이 아니다 — 사장님 지시 그대로다.
     그래서 이 장치는 **더 크게 흔들리는 엔진을 고를 수 있다.** 그 대가(낙폭)는
     화면에 같이 적는다.

■ 이 고르는 규칙 자체도 검증한다 — 관문(`gate`)

  같은 규칙을 2016년부터 매주 돌려 본 **선택기의 자산 곡선**(갈아탈 때 수수료
  포함)을 만든다. 2016년 이후 그 곡선의 연수익이 **지금 엔진(risk12)을 그대로
  둔 것보다 높고**, 최대낙폭이 `MDD_FLOOR`보다 나쁘지 않을 때만 선택기가 실계좌
  엔진을 정한다. 아니면 risk12 그대로다(결과는 공개). 이것도 기계가 정한다 —
  판정 규칙을 결과보다 먼저 박았으므로.

■ 정직한 한계

  · 후보 곡선은 **시뮬레이션**이다(같은 코드·같은 비용이지만 실계좌 체결과
    다르다). 실계좌 성적은 사전 등록된 판정(`trend_core_live`)이 따로 잰다.
  · 과거 3년에 잘 된 엔진이 앞으로도 잘 된다는 보장은 없다 — 이 규칙이 그
    가정 위에 서 있고, 그 가정이 2016년 이후에 맞았는지가 위 관문이다.
  · 40종목은 사람이 오늘 고른 목록이라 생존 편향이 있다(감사 336 B 참조).
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from quant.portfolio import trend_core as T

REGISTERED_ON = "2026-10-10"
WINDOW = 756            # 최근 3년(영업일)
MIN_HOLD = 63           # 갈아탄 뒤 3개월은 그대로
T_SWITCH = 1.35         # = retrain.CONFIRM_T_CAP (검사가 같은 값인지 본다)
MDD_FLOOR = -0.40       # 병적 낙폭 문턱(최적화 손잡이 아님)
JUDGE_START = "2016-01-01"
BASELINE = "risk12"
STALE_DAYS = 14         # 이보다 낡은 선택은 안 쓴다(주간 잡이 두 번 빠진 것)
SELECT_FILE = "engine_select.json"

CANDIDATES = {
    "risk12": {"kind": "trend", "variant": "risk12"},
    "risk20": {"kind": "trend", "variant": "risk20"},
    "notional30": {"kind": "trend", "variant": "notional30"},
    "notional50": {"kind": "trend", "variant": "notional50"},
    "xs12": {"kind": "xs", "variant": "risk12"},
    "blend12": {"kind": "blend", "variant": "risk12"},
}

# 사람이 읽을 이름 — 화면이 그대로 쓴다.
LABELS = {
    "risk12": "위험 균등 · 변동성 12%",
    "risk20": "위험 균등 · 변동성 20%",
    "notional30": "금액 균등 · 상한 변동성 30%",
    "notional50": "금액 균등 · 상한 변동성 50%",
    "xs12": "상대 강세",
    "blend12": "추세 + 상대 강세",
}


def candidate_config(name: str) -> T.TrendConfig:
    spec = CANDIDATES[name]
    cfg = T.variant_config(spec["variant"])
    if spec["kind"] == "xs":
        cfg = T.TrendConfig(**{**cfg.__dict__, "rebalance": "M"})
    return cfg


def candidate_targets(closes: pd.DataFrame, name: str
                      ) -> tuple[pd.DataFrame, T.TrendConfig]:
    """후보의 목표 비중(날짜 × 자산)과 그 설정. 그날 종가까지만 본다."""
    spec = CANDIDATES[name]
    cfg = candidate_config(name)
    if spec["kind"] == "xs":
        return T.xsmom_weights(closes, cfg), cfg
    if spec["kind"] == "blend":
        return T.blend_weights(closes, cfg), cfg
    return T.target_weights(closes, cfg), cfg


def target_day(idx: pd.DatetimeIndex, rebalance: str):
    """검증과 같은 주기의 '목표를 정한 날' — 실계좌·그림자가 같은 답을 쓴다.

    검증은 금요일 종가 목표로 주 1회 매매했다(회전·비용이 그 가정 위에서
    나왔다). 매일 그날 목표를 따르면 같은 엔진이 검증보다 자주 사고팔아
    비용이 검증과 갈린다. 월 단위면 **끝난 달**의 마지막 영업일이다.
    """
    if rebalance == "D":
        return idx[-1]
    if rebalance == "M":
        prev = idx[(idx.year * 12 + idx.month) < (idx[-1].year * 12 + idx[-1].month)]
        return prev[-1] if len(prev) else idx[-1]
    fridays = idx[idx.weekday == 4]
    return fridays[-1] if len(fridays) else idx[-1]


def _cagr(r: pd.Series) -> float:
    r = r.dropna()
    if len(r) < 2:
        return float("nan")
    g = float((1.0 + r).prod())
    if g <= 0:
        return -1.0
    return g ** (T.PERIODS / len(r)) - 1.0


def _mdd(r: pd.Series) -> float:
    eq = (1.0 + r.fillna(0.0)).cumprod()
    return float((eq / eq.cummax() - 1.0).min()) if len(eq) else 0.0


def choose(returns: pd.DataFrame, upto, incumbent: str,
           held_days: int | None = None) -> dict:
    """그날(upto 포함)까지의 수익으로 다음 엔진을 고른다.

    returns: 날짜 × 후보의 일별 수익(수수료·환전 뺀 것).
    held_days: 지금 엔진을 몇 영업일째 쓰고 있나(None이면 제약 없음).
    """
    win = returns.loc[:upto].tail(WINDOW)
    table = {}
    for name in returns.columns:
        r = win[name]
        full = bool(r.notna().all()) and len(r) >= WINDOW
        table[name] = {"cagr": round(_cagr(r) * 100, 2) if full else None,
                       "mdd": round(_mdd(r) * 100, 2) if full else None}
    out = {"asof": str(pd.Timestamp(upto).date()), "incumbent": incumbent,
           "choice": incumbent, "table": table, "t": None, "reason": None}
    ok = {n: v for n, v in table.items()
          if v["cagr"] is not None and v["mdd"] / 100 >= MDD_FLOOR}
    if not ok:
        out["reason"] = "no_full_window"
        return out
    best = max(ok, key=lambda n: ok[n]["cagr"])
    out["best"] = best
    if best == incumbent:
        out["reason"] = "incumbent_best"
        return out
    if table.get(incumbent, {}).get("cagr") is None:
        # 지금 엔진을 잴 수 없으면(자료 부족) 갈아탈 근거도 없다.
        out["reason"] = "incumbent_unmeasured"
        return out
    d = (win[best] - win[incumbent]).dropna()
    sd = float(d.std())
    t = float(d.mean() / sd * np.sqrt(len(d))) if sd > 0 else 0.0
    out["t"] = round(t, 2)
    if t < T_SWITCH:
        out["reason"] = "not_significant"
        return out
    if held_days is not None and held_days < MIN_HOLD:
        out["reason"] = "min_hold"
        return out
    out["choice"] = best
    out["reason"] = "switch"
    return out


def switch_cost(w_old: pd.Series, w_new: pd.Series, cost_rate: dict,
                fx_keys=(), fx_cost: float = 0.0) -> float:
    """두 엔진의 보유를 갈아탈 때 드는 비용(자산 대비) — 시뮬레이션과 같은 셈."""
    cols = w_old.index.union(w_new.index)
    signed = w_new.reindex(cols).fillna(0.0) - w_old.reindex(cols).fillna(0.0)
    c = float(sum(abs(v) * float(cost_rate.get(k, 0.002))
                  for k, v in signed.items()))
    fx = [k for k in cols if k in set(fx_keys or ())]
    if fx and fx_cost:
        c += abs(float(signed[fx].sum())) * fx_cost
    return c


def meta_backtest(results: dict, cost_rate: dict, start: str = JUDGE_START,
                  fx_keys=(), fx_cost: float = 0.0,
                  baseline: str = BASELINE) -> dict:
    """선택 규칙을 start부터 매주 금요일 돌린 **선택기의 자산 곡선**.

    results: {후보: TrendResult}. 금요일 종가에 고르고 다음 영업일부터 그 후보의
    수익을 받는다. 갈아탄 날은 두 보유의 차이만큼 수수료를 뺀다.
    """
    rets = pd.DataFrame({n: r.equity.pct_change() for n, r in results.items()})
    idx = rets.index[rets.index >= pd.Timestamp(start)]
    # 처음 엔진은 선택기가 고른 것이 아니므로 보유 기간 제약을 안 건다 —
    # 실계좌 첫 회차도 같다(`held_days=None`).
    cur, since = baseline, MIN_HOLD
    daily, switches = [], []
    pending = None
    for day in idx:
        r = float(rets.at[day, cur]) if pd.notna(rets.at[day, cur]) else 0.0
        if pending is not None and pending != cur:
            c = switch_cost(results[cur].weights.loc[day],
                            results[pending].weights.loc[day],
                            cost_rate, fx_keys, fx_cost)
            switches.append({"date": str(day.date()), "from": cur,
                             "to": pending, "cost_pct": round(c * 100, 3)})
            r = (1.0 + r) * (1.0 - c) - 1.0
            cur, since = pending, 0
        pending = None
        daily.append(r)
        since += 1
        if day.weekday() == 4:
            dec = choose(rets, day, cur, held_days=since)
            if dec["choice"] != cur:
                pending = dec["choice"]
    meta = pd.Series(daily, index=idx)
    return {"returns": meta, "switches": switches,
            "stats": T.stats((1.0 + meta).cumprod())}


def gate(meta: dict, results: dict, start: str = JUDGE_START,
         baseline: str = BASELINE, wide: dict | None = None) -> dict:
    """선택기가 실계좌 엔진을 정할 자격 — 판정 구간 연수익이 기준선보다 높고
    최대낙폭이 병적 문턱 안일 때만.

    wide(감사 342): 같은 규칙을 **규칙으로 고른 넓은 ETF 목록**에서 돌린 결과
    `{"meta": …, "results": …}`. 주면 그쪽에서도 이겨야 통과다 — 사람이 오늘
    고른 40종목(지나고 보니 오른 종목)에서만 이기는 규칙은 생존 편향의 산물일
    수 있다. 넓은 목록 자료를 못 받았으면(None) 이 조건은 **못 쟀다**로 적고
    막지 않는다.
    """
    base = T.stats(results[baseline].equity[start:])
    m = meta["stats"]
    ok = bool(m and base and m["cagr"] > base["cagr"]
              and m["mdd"] / 100 >= MDD_FLOOR)
    out = {"pass": ok, "start": start, "selector": m, "baseline": base,
           "baseline_name": baseline, "switches": len(meta["switches"])}
    if wide is not None:
        wb = T.stats(wide["results"][baseline].equity[start:])
        wm = wide["meta"]["stats"]
        wok = bool(wm and wb and wm["cagr"] > wb["cagr"]
                   and wm["mdd"] / 100 >= MDD_FLOOR)
        out["wide"] = {"pass": wok, "selector": wm, "baseline": wb,
                       "switches": len(wide["meta"]["switches"])}
        out["pass"] = ok and wok
    else:
        out["wide"] = None
    return out


def confirm_wide(dec: dict, wide_returns: pd.DataFrame | None, upto) -> dict:
    """갈아타기 결정을 넓은 ETF 목록에서도 확인한다(감사 342).

    40종목에서 앞선 후보가 넓은 목록의 같은 후보로도 지금 엔진을 앞서야
    갈아탄다(최근 3년 연수익). 아니면 그대로 두고 이유를 `not_robust`로
    남긴다. 넓은 목록 자료가 없으면 확인을 **못 했다**고 적고 막지 않는다.
    """
    if dec.get("reason") != "switch":
        return dec
    if wide_returns is None or wide_returns.empty:
        dec["wide"] = None
        return dec
    w = choose(wide_returns, upto, dec["incumbent"])["table"]
    best, inc = dec["choice"], dec["incumbent"]
    dec["wide"] = {best: w.get(best), inc: w.get(inc)}
    b, i = (w.get(best) or {}).get("cagr"), (w.get(inc) or {}).get("cagr")
    if b is None or i is None or b <= i:
        dec["choice"] = inc
        dec["reason"] = "not_robust"
    return dec


def active_choice(state: dict | None, today) -> str | None:
    """state/engine_select.json에서 **지금 쓸** 후보 이름. 못 쓰면 None.

    관문을 통과했고, 선택이 `STALE_DAYS`보다 낡지 않았을 때만.
    """
    if not state or not (state.get("gate") or {}).get("pass"):
        return None
    name = state.get("active")
    if name not in CANDIDATES:
        return None
    try:
        age = (pd.Timestamp(today) - pd.Timestamp(state.get("asof"))).days
    except (TypeError, ValueError):
        return None
    return name if 0 <= age <= STALE_DAYS else None


def load_state(state_dir: str) -> dict | None:
    try:
        with open(os.path.join(state_dir, SELECT_FILE), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def public(state_dir: str) -> dict | None:
    """화면용 요약 — 지금 엔진, 누가 골랐나, 후보 표, 관문. 선택 기록이 없으면 None."""
    st = load_state(state_dir)
    if not st:
        return None
    dec = st.get("decision") or {}
    g = st.get("gate") or {}
    return {"asof": st.get("asof"), "active": st.get("active"),
            "active_label": st.get("active_label"),
            "previous": st.get("previous"), "switched": st.get("switched"),
            "reason": dec.get("reason"), "t": dec.get("t"), "best": dec.get("best"),
            "gate": {"pass": g.get("pass"), "selector": g.get("selector"),
                     "baseline": g.get("baseline"), "switches": g.get("switches"),
                     "start": g.get("start"), "wide": g.get("wide")},
            "candidates": {n: {"label": c.get("label"), "window": c.get("window"),
                               "judge": c.get("judge")}
                           for n, c in (st.get("candidates") or {}).items()},
            "rule": st.get("rule"), "stale_days": STALE_DAYS,
            "cost_basis": st.get("cost_basis")}
