"""안전장치가 스스로 꺼지지 않게 — 기준값·한도의 공통 판정 (감사 198).

이 저장소에는 매매를 강제로 멈추는 장치가 둘 있다.

    DailyLossKillSwitch  (killswitch.py)      하루 -x% 도달 → 그날 하루 중단
    CircuitBreaker       (circuit_breaker.py) 고점 대비 -x% 도달 → 수동 reset까지 중단

둘 다 **"기준선을 기억해 두고 지금 자산과 비교한다"**는 같은 모양이고,
그래서 **같은 두 가지 방식으로 조용히 꺼진다.** 실측(2026-08-13):

  ① 자산값이 한 번 NaN으로 들어와 기준선이 되면 그 뒤 모든 비교가 거짓이 된다.
     파이썬에서 NaN과의 모든 비교는 False이기 때문이다.

        킬스위치   : 그날 첫 관측이 NaN → -50%도, **-99%도 발동 안 함**
        서킷브레이커: 첫 관측이 NaN → peak=nan. `max(nan, x)`는 nan을 그대로
                     두므로(x > nan이 False) **세션이 끝날 때까지 회복 못 함**

     경고 한 줄도 없다. 로그만 보면 "오늘은 발동할 일이 없었다"와 구분되지 않는다.

  ② 반대로 inf가 들어오면 즉시 **오발동**한다. peak=inf가 되면 다음 관측이
     무엇이든 `x/inf - 1 = -100%` 낙폭이라 전 종목이 청산된다.

  ③ 한도를 분수 대신 퍼센트로 적으면(0.03 → 3, 0.20 → 20) 두 장치 모두
     **아무 말 없이 꺼진다.** `--daily-max-loss 3`은 "-300% 도달 시 중단"이고
     그런 일은 없다. 음수로 적으면 반대로 항상 발동한다.

세 경우 모두 **꺼진 줄 모르는 것**이 진짜 피해다. 안전장치는 없는 것보다
'있다고 믿는데 없는 것'이 나쁘다 — 그 믿음 위에서 더 크게 베팅하게 된다.

판정을 여기 한 곳에 모은다(감사 192 ㉞ '같은 판정을 두 곳에서 쓰면 언젠가
갈라진다'). 감사 182에서 브로커 둘만 고쳤다가 형제 넷을 빠뜨린 적이 있다.

표준 라이브러리만 쓴다 — 두 장치의 "어디서든 가볍게" 성질을 유지한다.
"""
from __future__ import annotations

import math

from quant.utils.logging import get_logger

log = get_logger("live.riskguard")


def usable_equity(value, where: str) -> float | None:
    """안전장치의 기준·비교에 쓸 수 있는 자산값인가. 아니면 None.

    None을 받은 호출자는 **기준선을 건드리지 말고 이번 판정만 보류**해야
    한다. 오염된 기준선은 다음 사이클이 멀쩡해도 되살아나지 않기 때문이다
    (킬스위치는 그날 하루, 서킷브레이커는 세션 전체).

    '모름'을 0이나 현재값으로 메우지 않는 이유는 브로커 쪽과 같다
    (`broker/base.py` get_cash 감사 182) — **모름은 숫자가 아니다.**
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = float("nan")
    if not math.isfinite(v):
        log.error(
            "%s: 자산값이 숫자가 아닙니다(%r) — 이번 사이클 판정을 보류하고 "
            "기준선은 그대로 둡니다. 이 값을 기준선으로 삼으면 안전장치가 "
            "조용히 꺼집니다", where, value)
        return None
    return v


def check_loss_limit(value, name: str) -> float | None:
    """손실 한도값 검증. None은 '이 장치 미사용'이라 그대로 통과.

    한도는 **분수**다 — 0.03이 3%다. (0, 1] 밖의 값은 오타로 본다:

        3    → -300% 도달 시 발동 = 영원히 안 함  (장치가 꺼진 것과 같다)
        0    → 손실 0%에서 발동 = 항상 발동
        -0.2 → 낙폭은 항상 0 이하이므로 항상 발동

    추측해서 고치지 않는다(감사 195: 모르는 값은 기본값+경고). 다만 여기는
    **기본값으로 두는 것 자체가 위험**하다 — 사장님이 -3%를 걸었다고 믿는데
    실제로는 안전장치가 없는 상태가 되기 때문이다. 그래서 조용히 넘어가지
    않고 **시작할 때 세워 버린다.** 설정 오타는 실행 전에 드러나야 한다.
    """
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} 한도가 숫자가 아닙니다: {value!r}") from exc
    if not math.isfinite(v):
        raise ValueError(f"{name} 한도가 유한한 숫자가 아닙니다: {value!r}")
    if not 0.0 < v <= 1.0:
        raise ValueError(
            f"{name} 한도는 0보다 크고 1 이하인 분수여야 합니다 (받은 값: {v!r}). "
            f"3%는 3이 아니라 0.03입니다 — 3으로 적으면 '-300% 도달 시 발동'이라 "
            f"안전장치가 영영 발동하지 않습니다.")
    return v
