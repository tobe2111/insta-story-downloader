"""전략별 방향 정확도 + 수익 지표를 뽑아 표로 출력한다.

정직성:
  - 합성 데이터(여러 시드 평균)로 '통제된 비교'를 낸다. 재현 가능하고,
    특정 종목의 우연에 흔들리지 않는다.
  - 실데이터(BTC/USDT)도 시도하지만, 네트워크가 없으면 합성으로 폴백된다.
  - 어떤 수치도 '미래 수익 보장'이 아니다. 과거·모의 성과일 뿐이다.
"""
from __future__ import annotations

import statistics as st

from quant.backtest import Backtester
from quant.data import SyntheticDataProvider, get_provider
from quant.robustness import directional_accuracy
from quant.strategies import default_ensemble, get_strategy

STRATS = ["ma_cross", "momentum", "rsi", "breakout", "ensemble", "ml"]
SEEDS = [1, 2, 3, 4, 5]
LIMIT = 800


def _strat(name):
    return default_ensemble() if name == "ensemble" else get_strategy(name)


def _run_one(name, df, ppy):
    strat = _strat(name)
    res = Backtester(strat, periods_per_year=ppy).run(df)
    sig = strat.generate_signals(df)
    acc = directional_accuracy(df, sig)["hit_rate"]
    bh = float(df["close"].iloc[-1] / df["close"].iloc[0] - 1.0)  # 매수후보유
    return {
        "acc": acc,
        "ret": res.metrics.total_return,
        "sharpe": res.metrics.sharpe,
        "mdd": res.metrics.max_drawdown,
        "bh": bh,
    }


def _fmt_pct(x):
    return "  N/A " if x != x else f"{x*100:6.1f}%"


def _table(title, rows):
    print(f"\n{'='*72}\n{title}\n{'='*72}")
    print(f"{'전략':<12}{'방향정확도':>10}{'총수익':>10}{'샤프':>8}"
          f"{'최대낙폭':>10}{'매수후보유':>10}")
    print("-" * 72)
    for name, m in rows.items():
        print(f"{name:<12}{_fmt_pct(m['acc']):>10}{_fmt_pct(m['ret']):>10}"
              f"{m['sharpe']:>8.2f}{_fmt_pct(m['mdd']):>10}{_fmt_pct(m['bh']):>10}")


def synthetic_report():
    agg = {n: {"acc": [], "ret": [], "sharpe": [], "mdd": [], "bh": []} for n in STRATS}
    for seed in SEEDS:
        df = SyntheticDataProvider(seed=seed).get_ohlcv("SIM", "1d", limit=LIMIT)
        for n in STRATS:
            m = _run_one(n, df, ppy=365)
            for k in agg[n]:
                agg[n][k].append(m[k])
    rows = {n: {k: st.mean(v) for k, v in agg[n].items()} for n in STRATS}
    _table(f"① 합성 데이터 {len(SEEDS)}회 평균 (봉 {LIMIT}개, 통제된 비교)", rows)


def real_report():
    try:
        prov = get_provider("crypto")
        df = prov.get_ohlcv("BTC/USDT", "1d", limit=LIMIT)
        provider = type(prov).__name__
    except Exception as exc:  # noqa: BLE001
        print(f"\n(실데이터 스킵: {exc})")
        return
    rows = {n: _run_one(n, df, ppy=365) for n in STRATS}
    _table(f"② 실데이터 BTC/USDT 일봉 {len(df)}개 ({provider})", rows)
    print("  ※ CI에 네트워크가 없으면 위 값은 합성 폴백입니다(거래소 접속 실패 시).")


if __name__ == "__main__":
    print("전략 성과 리포트 — 방향 정확도 & 수익 지표")
    print("⚠️ 과거/모의 성과이며 미래 수익을 보장하지 않습니다.")
    synthetic_report()
    real_report()
    print("\n해석: 방향정확도가 50%대에 머무는 게 정상입니다. 60%+ 가 나오면")
    print("      오히려 룩어헤드/과최적화를 의심해야 합니다. 총수익만 보지 말고")
    print("      샤프(위험대비)·최대낙폭·매수후보유 대비를 함께 보세요.")
