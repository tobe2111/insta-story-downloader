"""강제청산 — **감시 루프가 보기 전에 거래소가 가져가면 안전장치가 아니다.**

⚠️ 왜 이 파일이 생겼나 (2026-08-14, 사장님이 선물 투자 가능성을 물어서).

    이 시스템의 안전장치(킬스위치 -15%/-25%, 서킷브레이커)는 전부 **자산이
    0 아래로 안 간다**는 현물의 전제 위에 서 있다. 최악이어도 다음 배치가
    처리하면 된다.

    레버리지 선물은 그 전제가 깨진다. 10배면 자산이 9.5% 반대로 가는 순간
    계좌가 **없어진다.** 킬스위치가 깨어나기 전에 끝난다. 그러면 "낙폭
    -25%면 전량 관망합니다"는 선언만 남고 실제로는 아무것도 안 막는다 —
    이 저장소가 가장 경계하는 바로 그 상태다.

⚠️ **처음에 이 관문을 '가격'으로 짰다가 틀린 것을 실측으로 잡았다.**
   총노출과 레버리지를 따로 받아 비교했는데, 계좌 전액을 증거금으로 쓰면
   **그 둘은 같은 값**이다. 그렇게 짜면 노출이 낮을수록 레버리지를 더
   막는 이상한 답이 나온다(실측: 노출 50%에서 2배가 거부되고 100%에서는
   통과). 진짜 제약은 가격이 아니라 **시간**이다 —

       거래소는 실시간으로 청산한다. 우리 킬스위치는 감시 루프가 돌 때만
       작동한다. 그 사이에 가격이 청산선을 넘으면 우리는 손도 못 댄다.

   그래서 관문은 이렇게 묻는다: **감시 주기 안에 일어날 수 있는 최악의
   역방향 움직임보다 청산선이 멀리 있는가?**

   이 질문은 레버리지·변동성·감시 주기 셋을 한자리에 묶는다. 셋 중 하나만
   바뀌어도 답이 바뀌고, 그게 맞다.

⚠️ **레버리지가 없으면(1배) 이 관문은 언제나 통과한다.** 현물 롱은 가격이
   0이 돼야 청산이기 때문이다. 이 파일을 넣는 것만으로 오늘 동작은 한 글자도
   바뀌지 않는다 — 의도한 것이다. 관문이 먼저 서 있고, 문은 나중에 열린다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# 거래소 유지증거금률(maintenance margin rate)의 보수적 기본값.
# 실제 값은 거래소·심볼·포지션 크기(티어)마다 다르다 — **모르면 나쁜 쪽으로**
# 잡는다. 티어가 올라가면 이 값이 커지고, 커질수록 청산가가 진입가에 가까워진다.
DEFAULT_MMR = 0.005

# 감시 주기 안의 '최악'을 가정으로 잡을 때 쓰는 표준편차 배수.
# ⚠️ 이건 **가정**이다. 실측(worst_move)을 넘겨주면 그쪽을 쓴다 — 이 저장소는
#    가정보다 실측을 쓴다. 4σ는 정규분포에서 1/15,000이지만 코인·주식 수익률은
#    꼬리가 두꺼워 실제로는 훨씬 자주 온다. 그래서 아래 SAFETY_FACTOR가 또 있다.
SIGMA_MULTIPLE = 4.0

# 청산선이 '최악의 움직임'보다 몇 배 멀어야 하는가.
#
# 왜 1배로는 부족한가: ① 위 4σ는 가정이고 실제 꼬리는 더 두껍다 ② 킬스위치는
# 순간이동하지 않는다 — 감지하고, 주문을 내고, 체결돼야 한다 ③ 청산 주문에도
# 슬리피지가 있다. 1배는 "이론상 아슬아슬하게 산다"는 뜻이고 실전에서 그건
# 못 산다는 뜻이다.
SAFETY_FACTOR = 2.0

# 하루를 분으로 — 감시 주기를 봉 변동성과 같은 자로 재기 위해.
MINUTES_PER_DAY = 24 * 60

# ── 점프 바닥 — **아무리 자주 봐도 못 피하는 움직임** ──────────────────
#
# ⚠️ 이걸 안 넣었더니 실측에서 이런 답이 나왔다: 1분마다 감시하면 20배까지
#    안전하다. **틀렸다.** √시간 축소는 가격이 연속으로 움직인다고 가정하는데,
#    실제로는 두 틱 사이에 통째로 뛴다:
#      · 급락(플래시 크래시) — 코인에서 몇 분 만에 20%+ 가 여러 번 있었다
#      · 갭 — 주식은 장 마감과 개장 사이에 감시 자체가 불가능하다
#      · 거래소 장애·API 차단 — 우리 눈이 감겨 있는 동안 가격은 움직인다
#
#    그래서 감시 주기와 **무관한 바닥**을 둔다. 아무리 자주 봐도 이만큼은
#    각오해야 한다는 뜻이고, 이 바닥이 실질적인 레버리지 상한을 정한다.
#    (감시를 자주 돌리는 것이 무의미하다는 뜻은 아니다 — 바닥 위쪽의 위험은
#     실제로 줄어든다. 다만 바닥 아래로는 못 내려간다.)
#
# 값의 근거: 시장별 관측된 급락 규모. 모르는 시장은 가장 나쁜 값을 쓴다.
JUMP_FLOOR = {
    "crypto": 0.20,      # 24시간·서킷브레이커 없음 — 실제로 20%+ 급락 다수
    "us_stock": 0.10,    # 서킷브레이커가 있지만 개장 갭은 그대로 맞는다
    "kr_stock": 0.10,    # 상하한 ±30%, 개장 갭·거래정지
}
DEFAULT_JUMP_FLOOR = 0.20   # 모르면 가장 나쁜 쪽


@dataclass(frozen=True)
class Headroom:
    """청산까지의 여유. `ok`가 False면 그 포지션은 **잡으면 안 된다.**"""

    ok: bool
    move_to_liquidation: float    # 청산까지 필요한 역방향 변동(비율, 양수)
    worst_move: float             # 감시 주기 안에 일어날 수 있는 최악의 역방향 변동
    ratio: float                  # 앞의 것 ÷ 뒤의 것 — SAFETY_FACTOR 이상이어야 한다
    measured: bool                # worst_move가 실측인가(True) 가정인가(False)
    reason: str

    def describe(self) -> str:
        src = "실측" if self.measured else "가정"
        return (f"청산까지 {self.move_to_liquidation:.1%} · "
                f"감시 주기 최악 {self.worst_move:.1%}({src}) · "
                f"여유 {self.ratio:.1f}배 — {self.reason}")


def liquidation_price(entry: float, leverage: float, *, side: str = "long",
                      mmr: float = DEFAULT_MMR) -> float:
    """격리마진 기준 강제청산 가격.

    롱:  P = 진입가 × (1 − 1/L) ÷ (1 − mmr)
    숏:  P = 진입가 × (1 + 1/L) ÷ (1 + mmr)

    ⚠️ 수수료·펀딩비는 **넣지 않았다** — 넣으면 청산가가 진입가에 더 가까워지므로
       여기 값은 언제나 '실제보다 낙관적'이다. 숫자를 정확하게 만드는 대신
       **틀리는 방향을 알고 그만큼 물러선다**(SAFETY_FACTOR).
    """
    if entry <= 0:
        raise ValueError("진입가는 0보다 커야 합니다.")
    if leverage <= 0:
        raise ValueError("레버리지는 0보다 커야 합니다.")
    if not (0.0 <= mmr < 1.0):
        raise ValueError("유지증거금률은 0 이상 1 미만이어야 합니다.")
    if side == "long":
        return max(0.0, entry * (1.0 - 1.0 / leverage) / (1.0 - mmr))
    if side == "short":
        return entry * (1.0 + 1.0 / leverage) / (1.0 + mmr)
    raise ValueError(f"방향은 long 또는 short여야 합니다: {side!r}")


def move_to_liquidation(leverage: float, *, side: str = "long",
                        mmr: float = DEFAULT_MMR) -> float:
    """청산까지 필요한 **역방향 변동 비율**(양수). 진입가와 무관하다.

    1배(레버리지 없음) 롱은 1.0 — 가격이 0이 돼야 청산이라는 뜻이고,
    그게 지금 이 시스템의 상태다.
    """
    p = liquidation_price(100.0, leverage, side=side, mmr=mmr)
    return abs(p - 100.0) / 100.0


def interval_worst_move(daily_vol: float, guard_minutes: float, *,
                        sigma: float = SIGMA_MULTIPLE,
                        market: str = "") -> float:
    """감시 주기 안에 일어날 수 있는 최악의 역방향 변동 — **가정값**.

    일간 변동성을 √시간으로 축소한 뒤 sigma배. 다만 **점프 바닥 아래로는
    내려가지 않는다** — 두 틱 사이에 통째로 뛰는 움직임은 자주 본다고
    피할 수 있는 게 아니다(위 JUMP_FLOOR 주석 참고).

    실측(worst_move)이 있으면 그쪽을 쓴다 — 이건 실측이 없을 때의 대역이다.
    """
    floor = JUMP_FLOOR.get(str(market), DEFAULT_JUMP_FLOOR)
    if daily_vol <= 0 or guard_minutes <= 0:
        return 0.0
    scale = math.sqrt(min(1.0, guard_minutes / MINUTES_PER_DAY))
    return max(floor, float(daily_vol) * scale * float(sigma))


def check_headroom(leverage: float, *, daily_vol: float = 0.0,
                   guard_minutes: float = MINUTES_PER_DAY,
                   worst_move: float | None = None, market: str = "",
                   side: str = "long", mmr: float = DEFAULT_MMR,
                   safety: float = SAFETY_FACTOR) -> Headroom:
    """**이 관문이 이 파일의 전부다.** 감시가 보기 전에 청산되면 거부한다.

    leverage      : 포지션 레버리지 배수. 1.0이면 레버리지 없음.
    daily_vol     : 일간 변동성(수익률 표준편차, 예 0.03 = 3%).
    guard_minutes : 감시 루프가 도는 간격(분). 하루 1회면 1440.
    worst_move    : **실측한** 최악의 구간 변동(있으면 가정 대신 이걸 쓴다).

    통과 조건: (청산까지 변동) ≥ (감시 주기 최악 변동) × safety
    """
    x_liq = move_to_liquidation(leverage, side=side, mmr=mmr)
    measured = worst_move is not None
    x_worst = (float(worst_move) if measured
               else interval_worst_move(daily_vol, guard_minutes,
                                        market=market))

    if x_worst <= 0:
        # 변동성을 모르면 **통과시키지 않는다.** 모르는 것을 '위험 없음'으로
        # 읽는 것이 이 저장소가 계속 잡아온 실패다(미측정 = 절반 규칙과 같은
        # 정신). 레버리지가 없을 때만 무해하므로 그때만 통과.
        if leverage <= 1.0:
            return Headroom(True, x_liq, 0.0, float("inf"), measured,
                            "레버리지가 없어 강제청산될 수 없습니다")
        return Headroom(
            False, x_liq, 0.0, 0.0, measured,
            "변동성을 모르는 채로 레버리지를 쓸 수 없습니다 — 얼마나 빨리 "
            "움직이는지 모르면 감시 주기가 충분한지도 알 수 없습니다.")

    ratio = x_liq / x_worst
    if ratio >= safety:
        return Headroom(True, x_liq, x_worst, ratio, measured,
                        f"감시 주기 안에 청산될 여지가 없습니다(요구 {safety:.0f}배)")
    return Headroom(
        False, x_liq, x_worst, ratio, measured,
        f"**감시가 보기 전에 청산될 수 있습니다.** 자산이 {x_liq:.1%} 반대로 "
        f"움직이면 청산인데, 감시 주기({guard_minutes:.0f}분) 안에 "
        f"{x_worst:.1%}까지 움직일 수 있습니다(요구 {safety:.0f}배 여유, 지금 "
        f"{ratio:.1f}배). 이 조합에서는 킬스위치가 선언만 남고 실제로는 "
        f"아무것도 막지 못합니다 — 감시를 더 자주 돌리거나 배수를 낮추세요.")


def max_safe_leverage(*, daily_vol: float = 0.0,
                      guard_minutes: float = MINUTES_PER_DAY,
                      worst_move: float | None = None, market: str = "",
                      side: str = "long", mmr: float = DEFAULT_MMR,
                      safety: float = SAFETY_FACTOR,
                      cap: float = 20.0) -> float:
    """이 조건에서 관문을 통과하는 **가장 큰 레버리지**. 없으면 1.0(금지).

    설정 화면·문서가 "몇 배까지 됩니까"에 답할 때 쓰는 값이다. 사람이 어림
    잡아 적어 두면 그 숫자는 반드시 코드와 갈라진다.
    """
    kw = dict(daily_vol=daily_vol, guard_minutes=guard_minutes,
              worst_move=worst_move, market=market, side=side, mmr=mmr,
              safety=safety)
    if not check_headroom(1.0, **kw).ok:
        return 1.0
    lo, hi = 1.0, float(cap)
    if check_headroom(hi, **kw).ok:
        return round(hi, 2)
    for _ in range(60):                   # 이분법 — 배수에 단조라 수렴 보장
        mid = (lo + hi) / 2
        if check_headroom(mid, **kw).ok:
            lo = mid
        else:
            hi = mid
    return round(lo, 2)
