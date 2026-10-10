"""통화 캐리 · 환전 비용을 넣은 본 계좌 성적 — 장기 검증 (감사 339).

사장님(2026-10-10): "응 다 진행해줘" — ① 환전 비용 ② 세금 ③ 통화 캐리.

이 컨테이너는 시세 서버에 못 닿으므로 GitHub Actions(`research-trend.yml`)에서
돌리고 로그로 읽는다. 결과는 `FX_CARRY_RESULT:` 한 줄 JSON으로도 찍는다.

■ 정정 — 감사 337에서 "통화 캐리는 무료 자료가 없어 못 잰다"고 적었는데 틀렸다.
  FRED(미 연준 자료)가 주요국 3개월 금리 월간 계열(OECD, IR3TIB01…)을 공개한다.
  그래서 통화 ETF로 캐리를 잴 수 있다. 원자재 캐리(월물 가격 차)는 여전히 못 잰다.

■ 사전 등록(2026-10-10, 이 파일을 커밋하는 시점 — 결과 보기 전)

  · 통화 6개(유로·엔·파운드·호주달러·캐나다달러·스위스프랑) — 통화 ETF
    FXE·FXY·FXB·FXA·FXC·FXF. 신호 = 그 나라 3개월 금리 − 미국 3개월 금리.
    금리는 **월말 공표분을 한 달 늦게** 쓴다(그 달 값은 다음 달에야 나온다).
  · 후보 셋(더 늘리지 않는다):
      K1 캐리 양방향 — 금리차 상위 2 롱 · 하위 2 숏, 역변동성, 목표 변동성 8%
         (선물·증거금 계좌용 정보 — 본 계좌는 숏을 못 한다)
      K2 캐리 롱 전용 — 금리차가 **양수인** 통화 중 상위 2만, 목표 변동성 8%
      K3 본 계좌 엔진(A) 80% + K2 20%(위험 기준으로 섞음)
  · **적용 조건**(본 계좌에 K3를 붙일 자격): 2015년까지 샤프가 A보다 높고,
    2016년 이후 샤프가 A 이상이며, 2016년 이후 최대낙폭이 A의 1.2배보다 나쁘지
    않을 것. 아니면 A 유지(결과 공개).
  · 비용: 종목별 실측 편도 + **환전 편도 0.25%**(장부와 같은 기본값, 달러 자산
    순매매에만). 본 계좌 엔진 A의 **환전 전·후 성적을 나란히** 낸다 — 환전
    비용이 검증 숫자를 얼마나 깎는지가 이 실험의 첫 번째 답이다.
  · 시도 수: 감사 335~337의 18개 + 이번 3개 = 21개로 DSR을 낸다.
"""
from __future__ import annotations

import io
import json
import sys
import urllib.request

import numpy as np
import pandas as pd

sys.path.insert(0, ".")

from quant.live.tax_kr import FX_SPREAD_DEFAULT  # noqa: E402
from quant.portfolio import trend_core as T  # noqa: E402
from quant.robustness.deflated_sharpe import deflated_sharpe_ratio  # noqa: E402
from scripts.trend_core_research import (  # noqa: E402
    fetch_all, one_way_costs, _universe)

PICK_END = "2015-12-31"
JUDGE_START = "2016-01-01"
N_TRIALS = 21
MDD_SLACK = 1.2
CARRY_VOL = 0.08
FX = {"FXE": "EZ", "FXY": "JP", "FXB": "GB", "FXA": "AU", "FXC": "CA",
      "FXF": "CH"}


def fred(series: str) -> pd.Series:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
    with urllib.request.urlopen(url, timeout=60) as r:
        df = pd.read_csv(io.StringIO(r.read().decode()))
    df.columns = ["date", "v"]
    df["v"] = pd.to_numeric(df["v"], errors="coerce")
    s = df.dropna().set_index(pd.to_datetime(df.dropna()["date"]))["v"]
    print(f"  ✓ {series} {len(s)}개월 {s.index[0].date()}~{s.index[-1].date()}")
    return s


def rate_diff(index: pd.DatetimeIndex) -> pd.DataFrame:
    """일별 금리차(그 나라 − 미국, %p). 월 값을 **다음 달 말**부터 쓴다."""
    us = fred("IR3TIB01USM156N")
    out = {}
    for etf, cc in FX.items():
        try:
            r = fred(f"IR3TIB01{cc}M156N")
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗ {cc} — {exc}")
            continue
        d = (r - us).dropna()
        # 1월 값(1월 1일 날짜)은 2월에야 공표된다 → 2월 말부터 쓴다.
        d.index = d.index + pd.offsets.MonthEnd(2)
        out[f"us_stock:{etf}"] = d.reindex(index, method="ffill")
    return pd.DataFrame(out)


