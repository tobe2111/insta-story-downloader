"""매니지드 퓨처스(다자산 선물 추세) · 캐리 · 조합 — 장기 검증 (감사 337).

사장님(2026-10-10): "더 이상적으로 구현하는 방법은? 투자 세상에서 가장 잘
해야해" → (제안 4가지) → "다 해줘"

이 컨테이너는 시세 서버에 못 닿으므로 GitHub Actions(`research-trend.yml`)에서
돌리고 로그로 읽는다. 결과는 `MANAGED_FUTURES_RESULT:` 한 줄 JSON으로도 찍는다.

■ 왜 이것을 재나
  본 계좌 추세 코어는 빚을 못 내는 현물이라 위험을 연 5~6%밖에 못 진다(감사
  336: 목표를 20%로 올려도 실현 6.7%). 추세추종이 가장 오래 검증된 자리는
  **주가지수·채권·통화·원자재 선물**이고, 선물은 증거금 계좌라 같은 신호로
  위험을 연 10~15%까지 질 수 있다. 같은 실력이면 수익이 그만큼 커진다.

■ 사전 등록(2026-10-10, 이 파일을 커밋하는 시점 — 결과 보기 전)

  · 주 자료: **선물 대용 ETF**(아래 MF_ETFS, 2003~). ETF 수익에서 단기 국채
    금리(^IRX)를 빼 **초과수익**을 만든다 — 선물을 증거금으로 들고 나머지 현금이
    국채 이자를 받는 것과 같은 셈이다. 그래서 레버리지에 이자 비용이 자연히 든다.
    숏은 ETF 차입료 대신 선물로 잡는다고 보고 따로 물리지 않는다(선물 숏은
    차입료가 없다) — 대신 비용은 미국 주식 실측 편도(선물보다 비싸다)로 보수적.
  · 보조 자료: 야후 **연속 선물**(=F). ⚠️ 연속 계열은 월물 교체일에 가격이
    뛰어(롤 갭) 수익이 왜곡된다 — 고르는 데 안 쓰고, 고른 후보의 방향이 같은지만
    본다.
  · 후보 다섯(더 늘리지 않는다):
      M1 추세 양방향 · 목표 변동성 10%
      M2 추세 양방향 · 15%
      M3 추세 롱 전용 · 15%
      M4 조합(추세 양방향 + 상대 강세 + 채권 캐리, 위험 ⅓씩) · 15%
      M5 조합 · 10%
    모두 총노출 ≤ 3배, 한 종목 ±0.5배, 주 1회(금), 밴드 2%.
  · 채권 캐리: 10년 금리(^TNX) − 3개월(^IRX)가 양수일 때 그 기울기에 비례해
    중·장기 국채(IEF·TLT)를 든다. ⚠️ 통화 캐리(나라별 금리)와 원자재 캐리(월물
    가격 차)는 무료 자료가 없어 **넣지 못한다** — 재료는 사람이 붙인다.
  · **고르는 구간**: ~2015-12-31, 초과수익 샤프 최고.
  · **적용 조건**(모의 트랙을 열 자격): 판정 구간(2016~) 초과수익 샤프 ≥ 0.4,
    최대낙폭 > −30%, 그리고 시도 횟수로 보정한 샤프 신뢰도(DSR) ≥ 0.9.
    시도 횟수는 이 저장소가 지금까지 잰 포트폴리오 후보 전부(`TRIAL_LEDGER`)다.
  · 실계좌(선물 계좌 개설)는 이 결과와 별개로 **사장님 결정**이다.
"""
from __future__ import annotations

import json
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, ".")

from quant.live.daily import measured_cost_model  # noqa: E402
from quant.portfolio import trend_core as T  # noqa: E402
from quant.robustness.deflated_sharpe import deflated_sharpe_ratio  # noqa: E402

PICK_END = "2015-12-31"
JUDGE_START = "2016-01-01"
MIN_JUDGE_SHARPE = 0.4
MAX_JUDGE_MDD = -30.0
MIN_DSR = 0.9

