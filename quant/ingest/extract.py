"""글에서 **검증 가능한 규칙**을 뽑는다 — 못 뽑으면 못 뽑았다고 말한다.

⚠️ 이 파일에서 가장 중요한 기능은 규칙을 뽑는 게 아니라 **"이 자료에는 규칙이
   없습니다"라고 말할 수 있는 것**이다.

   투자 자료 대부분에는 검증 가능한 규칙이 없다. "시장의 흐름을 읽어라",
   "손실은 짧게 이익은 길게", "공포에 사서 탐욕에 팔아라" — 전부 맞는 말이지만
   **컴퓨터가 실행할 수 없다.** 언제 사는지 숫자로 안 적혀 있기 때문이다.

   여기서 억지로 규칙을 짜내면 그건 자료의 전략이 아니라 **우리가 지어낸
   전략**이고, 사용자는 자기 아이디어가 검증됐다고 오해한다. 그건 이 제품이
   싸우는 바로 그 종류의 거짓말이다.

⚠️ **왜 AI에게 안 맡기고 패턴으로 뽑는가.** AI에게 "이 글의 전략을 뽑아줘"라고
   하면 **거의 항상 뭔가를 내놓는다** — 글에 규칙이 없어도. 그게 언어모델이
   하는 일이다. 그러면 위에 적은 실패가 기본값이 된다.

   그래서 기본 경로는 **결정론적 패턴**이다. 못 찾으면 빈손으로 돌아온다.
   나중에 AI를 붙이더라도 규칙은 같다: 뽑은 조건마다 **근거가 된 원문 문장**을
   대야 하고, 못 대면 버린다(`spec.py`의 `quote` 검사가 강제한다).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from quant.ingest.spec import (
    Condition,
    SpecError,
    StrategySpec,
    safe_strategy_name,
)

# 한 문장에서 이 정도는 봐야 규칙이다 — 숫자 없는 문장은 규칙이 될 수 없다.
_SENT = re.compile(r"[^.!?。\n]+[.!?。\n]?")

# 지표 이름 → 명세 용어. 한국어·영어 표기를 모두 받는다.
_MA = r"(?:이동\s*평균(?:선)?|이평(?:선)?|MA|SMA|단순\s*이동\s*평균)"
_EMA = r"(?:지수\s*이동\s*평균(?:선)?|지수\s*이평(?:선)?|EMA)"

_BUY = r"(?:매수|산다|사고|삽니다|사면|매입|진입|롱|buy|long)"
_SELL = r"(?:매도|판다|팔고|팝니다|팔면|청산|정리|숏|sell|short|exit|close)"

# ── 규칙 조각을 알아보는 패턴 ────────────────────────────────────
# 각 패턴은 (정규식, 만드는 함수)이며, 함수는 Condition 또는 None을 준다.
# 새 패턴을 넣을 때는 **반드시** tests/test_only_real_rules_become_strategies.py
# 에 '이건 뽑혀야 한다'와 '이건 안 뽑혀야 한다'를 같이 넣을 것.


@dataclass
class Extraction:
    """뽑은 결과. `spec`이 None이면 못 뽑은 것이고, `reasons`가 그 이유다."""

    spec: StrategySpec | None
    reasons: list[str]
    sentences_seen: int = 0

    @property
    def ok(self) -> bool:
        return self.spec is not None


def _ma_cross(sent: str) -> tuple[Condition | None, Condition | None]:
    """'20일선이 60일선을 상향 돌파하면 매수' 꼴."""
    m = re.search(
        rf"(\d{{1,3}})\s*(?:일|봉)?\s*{_MA}?\s*(?:선)?[가-힣\s]*?"
        rf"(\d{{1,3}})\s*(?:일|봉)?\s*{_MA}?\s*(?:선)?"
        # ⚠️ '뚫다'를 빼먹고 있었다(감사 269). 한국어 매매 글에서 "위로
        #    뚫으면"은 "위로 돌파하면"만큼 흔하다. 실측: 사용자가 매수는
        #    "위로 돌파", 매도는 "아래로 뚫으면"으로 적었더니 **매도 규칙만
        #    조용히 사라졌다** — 사는 규칙만 있고 파는 규칙이 없는 전략이 된다.
        rf"[^.!?\n]*?(상향\s*(?:돌파|뚫)|하향\s*(?:돌파|뚫)|"
        rf"위로\s*(?:돌파|뚫)|아래로\s*(?:돌파|뚫)|"
        rf"golden\s*cross|dead\s*cross|넘으면|밑으로)",
        sent, re.I)
    if not m:
        return None, None
    fast, slow, how = m.group(1), m.group(2), m.group(3).lower()
    up = bool(re.search(r"상향|위로|golden|넘으면", how))
    cond = Condition(f"sma:{fast}", "cross_above" if up else "cross_below",
                     f"sma:{slow}", sent.strip())
    # ⚠️ 같은 문장 꼴이 사는 규칙일 수도, 파는 규칙일 수도 있다. 문장이
    #    '매수'라 하면 진입, '매도'라 하면 청산이다. 이걸 안 보고 전부 진입으로
    #    넣으면 "하향 돌파하면 매도한다"가 **매수 조건**으로 들어간다.
    buy = bool(re.search(_BUY, sent, re.I))
    sell = bool(re.search(_SELL, sent, re.I))
    if sell and not buy:
        return None, cond
    if buy and not sell:
        return cond, None
    # 한 문장에 둘 다 있거나(예: "돌파하면 매수, 반대면 매도") 아무것도 없으면
    # 어느 쪽인지 단정하지 않는다 — 방향을 잘못 넣는 것보다 안 넣는 게 낫다.
    return None, None


def _rsi_level(sent: str) -> tuple[Condition | None, Condition | None]:
    """'RSI가 30 아래면 매수' / 'RSI 70 위면 매도' 꼴."""
    m = re.search(r"RSI[^0-9\n]{0,20}(\d{1,3})", sent, re.I)
    if not m:
        return None, None
    level = int(m.group(1))
    if not (0 < level < 100):
        return None, None
    below = bool(re.search(r"(이하|아래|밑|미만|below|under|과매도)", sent, re.I))
    above = bool(re.search(r"(이상|위|초과|above|over|과매수)", sent, re.I))
    if below == above:            # 둘 다거나 둘 다 아니면 방향을 모른다
        return None, None
    buy = bool(re.search(_BUY, sent, re.I))
    sell = bool(re.search(_SELL, sent, re.I))
    cond = Condition("rsi:14", "<=" if below else ">=", str(level), sent.strip())
    if buy and not sell:
        return cond, None
    if sell and not buy:
        return None, cond
    # 매수인지 매도인지 안 적혀 있으면 **관례로 채우지 않는다.**
    # "RSI 30"만 보고 매수라고 정하는 건 자료가 아니라 우리 상식이다.
    return None, None


def _price_ma(sent: str) -> tuple[Condition | None, Condition | None]:
    """'주가가 200일 이동평균선 위에 있으면 매수' 꼴."""
    m = re.search(rf"(?:주가|종가|가격|price|close)[^.\n]{{0,20}}?"
                  rf"(\d{{1,3}})\s*(?:일|봉)?\s*({_MA}|{_EMA})", sent, re.I)
    if not m:
        return None, None
    period, kind = m.group(1), m.group(2)
    ind = "ema" if re.match(_EMA, kind, re.I) else "sma"
    above = bool(re.search(r"(위|이상|상회|above|넘)", sent, re.I))
    below = bool(re.search(r"(아래|이하|밑|하회|below)", sent, re.I))
    if above == below:
        return None, None
    cond = Condition("close", ">" if above else "<", f"{ind}:{period}",
                     sent.strip())
    buy = bool(re.search(_BUY, sent, re.I))
    sell = bool(re.search(_SELL, sent, re.I))
    if buy and not sell:
        return cond, None
    if sell and not buy:
        return None, cond
    return None, None


def _breakout(sent: str) -> tuple[Condition | None, Condition | None]:
    """'20일 신고가를 뚫으면 매수' 꼴 — 터틀 트레이딩 계열."""
    m = re.search(r"(\d{1,3})\s*(?:일|봉)[^.\n]{0,16}?"
                  r"(신고가|최고가|고점|신저가|최저가|저점)", sent, re.I)
    if not m:
        return None, None
    period, what = m.group(1), m.group(2)
    high = bool(re.search(r"신고가|최고가|고점", what))
    buy = bool(re.search(_BUY, sent, re.I))
    sell = bool(re.search(_SELL, sent, re.I))
    if high and buy and not sell:
        return Condition("close", ">", f"high:{period}", sent.strip()), None
    if (not high) and sell and not buy:
        return None, Condition("close", "<", f"low:{period}", sent.strip())
    if (not high) and buy and not sell:      # 저점 매수(역추세)
        return Condition("close", "<", f"low:{period}", sent.strip()), None
    return None, None


_PATTERNS = (_ma_cross, _rsi_level, _price_ma, _breakout)

# 규칙처럼 들리지만 **실행할 수 없는** 말들. 이게 있는데 조건이 하나도 안
# 나오면, "규칙이 없다"가 아니라 "규칙처럼 보이지만 숫자가 없다"고 말해 준다 —
# 사용자가 자기 자료를 고칠 수 있게.
_VAGUE = re.compile(
    r"(흐름|분위기|감각|촉|눈치|심리|공포|탐욕|과감|신중|추세를\s*읽|"
    r"손실은\s*짧게|이익은\s*길게|무릎에\s*사서|어깨에\s*팔|"
    r"trend|sentiment|feel|gut)", re.I)

# **숫자가 있고 매매 행위를 말하는데 우리가 못 옮긴 문장**을 찾기 위한 그물
# (감사 269). 이런 문장이 있는데 아무 말 없이 지나가면, 사용자는 "✅ 이렇게
# 읽었습니다"를 보고 자기 규칙이 **전부** 반영된 줄 안다.
#
# 실측: "손절은 -8%, 익절은 +20%로 잡습니다"를 넣었더니 조건 두 개만
# 보여주고 이 문장은 **언급조차 되지 않았다.** 사용자 입장에서 가장 중요한
# 위험 관리 규칙이 조용히 사라진 셈이다. 지어내지 않는 것과 말하지 않는
# 것은 다르다 — 이 저장소는 전자를 지키기로 했지 후자를 허용한 적이 없다.
_RULEISH = re.compile(
    r"(?=.*\d)"                                     # 숫자가 있고
    r".*(매수|매도|사|팔|진입|청산|손절|익절|보유|비중|분할|"
    r"buy|sell|entry|exit|stop|target|position)", re.I)


def extract_spec(text: str, *, title: str = "", source: dict | None = None,
                 max_conditions: int = 4) -> Extraction:
    """글 → 전략 명세. **못 뽑으면 spec=None과 이유를 준다.**

    max_conditions: 진입 조건 상한. 조건이 많을수록 과거에만 맞을 확률이
      올라간다(과최적화) — 한 자료에서 열 개를 뽑아 전부 AND로 걸면
      백테스트는 아름답고 실전은 아무것도 안 산다.
    """
    reasons: list[str] = []
    body = str(text or "")
    if not body.strip():
        return Extraction(None, ["자료에서 글자를 읽지 못했습니다 — 스캔한 "
                                 "이미지 PDF이거나 자막이 없는 영상일 수 있습니다."])

    sentences = [s.strip() for s in _SENT.findall(body) if s.strip()]
    entry: list[Condition] = []
    exits: list[Condition] = []
    seen: set[tuple[str, str, str]] = set()
    used: set[str] = set()          # 조건을 하나라도 내놓은 문장
    for sent in sentences:
        for pat in _PATTERNS:
            e, x = pat(sent)
            for cond, bucket in ((e, entry), (x, exits)):
                if cond is None:
                    continue
                used.add(sent)
                key = (cond.left, cond.op, cond.right)
                if key in seen:
                    continue
                seen.add(key)
                bucket.append(cond)

    # 규칙처럼 생겼는데 **우리가 못 옮긴** 문장 (감사 269).
    # 손절·익절·분할매수처럼 사용자에게 가장 중요한 규칙이 여기 걸린다.
    unread = [s for s in sentences if s not in used and _RULEISH.match(s)]

    if not entry:
        # 왜 못 뽑았는지를 **구별해서** 말한다. "규칙이 없다"와 "규칙은 있는데
        # 숫자가 없다"는 사용자가 할 일이 다르다.
        if _VAGUE.search(body):
            reasons.append(
                "규칙처럼 읽히는 대목은 있지만 **숫자로 적힌 조건이 없습니다.** "
                "'추세를 읽어라' 같은 문장은 사람은 이해해도 컴퓨터는 실행할 수 "
                "없습니다. '20일 이동평균이 60일을 위로 돌파하면 매수'처럼 "
                "숫자와 비교가 들어간 문장이 있어야 검증할 수 있습니다.")
        else:
            reasons.append(
                "이 자료에서 **언제 사는지**를 찾지 못했습니다. 매수 조건이 "
                "숫자로 적힌 문장이 있어야 합니다.")
        if exits:
            reasons.append(
                f"파는 조건은 {len(exits)}개 찾았지만, 사는 조건 없이는 "
                f"전략이 되지 않습니다.")
        return Extraction(None, reasons, len(sentences))

    if len(entry) > max_conditions:
        # 자르되 **자른 사실을 남긴다** — 조용히 버리면 사용자는 자기 규칙이
        # 다 반영된 줄 안다.
        reasons.append(
            f"매수 조건을 {len(entry)}개 찾았지만 앞의 {max_conditions}개만 "
            f"씁니다. 조건을 많이 겹칠수록 과거에만 맞을 확률이 올라갑니다"
            f"(과최적화). 뺀 조건: "
            + " · ".join(c.describe() for c in entry[max_conditions:]))
        entry = entry[:max_conditions]

    # ⚠️ **못 옮긴 것을 말한다.** 지어내지 않는 것과 말하지 않는 것은 다르다.
    #    "✅ 이렇게 읽었습니다"만 보여주면 사용자는 자기 규칙이 전부 반영된
    #    줄 안다 — 실제로는 손절·익절이 통째로 빠졌는데도.
    if unread:
        shown = unread[:5]
        more = f" (외 {len(unread) - len(shown)}문장)" if len(unread) > len(shown) else ""
        reasons.append(
            "**다음 문장은 규칙처럼 보이는데 옮기지 못했습니다** — 이 "
            "부분은 검증에 **반영되지 않습니다**. 지금 옮길 수 있는 것은 "
            "지표 사이의 비교(이동평균 교차·RSI 수준·가격 돌파)뿐이고, "
            "손절·익절·분할매수처럼 보유 중에 값을 재는 규칙은 아직 "
            "지원하지 않습니다"
            + more + ":\n    · " + "\n    · ".join(shown))

    spec = StrategySpec(
        name=safe_strategy_name(title or (source or {}).get("ref", "")),
        entry=entry, exit=exits[:max_conditions],
        source=dict(source or {}), notes=list(reasons),
    )
    # ⚠️ 조건을 찾았다고 전략이 되는 건 아니다. 명세 자체가 실행 불가능한
    #    조합일 수 있다(예: 매수가 '돌파'뿐인데 파는 규칙이 없음 — 하루 들고
    #    파는 전략이 된다). 그때는 **터뜨리지 말고** 이유를 돌려준다 — 이
    #    함수의 계약은 "못 뽑으면 이유를 준다"이지 "예외를 던진다"가 아니다.
    try:
        spec.validate()
    except SpecError as exc:
        reasons.append(str(exc))
        return Extraction(None, reasons, len(sentences))
    return Extraction(spec, reasons, len(sentences))
