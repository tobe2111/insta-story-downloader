"""긴 검증 — **같은 설정이 몇 시기에 통했나** (감사 256, 횡단면의 짝).

`crosssection.py`가 "같은 설정을 전 종목에 적용해 몇 곳에서 통했나"를 잰다면,
여기서는 **같은 설정을 훨씬 긴 과거에 적용해 몇 시기에 통했나**를 잰다.
하나는 옆으로, 하나는 뒤로 넓힌 같은 질문이다.

왜 만들었나. 오디션이 보는 구간은 800봉(3.2년)이고, 그중 결승에 쓰는 것은
마지막 120봉(반년)뿐이다. 반년짜리 성적으로는 "이 설정이 진짜인가"에
답할 수 없다 — 한 번의 상승장이 만든 착시와 구별이 안 된다.

**학습창은 늘리지 않는다.** 250봉 그대로다. 10년치로 학습시키면 이미 죽은
패턴(2015년의 시장)을 배우게 되고, 그건 개선이 아니라 퇴보다. 늘리는 것은
**검증 구간**뿐이다 — 250봉으로 배우고 다음 구간에서 시험하는 것을 과거
전체에 걸쳐 반복한다(워크포워드). 그래서 이 모듈이 내는 숫자는 학습에
쓰이지 않은 구간의 성적이다.

⚠️ **생존 편향** — 이 지표의 가장 큰 한계다. 여기서 10년을 돌리는 20종목은
   **오늘 시점에 살아남아 우리가 고른** 종목이다. 10년 전의 우리는 이 20개를
   고를 수 없었다. 그때 골랐을 종목 중 일부는 상장폐지됐고, 그 실패는 이
   숫자 어디에도 없다. **그래서 이 성적은 실제로 얻을 수 있었던 것보다
   좋다.** 얼마나 좋은지는 모른다 — 모르는 것을 안다고 적지 않는다.

⚠️ 챔피언 설정도 최근 데이터에서 뽑혔다(감사 240·255와 같은 주의). 과거
   구간에 대해서는 그 설정이 '미래를 알고 고른' 설정이다.

그래서 이 모듈은 **판정이 아니라 관찰**이다. 승격 규칙을 건드리지 않는다.
"""

from __future__ import annotations

import glob
import json
import math
import os

from quant.utils.logging import get_logger

log = get_logger("live.walkforward")

# 목표 깊이 — 일봉 2,500개 ≈ 주식 10년, 코인 6.8년. 거래소·야후가 그만큼
# 안 주면 주는 만큼만 쓰고, 몇 봉을 실제로 썼는지 보고서에 적는다.
LONG_BARS = 2500

# 구간 수 — 2,500봉을 8등분하면 한 구간이 대략 1년 3개월이다. 구간이 너무
# 잘면 한 구간의 표본이 모자라 부호가 동전 던지기가 된다.
SEGMENTS = 8

# 한 구간이 이보다 짧으면 성적을 내지 않는다(모르면 안 적는다).
MIN_SEGMENT_BARS = 40

SURVIVORSHIP_NOTE = (
    "이 성적은 **오늘 살아남은 종목**으로만 계산했습니다. 10년 전에는 이 "
    "종목들을 고를 수 없었고, 그때 골랐을 종목 중 사라진 것들의 손실은 "
    "여기에 없습니다 — 그래서 실제로 얻을 수 있었던 것보다 좋게 나옵니다.")

IN_SAMPLE_NOTE = (
    "설정 자체는 최근 데이터에서 뽑혔습니다. 과거 구간에 대해서는 "
    "'답을 보고 고른' 설정이라는 뜻입니다.")


