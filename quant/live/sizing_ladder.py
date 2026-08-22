"""사이징 사다리 — 같은 확률에 **크기 규칙만** 바꾼 가상 계좌들 (2026-08-22).

⚠️ 왜 만들었나. 사장님 질문: *"왜 이렇게 단타도 조금씩만 하는거야?"*
   미국 장중 계좌 21회차를 뜯어 금액 사슬을 실측했다:

       가상 자금 $10,000 ÷ 종목 8개 = 한 종목 몫 $1,248
       × 신호 세기 0.086            = 실제 주문 $107   (자본의 약 1%)

   범인은 종목 나누기가 아니라 **신호 세기 0.086**이었다. 그 값은 모델의
   상승확률을 비중으로 바꾸는 한 줄에서 나온다(quant/strategies/ml.py):

       비중 = (상승확률 − 문턱 0.55) ÷ 0.45     ← 만점은 확률 100%일 때

   실측 중앙 확률은 0.589다. 즉 **모델이 59%만 확신하니까 9%만 거는 것**이고,
   금액이 작은 진짜 이유는 규칙이 아니라 **확신이 얕다는 사실**이다.

⚠️⚠️ 그리고 이 규칙은 생각보다 방어 가능하다. 같은 확률에서 이론값과 대면:

       확률 0.589  →  현행 0.087 · 켈리 0.178 · **켈리 절반 0.089**

   현행은 관측 구간에서 사실상 **절반 켈리**다(파산 위험을 줄이려고 켈리의
   절반만 거는 것이 표준 관행). 다만 확신이 커지면 갈라진다 — 확률 0.95에서
   현행 0.889 vs 켈리 절반 0.45로, 현행이 훨씬 공격적이다.

   그러니 이 축의 문제는 "값이 틀렸다"가 아니라 **"한 번도 재본 적이 없다"**
   이다. 저장소가 스스로 적어 둔 대로 — *"비중을 정하는 방식(sizing) —
   오디션이 184회 동안 한 번도 안 흔든 축"*. 종목·전략·주기·배분은 매일 밤
   심사를 받는데 "얼마를 걸까"만 기본값 그대로였다.

여기서 그 비대칭을 끝낸다. 본 계좌가 그날 실제로 낸 **같은 확률**에
크기 규칙만 바꿔 가상 계좌 넷을 나란히 굴린다:

    current   — 현행 (p − thr) / (1 − thr)
    kelly     — 켈리(짝수배당 근사) 2p − 1
    half      — 켈리 절반 p − 0.5
    allin     — 문턱을 넘으면 전량

정직한 규약:
  · **데드존은 넷 다 같다**(확률이 문턱 미만이면 관망). 크기 규칙만 다르게
    둬야 이 축이 격리된다 — 진입 조건까지 같이 바꾸면 무엇이 이겼는지
    말할 수 없다.
  · 확률을 못 받은 종목은 그날 그 종목을 통째로 뺀다(넷 다 똑같이). 확률을
    0.5로 가정하면 '모른다'가 '관망 판단'으로 둔갑한다.
  · 평가는 배분 사다리와 같은 규약 — 종가 마크 · 전일 목표를 오늘 수익에
    적용(1봉 지연) · 회전율×수수료만 차감. 본 계좌의 변동성 타깃·킬스위치·
    검증 게이트·켈리 상한은 **없다**. 따라서 절대 성적을 본 계좌와 비교하면
    안 되고, 이 넷 사이의 상대 비교만 뜻이 있다.
  · 트랙이 4개다 — 우연히 좋아 보이는 승자가 나올 확률도 4배다(다중검정).
  · 본 계좌에는 적용하지 않는다. 크기 규칙은 판정 시계의 축(②실행 구조)이라
    적용하는 순간 90일 시계가 리셋된다.

실패 원칙: 이 실험의 어떤 실패도 본 계좌 배치를 죽이면 안 된다.
"""
from __future__ import annotations

import json
import os

from quant.utils.logging import get_logger

log = get_logger("live.sizing_ladder")

SIZERS = ("current", "kelly", "half", "allin")
START_CASH = 1_000_000.0
FEE = 0.001            # 회전율당 10bp — 네 계좌 공통(상대 비교 전용)
DIR = "sizing_ladder"
KEEP_DAYS = 400


def size_of(sizer: str, prob: float, threshold: float) -> float:
    """확률 하나를 목표 비중(0~1)으로. 데드존은 네 규칙이 공유한다.

    ⚠️ 데드존을 공유하는 것이 이 실험의 핵심이다. 진입 조건까지 바꾸면
       '더 자주 사서 이겼는지' '크게 사서 이겼는지'를 구별할 수 없다.
    """
    p = float(prob)
    thr = float(threshold)
    if not (0.0 <= p <= 1.0) or not (0.5 < thr < 1.0):
        return 0.0
    if p < thr:
        return 0.0                       # 데드존 — 넷 다 관망
    if sizer == "current":
        return min(1.0, max(0.0, (p - thr) / (1.0 - thr)))
    if sizer == "kelly":
        return min(1.0, max(0.0, 2.0 * p - 1.0))
    if sizer == "half":
        return min(1.0, max(0.0, p - 0.5))
    if sizer == "allin":
        return 1.0
    raise ValueError(f"모르는 크기 규칙: {sizer}")


