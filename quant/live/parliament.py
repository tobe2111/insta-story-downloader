"""의회(parliament) — 챔피언 '교체'가 아니라 상위 전략 '혼합'으로 운용한다.

단일 챔피언이 전액을 굴리면 교체 순간마다 포트폴리오가 급변하고, 한 전략의
붕괴가 곧 계좌의 붕괴다. 의회는 오디션(2단계 관문)을 통과한 전략 최대 K개에
비중을 나눠 주고, 매일 밤 홀드아웃 성과에 따라 그 비중을 '서서히'(EMA)
조정한다 — "챔피언 교체" 대신 "의회 구성 변화"의 서사.

원칙:
  · 입성은 오디션 통과로만 — 비중 조정은 점진, 진입은 엄격(다중검정 관문 유지)
  · 상관 다양성 강제 — 홀드아웃 수익률 상관이 CORR_CAP을 넘는 두 의원은
    같은 실수를 두 번 검증하는 것이므로 점수 낮은 쪽을 탈락시킨다
  · 리더(최대 비중)가 champions.json의 strategy/params 자리를 유지해
    돌연변이·설명·verify 등 단일 챔피언 경로와 호환된다
  · 비중이 MIN_WEIGHT 아래로 시들면 의석을 잃는다(자연 퇴출)
"""
from __future__ import annotations

import math

from quant.utils.logging import get_logger
from quant.utils.numerics import degenerate_spread

log = get_logger("parliament")

PARLIAMENT_K = 3          # 최대 의석 수
CORR_CAP = 0.97           # 이 이상 상관이면 중복 의원 — 다양성 강제
EMA_STEP = 0.25           # 하루에 목표 비중으로 이만큼만 이동(급변 방지)
MIN_WEIGHT = 0.05         # 이 미만이면 의석 상실
ENTRY_WEIGHT = 0.25       # 오디션 통과 신입의 초기 의석
SOFTMAX_TEMP = 12.0       # 홀드아웃 수익 차이 → 목표 비중 민감도

# ── 다양성 의석 (감사 276) ──────────────────────────────────────────
#
# ⚠️ 이 파일은 자기 문제를 이미 적어 두고 있었다(`seat_census` 주석):
#    "의석은 오직 2단계 오디션을 통과한 승격자만 얻는데, 승격은 139회 중
#     1회 일어났다." 실측 2026-08-17 기준 **189회 중 1회(0.5%)**이고,
#    20계좌 전부가 1석이며 챔피언 19/20이 파라미터까지 완전히 같다.
#    종목은 20개인데 **모델은 하나**다 — 그 모델이 틀리는 날 20종목이
#    동시에 틀린다. 배분(HRP·ERC)은 종목 상관을 낮추지만 모델 상관은 1.0이다.
#
#    구조가 없어서가 아니다. **문이 하나뿐**이어서다. 그 문은 이렇게 묻는다:
#
#        "이 후보가 챔피언보다 **더 나은가?**"   (우월성 검정)
#
#    포트폴리오 이론이 말하는 두 번째 질문이 통째로 빠져 있었다:
#
#        "이 후보가 챔피언만큼 하면서 **상관이 낮은가?**"  (비열등성 + 다양성)
#
#    기대수익이 같고 상관이 낮은 자산을 섞으면 **샤프가 오른다.** 그건
#    관문을 무르게 하는 것이 아니라 **다른 질문을 묻는 것**이다. 그래서
#    승격(챔피언 교체)의 문턱은 그대로 두고, 의회에만 두 번째 문을 단다.
#
# 이 문도 공짜가 아니다. 세 관문을 전부 통과해야 한다:
#   ① 선발전에서 **유의하게 못하지 않을 것**(t > -DIVERSIFIER_T_FLOOR)
#   ② 결승 구간(최근 미공개)에서도 **유의하게 못하지 않을 것** — 여기서
#      다시 재므로 선발전 우연으로는 못 들어온다
#   ③ 앉아 있는 모든 의원과 **상관이 낮을 것**(< DIVERSIFIER_CORR_MAX)
# 그리고 의석은 승격자보다 **작게**(0.15 < 0.25) 준다 — 이긴 것과 다른 것은
# 같은 대우를 받지 않는다.
DIVERSIFIER_CORR_MAX = 0.5   # 이보다 상관이 낮아야 '다른 베팅'이다
DIVERSIFIER_T_FLOOR = 1.0    # 이만큼도 못 지면(=유의하게 나쁘지 않으면) 통과
DIVERSIFIER_WEIGHT = 0.15    # 다양성 신입의 초기 의석(승격자보다 작다)
DIVERSIFIER_PER_NIGHT = 1    # 하룻밤에 최대 몇 석까지 새로 여는가(급변 방지)


