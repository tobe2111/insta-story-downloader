"""종목 횡단(패널) 관문 — 한 **설정**이 여러 종목에서 함께 좋은가를 잰다.

사장님 결정(2026-08-27, ①안): *지금 바꾸되 기존 관문도 나란히 계속 기록한다.*

■ 왜 필요했나 (실측)

지금 관문은 **종목 하나씩** 판정한다. 그런데 홀드아웃의 실효 표본이 너무
작다 — 재학습 장부 실측으로 중앙 **63봉**이다. 그 표본으로 탈락한 후보들이
"우연이 아니다"(t=2)를 보이려면 중앙 **734봉**이 필요했다. **11배 모자란다.**

그래서 결승을 이긴 20건 중 19건이 부트스트랩 동시검정에서 막혔고
(p 중앙 0.477 — 문턱 0.1에 아깝게 걸린 게 아니라 한참 멀다), 시행 11,721회에
승격은 2회뿐이었다. 관문이 까다로운 게 아니라 **재는 자가 짧았다.**

■ 어떻게 늘리나 — 그리고 늘리면 안 되는 방식

"40종목 × 63봉 = 2,500 표본"으로 세면 **거짓으로 느슨해진다.** 같은 날
여러 종목의 수익률은 함께 움직이므로 독립 표본이 아니다.

올바른 형태는 **날짜별 횡단 평균을 관측 하나로 보는 것**이다. 종목 고유
잡음은 평균에서 상쇄되고 시장 전체 움직임만 남는다 — 상관을 자동으로
올바르게 처리한다.

    실측(스냅샷 32종목 × 125일, 2026-08-27):
      · 종목 간 **초과수익** 상관 중앙값 **0.002** — 사실상 0.
        시장 움직임이 '챌린저 − 챔피언' 차이에서 상쇄되기 때문이다.
      · 분산 감소 **16.2배**(완전 독립이면 32배) → t는 약 **4배**.

■ ⚠️ 이 관문은 느슨해지는 것이 아니라 **재는 대상이 바뀌는** 것이다

패널 관문은 한 설정이 **여러 종목에서 같은 방향으로** 도움이 될 때만 점수를
준다. 종목마다 부호가 갈리면 평균에서 상쇄돼 오히려 t가 **떨어진다** —
실측에서 그대로 나타났다(종목별 |t| 중앙 0.583 vs 패널 |t| 0.487).

그게 결함이 아니라 이 설계의 핵심이다. **한 종목에서만 좋아 보이는 설정은
대개 잡음이고, 이 관문은 거기에 점수를 주지 않는다.** 즉 질문이
"이 종목에서 운이 좋았나"에서 "이 설정이 진짜인가"로 바뀐다.

■ 다중검정

보정은 **설정 개수**에 걸린다(종목 수가 아니다). 한 설정을 40종목에 돌리는
것은 40번의 시도가 아니라 **한 번의 시도를 40배 정밀하게** 재는 것이다.
"""
from __future__ import annotations

import math

import pandas as pd

# 패널 관측(날짜) 최소 개수 — 이보다 적으면 판정하지 않는다.
# 종목을 아무리 많이 모아도 **날짜가 짧으면 t는 못 믿는다**(관측 단위가
# 날짜이기 때문이다). 종목 수로 이 조건을 대신할 수 없다.
MIN_PANEL_DATES = 40

# 패널에 참여해야 하는 최소 종목 수. 하나뿐이면 그냥 종목별 관문이고,
# 그걸 '패널'이라 부르면 기록이 거짓말을 한다.
MIN_PANEL_SYMBOLS = 5


def panel_diff(per_symbol: dict[str, pd.Series],
               min_symbols: int = MIN_PANEL_SYMBOLS) -> pd.Series:
    """종목별 초과수익 계열을 **날짜별 횡단 평균** 한 줄로 접는다.

    per_symbol: {종목키: 초과수익(챌린저 − 챔피언) 날짜 색인 시리즈}

    ⚠️ 날짜마다 참여 종목 수가 다르면(휴장·상장일 차이) 평균의 분산이
       날짜마다 달라진다. 그래서 **그날 최소 종목 수를 못 채운 날은 버린다** —
       한 종목만 남은 날의 값을 다른 날과 똑같이 세면, 그날의 잡음이
       통째로 패널 통계에 들어온다.
    """
    if not per_symbol:
        return pd.Series(dtype=float)
    frame = pd.DataFrame(per_symbol)
    enough = frame.notna().sum(axis=1) >= max(1, int(min_symbols))
    return frame[enough].mean(axis=1).dropna()


