"""두 번째 수익원 · 넓은 종목 목록 · 환율 — 장기 검증 (감사 336).

사장님(2026-10-09): "응 2,3번 진행하고 나머지도 다 해줘"
  ② 추세 말고 **다른 수익원**(종목 간 상대 강세 = 횡단면 모멘텀)
  ③ 사람이 고른 40종목 말고 **규칙으로 고른 넓은 ETF 목록**
  ⑥ 본 계좌는 원화인데 검증은 달러로 쟀다 — **환율을 넣어** 다시 잰다

이 컨테이너는 시세 서버에 못 닿으므로 GitHub Actions(`research-trend.yml`)에서
돌리고 로그로 읽는다. 결과는 `MULTI_SLEEVE_RESULT:` 한 줄 JSON으로도 찍는다.

■ 사전 등록(2026-10-09, 이 파일을 커밋하는 시점 — 결과 보기 전)

  · 후보는 넷뿐이다. 모두 목표 변동성 12%(지금 실계좌 risk12와 같은 위험):
      A  지금 것      — 현 40종목 · 추세
      B  넓힌 목록    — 현 40종목 + 넓은 ETF 50개 · 추세
      C  상대 강세    — 같은 넓힌 목록 · 횡단면 모멘텀(월 1회)
      D  섞음         — 같은 넓힌 목록 · 추세와 상대 강세를 위험 기준 반반(주 1회)
  · **고르는 구간**: 데이터 시작 ~ 2015-12-31, 샤프 최고.
  · **적용 조건**: 고른 것이 A가 아니고, **판정 구간(2016~)** 샤프가 A 이상이며,
    판정 구간 최대낙폭이 A의 1.5배보다 나쁘지 않을 때만 실계좌에 붙인다.
    아니면 A 그대로(결과는 공개).
  · 위험 수준(목표 변동성 20%)과 원화 환산 성적은 **고르는 데 안 쓴다** —
    사장님 결정을 위한 정보로만 낸다.
  · 비용: 종목별 실측 편도(`measured_cost_model`) — 본 계좌와 같은 자.
  · 환율: 야후 KRW=X(원/달러). 한국 종목은 원화 그대로, 나머지(미국·코인)는
    달러 자산으로 보고 그날 환율 변화를 곱한다. 현금은 원화(환율 영향 0).
    ⚠️ 환헤지 비용(두 나라 금리 차)은 자료가 없어 **안 넣는다** — 그래서
    '달러 기준' 줄은 공짜로 헤지한 경우의 근사다. 그렇게 적는다.
"""
from __future__ import annotations

import json
import sys
import time

import pandas as pd

sys.path.insert(0, ".")

from quant.portfolio import trend_core as T  # noqa: E402
from scripts.trend_core_research import (  # noqa: E402
    fetch_all, one_way_costs, _universe)

PICK_END = "2015-12-31"
JUDGE_START = "2016-01-01"
MDD_SLACK = 1.5


def fetch_broad() -> dict:
    import yfinance as yf
    out = {}
    for tk in T.BROAD_ETFS:
        key = f"us_stock:{tk}"
        try:
            df = yf.download(tk, start="2003-01-01", progress=False,
                             auto_adjust=True)
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗ {tk} — {exc}")
            continue
        if df is None or df.empty:
            print(f"  ✗ {tk} 없음")
            continue
        c = df["Close"]
        if isinstance(c, pd.DataFrame):
            c = c.iloc[:, 0]
        out[key] = c.dropna()
        print(f"  ✓ {tk} {len(c)}봉 {c.index[0].date()}~")
    return out


def fetch_fx() -> pd.Series:
    import yfinance as yf
    df = yf.download("KRW=X", start="2003-01-01", progress=False,
                     auto_adjust=True)
    c = df["Close"]
    if isinstance(c, pd.DataFrame):
        c = c.iloc[:, 0]
    c = c.dropna()
    c = c[(c > 500) & (c < 3000)]          # 야후 KRW=X의 알려진 튀는 값 제거
    c.index = pd.to_datetime(c.index).tz_localize(None).normalize()
    return c[~c.index.duplicated(keep="last")]


def krw_equity(res, closes: pd.DataFrame, fx: pd.Series) -> pd.Series:
    """달러 자산 몫에 그날 환율 변화를 얹은 **원화 기준** 자산 곡선."""
    f = fx.reindex(closes.index).ffill().pct_change(fill_method=None).fillna(0.0)
    rets = closes.pct_change(fill_method=None).fillna(0.0)
    usd = [k for k in closes.columns if not k.startswith("kr_stock:")]
    w_prev = res.weights.shift(1).fillna(0.0)[usd]
    usd_r = (w_prev * rets[usd]).sum(axis=1)
    r = res.equity.pct_change().fillna(res.equity.iloc[0] - 1.0)
    r_krw = r + w_prev.sum(axis=1) * f + usd_r * f
    return (1.0 + r_krw).cumprod()


