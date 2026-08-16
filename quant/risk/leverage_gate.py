"""레버리지 관문 — **세 개를 다 통과해야 열린다. 기본은 잠김.**

⚠️ 이 파일이 이번 작업의 자물쇠다 (2026-08-14, 사장님 지시로 선물 준비).

    ① 청산이 감시보다 먼저 오지 않는가       (risk/liquidation.py)
    ② 감시가 **실제로** 그만큼 자주 돌았는가  (live/guard.py 심장박동)
    ③ 도중에 죽지 않는가                     (robustness/ruin.py)

    셋 중 하나라도 답이 없거나 아니오면 **레버리지는 1배**다. 즉 지금과 같다.

⚠️ **"열려 있는데 안 쓴다"와 "잠겨 있다"는 다르다.** 이 저장소가 이번 주
   내내 고친 결함이 전부 전자였다 — 문서는 막는다고 적혀 있는데 코드는 안
   막았다. 그래서 여기서는 기본값이 **잠김**이고, 여는 것은 세 관문의
   통과라는 사실뿐이다. 사람이 설정으로 뚫을 수 있는 구멍을 두지 않는다.

⚠️ 그리고 **모르면 잠긴다.** 변동성을 모르거나, 심장박동이 모자라거나,
   수익률 표본이 모자라면 전부 '안전'이 아니라 '모름'이고, 모름은 잠김이다.
   미측정을 통과로 읽는 것이 검증 게이트에서 이미 고친 실패다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# 관문을 다 통과해도 넘지 않는 절대 상한. 계산이 아무리 관대해도 여기서 멈춘다.
# ⚠️ 계산을 믿되 무한히 믿지는 않는다 — 모든 가정이 동시에 낙관적일 수 있다.
HARD_CAP = 3.0


@dataclass
class LeverageDecision:
    """허용 배수와 **왜 그 값인지**. 1.0이면 레버리지 금지(지금 상태)."""

    allowed: float
    binding: str                       # 무엇이 한도를 정했는가
    checks: list[dict] = field(default_factory=list)

    @property
    def locked(self) -> bool:
        return self.allowed <= 1.0

    def describe(self) -> str:
        head = ("레버리지 **잠김**(1배 — 지금과 같음)" if self.locked
                else f"레버리지 최대 **{self.allowed:g}배**")
        lines = [f"{head} · 한도를 정한 것: {self.binding}"]
        for c in self.checks:
            mark = "✅" if c["ok"] else "❌"
            lines.append(f"  {mark} {c['name']}: {c['detail']}")
        return "\n".join(lines)


def decide(*, returns=None, daily_vol: float = 0.0, market: str = "",
           state_dir: str = "state", now_iso: str | None = None,
           requested: float = 1.0,
           guard_minutes: float | None = None) -> LeverageDecision:
    """세 관문을 걸어 **실제로 허용할 배수**를 정한다.

    requested      : 쓰고 싶은 배수. 관문을 넘으면 그대로, 못 넘으면 깎인다.
    guard_minutes  : 감시 주기를 직접 줄 때(시험용). 기본은 **실측**을 쓴다.

    ⚠️ 반환값은 '권고'가 아니라 **한도**다. 부르는 쪽이 이 값을 무시할 수
       있으면 관문이 아니다 — 호출부는 반드시 min(원하는 값, allowed)을 쓴다.
    """
    from quant.live.guard import observed_gap_minutes
    from quant.risk.liquidation import max_safe_leverage
    from quant.robustness.ruin import max_leverage_by_ruin

    checks: list[dict] = []
    limits: list[tuple[float, str]] = [(HARD_CAP, "절대 상한")]

    # ── ② 감시가 실제로 얼마나 자주 돌았는가 (먼저 본다 — ①의 입력이다)
    observed = (float(guard_minutes) if guard_minutes is not None
                else observed_gap_minutes(state_dir, now_iso=now_iso))
    if observed is None:
        checks.append({"name": "장중 감시 실적", "ok": False,
                       "detail": "심장박동 기록이 모자라 **실제 감시 간격을 "
                                 "모릅니다.** 설정값이 아니라 실측이 필요합니다 — "
                                 "감시 루프를 돌려 기록을 쌓아 주세요."})
        return LeverageDecision(1.0, "장중 감시 실적 없음", checks)
    checks.append({"name": "장중 감시 실적", "ok": True,
                   "detail": f"관측된 **최악** 간격 {observed:,.0f}분 "
                             f"(설정이 아니라 실제로 벌어진 간격입니다)"})

    # ── ① 청산이 감시보다 먼저 오는가
    if daily_vol <= 0:
        checks.append({"name": "청산 여유", "ok": False,
                       "detail": "변동성을 몰라 청산까지의 여유를 잴 수 없습니다."})
        return LeverageDecision(1.0, "변동성 미측정", checks)
    liq_cap = max_safe_leverage(daily_vol=daily_vol, guard_minutes=observed,
                                market=market)
    limits.append((liq_cap, "청산 여유"))
    checks.append({"name": "청산 여유", "ok": liq_cap > 1.0,
                   "detail": f"이 감시 간격·변동성에서 최대 {liq_cap:g}배"})

    # ── ③ 도중에 죽지 않는가
    if returns is None or len(list(returns)) < 30:
        checks.append({"name": "파산확률", "ok": False,
                       "detail": "수익률 표본이 모자라 파산확률을 못 잽니다 — "
                                 "모르는 것을 '안전'으로 읽지 않습니다."})
        return LeverageDecision(1.0, "파산확률 미측정", checks)
    ruin_cap = max_leverage_by_ruin(returns)
    limits.append((ruin_cap, "파산확률"))
    checks.append({"name": "파산확률", "ok": ruin_cap > 1.0,
                   "detail": f"파산확률 기준 최대 {ruin_cap:g}배"})

    cap, binding = min(limits, key=lambda x: x[0])
    want = max(1.0, float(requested))
    # 요청이 한도보다 낮으면 요청대로 — 관문은 **상한**이지 목표가 아니다.
    allowed, binding = (want, "요청값") if want < cap else (cap, binding)
    return LeverageDecision(round(max(1.0, allowed), 2), binding, checks)
