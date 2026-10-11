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
    # ── 감사 343 ① — 규칙으로 고른 넓은 ETF 목록(40종목 + BROAD_ETFS)에서
    # 매매하는 후보. 사람이 고른 40종목의 생존 편향이 없는 쪽이다. 매일
    # 배치가 그 ETF들의 종가를 엔진 전용으로 따로 받는다(`wide_extra_keys`).
    "xs12w": {"kind": "xs", "variant": "risk12", "universe": "wide"},
    "blend12w": {"kind": "blend", "variant": "risk12", "universe": "wide"},
    # ── 감사 343 ② — 하락장 방어: 상대 강세에 **시장 추세 필터**를 건다.
    # 시장(SPY)의 21·63·126·252일 수익 중 양수인 비율(0~1)만큼만 담는다 —
    # 시장이 내림 추세면 현금 쪽으로 물러난다. 문턱을 고르지 않는다(비율 그대로).
    "xs12f": {"kind": "xs", "variant": "risk12", "filter": "market"},
    "xs12fw": {"kind": "xs", "variant": "risk12", "filter": "market",
               "universe": "wide"},
}

#: 감사 343 ③ — 하나만 고르지 않고 **최근 상위 둘을 반씩** 담는 후보. 다른
#: 후보들의 결과로 만들어지므로 `CANDIDATES`가 아니라 따로 둔다.
TOP2 = "top2"
MARKET_KEY = "us_stock:SPY"

# 사람이 읽을 이름 — 화면이 그대로 쓴다.
LABELS = {
    "risk12": "위험 균등 · 변동성 12%",
    "risk20": "위험 균등 · 변동성 20%",
    "notional30": "금액 균등 · 상한 변동성 30%",
    "notional50": "금액 균등 · 상한 변동성 50%",
    "xs12": "상대 강세",
    "blend12": "추세 + 상대 강세",
    "xs12w": "상대 강세 · 넓은 목록",
    "blend12w": "추세 + 상대 강세 · 넓은 목록",
    "xs12f": "상대 강세 · 하락장 방어",
    "xs12fw": "상대 강세 · 하락장 방어 · 넓은 목록",
    TOP2: "최근 상위 둘 섞기",
}

#: 넓은 목록의 추가 종목 — 규칙으로 고른 ETF(감사 336). 40종목과 겹치는 것은
#: 40종목 쪽 시세를 쓴다(같은 열).
WIDE_KEYS = tuple(f"us_stock:{t}" for t in T.BROAD_ETFS)


def universe_of(name: str) -> str:
    return CANDIDATES.get(name, {}).get("universe", "core")


def wide_extra_keys(core_keys) -> list:
    """넓은 목록 중 40종목(core_keys)에 없는 것 — 매일 배치가 따로 받는다."""
    core = set(core_keys or ())
    return [k for k in WIDE_KEYS if k not in core]


def candidate_config(name: str) -> T.TrendConfig:
    spec = CANDIDATES[name]
    cfg = T.variant_config(spec["variant"])
    if spec["kind"] == "xs":
        cfg = T.TrendConfig(**{**cfg.__dict__, "rebalance": "M"})
    return cfg


def candidate_targets(closes: pd.DataFrame, name: str, core_keys=None
                      ) -> tuple[pd.DataFrame, T.TrendConfig]:
    """후보의 목표 비중(날짜 × 자산)과 그 설정. 그날 종가까지만 본다.

    core_keys(감사 343): 40종목의 열 이름. 주면 40종목 후보는 그 열만 보고,
    넓은 목록 후보는 전부 본다. 안 주면 받은 열 전부를 본다(연구·검사용).
    결과는 언제나 closes의 열 전체로 맞춘다(안 보는 열은 0).
    """
    spec = CANDIDATES[name]
    cfg = candidate_config(name)
    cols = list(closes.columns)
    if core_keys is not None and universe_of(name) == "core":
        keep = set(core_keys)
        cols = [c for c in cols if c in keep]
    sub = closes[cols]
    if spec["kind"] == "xs":
        tgt = T.xsmom_weights(sub, cfg)
    elif spec["kind"] == "blend":
        tgt = T.blend_weights(sub, cfg)
    else:
        tgt = T.target_weights(sub, cfg)
    if spec.get("filter") == "market":
        tgt = tgt.mul(market_filter(closes), axis=0)
    return tgt.reindex(columns=closes.columns, fill_value=0.0), cfg