def carry_weights(closes: pd.DataFrame, diff: pd.DataFrame, long_short: bool
                  ) -> pd.DataFrame:
    rets = closes.pct_change(fill_method=None)
    vol = rets.ewm(halflife=60, min_periods=60).std() * np.sqrt(T.PERIODS)
    out = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
    cols = [c for c in diff.columns if c in closes.columns]
    for i, day in enumerate(closes.index):
        d = diff.loc[day, cols].dropna()
        v = vol.loc[day, d.index]
        d = d[v.notna() & (v > 0)]
        if len(d) < 4:
            continue
        srt = d.sort_values(ascending=False)
        longs = [k for k in srt.index[:2] if (long_short or srt[k] > 0)]
        shorts = list(srt.index[-2:]) if long_short else []
        w = pd.Series(0.0, index=d.index)
        for k in longs:
            w[k] = 1.0 / vol.at[day, k]
        for k in shorts:
            w[k] = -1.0 / vol.at[day, k]
        if (w == 0).all():
            continue
        win = rets.iloc[max(0, i - 125): i + 1][list(w.index)]
        cov = win.cov() * T.PERIODS
        if cov.isna().values.any():
            continue
        ex = float(np.sqrt(max(w.values @ cov.values @ w.values, 0.0)))
        if ex <= 0:
            continue
        w = w * (CARRY_VOL / ex)
        out.loc[day, w.index] = w.values
    return out


def segs(eq):
    return {"pick": T.stats(eq[:PICK_END]), "judge": T.stats(eq[JUDGE_START:]),
            "last2y": T.stats(eq[eq.index >= eq.index[-1] - pd.Timedelta(days=730)])}


def row(name, res):
    yrs = len(res.equity) / T.PERIODS
    jr = res.equity[JUDGE_START:].pct_change().dropna()
    return {"name": name, **segs(res.equity),
            "cost_pct_yr": round(float(res.cost.sum()) / yrs * 100, 3),
            "turnover_yr": round(float(res.turnover.sum()) / yrs, 2),
            "dsr_judge": round(deflated_sharpe_ratio(jr.values, n_trials=N_TRIALS), 3)}


def main():
    print("본 계좌 40종목 + 통화 ETF —")
    targets = _universe()
    extra = [("us_stock", etf) for etf in FX if ("us_stock", etf) not in targets]
    frames = fetch_all(targets + extra)
    closes = T.align_business_days(frames)
    a_cols = [f"{m}:{s}" for m, s in targets if f"{m}:{s}" in closes.columns]
    cost = one_way_costs(closes.columns)
    fx_keys = {c for c in closes.columns if c.startswith("us_stock:")}
    print("금리(FRED) —")
    diff = rate_diff(closes.index)

    cfg = T.variant_config("risk12")
    a_w = T.target_weights(closes[a_cols], cfg).reindex(columns=closes.columns,
                                                        fill_value=0.0)
    rows = [
        row("A_환전전", T.simulate(closes, cost, cfg, targets=a_w)),
        row("A_환전후", T.simulate(closes, cost, cfg, targets=a_w,
                                 fx_keys=fx_keys, fx_cost=FX_SPREAD_DEFAULT)),
    ]
    mcfg = T.TrendConfig(rebalance="M", band=0.0, max_gross=2.0, asset_cap=1.0)
    k1 = carry_weights(closes, diff, long_short=True)
    k2 = carry_weights(closes, diff, long_short=False)
    rows.append(row("K1_캐리양방향", T.simulate(closes, cost, mcfg, targets=k1)))
    rows.append(row("K2_캐리롱", T.simulate(closes, cost, mcfg, targets=k2,
                                          fx_keys=fx_keys, fx_cost=FX_SPREAD_DEFAULT)))
    k3 = T.combine_sleeves(closes, [a_w, k2], cfg, [0.8, 0.2])
    rows.append(row("K3_A+캐리20%", T.simulate(closes, cost, cfg, targets=k3,
                                             fx_keys=fx_keys, fx_cost=FX_SPREAD_DEFAULT)))

    print(f"\n=== 감사 339 — {closes.index[0].date()}~{closes.index[-1].date()} ===")
    print(f"{'':14s} {'구간':6s} {'연수익%':>7s} {'변동성%':>7s} {'샤프':>5s} {'최대낙폭%':>8s}")
    for r in rows:
        for seg in ("pick", "judge", "last2y"):
            s = r.get(seg) or {}
            print(f"{r['name']:14s} {seg:6s} {s.get('cagr', 0):7.2f} {s.get('vol', 0):7.2f} "
                  f"{s.get('sharpe', 0):5.2f} {s.get('mdd', 0):8.2f}")
        print(f"{'':14s} 비용 {r['cost_pct_yr']}%/년 · 회전 {r['turnover_yr']}/년 · "
              f"DSR(시도 {N_TRIALS}) {r['dsr_judge']}")
    a = rows[1]
    k3r = rows[-1]
    ap, aj = a["pick"] or {}, a["judge"] or {}
    kp, kj = k3r["pick"] or {}, k3r["judge"] or {}
    apply = (kp.get("sharpe", -9) > ap.get("sharpe", 9)
             and kj.get("sharpe", -9) >= aj.get("sharpe", 9)
             and kj.get("mdd", -100) >= aj.get("mdd", 0) * MDD_SLACK)
    print(f"\n→ 환전 비용이 깎은 몫(판정 구간 연수익): "
          f"{(rows[0]['judge'] or {}).get('cagr')} → {aj.get('cagr')}")
    print(f"→ 사전 등록 규칙: K3 적용 {'충족' if apply else '미달 — A 유지'}")
    print("FX_CARRY_RESULT: " + json.dumps({"apply": apply, "rows": rows},
                                            ensure_ascii=False))


if __name__ == "__main__":
    main()