def panel_verdict(per_symbol: dict[str, pd.Series], *, t_threshold: float,
                  min_dates: int = MIN_PANEL_DATES,
                  min_symbols: int = MIN_PANEL_SYMBOLS) -> dict:
    """패널 관문의 판정 — 통계만 낸다. 승격 여부는 호출자가 정한다.

    반환에 ``skipped``가 있으면 **판정하지 않았다는 뜻**이고, 그것은
    '통과'가 아니다(감사 226 — 건너뜀은 통과가 아니다).
    """
    symbols = [k for k, s in per_symbol.items() if s is not None and len(s)]
    if len(symbols) < min_symbols:
        return {"skipped": True, "n_symbols": len(symbols), "n_dates": 0,
                "reason": (f"패널에 선 종목이 {len(symbols)}개뿐입니다"
                           f"(최소 {min_symbols}) — 한 종목짜리 평균을 "
                           "'패널'이라고 부르지 않습니다")}
    series = panel_diff({k: per_symbol[k] for k in symbols}, min_symbols)
    n = int(len(series))
    if n < min_dates:
        return {"skipped": True, "n_symbols": len(symbols), "n_dates": n,
                "reason": (f"패널 날짜가 {n}일뿐입니다(최소 {min_dates}) — "
                           "종목을 늘려도 날짜가 짧으면 t를 못 믿습니다")}
    mean = float(series.mean())
    std = float(series.std(ddof=1))
    from quant.utils.numerics import degenerate_spread
    degenerate = degenerate_spread(std, float(series.abs().mean()))
    t_stat = 0.0 if (degenerate or n <= 1) else mean / (std / math.sqrt(n))
    # 방향 일관성 — 몇 종목에서 실제로 이겼나. t가 커도 한 종목의 대박이
    # 만든 값이면 '설정이 진짜'가 아니다.
    wins = sum(1 for k in symbols
               if len(per_symbol[k].dropna()) and float(per_symbol[k].mean()) > 0)
    per_t = symbol_t_stats(per_symbol, symbols, t_threshold)
    return {
        "skipped": False,
        "n_symbols": len(symbols),
        "n_dates": n,
        "mean_diff": mean,
        "t_stat": t_stat,
        "symbol_wins": wins,
        "symbol_win_rate": wins / len(symbols),
        "t_threshold": float(t_threshold),
        "pass": bool(t_stat > t_threshold),
        # ⚠️ **같은 설정을 종목별로도 재서 나란히 남긴다**(사장님 ①안).
        #    아래 `symbol_t_stats`의 주석 참조 — 이게 없으면 승격이 0건인
        #    동안 두 관문의 대조가 성립하지 않는다.
        **per_t,
    }


