"""전략 **명세**(spec) — 자료에서 뽑은 규칙을 사람이 읽을 수 있는 형태로.

명세는 JSON 하나다. 예:

    {
      "version": 1,
      "name": "내-이평선-전략",
      "source": {"kind": "pdf", "ref": "책_3장.pdf", "page": 42},
      "entry":  [{"left": "sma:20", "op": ">", "right": "sma:60",
                  "quote": "20일선이 60일선을 상향 돌파하면 매수한다"}],
      "exit":   [{"left": "sma:20", "op": "<", "right": "sma:60",
                  "quote": "반대로 하향 돌파하면 청산한다"}],
      "weight": 1.0,
      "allow_short": false
    }

⚠️ **왜 코드가 아니라 명세인가.** 자료에서 뽑은 것을 파이썬 코드로 만들면
   ① 사람이 검토할 수 없고 ② 남이 준 파일이 우리 프로세스에서 실행되는 통로가
   된다(사용자가 100명이면 임의 코드 실행 경로가 100개다). 명세는 **데이터**라
   실행 권한이 없고, 여기 적힌 연산자 목록 밖으로 나갈 수 없다.

⚠️ **`quote`는 장식이 아니다.** 모든 조건에는 근거가 된 원문 문장이 붙는다.
   근거를 못 대는 조건은 만들지 않는다 — 그 순간 "자료의 전략"이 아니라
   "우리가 지어낸 전략"이 되고, 사용자는 자기 아이디어가 검증됐다고 오해한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from quant.strategies.base import Strategy

SPEC_VERSION = 1

# 쓸 수 있는 지표 — **이 목록 밖은 명세로 표현할 수 없다.**
# 좁게 시작하는 것이 의도다. 넓히려면 여기에 추가하고 검사를 붙인다.
#   close/open/high/low/volume : 그 봉의 값
#   sma:N   단순이동평균 N봉        ema:N   지수이동평균 N봉
#   rsi:N   RSI N봉                 ret:N   N봉 수익률(%)
#   high:N  최근 N봉 최고가         low:N   최근 N봉 최저가
#   vol:N   N봉 변동성(수익률 표준편차)
#   bb_up:N / bb_lo:N  볼린저밴드 상단/하단 (N봉, 표준편차 2배 고정 — 교과서
#                      기본값. 자료가 다른 배수를 명시하는 경우는 드물고,
#                      명시했다면 그 문장은 '못 옮김'으로 보고된다)
#   vol_ratio:N  오늘 거래량 ÷ 어제까지 N봉 평균 거래량 (2.0 = 평균의 2배)
#   macd / macd_sig  MACD(12,26)와 시그널(9) — 관례 고정값
#   up_streak / down_streak  오늘까지 연속 상승/하락 마감 일수
_BARE = {"close", "open", "high", "low", "volume",
         "macd", "macd_sig", "up_streak", "down_streak"}
_PARAM = {"sma", "ema", "rsi", "ret", "high", "low", "vol",
          "bb_up", "bb_lo", "vol_ratio"}
# 사건형 연산자 — **그 봉에서만** 참이다. 상태형(>, < 등)과 다르게 다뤄야 한다.
_EVENTS = {"cross_above", "cross_below"}
_OPS = {">", ">=", "<", "<="} | _EVENTS

# 파라미터 상한 — 800봉 학습창에서 워밍업이 창을 다 먹지 않게.
MAX_PERIOD = 400


class SpecError(ValueError):
    """명세가 실행할 수 없는 상태 — 이유를 사람 말로 담는다."""


def _num(text: str) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class Condition:
    """조건 하나. `left op right` 이고, right는 지표거나 숫자다."""

    left: str
    op: str
    right: str
    quote: str = ""          # 근거가 된 원문 — 비어 있으면 명세가 거부된다

    def describe(self) -> str:
        """사람이 읽을 한 줄 — 화면·장부에 그대로 나간다."""
        left = _pretty(self.left)
        if self.op in ("cross_above", "cross_below"):
            way = "위로" if self.op == "cross_above" else "아래로"
            right = _pretty(self.right)
            return (f"{left}{_josa(left)} {right}{_josa(right, '을', '를')} "
                    f"{way} 돌파")
        sym = {">": ">", ">=": "≥", "<": "<", "<=": "≤"}[self.op]
        return f"{left} {sym} {_pretty(self.right)}"


def _josa(word: str, with_batchim: str = "이", without: str = "가") -> str:
    """받침 유무에 따라 조사를 고른다. 설명문이 어색하면 읽는 사람이 안 읽는다."""
    if not word:
        return without
    ch = word[-1]
    if "가" <= ch <= "힣":
        return with_batchim if (ord(ch) - 0xAC00) % 28 else without
    return without


def _pretty(term: str) -> str:
    """'sma:20' → '20봉 이동평균'. 숫자는 그대로."""
    if _num(term) is not None:
        return term
    kind, _, param = term.partition(":")
    ko = {"sma": "봉 이동평균선", "ema": "봉 지수이동평균선", "rsi": "봉 RSI",
          "ret": "봉 수익률", "high": "봉 최고가", "low": "봉 최저가",
          "vol": "봉 변동성", "bb_up": "봉 볼린저밴드 상단",
          "bb_lo": "봉 볼린저밴드 하단", "vol_ratio": "봉 평균 대비 거래량 배수"}
    if kind in ko and param:
        return f"{param}{ko[kind]}"
    return {"close": "종가", "open": "시가", "high": "고가", "low": "저가",
            "volume": "거래량", "macd": "MACD", "macd_sig": "MACD 시그널",
            "up_streak": "연속 상승 마감 일수",
            "down_streak": "연속 하락 마감 일수"}.get(kind, term)


@dataclass
class StrategySpec:
    """명세 전체. `validate()`를 통과해야 전략이 될 수 있다."""

    name: str
    entry: list[Condition]
    exit: list[Condition] = field(default_factory=list)
    weight: float = 1.0
    allow_short: bool = False
    source: dict = field(default_factory=dict)
    version: int = SPEC_VERSION
    # 자료에서 규칙을 못 뽑았을 때 그 사실과 이유. 비어 있어야 정상이다.
    notes: list[str] = field(default_factory=list)
    # 손절/익절 — 진입가 대비 %. {"pct": 8.0, "quote": "원문"} 또는 None.
    # 조건(Condition)이 아니라 별도 필드인 이유: 지표 비교는 봉만 보면 되지만
    # 손절은 **내가 얼마에 샀는지**를 기억해야 한다(경로 의존). 판정은 종가
    # 기준이다 — 일봉 시스템이라 장중 이탈은 못 보고, 갭 하락이면 손절선보다
    # 나쁜 가격에 나간다. 이 한계는 summary에 그대로 적는다.
    # 버전을 안 올린 이유: 선택 필드 추가라 옛 명세는 그대로 읽힌다.
    stop: dict | None = None
    target: dict | None = None

    # ── 검증 ──────────────────────────────────────────────────────
    def validate(self) -> None:
        """실행 가능한지 확인한다. 못 쓰면 **이유를 사람 말로** 던진다."""
        if self.version != SPEC_VERSION:
            raise SpecError(
                f"명세 버전이 {self.version}입니다 — 이 프로그램은 "
                f"{SPEC_VERSION}만 읽습니다.")
        if not str(self.name).strip():
            raise SpecError("전략에 이름이 없습니다.")
        if not self.entry:
            raise SpecError(
                "매수(진입) 조건이 없습니다 — 이 자료에서는 '언제 사는지'를 "
                "찾지 못했습니다. 규칙이 글로 적혀 있지 않으면 검증할 수 없습니다.")
        if not (0.0 < float(self.weight) <= 1.0):
            raise SpecError(
                f"비중이 {self.weight}입니다 — 0 초과 1 이하여야 합니다. "
                f"1을 넘는 값은 레버리지이고, 이 시스템은 레버리지를 쓰지 않습니다.")
        for c in list(self.entry) + list(self.exit):
            _check_condition(c)
        for label, rule in (("손절", self.stop), ("익절", self.target)):
            if rule is None:
                continue
            pct = _num((rule or {}).get("pct"))
            if pct is None or not (0.0 < pct < 100.0):
                raise SpecError(
                    f"{label}이 {rule!r}입니다 — 0 초과 100 미만의 %여야 합니다.")
            if not str(rule.get("quote", "")).strip():
                raise SpecError(
                    f"{label} 규칙에 근거 문장이 없습니다 — 자료의 어느 대목에서 "
                    f"나왔는지 댈 수 없는 규칙은 만들지 않습니다.")
        # ⚠️ **돌파는 사건이지 상태가 아니다** (2026-08-14, 만들자마자 실측으로
        #    잡음). '20일선이 60일선을 상향 돌파'는 그 한 봉에서만 참이다.
        #    청산 규칙이 없으면 "진입 조건이 깨지면 청산"으로 도는데, 돌파는
        #    다음 봉에 곧바로 거짓이 되므로 **하루 들고 파는 전략**이 된다.
        #
        #    실측(400봉): 보유 비율 0.8% · 진입 3회. 살아 있는 것처럼 보이지만
        #    사실상 아무것도 안 하는 전략이고, 수수료만 내고 진다.
        #
        #    "골든크로스에 산다"는 보통 "데드크로스에 판다"를 뜻하지만,
        #    **자료가 그렇게 안 적었으면 우리가 채우지 않는다.** 물어보게 한다.
        if (self.entry and all(c.op in _EVENTS for c in self.entry)
                and not self.exit and not (self.stop or self.target)):
            raise SpecError(
                "매수 조건이 '돌파'뿐인데 **언제 파는지가 없습니다.** 돌파는 그 "
                "봉에서만 일어나는 사건이라, 파는 조건이 없으면 사자마자 다음 "
                "봉에 파는 전략이 됩니다(수수료만 나갑니다). 자료에 파는 규칙이 "
                "있으면 그 문장을 함께 넣어 주세요 — 없으면 저희가 임의로 "
                "'반대 돌파에 판다'고 정하지 않습니다.")

    # ── 사람이 읽는 요약 ─────────────────────────────────────────
    def summary(self) -> str:
        lines = [f"전략 '{self.name}'"]
        lines += ["  살 때: " + c.describe() for c in self.entry]
        lines += ["  팔 때: " + c.describe() for c in self.exit] or [
            "  팔 때: (손절/익절로만 나갑니다)" if (self.stop or self.target)
            else "  팔 때: (조건 없음 — 살 조건이 깨지면 청산합니다)"]
        if self.stop:
            lines.append(f"  손절: 진입가 대비 -{float(self.stop['pct']):g}% "
                         "(종가 기준 — 갭 하락이면 더 나쁜 가격에 나갑니다)")
        if self.target:
            lines.append(f"  익절: 진입가 대비 +{float(self.target['pct']):g}% "
                         "(종가 기준)")
        lines.append(f"  비중: {self.weight:.0%}"
                     + (" · 숏 허용" if self.allow_short else ""))
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "version": self.version, "name": self.name,
            "source": self.source, "weight": self.weight,
            "allow_short": self.allow_short,
            "entry": [vars(c) for c in self.entry],
            "exit": [vars(c) for c in self.exit],
            "notes": self.notes,
            "stop": self.stop, "target": self.target,
        }


def _check_condition(c: Condition) -> None:
    if c.op not in _OPS:
        raise SpecError(
            f"'{c.op}'는 쓸 수 없는 비교입니다. 가능: {', '.join(sorted(_OPS))}")
    for side, term in (("왼쪽", c.left), ("오른쪽", c.right)):
        if side == "오른쪽" and _num(term) is not None:
            continue                       # 오른쪽은 숫자여도 된다
        _check_term(term, side)
    if _num(c.left) is not None:
        raise SpecError("왼쪽에는 숫자가 아니라 지표가 와야 합니다.")
    # ⚠️ 근거 없는 조건은 만들지 않는다. 이 검사가 없으면 "자료에서 뽑았다"는
    #    말과 실제가 갈라지고, 사용자는 자기 자료가 검증됐다고 오해한다.
    if not str(c.quote).strip():
        raise SpecError(
            f"조건 '{c.describe()}'에 근거 문장이 없습니다 — 자료의 어느 대목에서 "
            f"나왔는지 댈 수 없는 규칙은 만들지 않습니다.")


def _check_term(term: str, side: str) -> None:
    kind, sep, param = str(term).partition(":")
    if not sep:
        if kind not in _BARE:
            raise SpecError(
                f"{side}의 '{term}'을 모릅니다. 가능: "
                f"{', '.join(sorted(_BARE))} 또는 "
                f"{', '.join(sorted(_PARAM))}:숫자")
        return
    if kind not in _PARAM:
        raise SpecError(f"{side}의 '{kind}'를 모릅니다.")
    n = _num(param)
    if n is None or n != int(n) or int(n) < 1:
        raise SpecError(f"'{term}'의 기간은 1 이상의 정수여야 합니다.")
    if int(n) > MAX_PERIOD:
        raise SpecError(
            f"'{term}'의 기간 {int(n)}봉이 너무 깁니다(최대 {MAX_PERIOD}봉) — "
            f"학습 창을 워밍업이 다 먹어 채점할 봉이 남지 않습니다.")


def spec_from_dict(d: dict) -> StrategySpec:
    """JSON에서 읽은 dict → 명세. 모양이 틀리면 이유를 던진다."""
    if not isinstance(d, dict):
        raise SpecError("명세는 JSON 객체여야 합니다.")

    def conds(key: str) -> list[Condition]:
        raw = d.get(key) or []
        if not isinstance(raw, list):
            raise SpecError(f"'{key}'는 조건 목록이어야 합니다.")
        out = []
        for i, item in enumerate(raw):
            if not isinstance(item, dict):
                raise SpecError(f"'{key}'의 {i + 1}번째 조건이 객체가 아닙니다.")
            missing = {"left", "op", "right"} - set(item)
            if missing:
                raise SpecError(
                    f"'{key}'의 {i + 1}번째 조건에 {', '.join(sorted(missing))}이(가) "
                    f"없습니다.")
            out.append(Condition(str(item["left"]), str(item["op"]),
                                 str(item["right"]), str(item.get("quote", ""))))
        return out

    spec = StrategySpec(
        name=str(d.get("name", "")), entry=conds("entry"), exit=conds("exit"),
        weight=float(d.get("weight", 1.0)),
        allow_short=bool(d.get("allow_short", False)),
        source=dict(d.get("source") or {}),
        version=int(d.get("version", SPEC_VERSION)),
        notes=[str(x) for x in (d.get("notes") or [])],
        stop=dict(d["stop"]) if d.get("stop") else None,
        target=dict(d["target"]) if d.get("target") else None,
    )
    spec.validate()
    return spec


# ── 명세 → 지표 계산 ────────────────────────────────────────────────

def _series(term: str, df: pd.DataFrame) -> pd.Series:
    """지표 이름 → 값 Series. **미래를 참조하지 않는다.**

    모든 창은 `rolling(...)`(과거만)이고 shift(-n) 같은 건 여기 없다.
    tests/test_ingested_specs_do_not_look_ahead.py가 값으로 확인한다.
    """
    n = _num(term)
    if n is not None:
        return pd.Series(float(n), index=df.index)
    kind, _, param = term.partition(":")
    if kind in _BARE and not param:
        close = df["close"].astype(float)
        if kind in ("macd", "macd_sig"):
            macd = (close.ewm(span=12, adjust=False).mean()
                    - close.ewm(span=26, adjust=False).mean())
            return macd if kind == "macd" else macd.ewm(
                span=9, adjust=False).mean()
        if kind in ("up_streak", "down_streak"):
            # 오늘까지 며칠 연속으로 올라(내려) 마감했나 — diff는 과거만 본다.
            move = close.diff()
            hit = (move > 0) if kind == "up_streak" else (move < 0)
            return hit.groupby((~hit).cumsum()).cumsum().astype(float)
        return df[kind].astype(float)
    p = int(float(param))
    close = df["close"].astype(float)
    if kind == "sma":
        return close.rolling(p).mean()
    if kind == "ema":
        return close.ewm(span=p, adjust=False).mean()
    if kind == "rsi":
        from quant.strategies.rsi import rsi as _rsi
        return _rsi(close, p)
    if kind == "ret":
        return close.pct_change(p) * 100.0
    if kind == "high":
        # ⚠️ shift(1) — 오늘 고가가 '최근 N봉 최고가'에 들어가면 "오늘 고가가
        #    최근 최고가를 넘으면 산다"가 항상 참이 된다(자기 자신과 비교).
        #    실제로 살 수 있는 것은 **어제까지의** 최고가를 넘는 순간이다.
        return df["high"].astype(float).rolling(p).max().shift(1)
    if kind == "low":
        return df["low"].astype(float).rolling(p).min().shift(1)
    if kind == "vol":
        return close.pct_change().rolling(p).std() * 100.0
    if kind in ("bb_up", "bb_lo"):
        mid = close.rolling(p).mean()
        sd = close.rolling(p).std()
        return mid + 2.0 * sd if kind == "bb_up" else mid - 2.0 * sd
    if kind == "vol_ratio":
        # ⚠️ 평균은 **어제까지** — 오늘 거래량을 분모에도 넣으면 "평균의
        #    2배"가 스스로를 희석해 큰 날일수록 문턱이 올라간다.
        avg = df["volume"].astype(float).rolling(p).mean().shift(1)
        return df["volume"].astype(float) / avg
    raise SpecError(f"'{term}'을 계산할 수 없습니다.")   # validate가 먼저 막는다


def _evaluate(c: Condition, df: pd.DataFrame) -> pd.Series:
    """조건 하나 → True/False Series. 값이 없는 구간(워밍업)은 False."""
    left, right = _series(c.left, df), _series(c.right, df)
    if c.op in (">", ">=", "<", "<="):
        out = {">": left > right, ">=": left >= right,
               "<": left < right, "<=": left <= right}[c.op]
    else:
        # 돌파는 **어제는 아니었는데 오늘은 그렇다** — 직전 봉과 비교한다.
        prev_l, prev_r = left.shift(1), right.shift(1)
        if c.op == "cross_above":
            out = (left > right) & (prev_l <= prev_r)
        else:
            out = (left < right) & (prev_l >= prev_r)
    # 워밍업 구간(지표가 아직 없는 봉)은 저절로 False가 된다 — pandas에서
    # NaN과의 비교는 NaN이 아니라 **False**다. 진입 조건이면 "안 산다",
    # 청산 조건이면 "안 판다"가 되어 둘 다 맞는 기본값이다.
    #
    # ⚠️ 여기 원래 `known = left.notna() & right.notna()` 마스크를 두고
    #    "NaN을 조건 불충족으로 읽으면 워밍업이 '팔아야 할 때'로 채점된다"는
    #    주석을 달아 놨었다. **그 주석이 틀렸고 마스크는 아무것도 안 했다**
    #    (2026-08-14, 변이 검사가 잡았다 — 마스크를 지워도 결과가 한 봉도
    #    안 바뀐다). 하는 일이 없는데 막는다고 적힌 장치가 이 저장소에서
    #    가장 위험한 종류라, 주석을 고치는 대신 **장치를 지웠다**.
    return out.astype(bool)


class SpecStrategy(Strategy):
    """명세를 그대로 실행하는 전략. **다른 전략과 완전히 동등하게** 취급된다.

    백테스트·검증 3종·페이퍼·실거래 어디서든 기본 전략과 같은 대우를 받고,
    같은 심사(선발전·결승전·검증 게이트)를 통과해야 돈이 간다.

    동작: 진입 조건이 **전부** 참이면 목표 비중, 청산 조건이 하나라도 참이면
    0으로. 그 사이에는 직전 상태를 유지한다(상태기계 — rsi.py와 같은 방식).
    청산 조건이 없으면 '진입 조건이 깨지는 순간' 청산한다.
    """

    name = "spec"

    def __init__(self, spec: StrategySpec):
        spec.validate()
        self.spec = spec
        self.name = str(spec.name)
        self.allow_short = bool(spec.allow_short)

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        enter = np.logical_and.reduce(
            [_evaluate(c, df).to_numpy() for c in self.spec.entry])
        if self.spec.exit:
            leave = np.logical_or.reduce(
                [_evaluate(c, df).to_numpy() for c in self.spec.exit])
        elif self.spec.stop or self.spec.target:
            # 청산 조건은 없지만 손절/익절이 있다 — 나가는 길은 그 둘뿐이다.
            # 여기서 ~enter로 두면 돌파-진입 전략이 하루살이가 된다.
            leave = np.zeros(len(df), dtype=bool)
        else:
            leave = ~enter          # 청산 규칙이 없으면 진입 조건이 깨질 때

        stop = float(self.spec.stop["pct"]) if self.spec.stop else None
        target = float(self.spec.target["pct"]) if self.spec.target else None
        closes = df["close"].astype(float).to_numpy()
        w = float(self.spec.weight)
        out = np.zeros(len(df))
        pos, entry_px = 0.0, 0.0
        for i in range(len(df)):
            if pos == 0.0 and enter[i]:
                pos, entry_px = w, closes[i]
            elif pos != 0.0:
                # 손절/익절은 **진입가 대비 종가**로 판정한다. 진입 봉에서는
                # 재지 않는다(같은 종가와 비교하는 셈이라 뜻이 없다).
                hit_stop = (stop is not None and entry_px > 0
                            and closes[i] <= entry_px * (1 - stop / 100.0))
                hit_target = (target is not None and entry_px > 0
                              and closes[i] >= entry_px * (1 + target / 100.0))
                if leave[i] or hit_stop or hit_target:
                    pos = 0.0
            out[i] = pos
        return self._finalize(pd.Series(out, index=df.index), df.index)

    def describe(self) -> str:
        return self.spec.summary()


_IDENT = re.compile(r"[^0-9A-Za-z가-힣_-]+")


def safe_strategy_name(raw: str, prefix: str = "user") -> str:
    """자료 제목 → 전략 이름. 등록 이름에 이상한 글자가 들어가지 않게."""
    cleaned = _IDENT.sub("-", str(raw or "")).strip("-")[:40]
    return f"{prefix}:{cleaned}" if cleaned else f"{prefix}:이름없음"