MF_ETFS = {
    "SPY": "equity", "QQQ": "equity", "IWM": "equity", "EFA": "equity",
    "EEM": "equity", "EWJ": "equity", "VGK": "equity", "FXI": "equity",
    "SHY": "rates", "IEF": "rates", "TLT": "rates", "TIP": "rates",
    "LQD": "rates",
    "GLD": "real", "SLV": "real", "USO": "real", "UNG": "real",
    "DBA": "real", "DBB": "real", "DBC": "real",
    "FXE": "fx", "FXY": "fx", "FXB": "fx", "FXA": "fx", "FXC": "fx",
    "FXF": "fx", "UUP": "fx",
}
FUTS = {
    "ES=F": "equity", "NQ=F": "equity", "YM=F": "equity", "RTY=F": "equity",
    "ZT=F": "rates", "ZF=F": "rates", "ZN=F": "rates", "ZB=F": "rates",
    "GC=F": "real", "SI=F": "real", "HG=F": "real", "CL=F": "real",
    "NG=F": "real", "ZC=F": "real", "ZW=F": "real", "ZS=F": "real",
    "6E=F": "fx", "6J=F": "fx", "6B=F": "fx", "6A=F": "fx", "6C=F": "fx",
    "6S=F": "fx",
}

# 이 저장소가 지금까지 잰 **포트폴리오 단위** 후보 — 감사 335(4+4) · 336(4+1) ·
# 337(5). 새 후보를 재면 여기에 더한다. 줄이면 다중검정을 덜 치른다.
TRIAL_LEDGER = {
    "audit335_main": ["risk12", "risk20", "notional30", "notional50"],
    "audit335_futures": ["fut_long20", "fut_long40", "fut_ls20", "fut_ls40"],
    "audit336": ["A", "B", "C", "D", "A@20"],
    "audit337": ["M1", "M2", "M3", "M4", "M5"],
    "audit339": ["K1", "K2", "K3"],
    # 감사 341 — 40종목 위 새 후보 둘(상대 강세·섞음)과 선택 규칙 자체.
    "audit341": ["xs12", "blend12", "selector"],
}
N_TRIALS = sum(len(v) for v in TRIAL_LEDGER.values())

BASE = dict(max_gross=3.0, asset_cap=0.5)
CANDIDATES = {
    "M1": ("trend", dict(BASE, allow_short=True, target_vol=0.10)),
    "M2": ("trend", dict(BASE, allow_short=True, target_vol=0.15)),
    "M3": ("trend", dict(BASE, allow_short=False, target_vol=0.15)),
    "M4": ("combo", dict(BASE, allow_short=True, target_vol=0.15)),
    "M5": ("combo", dict(BASE, allow_short=True, target_vol=0.10)),
}


def _yf(tk: str, start="2000-01-01") -> pd.Series | None:
    import yfinance as yf
    try:
        df = yf.download(tk, start=start, progress=False, auto_adjust=True)
    except Exception as exc:  # noqa: BLE001
        print(f"  ✗ {tk} — {exc}")
        return None
    if df is None or df.empty:
        print(f"  ✗ {tk} 없음")
        return None
    c = df["Close"]
    if isinstance(c, pd.DataFrame):
        c = c.iloc[:, 0]
    c = c.dropna()
    c = c[c > 0]
    c.index = pd.to_datetime(c.index).tz_localize(None).normalize()
    print(f"  ✓ {tk} {len(c)}봉 {c.index[0].date()}~")
    return c[~c.index.duplicated(keep="last")]


def excess_closes(closes: pd.DataFrame, rf_daily: pd.Series) -> pd.DataFrame:
    """가격 → **초과수익 지수**(그날 수익 − 단기금리). 상장 전 NaN은 그대로."""
    r = closes.pct_change(fill_method=None)
    ex = r.sub(rf_daily.reindex(closes.index).ffill().fillna(0.0), axis=0)
    idx = (1.0 + ex.fillna(0.0)).cumprod()
    return idx.where(closes.notna())