def symbol_t_stats(per_symbol: dict[str, pd.Series], symbols: list[str],
                   t_threshold: float) -> dict:
    """같은 설정을 **종목 하나씩** 재면 뭐라고 하는가 — 대조용 통계.

    ■ 왜 필요한가 (2026-09-01 장부 실측)

    사장님 ①안은 "관문을 패널로 바꾸되 **기존 종목별 관문도 계속 계산해
    나란히 기록**하라"였다. 그래야 나중에 성적이 변했을 때 관문 때문인지
    시장 때문인지 가릴 수 있다.

    그런데 장부에 실제로 남던 것은 패널 t와 **부호만 센 승률**뿐이었다.
    "종목별 관문이 이 설정을 어떻게 봤나"(t가 문턱을 넘었나)는 없었다 —
    병기가 반만 되고 있었다.

    그 사이 실측(수정 후 4밤): 패널 판정 15건 **통과 0** · 종목별 심사 27건
    **승격 0**. 두 관문이 내내 똑같이 "아니오"만 했으니, 승격을 기다려
    대조를 얻으려는 계획은 **영영 안 온다**(종목별 관문의 역대 승격률은
    시행 11,721회 중 2회다). 대조는 판정 그 자체에서 나와야 한다.

    ■ ⚠️ 이것은 밤 오디션의 재연이 **아니다**

    진짜 종목별 관문은 그 종목·그날의 시도 수로 문턱을 정하고
    (``confirm_threshold``) 부트스트랩 동시검정까지 건다. 여기서는 **패널과
    같은 기준선**(`t_threshold`)을 종목마다 그대로 적용한다. 그래야 두 숫자가
    같은 자 위에 서고, "패널로 접으니 t가 이만큼 달라졌다"를 읽을 수 있다.
    다른 자로 잰 두 숫자를 나란히 놓으면 대조가 아니라 착시다.

    추가 백테스트는 없다 — 이미 모아 둔 종목별 초과수익 계열을 다시 셀 뿐이다.
    """
    from quant.utils.numerics import degenerate_spread

    ts: list[float] = []
    for k in symbols:
        s = per_symbol[k].dropna()
        if len(s) <= 1:
            continue
        sd = float(s.std(ddof=1))
        if degenerate_spread(sd, float(s.abs().mean())):
            ts.append(0.0)
            continue
        ts.append(float(s.mean()) / (sd / math.sqrt(len(s))))
    if not ts:
        return {"symbol_t_median": None, "symbol_pass": 0,
                "symbol_pass_rate": None, "symbol_t_n": 0}
    ts.sort()
    mid = len(ts) // 2
    median = ts[mid] if len(ts) % 2 else (ts[mid - 1] + ts[mid]) / 2
    hits = sum(1 for t in ts if t > t_threshold)
    return {"symbol_t_median": round(median, 4),
            "symbol_pass": hits,
            "symbol_pass_rate": round(hits / len(ts), 4),
            "symbol_t_n": len(ts)}


def power_gain(per_symbol: dict[str, pd.Series],
               min_symbols: int = MIN_PANEL_SYMBOLS) -> dict:
    """패널로 접었을 때 **분산이 실제로 얼마나 줄었는지** 되돌려 준다.

    ⚠️ 이 값을 장부에 남기는 이유: 관문을 바꿨는데 이득이 없거나 반대로
       과하게 느슨해졌다면, 그 사실이 숫자로 보여야 한다. "패널로 바꿨다"는
       선언은 이득의 증거가 아니다.

    독립이면 종목 수만큼 줄고, 완전히 같이 움직이면 하나도 안 준다.
    실측(2026-08-27)은 32종목에서 16.2배 — 그 사이 어딘가가 정상이다.
    """
    symbols = [k for k, s in per_symbol.items() if s is not None and len(s) > 1]
    if len(symbols) < min_symbols:
        return {"skipped": True, "n_symbols": len(symbols)}
    per_sd = pd.Series(
        {k: float(per_symbol[k].dropna().std(ddof=1)) for k in symbols})
    per_sd = per_sd[per_sd > 0]
    series = panel_diff({k: per_symbol[k] for k in symbols}, min_symbols)
    panel_sd = float(series.std(ddof=1)) if len(series) > 1 else 0.0
    if panel_sd <= 0 or per_sd.empty:
        return {"skipped": True, "n_symbols": len(symbols)}
    med = float(per_sd.median())
    return {
        "skipped": False,
        "n_symbols": len(symbols),
        "per_symbol_sd": med,
        "panel_sd": panel_sd,
        "variance_gain": (med / panel_sd) ** 2,   # 유효 표본 배수
        "t_gain": med / panel_sd,                 # t가 커지는 배수
        "if_independent": float(len(symbols)),    # 상한(완전 독립일 때)
    }


