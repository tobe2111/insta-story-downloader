"""추세추종 코어의 장기 검증 — 판정 규칙을 **결과를 보기 전에** 적어 둔다 (감사 335).

이 컨테이너는 시세 서버에 못 닿으므로, GitHub Actions(`research-trend.yml`)에서
돌리고 결과를 로그로 읽는다. 결과는 `TREND_RESEARCH_RESULT:` 한 줄 JSON으로도
찍는다.

■ 사전 등록(2026-10-09, 이 파일을 커밋하는 시점 — 결과 보기 전)

  · 후보 4개만 잰다(아래 VARIANTS). 더 늘리지 않는다 — 늘릴수록 우연히 좋은
    것이 뽑힌다.
  · **고르는 구간**: 데이터 시작 ~ 2015-12-31. 그 구간 샤프가 가장 높은 후보를
    채택 후보로 정한다.
  · **판정 구간**: 2016-01-01 ~ 끝. 채택 후보의 이 구간 성적만 '검증 성적'이다.
    판정 구간을 보고 후보를 바꾸지 않는다.
  · 비교 기준선(같은 비용): 균등 보유(월 1회 리밸런스), 60/40(SPY/IEF, 월 1회),
    SPY 보유.
  · 생존 편향 점검: ETF만 쓴 판(개별주·코인 제외)을 함께 낸다 — 오늘 고른
    개별주(NVDA 등)가 과거 성적을 부풀리는지 본다.
  · 비용: 종목별 실측 편도(`measured_cost_model`) — 본 계좌와 같은 자.
"""
from __future__ import annotations

import json
import sys
import time

import pandas as pd

sys.path.insert(0, ".")

from quant.live.daily import measured_cost_model  # noqa: E402
from quant.portfolio import trend_core as T  # noqa: E402

PICK_END = "2015-12-31"
JUDGE_START = "2016-01-01"
VARIANTS = {
    "risk12": T.TrendConfig(sizing="risk", target_vol=0.12),
    "risk20": T.TrendConfig(sizing="risk", target_vol=0.20),
    "notional30": T.TrendConfig(sizing="notional", vol_ref=0.30),
    "notional50": T.TrendConfig(sizing="notional", vol_ref=0.50),
}


def _universe() -> list[tuple[str, str]]:
    with open("state/universe.json", encoding="utf-8") as f:
        return [tuple(x) for x in json.load(f)["targets"]]


def fetch_all(targets) -> dict:
    from quant.data import get_provider
    out = {}
    for m, s in targets:
        start = "2017-08-01" if m == "crypto" else "2003-01-01"
        t0 = time.time()
        try:
            df = get_provider(m).get_ohlcv(s, "1d", start=start, limit=10000)
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗ {m}:{s} 수신 실패 — {exc}")
            continue
        if df is None or df.empty or df.attrs.get("synthetic_fallback"):
            print(f"  ✗ {m}:{s} 실데이터 없음")
            continue
        out[f"{m}:{s}"] = df["close"]
        print(f"  ✓ {m}:{s} {len(df)}봉 {df.index[0].date()}~{df.index[-1].date()}"
              f" ({time.time() - t0:.1f}s)")
    return out


def one_way_costs(cols) -> dict:
    out = {}
    for k in cols:
        m, s = k.split(":", 1)
        out[k] = float(measured_cost_model(m, symbol=s).total_one_way())
    return out


def benchmark(closes: pd.DataFrame, weights_fn, cost: dict) -> pd.Series:
    """월 1회 리밸런스 보유 기준선 — 같은 비용, 같은 체결 지연."""
    tgt = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
    for day in closes.index:
        tgt.loc[day] = weights_fn(closes.loc[day])
    cfg = T.TrendConfig(rebalance="M", band=0.0)
    return T.simulate(closes, cost, cfg, targets=tgt).equity


def _ew(row):
    live = row.dropna().index
    w = pd.Series(0.0, index=row.index)
    if len(live):
        w[live] = 1.0 / len(live)
    return w


def _sixty_forty(row):
    w = pd.Series(0.0, index=row.index)
    if pd.notna(row.get("us_stock:SPY")) and pd.notna(row.get("us_stock:IEF")):
        w["us_stock:SPY"], w["us_stock:IEF"] = 0.6, 0.4
    return w


def _spy(row):
    w = pd.Series(0.0, index=row.index)
    if pd.notna(row.get("us_stock:SPY")):
        w["us_stock:SPY"] = 1.0
    return w


def report(name, equity, res=None) -> dict:
    row = {"name": name,
           "all": T.stats(equity),
           "pick": T.stats(equity[:PICK_END]),
           "judge": T.stats(equity[JUDGE_START:]),
           "last2y": T.stats(equity[equity.index >= equity.index[-1] - pd.Timedelta(days=730)])}
    if res is not None:
        yrs = len(res.equity) / T.PERIODS
        row["turnover_yr"] = round(float(res.turnover.sum()) / yrs, 2)
        row["cost_pct_yr"] = round(float(res.cost.sum()) / yrs * 100, 3)
        row["avg_gross"] = round(float(res.gross.mean()), 2)
    return row


def run(closes: pd.DataFrame, label: str) -> dict:
    cost = one_way_costs(closes.columns)
    rows = []
    for name, cfg in VARIANTS.items():
        res = T.simulate(closes, cost, cfg)
        rows.append(report(name, res.equity, res))
    for name, fn in (("EW보유", _ew), ("60/40", _sixty_forty), ("SPY보유", _spy)):
        rows.append(report(name, benchmark(closes, fn, cost)))
    picked = max((r for r in rows if r["name"] in VARIANTS),
                 key=lambda r: (r["pick"] or {}).get("sharpe", -9))
    print(f"\n=== {label} — {len(closes.columns)}종목 · "
          f"{closes.index[0].date()}~{closes.index[-1].date()} ===")
    hdr = f"{'':12s} {'구간':6s} {'연수익%':>7s} {'변동성%':>7s} {'샤프':>5s} {'최대낙폭%':>8s}"
    print(hdr)
    for r in rows:
        for seg in ("pick", "judge", "last2y"):
            s = r[seg] or {}
            print(f"{r['name']:12s} {seg:6s} {s.get('cagr', 0):7.2f} "
                  f"{s.get('vol', 0):7.2f} {s.get('sharpe', 0):5.2f} {s.get('mdd', 0):8.2f}")
        if "turnover_yr" in r:
            print(f"{'':12s} 회전 {r['turnover_yr']}/년 · 비용 {r['cost_pct_yr']}%/년 · "
                  f"평균 노출 {r['avg_gross']}")
    print(f"→ 사전 등록 규칙(고르는 구간 샤프 최고)으로 채택: {picked['name']}")
    return {"label": label, "picked": picked["name"], "rows": rows}


def main():
    targets = _universe()
    print("시세 수신 —")
    frames = fetch_all(targets)
    closes = T.align_business_days(frames)
    out = {"full": run(closes, "전체 유니버스")}
    from quant.markets import SYMBOL_INFO
    etf_cols = [k for k in closes.columns if not k.startswith("crypto:")
                and ((SYMBOL_INFO.get(k) or {}).get("etf")
                     or k.split(":")[1] in {"GLD", "SLV", "TLT", "IEF", "LQD",
                                            "TIP", "DBC", "XLE", "XLU", "XLP",
                                            "VNQ", "UUP", "EWJ", "VGK", "EEM"})]
    out["etf_only"] = run(closes[etf_cols], "ETF만(생존 편향 점검)")
    print("TREND_RESEARCH_RESULT: " + json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