def carry_weights(closes: pd.DataFrame, slope: pd.Series,
                  cfg: T.TrendConfig) -> pd.DataFrame:
    """채권 캐리 — 수익률 곡선이 가파를수록 중·장기 국채를 더 든다(롱만)."""
    rets = closes.pct_change(fill_method=None)
    vol = rets.ewm(halflife=cfg.vol_halflife, min_periods=cfg.vol_halflife
                   ).std() * np.sqrt(T.PERIODS)
    bonds = [k for k in closes.columns if k.split(":")[1] in ("IEF", "TLT", "ZN=F", "ZB=F")]
    s = slope.reindex(closes.index).ffill()
    out = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
    for day in closes.index:
        sv = s.get(day)
        if sv is None or not np.isfinite(sv) or sv <= 0:
            continue
        live = [k for k in bonds if pd.notna(vol.at[day, k]) and vol.at[day, k] > 0]
        if not live:
            continue
        scale = min(1.0, sv / 2.0)              # 기울기 2%p 이상이면 가득
        for k in live:
            out.at[day, k] = scale * cfg.target_vol / vol.at[day, k] / len(live)
    return out


def weights_for(kind, closes, cfg, slope):
    if kind == "trend":
        return T.target_weights(closes, cfg)
    return T.combine_sleeves(closes, [
        T.target_weights(closes, cfg),
        T.xsmom_weights(closes, T.TrendConfig(**{**cfg.__dict__, "allow_short": False})),
        carry_weights(closes, slope, cfg)], cfg)


def evaluate(name, kind, params, closes, cost, slope, rf_growth):
    t0 = time.time()
    cfg = T.TrendConfig(**params)
    res = T.simulate(closes, cost, cfg, targets=weights_for(kind, closes, cfg, slope))
    ex_eq = res.equity
    tot_eq = ex_eq * rf_growth.reindex(ex_eq.index).ffill().fillna(1.0)
    yrs = len(ex_eq) / T.PERIODS
    jr = ex_eq[JUDGE_START:].pct_change().dropna()
    row = {"name": name, "kind": kind, "target_vol": params["target_vol"],
           "short": params["allow_short"],
           "pick_ex": T.stats(ex_eq[:PICK_END]),
           "judge_ex": T.stats(ex_eq[JUDGE_START:]),
           "judge_total": T.stats(tot_eq[JUDGE_START:]),
           "last2y_total": T.stats(tot_eq[tot_eq.index >= tot_eq.index[-1]
                                          - pd.Timedelta(days=730)]),
           "dsr_judge": round(deflated_sharpe_ratio(jr.values, n_trials=N_TRIALS), 3),
           "turnover_yr": round(float(res.turnover.sum()) / yrs, 2),
           "cost_pct_yr": round(float(res.cost.sum()) / yrs * 100, 3),
           "avg_gross": round(float(res.gross.mean()), 2)}
    print(f"  · {name} 끝 ({time.time() - t0:.0f}s)")
    return row


def show(rows, title):
    print(f"\n=== {title} ===")
    print(f"{'':6s} {'구간':10s} {'연수익%':>7s} {'변동성%':>7s} {'샤프':>5s} {'최대낙폭%':>8s}")
    for r in rows:
        for seg in ("pick_ex", "judge_ex", "judge_total", "last2y_total"):
            s = r.get(seg) or {}
            print(f"{r['name']:6s} {seg:10s} {s.get('cagr', 0):7.2f} {s.get('vol', 0):7.2f} "
                  f"{s.get('sharpe', 0):5.2f} {s.get('mdd', 0):8.2f}")
        if "turnover_yr" in r:
            print(f"{'':6s} 회전 {r['turnover_yr']}/년 · 비용 {r['cost_pct_yr']}%/년 · "
                  f"평균 노출 {r['avg_gross']}배 · DSR(시도 {N_TRIALS}) {r['dsr_judge']}")