ALL_NAMES = tuple(CANDIDATES) + (TOP2,)


def targets_today(closes: pd.DataFrame, name: str, core_keys=None,
                  state: dict | None = None) -> dict:
    """그 엔진이 **오늘 따를** 목표 — 실계좌·그림자가 같은 답을 쓰는 한 자리.

    검증과 같은 주기(`target_day`)의 목표 줄을 고른다. TOP2면 주간 잡이 적은
    짝(`state["top2_pair"]`)의 목표를 반씩 더한다(각자 자기 주기).
    """
    if name == TOP2:
        pair = list((state or {}).get("top2_pair") or [])
        if len(pair) != 2 or any(p not in CANDIDATES for p in pair):
            raise ValueError("상위 둘 짝이 정해지지 않았다")
        a, b = (targets_today(closes, p, core_keys) for p in pair)
        cols = set(a["weights"]) | set(b["weights"])
        return {"weights": {k: 0.5 * a["weights"].get(k, 0.0)
                            + 0.5 * b["weights"].get(k, 0.0) for k in cols},
                "target_day": max(a["target_day"], b["target_day"]),
                "asset_cap": max(a["asset_cap"], b["asset_cap"]),
                "pair": pair}
    tgt, cfg = candidate_targets(closes, name, core_keys=core_keys)
    day = target_day(tgt.index, cfg.rebalance)
    row = tgt.loc[day].fillna(0.0)
    return {"weights": {k: float(row.get(k, 0.0)) for k in closes.columns},
            "target_day": str(day.date()), "asset_cap": cfg.asset_cap}


def market_filter(closes: pd.DataFrame) -> pd.Series:
    """시장 추세 필터(감사 343 ②) — SPY 여러 기간 수익 중 양수인 비율(0~1).

    그날 종가까지만 본다. SPY가 없거나 아직 계산이 안 되는 날은 1(필터 없음) —
    못 잰 것을 '내림'으로 세지 않는다.
    """
    if MARKET_KEY not in closes.columns:
        return pd.Series(1.0, index=closes.index)
    return T.trend_score(closes[MARKET_KEY]).fillna(1.0)


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


BASE_CANDIDATES = 6     # T_SWITCH를 정한 날(감사 341)의 후보 수


def switch_threshold(n_candidates: int) -> float:
    """후보가 늘면 갈아타기 문턱도 오른다(감사 343) — 본페로니.

    감사 341의 문턱 1.35는 후보 6개(비교 5번)에서 정했다. 그때의 **전체 거짓
    갈아타기 예산**(5 × 한쪽 꼬리 확률)을 그대로 두고 비교 수로 나눈다 —
    후보를 많이 뽑을수록 '우연히 1등'이 쉬워지는 만큼 문턱이 저절로 오른다.
    6개 이하면 1.35 그대로다(내려가지 않는다).
    """
    from statistics import NormalDist
    nd = NormalDist()
    k0 = BASE_CANDIDATES - 1
    k = max(k0, int(n_candidates) - 1)
    family = k0 * (1.0 - nd.cdf(T_SWITCH))
    return round(max(T_SWITCH, nd.inv_cdf(1.0 - family / k)), 3)


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
    out["t_needed"] = switch_threshold(returns.shape[1])
    if t < out["t_needed"]:
        out["reason"] = "not_significant"
        return out
    if held_days is not None and held_days < MIN_HOLD:
        out["reason"] = "min_hold"
        return out
    out["choice"] = best
    out["reason"] = "switch"
    return out