def segs(eq: pd.Series) -> dict:
    return {"pick": T.stats(eq[:PICK_END]), "judge": T.stats(eq[JUDGE_START:]),
            "last2y": T.stats(eq[eq.index >= eq.index[-1] - pd.Timedelta(days=730)])}


def run_one(name, closes, cost, cfg, kind, fx):
    t0 = time.time()
    if kind == "trend":
        res = T.simulate(closes, cost, cfg)
    elif kind == "xs":
        res = T.simulate(closes, cost, T.TrendConfig(**{**cfg.__dict__, "rebalance": "M"}),
                         targets=T.xsmom_weights(closes, cfg))
    else:
        res = T.simulate(closes, cost, cfg, targets=T.blend_weights(closes, cfg))
    yrs = len(res.equity) / T.PERIODS
    row = {"name": name, "n": int(closes.shape[1]), **segs(res.equity),
           "turnover_yr": round(float(res.turnover.sum()) / yrs, 2),
           "cost_pct_yr": round(float(res.cost.sum()) / yrs * 100, 3),
           "avg_gross": round(float(res.gross.mean()), 2)}
    if fx is not None and len(fx):
        row["krw"] = segs(krw_equity(res, closes, fx))
    print(f"  · {name} 끝 ({time.time() - t0:.0f}s)")
    return row, res


def show(rows):
    print(f"{'':16s} {'구간':6s} {'연수익%':>7s} {'변동성%':>7s} {'샤프':>5s} {'최대낙폭%':>8s}")
    for r in rows:
        for seg in ("pick", "judge", "last2y"):
            s = r.get(seg) or {}
            print(f"{r['name']:16s} {seg:6s} {s.get('cagr', 0):7.2f} "
                  f"{s.get('vol', 0):7.2f} {s.get('sharpe', 0):5.2f} {s.get('mdd', 0):8.2f}")
        if "krw" in r:
            for seg in ("judge", "last2y"):
                s = r["krw"].get(seg) or {}
                print(f"{r['name']:16s} 원화{seg:4s} {s.get('cagr', 0):7.2f} "
                      f"{s.get('vol', 0):7.2f} {s.get('sharpe', 0):5.2f} {s.get('mdd', 0):8.2f}")
        if "turnover_yr" in r:
            print(f"{'':16s} 회전 {r['turnover_yr']}/년 · 비용 {r['cost_pct_yr']}%/년 · "
                  f"평균 노출 {r['avg_gross']} · {r['n']}종목")


def main():
    print("현 40종목 —")
    cur = fetch_all(_universe())
    print("넓은 ETF —")
    broad = fetch_broad()
    fx = fetch_fx()
    print(f"환율 KRW=X {len(fx)}봉 {fx.index[0].date()}~")
    c40 = T.align_business_days(cur)
    wide = T.align_business_days({**broad, **cur})   # 같은 열은 현 목록 시세
    cost40 = one_way_costs(c40.columns)
    costw = one_way_costs(wide.columns)
    cfg12 = T.variant_config("risk12")
    rows = []
    for name, cl, co, kind in (("A_현40_추세", c40, cost40, "trend"),
                               ("B_넓힘_추세", wide, costw, "trend"),
                               ("C_넓힘_상대강세", wide, costw, "xs"),
                               ("D_넓힘_섞음", wide, costw, "blend")):
        rows.append(run_one(name, cl, co, cfg12, kind, fx)[0])
    picked = max(rows, key=lambda r: (r["pick"] or {}).get("sharpe", -9))
    a = rows[0]
    pj, aj = picked["judge"] or {}, a["judge"] or {}
    apply = (picked is not a
             and pj.get("sharpe", -9) >= aj.get("sharpe", 9)
             and pj.get("mdd", -100) >= aj.get("mdd", 0) * MDD_SLACK)
    # 위험 수준 — 정보용(고르는 데 안 씀): 고른 것과 A를 목표 변동성 20%로.
    cfg20 = T.variant_config("risk20")
    risk = []
    for r, cl, co, kind in ((a, c40, cost40, "trend"),
                            (picked, wide if picked is not a else c40,
                             costw if picked is not a else cost40,
                             {"B": "trend", "C": "xs", "D": "blend"}.get(picked["name"][0], "trend"))):
        risk.append(run_one(r["name"] + "@20", cl, co, cfg20, kind, fx)[0])
        if picked is a:
            break
    print(f"\n=== 감사 336 — {wide.index[0].date()}~{wide.index[-1].date()} ===")
    show(rows)
    print("\n--- 위험 수준(목표 변동성 20%, 정보용) ---")
    show(risk)
    print(f"\n→ 사전 등록 규칙(고르는 구간 샤프 최고)으로 고름: {picked['name']} · "
          f"적용 {'충족' if apply else '미달 — A 유지'}")
    print("MULTI_SLEEVE_RESULT: " + json.dumps(
        {"picked": picked["name"], "apply": apply, "rows": rows, "risk20": risk},
        ensure_ascii=False))


if __name__ == "__main__":
    main()