def main():
    print("단기·장기 금리 —")
    irx = _yf("^IRX")
    tnx = _yf("^TNX")
    rf_daily = (irx / 100.0 / T.PERIODS) if irx is not None else pd.Series(dtype=float)
    slope = (tnx - irx).dropna() if (irx is not None and tnx is not None) else pd.Series(dtype=float)

    print("선물 대용 ETF —")
    frames = {}
    for tk, cls in MF_ETFS.items():
        s = _yf(tk, "2003-01-01")
        if s is not None:
            frames[f"us_stock:{tk}"] = s
            T.ASSET_CLASS.setdefault(f"us_stock:{tk}", cls)
    raw = T.align_business_days(frames)
    closes = excess_closes(raw, rf_daily)
    rf_growth = (1.0 + rf_daily.reindex(closes.index).ffill().fillna(0.0)).cumprod()
    cost = {k: float(measured_cost_model("us_stock", symbol=k.split(":")[1]).total_one_way())
            for k in closes.columns}
    rows = [evaluate(n, kind, p, closes, cost, slope, rf_growth)
            for n, (kind, p) in CANDIDATES.items()]
    # 기준선: 60/40(SPY/IEF) 무레버리지 — 같은 비용·같은 체결
    tgt = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
    ok = raw["us_stock:SPY"].notna() & raw["us_stock:IEF"].notna()
    tgt.loc[ok, "us_stock:SPY"], tgt.loc[ok, "us_stock:IEF"] = 0.6, 0.4
    bench = T.simulate(closes, cost, T.TrendConfig(rebalance="M", band=0.0), targets=tgt).equity
    btot = bench * rf_growth.reindex(bench.index).ffill().fillna(1.0)
    rows.append({"name": "60/40", "pick_ex": T.stats(bench[:PICK_END]),
                 "judge_ex": T.stats(bench[JUDGE_START:]),
                 "judge_total": T.stats(btot[JUDGE_START:]),
                 "last2y_total": T.stats(btot[btot.index >= btot.index[-1] - pd.Timedelta(days=730)])})
    show(rows, f"선물 대용 ETF {len(closes.columns)}종 · {closes.index[0].date()}~{closes.index[-1].date()}")
    picked = max((r for r in rows if r["name"] in CANDIDATES),
                 key=lambda r: (r["pick_ex"] or {}).get("sharpe", -9))
    j = picked["judge_ex"] or {}
    apply = (j.get("sharpe", -9) >= MIN_JUDGE_SHARPE and j.get("mdd", -100) > MAX_JUDGE_MDD
             and picked["dsr_judge"] >= MIN_DSR)

    # 보조: 연속 선물(롤 갭 있음) — 고른 후보만, 방향이 같은지 본다.
    print("\n연속 선물(보조) —")
    ff = {}
    for tk, cls in FUTS.items():
        s = _yf(tk)
        if s is not None:
            ff[f"fut:{tk}"] = s
            T.ASSET_CLASS.setdefault(f"fut:{tk}", cls)
    fut_row = None
    if len(ff) >= 8:
        fcl = T.align_business_days(ff)
        fcost = {k: 0.0003 for k in fcl.columns}          # 선물 편도 3bp(수수료+슬리피지)
        frf = (1.0 + rf_daily.reindex(fcl.index).ffill().fillna(0.0)).cumprod()
        kind, p = CANDIDATES[picked["name"]]
        fut_row = evaluate(picked["name"] + "@선물", kind, p, fcl, fcost, slope, frf)
        show([fut_row], f"연속 선물 {len(fcl.columns)}종(롤 갭 포함 — 방향 확인용)")
    print(f"\n→ 사전 등록 규칙으로 고름: {picked['name']} · 모의 트랙 자격 "
          f"{'충족' if apply else '미달'} (판정 샤프 {j.get('sharpe')} · 낙폭 {j.get('mdd')} · "
          f"DSR {picked['dsr_judge']} / 시도 {N_TRIALS})")
    print("MANAGED_FUTURES_RESULT: " + json.dumps(
        {"picked": picked["name"], "apply": apply, "n_trials": N_TRIALS,
         "rows": rows, "futures_check": fut_row}, ensure_ascii=False))


if __name__ == "__main__":
    main()