def _spec_of(m: dict) -> dict:
    return {"strategy": m["strategy"], "params": m["params"]}


def _same(a: dict, b: dict) -> bool:
    return (a.get("strategy") == b.get("strategy")
            and a.get("params") == b.get("params"))


def members_of(entry: dict) -> list[dict]:
    """champions 항목에서 의회 명단을 꺼낸다(없으면 현 챔피언 단독 의회)."""
    ms = entry.get("parliament")
    if ms:
        return [dict(m) for m in ms]
    return [{"strategy": entry["strategy"], "params": entry["params"],
             "weight": 1.0}]


def safe_corr(a, b) -> float:
    """두 수익률 계열의 상관 — **못 재면 NaN을 돌려준다.**

    ⚠️ 이 함수가 생긴 이유 (2026-08-17, 감사 276). 이 파일에는 감사 53에서
       세우고 2026-08-14에 다시 못 박은 규칙이 있다:

           "상관을 못 재면 '무상관(0)'이 아니라 '중복(1)'으로 본다.
            0으로 치면 계산 실패가 곧 통과가 되어, 다양성 강제 장치가
            하필 흔들리는 날에 정확히 반대로 동작한다."

       그 규칙은 `c != c`(NaN 검사)로 구현돼 있었다. **pandas 3.0에서
       그 전제가 무너졌다** — 한쪽이 상수인 계열의 상관이 이제 NaN이 아니라
       0에 가까운 부동소수(6.4e-18)로 나온다. 즉 '못 잰 것'이 '완벽하게
       무상관'으로 읽히고, 그건 다양성 판정에서 **가장 좋은 점수**다.
       가드가 막으려던 방향으로 정확히 열린 셈이다.

       실측: 상수 계열 하나를 다양성 지원자로 넣었더니 그대로 의석을 얻었다
       (이 감사의 검사가 그걸 잡았다).

    그래서 NaN에 기대지 않고 **분산이 의미 있는지 직접 본다.** 어느 한쪽이
    사실상 상수면 상관은 정의되지 않는다 — NaN을 돌려주고, 호출부는 그것을
    '중복'으로 취급한다.
    """
    try:
        a = a.dropna()
        b = b.dropna()
        idx = a.index.intersection(b.index)
        if len(idx) < 3:
            return float("nan")
        a, b = a.reindex(idx), b.reindex(idx)
        for s_ in (a, b):
            if degenerate_spread(float(s_.std(ddof=1)),
                                 float(s_.abs().mean())):
                return float("nan")       # 상수 계열 — 상관이 정의되지 않는다
        c = float(a.corr(b))
        return c if math.isfinite(c) else float("nan")
    except Exception:  # noqa: BLE001
        return float("nan")


def _paired_t(a, b) -> float:
    """a와 b의 **일별 차이**에 대한 짝지은 t값. 못 재면 0.0(중립).

    ⚠️ 0.0은 "차이가 없다"가 아니라 **"판정할 수 없다"**이다. 다양성 문은
       `t > -FLOOR`로 통과를 정하므로, 못 잰 후보는 통과 쪽으로 떨어진다 —
       그래서 이 함수만으로 문을 열지 않는다. 상관 관문(③)이 함께 걸린다.
    """
    try:
        d = (a - b).dropna()
        n = len(d)
        if n < 20:
            return 0.0
        sd = float(d.std(ddof=1))
        if not (sd > 0):
            return 0.0
        return float(d.mean() / (sd / math.sqrt(n)))
    except Exception:  # noqa: BLE001
        return 0.0


