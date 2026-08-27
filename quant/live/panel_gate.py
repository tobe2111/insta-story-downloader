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
    }


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
