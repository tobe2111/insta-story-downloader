"""과최적화 검증(PBO·DSR)을 **실제로 비중에 반영**하는 게이트.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ 왜 만들었나 — 말과 행동이 달랐다 (2026-08-14 발견)

제품 문서와 사이트는 이렇게 말하고 있었다:

    "전략 하나가 실제로 쓰이려면 DSR · PBO · CPCV를 전부 통과해야 합니다.
     하나라도 크게 실패하면 그 전략은 쓰지 않습니다."

코드는 그렇게 하지 않았다. PBO·DSR은 저장소 전체에서 세 곳에만 나왔다 —
계산(CLI), **경보**(flag_watch), 화면 표시(status). **아무것도 막지 않았다.**

발견 시점의 실제 값:
    BTC/USDT  PBO 0.78   ← 문서가 "0.7 초과면 사실상 확실한 과적합, 버릴 것"
    SPY       DSR 0.014  ← 문서 통과 기준 0.95
둘 다 매일 그대로 운용되고 있었다.

이 저장소가 가장 경계하는 실패("선언만 돼 있고 실제로는 안 막는 장치")가
하필 제품이 핵심 차별점이라고 부르는 자리에 있었다.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## 왜 '전부 아니면 전무'가 아니라 등급인가

문서의 원래 문장("통과 못 하면 안 쓴다")을 글자 그대로 구현하면 발견 당일
BTC가 즉시 0이 된다. 그것이 더 정직한가? 아니다 — PBO·DSR은 **연속적인
신뢰도 지표**이지 합격/불합격 도장이 아니고, 표본이 적으면 둘 다 심하게
흔들린다(BTC의 PBO 0.78은 300봉으로 잰 값이었다). 이분법으로 끊으면
'측정 잡음이 계좌를 끄는' 장치가 된다.

그래서 **신뢰도를 비중으로 번역**한다. 못 미더우면 적게 싣는다:

    통과   PBO ≤ 0.2  그리고 DSR ≥ 0.95        → 1.00 (그대로)
    경고   그 사이                              → 0.50 (절반)
    실패   PBO > 0.7 (문서가 "버릴 것"이라 쓴 선) → 0.00 (관망)
    미측정 기록 없음/오래됨                      → 0.50 (통과가 아니다)

**미측정을 1.0으로 두지 않는 것**이 이 설계의 핵심이다. "안 재봤다"와
"재봤더니 괜찮다"를 같게 취급하면, 검증이 통째로 죽은 날 시스템은 가장
공격적으로 돈을 굴린다 — 감사 105·127에서 반복해 겪은 실패 모양이다.

## 정직한 한계

- PBO·DSR이 통과라고 해서 미래 수익이 보장되지 않는다. 이 게이트는
  '노이즈를 고르고 있지 않다'는 약한 증거에 비중을 맞출 뿐이다.
- 표본이 적으면 두 지표 모두 불안정하다. 그래서 실패(0.0) 선은 문서가
  명시한 0.7로만 두고, 그 아래는 절반 감쇠에 그친다.
- 이 게이트는 **개별 종목의 비중만** 줄인다. 포트폴리오 전체를 멈추는 것은
  킬스위치·서킷브레이커의 일이다(서로 곱해져 더 보수적인 쪽이 이긴다).
"""
from __future__ import annotations

import datetime as _dt
import json
import os

from quant.utils.logging import get_logger

log = get_logger("validation_gate")

VALIDATION_FILE = "validation.json"

# 문서(5-4장)에 적힌 통과 기준 — 여기 숫자를 바꾸면 문서도 함께 바꿔야 한다.
PBO_PASS = 0.2          # 이하면 통과
PBO_FAIL = 0.7          # 초과면 "사실상 확실한 과적합 — 버릴 것"
DSR_PASS = 0.95         # 이상이면 통과

SCALE_PASS = 1.0
SCALE_WARN = 0.5
SCALE_FAIL = 0.0

# 검증 기록의 유통기한. 야간 검증은 매일 도는데, 며칠씩 멈춘 기록을 '오늘의
# 판정'으로 쓰면 고장난 검증이 통과 도장을 계속 찍어 준다. 주말·연휴로
# 2~3일 비는 것은 정상이라 넉넉히 잡되, 무한정 믿지는 않는다.
MAX_AGE_DAYS = 7


def _load(state_dir: str) -> dict:
    path = os.path.join(state_dir, VALIDATION_FILE)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError) as exc:
        # 읽기 실패를 '통과'로 만들지 않는다 — 빈 dict면 전 종목 '미측정'이
        # 되어 절반 감쇠가 걸린다(안전한 쪽으로 실패).
        log.warning("검증 장부를 읽지 못했다(전 종목 미측정 처리): %s", exc)
        return {}