# ── 상관까지 본 목표 비중 — **재는 것만 한다** (2026-08-19) ──────────
#
# ⚠️ 실측이 먼저다. 2026-08-19 기준 의석은 39개·전략 11종인데, **자금의
#    72.9%가 한 스펙(logreg 문턱 0.55)**에 있다. 왜 그런가를 코드에서 찾으면
#    이렇게 갈린다:
#
#      · 의석을 **여는 문**은 상관을 본다 — 다양성 의석은 상관 0.5 미만만.
#      · 의석 **크기를 정하는 규칙**은 수익만 본다 — softmax(홀드아웃 수익).
#
#    그래서 다르게 들어온 의원이 시간이 지나면 얇아진다. 포트폴리오 이론이
#    말하는 것은 반대다: 기대수익이 비슷하고 상관이 낮으면 **비중을 더 줘야**
#    전체 위험이 준다.
#
# ⚠️⚠️ 그런데 이것을 지금 본 계좌에 적용하면 **판정 시계가 리셋된다**
#      ('얼마를 사는가'는 세대 축 ②다). 사장님 지시: "무슨 수정을 해도 판정
#      시간은 리셋되면 안 된다." 그래서 여기서는 **재기만 한다** — 대안
#      비중을 계산해 나란히 적어 두고, 격차가 실제로 큰지 며칠 보고 나서
#      그림자 계좌로 태울지 정한다. 재지 않고 만드는 것이 더 나쁜 순서다.
#
# 계산: 의원들의 홀드아웃 일수익을 섞어 **샤프가 최대가 되는 비중**을
# 격자탐색(의석 3석 이하라 격자로 충분하고, 최적화 라이브러리 의존이 없다).
# 짧은 표본에서 최대 샤프는 흔들리므로 **균등으로 절반 당겨** 둔다.
DIVERSITY_SHRINK = 0.5     # 균등 쪽으로 이만큼 당긴다(짧은 표본 방어)
DIVERSITY_STEP = 0.05      # 격자 간격


def _simplex_grid(k: int, step: float):
    """합이 1인 비중 조합을 격자로 훑는다(k는 의석 수, 보통 ≤ 3)."""
    n = int(round(1.0 / step))

    def rec(left: int, slots: int):
        if slots == 1:
            yield (left,)
            return
        for i in range(left + 1):
            for rest in rec(left - i, slots - 1):
                yield (i,) + rest

    for combo in rec(n, k):
        yield tuple(c / n for c in combo)


def diversity_weights(rets: dict, kept: list) -> dict | None:
    """상관까지 본 목표 비중 — **기록용**이고 매매에 쓰지 않는다.

    rets: {의석 index: 일수익 시계열}, kept: 살아남은 의석 index 목록.
    못 재면 None(모름을 0으로 적지 않는다).
    """
    if len(kept) < 2:
        return None
    try:
        import pandas as pd

        mat = pd.concat([rets[i] for i in kept], axis=1).dropna()
        if len(mat) < 20:                 # 표본이 얇으면 최적화가 잡음이다
            return None
        arr = mat.to_numpy()
        best, best_sharpe = None, None
        for w in _simplex_grid(len(kept), DIVERSITY_STEP):
            r = arr @ w
            sd = float(r.std(ddof=1))
            if sd <= 0:
                continue
            sharpe = float(r.mean()) / sd
            if best_sharpe is None or sharpe > best_sharpe:
                best, best_sharpe = w, sharpe
        if best is None:
            return None
        eq = 1.0 / len(kept)
        out = {i: round((1 - DIVERSITY_SHRINK) * w + DIVERSITY_SHRINK * eq, 4)
               for i, w in zip(kept, best)}
        tot = sum(out.values()) or 1.0
        return {i: round(v / tot, 4) for i, v in out.items()}
    except Exception as exc:  # noqa: BLE001 — 계측 실패가 의회를 막지 않는다
        log.warning("다양성 비중 계측 실패(건너뜀): %s", exc)
        return None


