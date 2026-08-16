"""횡단면 증거 — **같은 설정이 몇 종목에서 통했나** (감사 255).

왜 만들었나. 오디션은 종목마다 **따로** 열린다. BTC 챔피언은 BTC 800봉으로만
검증되고, SPY 챔피언은 SPY 800봉으로만 검증된다. 그런데 실측(2026-08-15):

    20종목 중 **19종목이 똑같은 챔피언**을 쓰고 있다
    (ml / logreg / 문턱 0.55 / 학습창 250)

같은 설정을 20번 검증하면서 **매번 1/20의 증거만** 쓰고 있었다. 그래서
오디션 179회 중 승격이 1회(0.6%)이고, 그중 93%가 "후보가 챔피언을
통계적으로 못 이김"으로 끝났다 — 표본이 모자라 아무것도 증명되지 않는다.

여기서는 그 반대로 잰다. **오늘의 챔피언 설정을 전 종목에 그대로 적용해
몇 곳에서 통했는지** 센다. 종목 하나가 한 표다.

실측(2026-08-14 스냅샷, 800봉·코인 300봉):

    주식(한국+미국)  15종목 중 13 플러스(87%) · 샤프평균 +0.48 · t = +4.37
      한국            7종목 중  6 플러스(86%) · 샤프평균 +0.63 · t = +2.94
      미국            8종목 중  7 플러스(88%) · 샤프평균 +0.36 · t = +4.17
    코인              5종목 중  1 플러스(20%) · 샤프평균 -0.76 · t = -1.75

**주식과 코인이 반대 방향이다.** 종목별 오디션은 이것을 영영 볼 수 없다.

⚠️ **이 숫자는 인샘플이다**(감사 240과 같은 주의). 챔피언이 바로 그
   데이터에서 뽑혔으므로 t값을 '엣지 증명'으로 읽으면 안 된다. 다만 같은
   절차로 뽑은 설정이 한 시장에서만 뒤집히는 것은 선택 편향으로 설명하기
   어렵다 — 그 **방향의 차이**가 이 지표의 쓸모다.

⚠️ 종목 간 수익률은 상관돼 있다. 미국 8종목은 서로 닮아서 유효 표본은
   8보다 작고, 코인 5개는 사실상 한두 개에 가깝다. t는 부풀려져 있다.
   그래서 이 모듈은 t를 **판정이 아니라 관찰**로 남긴다 — 승격을 자동으로
   바꾸지 않는다.
"""

from __future__ import annotations

import glob
import json
import math
import os

from quant.utils.logging import get_logger

log = get_logger("live.crosssection")

# 이 표본으로는 무엇도 단정하지 않는다는 표식 — 화면·문서가 그대로 인용한다.
IN_SAMPLE_NOTE = ("챔피언을 뽑은 것과 같은 데이터에서 잰 값입니다(인샘플). "
                  "종목 간 상관이 있어 유효 표본은 종목 수보다 작습니다.")

MARKET_OF = {"crypto": "crypto", "kr_stock": "kr_stock", "us_stock": "us_stock"}

# 스냅샷을 고를 때 훑는 최근 날짜 수. 왜 '가장 최근'이 아닌가 —
# **하루가 통째로 안 찍히는 날이 있다.** 실측(2026-08-15): 그날 스냅샷에는
# 코인 5종목만 저장됐다(주식 배치가 그날 기록을 남기지 못함). 그 날을
# 그대로 쓰면 "20종목 중 14 플러스(t=+0.97)"가 "5종목 중 1 플러스(t=-1.39)"가
# 되어 정반대 결론이 나온다. 최근 며칠 중 **가장 많이 담긴 날**을 쓴다.
SNAPSHOT_LOOKBACK = 5


def _fullest_snapshot(state_dir: str) -> str | None:
    """최근 며칠 중 종목이 가장 많이 담긴 스냅샷 폴더(동률이면 최신)."""
    snaps = sorted(glob.glob(os.path.join(state_dir, "snapshots", "*")))
    recent = [s for s in snaps[-SNAPSHOT_LOOKBACK:] if os.path.isdir(s)]
    if not recent:
        return None
    return max(recent,
               key=lambda s: (len(glob.glob(os.path.join(s, "*.csv.gz"))), s))


def _split_key(filename: str) -> tuple[str, str] | None:
    """스냅샷 파일 이름 → (시장, 종목).

    ⚠️ `key.split("_", 1)`로 자르면 안 된다 — 시장 이름 자체에 밑줄이 있어
       (`kr_stock`) 주식 종목이 통째로 빠진다. 처음 이 분석을 돌렸을 때
       20종목 중 5개(코인)만 나왔고, 그 숫자로 결론을 낼 뻔했다.
    """
    stem = os.path.basename(filename).replace(".csv.gz", "")
    for market in MARKET_OF:
        if stem.startswith(market + "_"):
            symbol = stem[len(market) + 1:]
            return market, (symbol.replace("_", "/") if market == "crypto"
                            else symbol)
    return None