# ── 밤의 여러 회차를 나중에 **합칠 수 있게** 남기는 재료 ────────────────────
#
# ■ 왜 필요했나 (2026-09-01 장부 실측)
#
# 밤 배치는 하루에 두 번 돈다. 두 번째 회차는 앞 회차가 이미 심사한 종목을
# 건너뛰므로, 한 밤의 두 줄은 **서로 겹치지 않는 종목**을 본다. 실측:
#
#     밤 2026-08-31 : 12종목 + 5종목  (같은 명단 3설정)
#     밤 2026-09-01 : 13종목 + 11종목 (같은 명단 3설정)
#
# 즉 합치면 패널의 횡단 폭이 **거의 두 배**가 된다 — 그게 패널 관문을 만든
# 이유 그 자체다(작업 #56의 ⓑ).
#
# ⚠️ 그런데 지금 장부로는 **합칠 수가 없다.** 남는 것이 설정별 요약
#    (평균·t·날짜 수)뿐이라, 서로 다른 종목 집합에서 나온 두 t를 합쳐
#    union 의 t 를 만들 방법이 없다. 필요한 것은 **날짜별 합과 개수**다:
#
#        union 평균[날짜] = (합₁[날짜] + 합₂[날짜]) / (개수₁ + 개수₂)
#
#    이 두 줄은 기록해 두지 않으면 **나중에 되살릴 수 없다** — 그 밤의
#    백테스트를 통째로 다시 돌려야 하고, 챔피언은 그 사이 바뀐다.
#    그래서 승격을 옮기기 전에 재료부터 남긴다.
#
# ⚠️ 합산은 두 회차가 **겹치지 않는 종목**을 봤을 때만 옳다. 겹치면 그
#    종목이 두 번 세어진다. 그래서 설정마다 종목 열쇠도 함께 남기고,
#    겹치면 합치지 않고 **겹쳤다고 말한다**(조용히 두 번 세는 것보다 낫다).


def daily_terms(per_symbol: dict[str, pd.Series]) -> dict:
    """설정 하나의 **날짜별 합·개수** — 회차를 넘어 합치기 위한 재료.

    ⚠️ 최소 종목 수 필터를 **걸기 전** 값이다. 회차마다 걸어 버리면, 두
       회차가 각각 3·4종목이라 버린 날이 합쳐서 7종목이 되어도 되살아나지
       않는다. 거르는 일은 합친 **뒤에** 한 번만 한다.
    """
    frame = pd.DataFrame(
        {k: v for k, v in (per_symbol or {}).items()
         if v is not None and len(v)})
    if frame.empty:
        return {"dates": [], "sums": [], "counts": [], "symbols": []}
    sums = frame.sum(axis=1, min_count=1)
    counts = frame.notna().sum(axis=1)
    keep = counts > 0
    idx = frame.index[keep]
    dates = [d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
             for d in idx]
    return {
        "dates": dates,
        "sums": [round(float(x), 10) for x in sums[keep]],
        "counts": [int(x) for x in counts[keep]],
        "symbols": sorted(frame.columns.astype(str)),
    }


def symbol_terms(per_symbol: dict[str, pd.Series]) -> dict[str, list[float]]:
    """설정 하나의 **종목별 [t, 평균]** — ①안 병기를 밤 단위로 합치기 위한 재료.

    종목별 계열 전체를 남기면 장부가 몇 배로 커진다. 종목별 관문의 대조에
    실제로 쓰는 것은 t와 부호뿐이므로 그 둘만 남긴다.
    """
    from quant.utils.numerics import degenerate_spread

    out: dict[str, list[float]] = {}
    for k, series in (per_symbol or {}).items():
        if series is None:
            continue
        s = series.dropna()
        if len(s) <= 1:
            continue
        mean = float(s.mean())
        sd = float(s.std(ddof=1))
        deg = degenerate_spread(sd, float(s.abs().mean()))
        t = 0.0 if deg else mean / (sd / math.sqrt(len(s)))
        out[str(k)] = [round(t, 6), round(mean, 10)]
    return out