def _repick_days(idx: pd.DatetimeIndex) -> set:
    """상위 둘을 다시 고르는 날 — **매달 마지막 금요일**(월 1회).

    매주 다시 고르면 순위가 조금만 바뀌어도 반쪽을 갈아타며 수수료를 낸다.
    """
    fr = idx[idx.weekday == 4]
    if not len(fr):
        return set()
    s = pd.Series(fr, index=fr)
    last = s.groupby([fr.year, fr.month]).transform("max")
    return set(fr[fr == pd.DatetimeIndex(last.values)])


def top2_pick(returns: pd.DataFrame, upto) -> list | None:
    """최근 3년 연수익 상위 둘(낙폭 병적 문턱 안). 둘이 안 되면 None."""
    win = returns.loc[:upto].tail(WINDOW)
    ok = {}
    for n in returns.columns:
        r = win[n]
        if len(r) < WINDOW or not bool(r.notna().all()):
            continue
        if _mdd(r) >= MDD_FLOOR:
            ok[n] = _cagr(r)
    if len(ok) < 2:
        return None
    return sorted(ok, key=lambda n: ok[n], reverse=True)[:2]


def build_top2(results: dict, cost_rate: dict, fx_keys=(),
               fx_cost: float = 0.0) -> tuple:
    """상위 둘 섞기 후보의 자산 곡선(감사 343 ③) — 다른 후보 결과로 만든다.

    매달 마지막 금요일 종가로 짝을 정하고 다음 영업일부터 두 후보의 수익을
    반씩 받는다. 짝이 바뀐 날은 두 혼합 보유의 차이만큼 수수료를 뺀다.
    반환: (TrendResult, 지금 짝)
    """
    rets = pd.DataFrame({n: r.equity.pct_change() for n, r in results.items()})
    idx = rets.index
    repick = _repick_days(idx)
    cols = sorted(set().union(*(r.weights.columns for r in results.values())))

    def mix(pair, day):
        if not pair:
            return pd.Series(0.0, index=cols)
        a, b = (results[p].weights.loc[day].reindex(cols).fillna(0.0) for p in pair)
        return 0.5 * a + 0.5 * b

    pair, pending = None, None
    eq, eqs, ws, cs = 1.0, [], [], []
    for day in idx:
        r = (float(np.nanmean([rets.at[day, p] for p in pair]))
             if pair else 0.0)
        r = 0.0 if np.isnan(r) else r
        c = 0.0
        if pending is not None and pending != pair:
            c = switch_cost(mix(pair, day), mix(pending, day), cost_rate,
                            fx_keys, fx_cost)
            r = (r + 1.0) * (1.0 - c) - 1.0          # 짝을 바꾼 날의 비용
            pair = pending
        pending = None
        eq *= (1.0 + r)
        eqs.append(eq)
        cs.append(c)
        ws.append(mix(pair, day))
        if day in repick:
            pending = top2_pick(rets, day)
    equity = pd.Series(eqs, index=idx)
    res = T.TrendResult(equity=equity, returns=equity.pct_change(),
                        weights=pd.DataFrame(ws, index=idx),
                        turnover=pd.Series(0.0, index=idx),
                        cost=pd.Series(cs, index=idx),
                        gross=pd.Series(0.0, index=idx))
    return res, (pending or pair)


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
    if name not in ALL_NAMES:
        return None
    if name == TOP2 and len(state.get("top2_pair") or []) != 2:
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
            "top2_pair": st.get("top2_pair"), "t_needed": dec.get("t_needed"),
            "reason": dec.get("reason"), "t": dec.get("t"), "best": dec.get("best"),
            "gate": {"pass": g.get("pass"), "selector": g.get("selector"),
                     "baseline": g.get("baseline"), "switches": g.get("switches"),
                     "start": g.get("start"), "wide": g.get("wide")},
            "candidates": {n: {"label": c.get("label"), "window": c.get("window"),
                               "judge": c.get("judge")}
                           for n, c in (st.get("candidates") or {}).items()},
            "rule": st.get("rule"), "stale_days": STALE_DAYS,
            "cost_basis": st.get("cost_basis")}