def _load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            st = json.load(f)
        if isinstance(st, dict) and "history" in st:
            return st
    except (OSError, ValueError):
        pass
    return {"start_cash": START_CASH, "equity": START_CASH,
            "history": [], "prev_weights": {}, "prev_marks": {}}


def run_sizing_ladder(*, bar: str, probs: dict, thresholds: dict,
                      marks: dict, state_dir: str = "state") -> dict | None:
    """하루 1회 — 크기 규칙별 가상 계좌를 한 봉 전진시킨다. 같은 봉이면 멱등."""
    from quant.utils.jsonio import atomic_write_json

    # 확률을 못 받은 종목은 **넷 다** 그날 통째로 뺀다. 0.5로 채우면
    # '모른다'가 '관망하기로 판단했다'로 둔갑한다. 시세(marks)가 없는 종목도
    # 같은 이유로 빠진다 — 값을 매길 수 없는 것을 계좌에 담을 수는 없다.
    usable = {k: float(p) for k, p in (probs or {}).items()
              if isinstance(p, (int, float)) and 0.0 <= float(p) <= 1.0
              and k in marks}
    # ⚠️ 여기 위에 `if not marks: return None`이 한 줄 더 있었다. 뜻은 맞지만
    #    바로 아래 필터가 이미 같은 일을 해서 **행동으로는 관측되지 않았다**
    #    (변이 시험 2026-08-22: 그 줄을 떼도 어떤 검사도 안 잡았다). 있으나
    #    마나 한 방어는 "여기는 지켜지고 있다"는 착각만 남기므로 지운다.
    #    지켜야 할 것은 아래 한 줄이다 — 담을 것이 없는 날은 아무것도 쓰지
    #    않는다. 빈 회차가 남으면 곡선이 가짜 평평함을 얻는다.
    if not usable:
        return None
    n = len(usable)

    root = os.path.join(state_dir, DIR)
    os.makedirs(root, exist_ok=True)
    out = {}
    for sizer in SIZERS:
        path = os.path.join(root, f"{sizer}.json")
        st = _load(path)
        if st["history"] and st["history"][-1].get("date") == bar:
            out[sizer] = st["history"][-1]           # 같은 봉 재실행 — 멱등
            continue

        # ① 전일 목표를 오늘 수익에 적용(1봉 지연 — 배분 사다리와 같은 규약)
        ret = 0.0
        pw, pm = st.get("prev_weights") or {}, st.get("prev_marks") or {}
        for k, w in pw.items():
            p0, p1 = pm.get(k), marks.get(k)
            if p0 and p1 and float(p0) > 0:
                ret += float(w) * (float(p1) / float(p0) - 1.0)
        equity = float(st["equity"]) * (1.0 + ret)

        # ② 오늘의 목표 = 크기 규칙(확률) ÷ 종목 수(균등 슬라이스)
        #    슬라이스를 균등으로 고정한 이유: 배분 축은 배분 사다리가 이미
        #    재고 있다. 한 실험이 두 축을 함께 흔들면 어느 쪽이 이겼는지
        #    말할 수 없다.
        target = {k: size_of(sizer, p, float(thresholds.get(k, 0.55))) / n
                  for k, p in usable.items()}
        turnover = sum(abs(target.get(k, 0.0) - float(pw.get(k, 0.0)))
                       for k in set(target) | set(pw))
        equity -= equity * turnover * FEE

        keys = set(target) | set(pw)
        st.update({
            "equity": round(equity, 2),
            "prev_weights": {k: round(v, 6) for k, v in target.items()},
            "prev_marks": {k: float(marks[k]) for k in keys if marks.get(k)},
        })
        rec = {"date": bar, "equity": round(equity, 2),
               "return_pct": round((equity / START_CASH - 1) * 100, 3),
               "gross": round(sum(abs(v) for v in target.values()), 4),
               "symbols": n}
        st["history"] = (st["history"] + [rec])[-KEEP_DAYS:]
        atomic_write_json(path, st)
        out[sizer] = rec
    return out


def sizing_public(state_dir: str = "state") -> dict | None:
    """사이트 표시용 — 규칙별 현재 자산·수익률·평균 노출·표본 일수."""
    root = os.path.join(state_dir, DIR)
    if not os.path.isdir(root):
        return None
    rows = {}
    for sizer in SIZERS:
        st = _load(os.path.join(root, f"{sizer}.json"))
        if not st["history"]:
            continue
        last = st["history"][-1]
        gs = [float(r.get("gross") or 0.0) for r in st["history"]]
        rows[sizer] = {"equity": last["equity"],
                       "return_pct": last["return_pct"],
                       "gross_avg": round(sum(gs) / len(gs), 4),
                       "days": len(st["history"])}
    if not rows:
        return None
    return {"tracks": rows, "note": (
        "같은 확률에 **크기 규칙만** 바꾼 가상 계좌들입니다(종가 평가·"
        "수수료만, 본 계좌의 변동성 타깃·킬스위치·검증 게이트는 없음 — "
        "규칙 간 상대 비교 전용). 진입 조건(데드존)은 넷이 같습니다. "
        "트랙이 4개라 우연히 좋아 보이는 승자가 나올 확률도 4배입니다.")}