def merge_daily_terms(chunks: list[dict]) -> dict:
    """같은 설정을 본 **여러 회차**의 날짜별 합·개수를 하나로 포갠다.

    겹치는 종목이 있으면 합치지 않고 ``overlap``에 그 종목을 담아 돌려준다 —
    같은 종목을 두 번 세면 개수가 부풀어 t가 **거짓으로 커진다.**
    """
    sums: dict[str, float] = {}
    counts: dict[str, int] = {}
    seen: set[str] = set()
    overlap: set[str] = set()
    for chunk in chunks or []:
        syms = set(chunk.get("symbols") or [])
        overlap |= (seen & syms)
        seen |= syms
        for d, s, c in zip(chunk.get("dates") or [], chunk.get("sums") or [],
                           chunk.get("counts") or []):
            sums[d] = sums.get(d, 0.0) + float(s)
            counts[d] = counts.get(d, 0) + int(c)
    dates = sorted(sums)
    merged = {
        "dates": dates,
        "sums": [sums[d] for d in dates],
        "counts": [counts[d] for d in dates],
        "symbols": sorted(seen),
    }
    if overlap:
        merged["overlap"] = sorted(overlap)
    return merged


def verdict_from_terms(daily: dict,
                       sym_terms: dict[str, list[float]] | None = None, *,
                       t_threshold: float,
                       min_dates: int = MIN_PANEL_DATES,
                       min_symbols: int = MIN_PANEL_SYMBOLS) -> dict:
    """날짜별 합·개수만으로 패널 판정을 되살린다 — ``panel_verdict``와 같은 자.

    ⚠️ 겹친 종목이 있는 재료는 **판정하지 않는다**(건너뜀은 통과가 아니다).
    """
    if daily.get("overlap"):
        return {"skipped": True, "n_symbols": len(daily.get("symbols") or []),
                "n_dates": 0,
                "reason": ("회차 사이에 같은 종목이 겹쳐 있습니다"
                           f"({', '.join(daily['overlap'][:3])} 등 "
                           f"{len(daily['overlap'])}종목) — 합치면 그 종목이 "
                           "두 번 세어져 t가 거짓으로 커집니다")}
    counts = [int(c) for c in daily.get("counts") or []]
    n_symbols = len(daily.get("symbols") or []) or (max(counts) if counts else 0)
    if n_symbols < min_symbols:
        return {"skipped": True, "n_symbols": n_symbols, "n_dates": 0,
                "reason": (f"패널에 선 종목이 {n_symbols}개뿐입니다"
                           f"(최소 {min_symbols})")}
    vals = [float(s) / int(c)
            for s, c in zip(daily.get("sums") or [], counts)
            if int(c) >= min_symbols]
    n = len(vals)
    if n < int(min_dates):
        return {"skipped": True, "n_symbols": n_symbols, "n_dates": n,
                "reason": (f"패널 날짜가 {n}일뿐입니다(최소 {min_dates}) — "
                           "종목을 늘려도 날짜가 짧으면 t를 못 믿습니다")}
    from quant.utils.numerics import degenerate_spread

    series = pd.Series(vals, dtype=float)
    mean = float(series.mean())
    std = float(series.std(ddof=1))
    deg = degenerate_spread(std, float(series.abs().mean()))
    t_stat = 0.0 if (deg or n <= 1) else mean / (std / math.sqrt(n))
    out = {
        "skipped": False,
        "n_symbols": n_symbols,
        "n_dates": n,
        "mean_diff": mean,
        "t_stat": t_stat,
        "t_threshold": float(t_threshold),
        "pass": bool(t_stat > t_threshold),
    }
    ts = sorted(float(v[0]) for v in (sym_terms or {}).values())
    if ts:
        mid = len(ts) // 2
        wins = sum(1 for v in sym_terms.values() if float(v[1]) > 0)
        hits = sum(1 for t in ts if t > float(t_threshold))
        out.update({
            "symbol_wins": wins,
            "symbol_win_rate": round(wins / len(ts), 4),
            "symbol_t_median": round(
                ts[mid] if len(ts) % 2 else (ts[mid - 1] + ts[mid]) / 2, 4),
            "symbol_pass": hits,
            "symbol_pass_rate": round(hits / len(ts), 4),
            "symbol_t_n": len(ts),
        })
    return out