def weight_gap(actual: list[dict]) -> float | None:
    """지금 비중과 '상관까지 본 비중'의 거리(0~1). 없으면 None.

    0이면 두 규칙이 같은 답을 낸다는 뜻이고, 1에 가까울수록 지금 배분이
    상관을 무시하고 있다는 뜻이다. 총변동거리(L1의 절반)를 쓴다.
    """
    pairs = [(float(m.get("weight", 0.0)), m.get("alt_weight"))
             for m in (actual or [])]
    if len(pairs) < 2 or any(a is None for _w, a in pairs):
        return None
    return round(sum(abs(w - float(a)) for w, a in pairs) / 2.0, 4)


def update_parliament(entry: dict, df, *, build, cost_model=None,
                      confirm_window: int = 120,
                      promoted_spec: dict | None = None,
                      applicants: list[dict] | None = None,
                      next_open_fill: bool = False,
                      rebalance_band: float = 0.0) -> list[dict]:
    """의회 명단·비중을 갱신해 반환한다 (순수 계산 — 저장은 호출자 몫).

    1) 오디션을 통과한 promoted_spec이 있으면 신입 의석(ENTRY_WEIGHT) 부여
    2) 각 의원을 같은 데이터로 백테스트, '마지막 confirm_window봉' 수익으로 채점
    3) 수익률 상관 > CORR_CAP인 쌍은 점수 낮은 쪽 탈락(다양성 강제)
    4) softmax(점수) 목표 비중으로 EMA 한 걸음만 이동 — 급변 방지
    5) MIN_WEIGHT 미만 의석 몰수, 상위 K석만 유지, 비중 정규화
    실패(백테스트 불가 등) 시 기존 명단을 그대로 돌려준다 — 의회가 매매를
    막으면 안 된다.
    """
    from quant.backtest import Backtester

    members = members_of(entry)
    if promoted_spec is not None and not any(
            _same(_spec_of(m), promoted_spec) for m in members):
        scale = 1.0 - ENTRY_WEIGHT
        for m in members:
            m["weight"] = float(m.get("weight", 0.0)) * scale
        members.append({**promoted_spec, "weight": ENTRY_WEIGHT})

    def _run(spec: dict):
        """그 전략을 결승 구간에서 돌려 (수익률, 총수익, 관망여부)를 낸다.

        의원·지원자를 **같은 자로** 잰다 — 다른 자로 재면 그 차이가 곧
        의석 배분의 근거가 된다(오디션-현실 격차와 같은 계열).
        """
        res = Backtester(build(spec), cost_model=cost_model,
                         next_open_fill=next_open_fill,
                         rebalance_band=rebalance_band).run(df)
        r = res.returns.iloc[-confirm_window:]
        return (r, float((1 + r).prod() - 1),
                bool((res.positions.iloc[-confirm_window:].abs() < 1e-12).all()))

    try:
        rets, scores, idle = {}, {}, {}
        for i, m in enumerate(members):
            # 의석 채점도 오디션과 같은 체결 규칙으로 — 여기만 종가 체결·
            # 밴드 0으로 매기면 '싸게 평가된 고회전 의원'이 의석을 더 가져간다
            r, sc, idl = _run(_spec_of(m))
            rets[i] = r
            scores[i] = sc
            # 채점 구간에서 **한 번도 포지션을 갖지 않은** 의원 — 전략이
            # 아니라 현금이다(2026-08-14 발견). 이런 의원에게 의석을 주면
            # 그 비중만큼 책이 조용히 현금으로 가고, 장부에는 "의회가 그렇게
            # 배분했다"고 적힌다. 오디션 링에서 뺀 '무효 후보'와 같은 부류다.
            idle[i] = idl

        # ── 다양성 의석 — 두 번째 문(감사 276) ─────────────────────
        #    "더 낫나"가 아니라 "못하지 않으면서 다른가"를 묻는다.
        opened = 0
        for app in (applicants or []):
            if opened >= DIVERSIFIER_PER_NIGHT:
                break
            spec = {"strategy": app.get("strategy"),
                    "params": dict(app.get("params") or {})}
            if not spec["strategy"]:
                continue
            if any(_same(_spec_of(m), spec) for m in members):
                continue                      # 이미 앉아 있다
            # ① 선발전에서 유의하게 못하지 않았는가 (오디션이 이미 잰 값)
            st = app.get("select_t")
            if st is not None and float(st) <= -DIVERSIFIER_T_FLOOR:
                continue
            try:
                r, sc, idl = _run(spec)
            except Exception as exc:  # noqa: BLE001 — 지원자 하나가 의회를 막지 않는다
                log.warning("다양성 지원자 평가 실패(건너뜀): %s", exc)
                continue
            if idl:
                continue                      # 전략이 아니라 현금이다
            # ② 결승 구간에서도 유의하게 못하지 않은가 — 리더와 짝지어 잰다
            lead = max(scores, key=lambda i: scores[i])
            if _paired_t(r, rets[lead]) <= -DIVERSIFIER_T_FLOOR:
                continue
            # ③ 앉아 있는 모두와 상관이 낮은가 (못 재면 '중복'으로 본다)
            far = True
            for j in list(rets):
                c = safe_corr(r, rets[j])
                if c != c or abs(c) >= DIVERSIFIER_CORR_MAX:
                    far = False
                    break
            if not far:
                continue
            # 통과 — 기존 의석을 눌러 자리를 만든다(승격보다 작은 몫)
            for m in members:
                m["weight"] = float(m.get("weight", 0.0)) * (1.0 - DIVERSIFIER_WEIGHT)
            k = len(members)
            members.append({**spec, "weight": DIVERSIFIER_WEIGHT})
            rets[k], scores[k], idle[k] = r, sc, False
            opened += 1
            log.info("다양성 의석 개설 — 챔피언보다 낫지는 않지만 상관이 낮다: %s",
                     spec)

        # 다양성 강제 — 높은 점수 순으로 훑으며, 이미 남은 의원과 상관이
        # 과도한 후보는 탈락시킨다(같은 베팅을 두 자리 주지 않는다)
        order = sorted(scores, key=lambda i: -scores[i])
        kept: list[int] = []
        for i in order:
            if idle[i]:
                # 아무 베팅도 안 한 의원은 채점도 다양성 판정도 불가능하다.
                # '상관을 못 쟀으니 통과'로 흘려보내면 현금이 의석을 갖는다.
                log.warning("의석 제외 — 채점 구간에서 한 번도 포지션이 없던 "
                            "의원(전략이 아니라 현금이다): %s",
                            _spec_of(members[i]))
                continue
            dup = False
            for j in kept:
                # ⚠️ 예전에는 여기서 직접 `.corr()`을 불렀다. pandas 3.0이
                #    상수 계열에 NaN 대신 ~0을 돌려주면서 아래 NaN 검사가
                #    통째로 죽었다(감사 276). 판정은 safe_corr 한 곳에 있다.
                c = safe_corr(rets[i], rets[j])
                # ⚠️ 상관을 못 재면 '무상관(0)'이 아니라 '중복(1)'으로 본다
                #    (감사 53). 0으로 치면 계산 실패가 곧 통과가 되어, 같은
                #    베팅에 두 자리를 주는 쪽으로 가드가 열린다 — 다양성
                #    강제 장치가 실패할 때 정확히 반대로 동작하는 셈이다.
                #
                #    ⚠️⚠️ 2026-08-14: 위 주석은 예외(except)만 막고 있었고
                #    **정작 흔한 경로를 놓치고 있었다.** pandas의 corr는
                #    한쪽이 상수면 예외를 던지지 않고 조용히 **NaN**을
                #    돌려준다. 그런데 판정이 `c == c and c > CORR_CAP`이라
                #    NaN은 `c == c`에서 False가 되어 **'중복 아님'으로
                #    통과**했다 — 주석이 막겠다고 적어 둔 바로 그 방향으로
                #    3년째 열려 있었던 셈이다. NaN도 중복으로 본다.
                if c != c or c > CORR_CAP:
                    dup = True
                    break
            if not dup:
                kept.append(i)
        kept = kept[:PARLIAMENT_K]
        if not kept:
            return members

        # softmax 목표 비중 → EMA 한 걸음
        mx = max(scores[i] for i in kept)
        expo = {i: math.exp(min(60.0, (scores[i] - mx) * SOFTMAX_TEMP))
                for i in kept}
        tot = sum(expo.values())
        out = []
        for i in kept:
            target = expo[i] / tot
            prev = float(members[i].get("weight", 0.0))
            w = (1 - EMA_STEP) * prev + EMA_STEP * target
            out.append({**_spec_of(members[i]), "weight": w})
        out = [m for m in out if m["weight"] >= MIN_WEIGHT] or out[:1]
        s = sum(m["weight"] for m in out)
        for m in out:
            m["weight"] = round(m["weight"] / s, 4)
        # 상관까지 본 비중을 **나란히 적어 둔다** — 매매에는 쓰지 않는다.
        # 위 `out`은 MIN_WEIGHT로 걸러진 뒤라 kept와 명단이 다를 수 있어,
        # 살아남은 의석만 골라 다시 맞춘다.
        alive = [i for i in kept
                 if any(_same(_spec_of(members[i]), _spec_of(m)) for m in out)]
        alt = diversity_weights(rets, alive)
        if alt:
            for m in out:
                for i in alive:
                    if _same(_spec_of(members[i]), _spec_of(m)):
                        m["alt_weight"] = alt[i]
                        break
        out.sort(key=lambda m: -m["weight"])
        return out
    except Exception as exc:  # noqa: BLE001 — 의회 갱신 실패가 본류를 막으면 안 됨
        log.warning("의회 갱신 실패(기존 명단 유지): %s", exc)
        return members