def _stats(sharpes: list[float], wins: int) -> dict:
    """표본 통계 — 표본이 2개 미만이면 t를 만들지 않는다(모르면 None)."""
    n = len(sharpes)
    if n == 0:
        return {"n": 0, "wins": 0, "win_rate": None, "sharpe_mean": None,
                "sharpe_sd": None, "t": None}
    mean = sum(sharpes) / n
    out = {"n": n, "wins": wins, "win_rate": round(wins / n, 4),
           "sharpe_mean": round(mean, 4), "sharpe_sd": None, "t": None}
    if n >= 2:
        sd = math.sqrt(sum((x - mean) ** 2 for x in sharpes) / (n - 1))
        out["sharpe_sd"] = round(sd, 4)
        if sd > 0:
            out["t"] = round(mean / (sd / math.sqrt(n)), 4)
    return out


def pooled_evidence(state_dir: str = "state", snapshot: str | None = None,
                    champions: dict | None = None) -> dict:
    """오늘의 챔피언 설정을 전 종목에 적용한 횡단면 증거.

    스냅샷(그날 배치가 저장한 입력 그대로)을 쓴다 — 네트워크를 다시 타지
    않고, `verify`가 재현할 수 있는 같은 재료다.
    """
    import pandas as pd

    from quant.backtest import Backtester, CostModel
    from quant.strategies import get_strategy

    if champions is None:
        from quant.live.retrain import load_champions
        champions = load_champions(state_dir)
    snapshot = snapshot or _fullest_snapshot(state_dir)
    if not snapshot or not os.path.isdir(snapshot):
        return {}

    per_symbol, groups = [], {}
    for path in sorted(glob.glob(os.path.join(snapshot, "*.csv.gz"))):
        parsed = _split_key(path)
        if not parsed:
            continue
        market, symbol = parsed
        spec = champions.get(f"{market}:{symbol}") or {}
        if not spec:
            continue
        try:
            df = pd.read_csv(path, index_col=0, parse_dates=True)
            strat = get_strategy(spec.get("strategy", "ml"),
                                 **(spec.get("params") or {}))
            bt = Backtester(strat, cost_model=CostModel.for_market(market),
                            periods_per_year=365 if market == "crypto" else 252)
            m = bt.run(df).metrics
            row = {"key": f"{market}:{symbol}", "market": market,
                   "bars": int(len(df)),
                   "total_return": round(float(m.total_return), 6),
                   "sharpe": round(float(m.sharpe), 4)}
        except Exception as exc:  # noqa: BLE001 — 한 종목 실패가 전체를 막지 않는다
            log.warning("횡단면 %s:%s 실패: %s", market, symbol, exc)
            continue
        per_symbol.append(row)
        groups.setdefault(market, []).append(row)

    if not per_symbol:
        return {}

    def _agg(rows: list[dict]) -> dict:
        return _stats([r["sharpe"] for r in rows],
                      sum(1 for r in rows if r["total_return"] > 0))

    stocks = [r for r in per_symbol if r["market"] in ("kr_stock", "us_stock")]
    out = {
        "asof": os.path.basename(snapshot),
        "in_sample": True,          # ⚠️ 이 값을 지우면 화면이 실전 성적으로 읽는다
        "note": IN_SAMPLE_NOTE,
        "all": _agg(per_symbol),
        "stocks": _agg(stocks) if stocks else None,
        "markets": {m: _agg(rows) for m, rows in sorted(groups.items())},
        "symbols": sorted(per_symbol, key=lambda r: -r["sharpe"]),
    }
    log.info("횡단면 증거: 전체 %s종목 중 %s 플러스 · t=%s",
             out["all"]["n"], out["all"]["wins"], out["all"]["t"])
    return out


def format_pooled(ev: dict) -> str:
    """사람이 읽는 한 덩어리 — 배치 로그·주간 리포트에 그대로 쓴다."""
    if not ev or not ev.get("all"):
        return "횡단면 증거: 아직 없습니다(스냅샷 부족)."
    lines = [f"📐 횡단면 증거 ({ev.get('asof', '?')} 스냅샷) — "
             f"오늘의 챔피언 설정을 전 종목에 적용"]
    label = {"all": "전체", "stocks": "주식(한국+미국)",
             "crypto": "코인", "kr_stock": "  한국", "us_stock": "  미국"}
    rows = [("all", ev["all"])]
    if ev.get("stocks"):
        rows.append(("stocks", ev["stocks"]))
    rows += [(m, s) for m, s in (ev.get("markets") or {}).items()]
    for key, s in rows:
        if not s or not s["n"]:
            continue
        t = "—" if s["t"] is None else f"{s['t']:+.2f}"
        mean = "—" if s["sharpe_mean"] is None else f"{s['sharpe_mean']:+.2f}"
        lines.append(f"   {label.get(key, key):14s} {s['n']:2d}종목 · "
                     f"플러스 {s['wins']:2d}({s['win_rate']:.0%}) · "
                     f"샤프평균 {mean} · t={t}")
    lines.append(f"   ⚠️ {IN_SAMPLE_NOTE}")
    return "\n".join(lines)


def _cli() -> int:
    ev = pooled_evidence()
    print(format_pooled(ev))
    if ev:
        print("\n" + json.dumps(ev["symbols"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
