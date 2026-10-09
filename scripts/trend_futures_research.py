"""선물 트랙에 추세 코어를 쓸 수 있나 — 코인 5종목 장기 검증 (감사 335 ②).

사장님 승인(2026-10-09): "1,2번 진행" — ② 선물 계좌(레버리지 가능)에 같은
엔진을 쓰되 따로 검증한다.

■ 사전 등록(이 파일을 커밋하는 시점 — 결과 보기 전)

  · 후보 4개(`trend_core.FUTURES_VARIANTS`): 롱 전용/양방향 × 목표 변동성
    20%/40%. 레버리지 상한 3배(트랙의 기존 한도), 한 종목 상한 1배.
  · **고르는 구간**: 데이터 시작 ~ 2021-12-31(샤프 최고).
    **판정 구간**: 2022-01-01 ~ 끝 — 2022년 코인 폭락(BTC −65%)이 들어 있다.
  · 비용: 코인 실측 편도(`measured_cost_model("crypto")`) + **펀딩 연 11%를
    롱·숏 모두에** 물린다(보수적 — 실제로는 한쪽은 받는다).
  · 기준선: 비트코인 1배 보유, 코인 5종목 균등 보유(월 1회).
  · ⚠️ 시세는 야후(BTC-USD 등)다 — 거래소 무기한 선물 가격과 다르고,
    선물 체결 수수료는 현물 실측으로 대신한다. 근사라는 사실을 결과에 적는다.
  · 채택 후보의 **판정 구간** 샤프가 0 이하이거나 최대낙폭이 −50%보다 나쁘면
    선물 트랙에 적용하지 **않는다**(현행 유지 + 결과 공개).
"""
from __future__ import annotations

import json
import sys

import pandas as pd

sys.path.insert(0, ".")

from quant.live.daily import measured_cost_model  # noqa: E402
from quant.portfolio import trend_core as T  # noqa: E402

PICK_END = "2021-12-31"
JUDGE_START = "2022-01-01"
TICKERS = {"crypto:BTC/USDT": "BTC-USD", "crypto:ETH/USDT": "ETH-USD",
           "crypto:SOL/USDT": "SOL-USD", "crypto:BNB/USDT": "BNB-USD",
           "crypto:XRP/USDT": "XRP-USD"}
MAX_JUDGE_MDD = -50.0


def fetch() -> dict:
    import yfinance as yf
    out = {}
    for key, tk in TICKERS.items():
        df = yf.download(tk, start="2014-01-01", progress=False,
                         auto_adjust=True)
        if df is None or df.empty:
            print(f"  ✗ {tk}")
            continue
        close = df["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        out[key] = close.dropna()
        print(f"  ✓ {tk} {len(close)}봉 {close.index[0].date()}~{close.index[-1].date()}")
    return out


def main():
    frames = fetch()
    closes = T.align_business_days(frames)
    fee = float(measured_cost_model("crypto").total_one_way())
    cost = {k: fee for k in closes.columns}
    rows = []
    for name in T.FUTURES_VARIANTS:
        cfg = T.variant_config(name)
        res = T.simulate(closes, cost, cfg)
        yrs = len(res.equity) / T.PERIODS
        rows.append({"name": name,
                     "pick": T.stats(res.equity[:PICK_END]),
                     "judge": T.stats(res.equity[JUDGE_START:]),
                     "turnover_yr": round(float(res.turnover.sum()) / yrs, 2),
                     "cost_pct_yr": round(float(res.cost.sum()) / yrs * 100, 2),
                     "avg_gross": round(float(res.gross.mean()), 2)})
    for name, w in (("BTC보유", {"crypto:BTC/USDT": 1.0}), ("코인균등", None)):
        tgt = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
        for day in closes.index:
            live = closes.loc[day].dropna().index
            if w is None:
                if len(live):
                    tgt.loc[day, live] = 1.0 / len(live)
            elif "crypto:BTC/USDT" in live:
                tgt.loc[day, "crypto:BTC/USDT"] = 1.0
        eq = T.simulate(closes, cost, T.TrendConfig(rebalance="M", band=0.0),
                        targets=tgt).equity
        rows.append({"name": name, "pick": T.stats(eq[:PICK_END]),
                     "judge": T.stats(eq[JUDGE_START:])})
    picked = max((r for r in rows if r["name"] in T.FUTURES_VARIANTS),
                 key=lambda r: (r["pick"] or {}).get("sharpe", -9))
    j = picked["judge"] or {}
    ok = j.get("sharpe", 0) > 0 and j.get("mdd", -100) > MAX_JUDGE_MDD
    print(f"\n=== 코인 선물 — {closes.index[0].date()}~{closes.index[-1].date()} "
          f"· 편도 {fee * 1e4:.1f}bp + 펀딩 연 {T.FUTURES_CARRY * 100:.1f}% ===")
    print(f"{'':11s} {'구간':6s} {'연수익%':>8s} {'변동성%':>7s} {'샤프':>5s} {'최대낙폭%':>8s}")
    for r in rows:
        for seg in ("pick", "judge"):
            s = r[seg] or {}
            print(f"{r['name']:11s} {seg:6s} {s.get('cagr', 0):8.2f} {s.get('vol', 0):7.2f} "
                  f"{s.get('sharpe', 0):5.2f} {s.get('mdd', 0):8.2f}")
        if "turnover_yr" in r:
            print(f"{'':11s} 회전 {r['turnover_yr']}/년 · 매매비용 {r['cost_pct_yr']}%/년 · "
                  f"평균 노출 {r['avg_gross']}배")
    print(f"→ 사전 등록 규칙으로 채택: {picked['name']} · 적용 조건 "
          f"{'충족' if ok else '미달 — 적용 안 함'}")
    print("TREND_FUTURES_RESULT: " + json.dumps(
        {"picked": picked["name"], "apply": ok, "rows": rows}, ensure_ascii=False))


if __name__ == "__main__":
    main()