def parliament_summary(entry: dict) -> str | None:
    """사람용 요약 '전략A 60% + 전략B 40%'. 단독 의회면 None."""
    ms = entry.get("parliament") or []
    if len(ms) < 2:
        return None
    return " + ".join(f"{m['strategy']} {m['weight']:.0%}" for m in ms)


def seat_census(champions: dict | None) -> dict:
    """전 계좌 의석 현황 — "3석 분산 운용"이 사실인지 약속인지 답하는 한 자리.

    ⚠️ 왜 이게 필요한가(2026-08-13 감사 225): 사이트는 "통과자 최대 3개가
    의석을 나눠 갖는다 … 단일 전략 붕괴가 계좌 붕괴가 되는 구조를 없앤
    것"이라고 **현재형으로** 적고 있었다. 그런데 실제 장부는 20계좌 전부가
    **1석**이다 — 한 번도 2석이 된 적이 없다.

    구조가 잠들어 있는 이유는 명확하다: 의석은 오직 2단계 오디션을 통과한
    승격자만 얻는데, 승격은 139회 중 1회 일어났고 그 1회조차 챔피언의
    파라미터 변형이라 상관 게이트(CORR_CAP)가 즉시 한 석으로 합쳤다.
    설계가 틀린 것은 아니다 — 틀린 것은 **잠든 구조를 작동 중인 것처럼
    말한 문장**이다.

    그리고 하필 `parliament_summary`는 2석 이상일 때만 문장을 내놓는다.
    즉 이 장치는 **작동할 때만 자기를 알리고, 잠들어 있을 때는 침묵한다** —
    사장님이 보시기엔 아무 말이 없으니 잘 돌아가는 것으로 읽힌다. 그래서
    잠든 상태 자체를 숫자로 내보내고, 사이트 문장이 그 숫자를 읽게 한다.
    """
    counts: dict[str, int] = {}
    for key, entry in (champions or {}).items():
        if not isinstance(entry, dict):
            continue
        try:
            counts[key] = len(members_of(entry))
        except (KeyError, TypeError):
            continue          # 구버전/손상 항목 — 셀 수 없으면 세지 않는다
    multi = sum(1 for v in counts.values() if v >= 2)

    # ⚠️ 의석 수는 절반의 답이다(2026-08-19). 39석·11종인데 **자금의 72.9%가
    #    한 스펙**에 있었다 — 자리를 여러 개 준 것과 돈을 나눠 준 것은 다른
    #    이야기다. 그래서 (a) 스펙별 자금 점유와 (b) '상관까지 본 비중'과의
    #    거리를 함께 낸다. (b)는 재기만 하는 값이다 — 적용하면 판정 시계가
    #    리셋되므로, 격차가 큰지 먼저 보고 그림자로 태울지 정한다.
    import json as _json

    share: dict[str, float] = {}
    gaps: list[float] = []
    n_acct = 0
    for entry in (champions or {}).values():
        if not isinstance(entry, dict) or "strategy" not in entry:
            continue
        try:
            ms = members_of(entry)
        except (KeyError, TypeError):
            continue
        n_acct += 1
        tot = sum(float(m.get("weight", 0.0)) for m in ms) or 1.0
        for m in ms:
            k = m["strategy"] + ":" + _json.dumps(m.get("params"),
                                                 sort_keys=True)
            share[k] = share.get(k, 0.0) + float(m.get("weight", 0.0)) / tot
        g = weight_gap(ms)
        if g is not None:
            gaps.append(g)
    top = max((v / n_acct for v in share.values()), default=None) if n_acct \
        else None

    return {
        "accounts": len(counts),
        "single_seat": len(counts) - multi,
        "multi_seat": multi,
        "max_seats": max(counts.values(), default=0),
        "cap": PARLIAMENT_K,
        # 지금 실제로 분산 운용 중인가 — 문장이 아니라 이 불리언이 답한다
        "diversified": multi > 0,
        # 서로 다른 전략 스펙이 몇 종이고, 그중 **가장 큰 하나가 자금의
        # 몇 %를 쥐고 있는가**. 의석이 많아도 이 값이 크면 베팅은 하나다.
        "distinct_specs": len(share),
        "top_spec_share": (round(top, 4) if top is not None else None),
        # 지금 비중과 '상관까지 본 비중'의 평균 거리(0~1). None이면 아직
        # 못 잰 것이고, 0으로 적지 않는다.
        "weight_gap": (round(sum(gaps) / len(gaps), 4) if gaps else None),
        "weight_gap_measured": len(gaps),
    }


class ParliamentStrategy:
    """의회 혼합 전략 — 의원 신호의 비중 가중합.

    개별 의원이 실패하면 그 의원만 관망(0) 처리한다.
    """

    name = "parliament"

    def __init__(self, members: list[dict], build):
        self._members = [(build(_spec_of(m)), float(m["weight"]))
                         for m in members]
        self.allow_short = any(getattr(s, "allow_short", False)
                               for s, _ in self._members)

    def generate_signals(self, df):
        import pandas as pd
        total = pd.Series(0.0, index=df.index)
        wsum = sum(w for _, w in self._members) or 1.0
        for strat, w in self._members:
            try:
                sig = strat.generate_signals(df).reindex(df.index).fillna(0.0)
            except Exception as exc:  # noqa: BLE001 — 한 의원의 실패는 그 의원만 관망
                log.warning("의원 신호 실패(관망 처리): %s", exc)
                continue
            total = total + sig * (w / wsum)
        # 신뢰도 곡선용 — 리더(최대 비중 의원)의 예측확률을 노출
        leader = max(self._members, key=lambda t: t[1])[0] if self._members else None
        self.last_proba_ = getattr(leader, "last_proba_", None)
        return total.clip(-1.0, 1.0)