def _sharpe(returns, periods_per_year: int) -> float | None:
    """구간 샤프 — 표본이 2개 미만이거나 변동이 사실상 0이면 만들지 않는다.

    ⚠️ `sd <= 0`으로 판정하면 안 된다(감사 146·149·159와 같은 병). 같은 값이
       늘어선 계열의 표준편차는 부동소수 상쇄 때문에 0이 아니라 1e-19쯤으로
       나오고, 그것으로 나누면 **샤프 수천**이 튀어나온다. 실제로 이 모듈의
       첫 판에서 그렇게 나왔다 — 상대 오차로 판정한다.
    """
    from quant.utils.numerics import degenerate_spread

    n = len(returns)
    if n < 2:
        return None
    mean = float(returns.mean())
    sd = float(returns.std(ddof=1))
    if not math.isfinite(sd) or degenerate_spread(sd, float(returns.abs().mean())):
        return None
    return round(mean / sd * math.sqrt(periods_per_year), 4)


def segment_scores(returns, warmup: int, market: str,
                   segments: int = SEGMENTS, hold=None) -> list[dict]:
    """워밍업 이후 수익 시계열을 연속 구간으로 잘라 구간별 성적을 낸다.

    ⚠️ 워밍업(학습창)을 안 빼면 신호가 없던 구간의 0들이 첫 구간을 '무성과'로
       만든다 — 그 0은 성과가 아니라 **아직 시작 안 함**이다.

    hold를 주면 **같은 구간의 '그냥 보유' 수익**을 나란히 담는다. 대조군이
    없으면 이 보고서는 스스로를 속인다 — 실측(2026-08-14): 구간의 62%가
    플러스였지만, 보유를 이긴 구간은 **31%**뿐이었다. 앞 숫자만 보면 잘하고
    있는 것처럼 보인다. 사이트가 이미 "그냥 보유했다면을 나란히 보여줍니다"
    라고 약속하고 있으므로, 여기 빠져 있던 것은 그 약속의 구멍이었다.
    """
    oos = returns.iloc[warmup:] if warmup > 0 else returns
    ppy = 365 if market == "crypto" else 252
    n = len(oos)
    if n < MIN_SEGMENT_BARS:
        return []
    bh = None
    if hold is not None:
        # 같은 인덱스로 맞춘다 — 어긋난 채 비교하면 대조군이 거짓말이 된다.
        bh = hold.reindex(oos.index).fillna(0.0)
    k = max(1, min(int(segments), n // MIN_SEGMENT_BARS))
    out = []
    for i in range(k):
        lo, hi = n * i // k, n * (i + 1) // k
        part = oos.iloc[lo:hi]
        if len(part) < 2:
            continue
        row = {
            "from": str(part.index[0])[:10],
            "to": str(part.index[-1])[:10],
            "bars": int(len(part)),
            "total_return": round(float((1 + part).prod() - 1), 6),
            "sharpe": _sharpe(part, ppy),
        }
        if bh is not None:
            hr = float((1 + bh.iloc[lo:hi]).prod() - 1)
            row["hold_return"] = round(hr, 6)
            row["beat_hold"] = bool(row["total_return"] > hr)
        out.append(row)
    return out


def long_history(market: str, symbol: str, bars: int = LONG_BARS):
    """가능한 만큼 깊은 과거를 받아 온다. 못 받으면 None(지어내지 않는다).

    합성 폴백은 **거부한다** — 가짜 시세로 만든 10년 성적은 그럴듯한
    거짓말이고, 이 보고서의 목적과 정면으로 어긋난다.
    """
    try:
        from quant.data import get_provider
        df = get_provider(market).get_ohlcv(symbol, "1d", limit=bars)
    except Exception as exc:  # noqa: BLE001 — 한 종목 실패가 보고서를 막지 않는다
        log.warning("긴 과거 수신 실패 %s/%s: %s", market, symbol, exc)
        return None
    if df is None or df.empty or df.attrs.get("synthetic_fallback"):
        return None
    return df


def _snapshot_frame(state_dir: str, market: str, symbol: str):
    """네트워크를 못 쓸 때의 대체 — 그날 배치가 저장한 입력 그대로."""
    import pandas as pd

    snaps = sorted(glob.glob(os.path.join(state_dir, "snapshots", "*")))
    stem = f"{market}_{symbol.replace('/', '_')}.csv.gz"
    for snap in reversed(snaps):
        path = os.path.join(snap, stem)
        if os.path.exists(path):
            try:
                return pd.read_csv(path, index_col=0, parse_dates=True)
            except Exception as exc:  # noqa: BLE001
                log.warning("스냅샷 읽기 실패 %s: %s", path, exc)
    return None


def walkforward_report(state_dir: str = "state", *, bars: int = LONG_BARS,
                       champions: dict | None = None,
                       fetch: bool = True,
                       segments: int = SEGMENTS) -> dict:
    """챔피언 설정을 종목별 최장 과거에 적용한 구간별 성적.

    fetch=False면 네트워크를 타지 않고 스냅샷만 쓴다(검사·오프라인용).
    """
    from quant.backtest import Backtester, CostModel
    from quant.strategies import get_strategy

    if champions is None:
        from quant.live.retrain import load_champions
        champions = load_champions(state_dir)
    if not champions:
        return {}

    rows = []
    for key, spec in sorted(champions.items()):
        market, _, symbol = key.partition(":")
        if not symbol:
            continue
        df = long_history(market, symbol, bars) if fetch else None
        source = "실데이터"
        if df is None:
            df = _snapshot_frame(state_dir, market, symbol)
            source = "스냅샷"
        if df is None or df.empty:
            continue
        params = dict(spec.get("params") or {})
        warmup = int(params.get("train_window") or 0)
        try:
            strat = get_strategy(spec.get("strategy", "ml"), **params)
            res = Backtester(strat, cost_model=CostModel.for_market(market),
                             periods_per_year=365 if market == "crypto" else 252
                             ).run(df)
        except Exception as exc:  # noqa: BLE001
            log.warning("워크포워드 %s 실패: %s", key, exc)
            continue
        # 대조군 — 같은 구간을 '그냥 보유'했다면. 없으면 이 보고서는
        # 스스로를 속인다(플러스 62% vs 보유를 이긴 31%).
        hold = df["close"].pct_change().fillna(0.0)
        segs = segment_scores(res.returns, warmup, market, segments, hold=hold)
        if not segs:
            continue
        wins = sum(1 for s in segs if s["total_return"] > 0)
        beats = sum(1 for s in segs if s.get("beat_hold"))
        # 자본을 얼마나 실제로 굴렸나 — 이 숫자가 어디에도 없어서 "자본의
        # 91%가 늘 현금"이라는 사실을 아무도 몰랐다(2026-08-16 실측).
        pos = res.positions.iloc[warmup:]
        rows.append({
            "key": key, "market": market, "symbol": symbol,
            "source": source, "bars": int(len(df)),
            "from": str(df.index[0])[:10], "to": str(df.index[-1])[:10],
            "warmup": warmup,
            "segments": segs,
            "segment_wins": wins, "n_segments": len(segs),
            "beat_hold_segments": beats,
            "time_in_market": round(float((pos != 0).mean()), 4) if len(pos) else None,
            "avg_exposure": round(float(pos.mean()), 4) if len(pos) else None,
            "worst_segment": min(segs, key=lambda s: s["total_return"]),
        })

    if not rows:
        return {}
    total_segs = sum(r["n_segments"] for r in rows)
    total_wins = sum(r["segment_wins"] for r in rows)
    total_beats = sum(r["beat_hold_segments"] for r in rows)
    deepest = max(r["bars"] for r in rows)
    shallowest = min(r["bars"] for r in rows)
    deployed = [r["avg_exposure"] for r in rows if r["avg_exposure"] is not None]
    in_mkt = [r["time_in_market"] for r in rows if r["time_in_market"] is not None]
    out = {
        "requested_bars": int(bars),
        "deepest_bars": deepest,
        "shallowest_bars": shallowest,
        "n_symbols": len(rows),
        "segment_wins": total_wins,
        "n_segments": total_segs,
        "win_rate": round(total_wins / total_segs, 4) if total_segs else None,
        # ⚠️ 플러스 비율만 보면 잘하는 것처럼 보인다. 이 줄이 진짜 성적이다.
        "beat_hold_segments": total_beats,
        "beat_hold_rate": (round(total_beats / total_segs, 4)
                           if total_segs else None),
        # ⚠️ 이름과 계산이 어긋나면 안 된다 — 이것은 '누적 수익이 보유를
        #    이긴 종목'이 아니라 **구간의 과반에서 이긴 종목** 수다.
        "majority_beat_hold_symbols": sum(
            1 for r in rows if r["beat_hold_segments"] * 2 > r["n_segments"]),
        "avg_exposure": (round(sum(deployed) / len(deployed), 4)
                         if deployed else None),
        "time_in_market": (round(sum(in_mkt) / len(in_mkt), 4)
                           if in_mkt else None),
        # ⚠️ 이 두 표식을 지우면 화면이 '실제로 벌 수 있었던 돈'으로 읽는다.
        "survivorship_biased": True,
        "in_sample_setting": True,
        "notes": [SURVIVORSHIP_NOTE, IN_SAMPLE_NOTE],
        "symbols": sorted(rows, key=lambda r: -r["beat_hold_segments"]),
    }
    log.info("워크포워드: %s종목 · 구간 %s개 중 플러스 %s개",
             out["n_symbols"], total_segs, total_wins)
    return out


def format_walkforward(rep: dict) -> str:
    """사람이 읽는 한 덩어리 — 주간 보고서에 그대로 붙인다."""
    if not rep or not rep.get("n_segments"):
        return "긴 검증: 아직 없습니다(과거 데이터 부족)."
    lines = [
        f"🕰 긴 검증 — 챔피언 설정을 최장 과거에 적용 "
        f"({rep['n_symbols']}종목 · 최대 {rep['deepest_bars']:,}봉)",
        f"   전체 {rep['n_segments']}구간 중 플러스 {rep['segment_wins']}개"
        f"({rep['win_rate']:.0%})",
    ]
    if rep.get("beat_hold_rate") is not None:
        # ⚠️ 대조군이 진짜 성적이다 — 플러스 비율은 상승장이면 저절로 높다.
        lines.append(
            f"   ⚖️ 그중 **그냥 보유를 이긴 구간 {rep['beat_hold_segments']}개"
            f"({rep['beat_hold_rate']:.0%})** · 구간 과반에서 보유를 이긴 종목 "
            f"{rep['majority_beat_hold_symbols']}/{rep['n_symbols']}")
    if rep.get("avg_exposure") is not None:
        # ⚠️ 이것은 **종목 하나만 굴리는 참고 계좌** 기준이다. 통합 계좌는
        #    20종목을 합치므로 총노출이 이보다 훨씬 크다(실측 42~51%).
        #    라벨을 뭉뚱그리면 "자본의 91%가 현금"이라는 틀린 결론이 나온다.
        lines.append(
            f"   💰 종목당 평균 노출 {rep['avg_exposure']:.0%} · "
            f"시장에 있던 시간 {rep['time_in_market']:.0%} "
            f"(종목별 참고 계좌 기준 — 통합 계좌 총노출은 별도)")
    for r in rep["symbols"][:20]:
        worst = r["worst_segment"]
        lines.append(
            f"   {r['key']:22s} 플러스 {r['segment_wins']}/{r['n_segments']} · "
            f"보유이김 {r['beat_hold_segments']}/{r['n_segments']} · "
            f"노출 {(r['avg_exposure'] or 0):.0%} · "
            f"{r['from']}~{r['to']}({r['bars']:,}봉·{r['source']}) · "
            f"최악 {worst['from']} {worst['total_return'] * 100:+.1f}%")
    for note in rep.get("notes") or []:
        lines.append(f"   ⚠️ {note}")
    return "\n".join(lines)


def _cli(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="긴 검증(워크포워드) 보고서")
    ap.add_argument("--state-dir", default="state")
    ap.add_argument("--bars", type=int, default=LONG_BARS)
    ap.add_argument("--offline", action="store_true",
                    help="네트워크를 타지 않고 스냅샷만 쓴다")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    rep = walkforward_report(args.state_dir, bars=args.bars,
                            fetch=not args.offline)
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
    else:
        print(format_walkforward(rep))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
