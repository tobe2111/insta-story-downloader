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

log = get_logger("parliament")

PARLIAMENT_K = 3          # 최대 의석 수
CORR_CAP = 0.97           # 이 이상 상관이면 중복 의원 — 다양성 강제
EMA_STEP = 0.25           # 하루에 목표 비중으로 이만큼만 이동(급변 방지)
MIN_WEIGHT = 0.05         # 이 미만이면 의석 상실
ENTRY_WEIGHT = 0.25       # 오디션 통과 신입의 초기 의석
SOFTMAX_TEMP = 12.0       # 홀드아웃 수익 차이 → 목표 비중 민감도


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


def update_parliament(entry: dict, df, *, build, cost_model=None,
                      confirm_window: int = 120,
                      promoted_spec: dict | None = None,
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

    try:
        rets, scores = {}, {}
        for i, m in enumerate(members):
            # 의석 채점도 오디션과 같은 체결 규칙으로 — 여기만 종가 체결·
            # 밴드 0으로 매기면 '싸게 평가된 고회전 의원'이 의석을 더 가져간다
            res = Backtester(build(_spec_of(m)), cost_model=cost_model,
                             next_open_fill=next_open_fill,
                             rebalance_band=rebalance_band).run(df)
            r = res.returns.iloc[-confirm_window:]
            rets[i] = r
            scores[i] = float((1 + r).prod() - 1)

        # 다양성 강제 — 높은 점수 순으로 훑으며, 이미 남은 의원과 상관이
        # 과도한 후보는 탈락시킨다(같은 베팅을 두 자리 주지 않는다)
        order = sorted(scores, key=lambda i: -scores[i])
        kept: list[int] = []
        for i in order:
            dup = False
            for j in kept:
                try:
                    c = float(rets[i].corr(rets[j]))
                except Exception:  # noqa: BLE001
                    # 상관을 못 재면 '무상관(0)'이 아니라 '중복(1)'으로 본다
                    # (감사 53). 0으로 치면 계산 실패가 곧 통과가 되어, 같은
                    # 베팅에 두 자리를 주는 쪽으로 가드가 열린다 — 다양성
                    # 강제 장치가 실패할 때 정확히 반대로 동작하는 셈이다.
                    c = 1.0
                if c == c and c > CORR_CAP:
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
    return {
        "accounts": len(counts),
        "single_seat": len(counts) - multi,
        "multi_seat": multi,
        "max_seats": max(counts.values(), default=0),
        "cap": PARLIAMENT_K,
        # 지금 실제로 분산 운용 중인가 — 문장이 아니라 이 불리언이 답한다
        "diversified": multi > 0,
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