class PanelCollector:
    """밤 배치가 종목을 도는 동안 **설정별로** 초과수익 계열을 모은다.

    ⚠️ 종목을 가로질러 묶을 수 있는 것은 **여러 종목에 똑같이 선 설정**뿐이다.
       ``mutate_champion()``이 만든 변형은 그 종목 챔피언 주변에서 나온
       것이라 종목마다 다르다 — 그것들을 한 통에 담으면 "같은 설정이 여러
       종목에서 좋았다"가 아니라 **서로 다른 설정들의 평균**이 되고, 그건
       아무 뜻도 없는 숫자다. 그래서 설정 열쇠가 같은 것만 쌓인다.

    수집만 한다 — 판정은 ``verdicts()``를 부르는 쪽의 몫이고, 승격은 또 그
    바깥이다. 재는 것과 정하는 것을 한 함수에 섞지 않는다.
    """

    def __init__(self) -> None:
        self._by_spec: dict[str, dict[str, pd.Series]] = {}

    def add(self, symbol_key: str, diffs: dict[str, pd.Series]) -> None:
        """한 종목의 {설정열쇠: 초과수익 계열}을 통에 붓는다."""
        for spec, series in (diffs or {}).items():
            if series is None or not len(series):
                continue
            self._by_spec.setdefault(spec, {})[symbol_key] = series

    @property
    def specs(self) -> list[str]:
        return sorted(self._by_spec)

    def symbols_for(self, spec: str) -> int:
        return len(self._by_spec.get(spec, {}))

    def verdicts(self, *, t_threshold: float,
                 min_dates: int = MIN_PANEL_DATES,
                 min_symbols: int = MIN_PANEL_SYMBOLS) -> list[dict]:
        """설정마다 패널 판정 — **판정된 것만** 돌려준다.

        ⚠️ 다중검정 보정은 **설정 개수**에 걸어야 한다(종목 수가 아니라).
           한 설정을 40종목에 돌리는 것은 40번의 시도가 아니라 한 번의 시도를
           40배 정밀하게 재는 것이다. 그 보정은 호출자가 ``t_threshold``에
           실어 넘긴다 — 여기서 문턱을 스스로 정하지 않는다(정하는 자와 재는
           자를 나눈다).
        """
        out: list[dict] = []
        for spec in self.specs:
            v = panel_verdict(self._by_spec[spec], t_threshold=t_threshold,
                              min_dates=min_dates, min_symbols=min_symbols)
            v["spec_key"] = spec
            if not v.get("skipped"):
                v["gain"] = power_gain(self._by_spec[spec], min_symbols)
            out.append(v)
        return out

    def terms_for(self, spec: str) -> dict:
        """설정 하나의 **합칠 수 있는 재료**(날짜별 합·개수 + 종목별 t·평균).

        장부에 이것을 남겨야 같은 밤의 여러 회차를 나중에 하나로 포갤 수
        있다. 안 남기면 그 밤은 **영영 못 합친다**(작업 #56의 ⓑ).
        """
        per = self._by_spec.get(spec, {})
        out = daily_terms(per)
        out["symbol_terms"] = symbol_terms(per)
        return out

    def panel_frame(self, min_symbols: int = MIN_PANEL_SYMBOLS,
                    min_dates: int = MIN_PANEL_DATES) -> pd.DataFrame:
        """설정별 패널 계열을 **같은 날짜 위에 나란히** 세운 표(날짜 × 설정).

        동시검정(현실성 검사)을 패널에도 걸기 위한 재료다. 그 검정은 "오늘
        링의 후보 N명 중 최고 t가 우연으로 나올 확률"을 부트스트랩으로 직접
        재는데, **여기서 N은 종목 수가 아니라 설정 수**다. 설정을 많이 세울수록
        귀무 세계의 최고 t도 같이 커져 p가 정직하게 커진다 — 로그 공식도
        상한도 필요 없다(``confirm_threshold``가 상한에 붙어 더 안 오르는
        구간이 생겼던 문제의 해법이 이것이었다).

        ⚠️ 날짜는 **교집합**을 쓴다. 설정마다 다른 날짜 위의 값을 한 표에
           담으면, 부트스트랩이 같은 날의 시장 움직임을 서로 다른 날처럼
           재조합해 상관을 지워 버린다 — p가 거짓으로 작아진다.
        """
        cols: dict[str, pd.Series] = {}
        for spec in self.specs:
            series = panel_diff(self._by_spec[spec], min_symbols)
            if len(series) >= min_dates:
                cols[spec] = series
        if not cols:
            return pd.DataFrame()
        return pd.DataFrame(cols).dropna(how="any")