def _age_days(rec: dict, asof: str | None) -> int | None:
    """검증 기록이 며칠 된 것인지. 날짜가 없거나 못 읽으면 None(=나이 미상)."""
    day = rec.get("asof") or rec.get("date")
    if not day or not asof:
        return None
    try:
        return (_dt.date.fromisoformat(str(asof)[:10])
                - _dt.date.fromisoformat(str(day)[:10])).days
    except ValueError:
        return None


def grade(rec: dict | None, asof: str | None = None) -> dict:
    """검증 기록 하나를 (등급, 비중 배수, 사람이 읽을 이유)로 번역한다.

    반환: {"grade", "scale", "why", "pbo", "dsr", "age_days"}
    """
    if not rec:
        return {"grade": "미측정", "scale": SCALE_WARN, "pbo": None, "dsr": None,
                "age_days": None,
                "why": "과최적화 검증 기록이 없습니다 — '통과'가 아니라 "
                       "'모른다'이므로 비중을 절반으로 줄입니다."}

    age = _age_days(rec, asof)
    if age is not None and age > MAX_AGE_DAYS:
        return {"grade": "만료", "scale": SCALE_WARN,
                "pbo": rec.get("pbo"), "dsr": rec.get("dsr"), "age_days": age,
                "why": f"검증 기록이 {age}일 전 것입니다(유통기한 "
                       f"{MAX_AGE_DAYS}일) — 오늘의 판정으로 쓸 수 없어 "
                       "비중을 절반으로 줄입니다."}

    pbo = rec.get("pbo")
    dsr = rec.get("dsr")
    pbo = float(pbo) if isinstance(pbo, (int, float)) else None
    dsr = float(dsr) if isinstance(dsr, (int, float)) else None
    base = {"pbo": pbo, "dsr": dsr, "age_days": age}

    if pbo is not None and pbo > PBO_FAIL:
        return {**base, "grade": "실패", "scale": SCALE_FAIL,
                "why": f"과최적화 확률(PBO) {pbo:.0%} — 문서가 '버릴 것'이라 "
                       f"정한 선({PBO_FAIL:.0%})을 넘었습니다. 오늘 이 종목은 "
                       "관망합니다."}

    reasons = []
    if pbo is None and dsr is None:
        return {**base, "grade": "미측정", "scale": SCALE_WARN,
                "why": "기록은 있으나 PBO·DSR이 둘 다 비어 있습니다 — "
                       "'통과'가 아니므로 비중을 절반으로 줄입니다."}
    if pbo is not None and pbo > PBO_PASS:
        reasons.append(f"과최적화 확률(PBO) {pbo:.0%} > 기준 {PBO_PASS:.0%}")
    if dsr is not None and dsr < DSR_PASS:
        reasons.append(f"보정 샤프(DSR) {dsr:.2f} < 기준 {DSR_PASS:.2f}")
    if reasons:
        return {**base, "grade": "경고", "scale": SCALE_WARN,
                "why": " · ".join(reasons) + " — 비중을 절반으로 줄입니다."}
    return {**base, "grade": "통과", "scale": SCALE_PASS,
            "why": "과최적화 검증 통과 — 비중을 그대로 씁니다."}


def validation_grades(keys, state_dir: str = "state",
                      asof: str | None = None) -> dict[str, dict]:
    """운용 대상 키('market:symbol') 목록 → 종목별 등급표.

    측정된 적 없는 종목도 **빠짐없이** 넣는다. 목록에서 빠지면 그 종목은
    아무 감쇠도 안 받고, '측정 안 됨'이 조용히 '통과'가 된다.
    """
    data = _load(state_dir)
    return {k: grade(data.get(k), asof) for k in keys}


def validation_damp(keys, state_dir: str = "state",
                    asof: str | None = None) -> dict[str, float]:
    """종목별 비중 배수만 뽑아 쓴다(daily의 guard_damp와 같은 모양)."""
    return {k: float(g["scale"])
            for k, g in validation_grades(keys, state_dir, asof).items()}


def gate_summary(grades: dict[str, dict]) -> str:
    """사람이 읽을 한 줄 요약 — 장부·브리핑용."""
    if not grades:
        return "검증 게이트: 대상 없음"
    order = ["실패", "경고", "만료", "미측정", "통과"]
    counts = {g: 0 for g in order}
    for v in grades.values():
        counts[v["grade"]] = counts.get(v["grade"], 0) + 1
    parts = [f"{g} {counts[g]}" for g in order if counts.get(g)]
    return "검증 게이트: " + " · ".join(parts)
