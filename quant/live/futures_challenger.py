"""선물 트랙 — **버려지던 절반(숏)을 쓰면 정말 나아지는가**를 재는 실험.

⚠️ 왜 이 파일이 생겼나 (2026-08-22, 사장님 지시).

    "선물 거래 페이지를 별도로 만들어 진행하자. 매수/매도 포지션 모두
     가지면 머신러닝에 도움되지 않나?"

**맞는 직관이었고, 실측이 그것을 뒷받침한다.**

지금까지 이 시스템은 모든 판단을 "산다 / 안 산다" 둘로만 냈다. 그런데
머신러닝 챔피언이 실제로 내놓는 것은 **상승 확률**이다. 확률이 0.55를
넘으면 산다. 그러면 확률이 0.20인 봉 — 모델이 "내릴 것"이라고 꽤 확신하는
봉 — 은 어떻게 되는가? **"안 산다"로 뭉개져 버려진다.** 0.50(모른다)과
0.20(내린다)이 같은 취급을 받는 것이다.

실측(2026-08-21 스냅샷, BTC/USDT 800봉, logreg 챔피언 설정):

    숏 금지:  롱 216봉 · 관망 584봉 · 숏   0봉
    숏 허용:  롱 216봉 · 관망 402봉 · 숏 182봉

**롱 판단은 한 개도 안 바뀌었다**(216 그대로). 관망 584봉 중 182봉
(전체의 22.8%)이 "모른다"가 아니라 "내린다"였을 뿐이다. 그 절반을 쓰는
것이 이 트랙이다.

⚠️ 그러나 **이것은 아직 가설이다.** 숏이 더 자주 발동한다는 것과 숏이
   돈을 번다는 것은 전혀 다른 말이다. 숏에는 롱에 없는 비용과 위험이
   붙는다(아래). 그래서 믿지 않고 **나란히 돌려서 잰다** — 같은 규칙,
   같은 비용, 같은 종목, 방향 허용 여부만 다르게.

■ 레버리지 — 확신에 비례해서 쓴다 (2026-08-22 사장님 지시)

    처음 만들 때는 1배로 잠가 두었다. 사장님 지시로 풀었다.

        "선물은 레버리지를 써도 되게끔 해. 그만큼 수익 실현에 확신이
         있으면 하는거잖아."

    맞는 말이다. 그리고 이 시스템에는 **확신을 나타내는 숫자가 이미
    있다** — 신호의 크기(|신호|)다. 머신러닝 챔피언의 신호는 상승 확률이
    문턱에서 얼마나 멀리 떨어졌는지를 [-1, 1]로 담고 있다. 확률이 0.56이면
    작은 수, 0.95면 큰 수다.

    그래서 배율을 **사람이 고르지 않는다.** 신호가 고른다:

        배율 = 1 + (최대배율 − 1) × |신호|

    확신이 없는 날은 1배 그대로고, 모델이 크게 확신하는 날에만 배율이
    올라간다. 이것이 "확신이 있으면 하는 것"의 실제 구현이다 — 매일 똑같이
    3배를 태우는 것은 확신이 아니라 습관이다.

    ⚠️ **그 확신이 실제로 맞는지는 아직 증명되지 않았다.** 모델의 확률이
       잘 보정돼(calibrated) 있는지 이 트랙은 아직 재지 않았다. 확신이
       클수록 크게 태우는데 그 확신이 틀리면 손실도 그만큼 커진다.
       배율은 이 실험의 **가설을 키우는 장치**이지 우위를 만드는 장치가
       아니다. 화면이 이 사실을 그대로 적는다.

■ 배율을 쓰면 **1배에는 없던 위험**이 생긴다 — 청산

    1배에서는 가격이 반토막 나도 계좌가 반토막 날 뿐이다. 3배에서는
    **30%쯤 역행하면 증거금이 바닥나고 거래소가 강제로 청산한다.** 그
    순간 손실이 확정되고, 그 뒤 가격이 되돌아와도 회복할 것이 없다.

    실측(자산 10,000 · 확신 최대로 3배를 태운 롱):

        10% 하락 → 자산 6,955 (증거금률 0.258)
        20% 하락 → 자산 3,955 (0.165)
        30% 하락 → 자산   955 (0.046) → **청산**

    코인이 하루에 10% 넘게 움직이는 날은 드물지 않다. 배율은 그 하루를
    계좌의 마지막 날로 만들 수 있다.

    이걸 모델에 안 넣으면 이 트랙은 **현실에 존재할 수 없는 성적**을
    낸다 — 실제로는 이미 털렸을 자리에서 계속 버티는 계좌가 된다.
    그래서 유지증거금을 재고, 밑돌면 전량 청산한다(`liquidation_check`).

■ 이 트랙이 지키는 나머지

    ① **자금조달 비용(funding)을 문다.** 무기한 선물은 8시간마다 포지션에
       비례해 돈을 주고받는다. 이걸 빼면 이 트랙만 유리한 자로 재게 된다 —
       이 저장소가 감사 296에서 고친 바로 그 병이다.
    ③ **숏에는 하드 스톱이 있다.** 롱은 최대 −100%지만 숏은 이론상 손실이
       무한하다(가격이 두 배가 되면 그 슬라이스가 통째로 날아간다).
       종목별 손실 한도를 걸고, 걸리면 그 자리에서 청산한다.
    ④ **숏을 못 하는 종목은 못 한다고 적는다.** 규칙 전략(이동평균 교차
       등)은 애초에 음수 신호를 내지 않는다 — 실측으로 확인했다. 그런
       종목에 억지로 숏을 만들지 않고, 화면이 "이 종목은 롱만"이라고
       말한다. 못 하는 것을 하는 척하면 그 페이지는 증거가 아니다.
    ⑤ **본 계좌·장중 트랙과 완전히 분리.** 자기 장부만 쓴다(state/futures/).
       통화는 USDT 하나. 비교는 금액이 아니라 퍼센트로만 한다.
"""
from __future__ import annotations

import json
import os

from quant.live.intraday_challenger import (
    LOOKBACK_BARS, MIN_BARS, MIN_TRADE_FRAC, MIN_TRADE_USDT, TIMEFRAME,
    UNIVERSE, _fetch_real, confirmed_bars, observed_gap_minutes,
)
from quant.utils.logging import get_logger

log = get_logger("live.futures")

START_CASH_USDT = 10_000.0
STATE_FILE = "futures.json"
KIND = "futures-experiment"
ROUNDS_KEEP = 2000
CURVE_KEEP = 500

# ⚠️ 배율 상한. 총 노출(|롱|+|숏|)이 자산의 이 배수를 못 넘는다.
#    **이 값을 올리는 것은 전략 변경이 아니라 위험 성격의 변경이다** —
#    사장님 승인 없이 올리지 않는다.
#
#    2026-08-22 사장님 지시로 1.0 → 3.0. 3을 고른 이유: 유지증거금
#    (MAINTENANCE_MARGIN_RATE) 기준으로 3배는 **약 29.7% 역행에서 청산**
#    된다(손으로 검산: 자산 10,000·노출 30,000에서 30% 하락 → 자산 955,
#    증거금률 0.0455 < 0.05 → 청산).
#    코인 하루 변동이 10%를 넘는 날이 드물지 않으므로 그보다 크게 잡으면
#    '실험'이 아니라 '동전 던지기'가 된다. 더 올리려면 청산 문턱이 어디로
#    내려가는지 함께 보고 정해야 한다.
MAX_GROSS_EXPOSURE = 3.0

# 유지증거금률 — 자산이 총 노출의 이 비율 밑으로 내려가면 **강제 청산**.
# 실제 거래소는 종목·구간마다 다르게 매기지만(0.4%~수%), 여기서는 하나로
# 잡고 화면에 가정이라고 적는다. 0으로 두는 것보다 이쪽이 정직하다 —
# 0은 "청산이 없다"는 주장이고, 그 주장은 선물에서 거짓이다.
MAINTENANCE_MARGIN_RATE = 0.05

# ⚠️ **규칙이 바뀐 날을 기록에 남긴다.** 이 트랙은 1배로 24회차를 돌고
#    나서 배율이 켜졌다. 그 사실을 안 적으면 자산 곡선의 한 지점부터
#    성격이 달라지는데 보는 사람은 이유를 모른다 — 그건 조용한 골대
#    이동이고, 이 저장소가 판정 시계에서 가장 엄격하게 막는 것이다
#    (감사 308. 과거 회차는 고치지 않는다 — 그때는 정말 1배였다).
LEVERAGE_ENABLED_ON = "2026-08-23"
RULE_CHANGES = [
    {"on": LEVERAGE_ENABLED_ON,
     "what": "배율을 켰습니다(최대 3배, 신호의 확신에 비례). 청산도 함께 "
             "모델에 넣었습니다.",
     "why": "사장님 지시 — \"그만큼 수익 실현에 확신이 있으면 하는거잖아\". "
            "이 날 이전 회차는 전부 1배이며, 그 기록은 고치지 않았습니다."},
]

# 무기한 선물 자금조달 — 8시간마다 정산된다. 실제 요율은 시장마다 매
# 시각 다르고 이 배치는 그 값을 받아 오지 않는다. 그래서 **받아 온 척하지
# 않고**, 공개된 장기 중앙값 수준의 가정치를 쓰고 화면에 '가정'이라고
# 적는다. 0으로 두는 것보다 이쪽이 정직하다 — 0은 "안 문다"는 주장이고,
# 그 주장은 사실이 아니다.
FUNDING_RATE_PER_8H = 0.0001        # 0.01% — 롱이 숏에 주는 방향을 양수로
FUNDING_HOURS = 8.0

# 숏 하드 스톱 — 그 종목의 진입가 대비 손실이 이만큼이면 그 자리에서 청산.
# 롱에는 파산이라는 자연 바닥이 있지만 숏에는 없다.
SHORT_STOP_PCT = 0.25

HONEST_LIMITS = [
    "가상 자금(USDT)입니다 — 실제 돈이 아니고, 실제 호가·유동성·증거금을 "
    "겪지 않습니다",
    "레버리지를 씁니다(최대 3배). 배율은 **신호의 확신에 비례**합니다 — "
    "확신이 없는 날은 1배입니다. 다만 그 확신이 실제로 맞는지는 이 트랙이 "
    "아직 증명하지 않았습니다",
    "배율을 쓰면 **청산**이 생깁니다. 자산이 총 노출의 5% 밑으로 내려가면 "
    "전량 강제 청산합니다 — 그 뒤 가격이 되돌아와도 회복할 것이 없습니다. "
    "유지증거금률 5%는 **가정치**이며 실제 거래소와 다릅니다",
    "자금조달 비용은 **가정치**입니다(8시간마다 0.01%) — 실제 요율을 받아 "
    "오지 않습니다. 실제와 다를 수 있습니다",
    "숏은 머신러닝 챔피언이 붙은 종목에서만 가능합니다 — 규칙 전략은 "
    "음수 신호를 내지 않습니다",
    "'숏이 더 자주 발동한다'와 '숏이 돈을 번다'는 다른 말입니다. 이 트랙은 "
    "후자를 아직 증명하지 않았습니다",
]


def _dir(state_dir: str) -> str:
    return os.path.join(state_dir, "futures")


def _path(state_dir: str) -> str:
    return os.path.join(_dir(state_dir), STATE_FILE)


def load_state(state_dir: str = "state") -> dict:
    p = _path(state_dir)
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                st = json.load(f)
        except (OSError, json.JSONDecodeError):
            st = {}
    else:
        st = {}
    st.setdefault("kind", KIND)
    st.setdefault("start_cash", START_CASH_USDT)
    st.setdefault("cash", START_CASH_USDT)
    st.setdefault("positions", {})
    st.setdefault("avg_cost", {})
    st.setdefault("cost_paid", 0.0)
    st.setdefault("funding_paid", 0.0)
    st.setdefault("rounds", [])
    st.setdefault("curve", [])
    st.setdefault("last_prices", {})
    st.setdefault("liquidations", 0)
    return st


def save_state(st: dict, state_dir: str = "state") -> None:
    os.makedirs(_dir(state_dir), exist_ok=True)
    with open(_path(state_dir), "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)


def mark_equity(st: dict, prices: dict) -> float:
    """자산 = 현금 + Σ(수량 × 현재가).

    ⚠️ 숏은 수량이 **음수**다. 그래서 이 한 줄이 롱과 숏 모두에 맞다 —
       숏을 위한 별도 계산을 만들지 않는다(두 계산은 언젠가 갈라진다).
       숏을 열면 현금이 늘고 수량이 음수가 되며, 가격이 오르면 그 음수가
       더 크게 빼간다.
    """
    eq = float(st.get("cash") or 0.0)
    for sym, q in (st.get("positions") or {}).items():
        px = prices.get(sym)
        if px:
            eq += float(q) * float(px)
    return eq


def gross_exposure(st: dict, prices: dict) -> float:
    """총 노출 = Σ|수량 × 현재가|. 롱과 숏이 **서로를 상쇄하지 않는다.**

    순노출(롱−숏)로 재면 "롱 100% + 숏 100%"가 0으로 보인다. 그건 위험이
    없다는 뜻이 아니라 **두 배로 걸려 있다**는 뜻이다.
    """
    out = 0.0
    for sym, q in (st.get("positions") or {}).items():
        px = prices.get(sym)
        if px:
            out += abs(float(q) * float(px))
    return out


def can_short(spec: dict | None) -> bool:
    """이 종목이 숏을 낼 수 있는가 — 머신러닝 챔피언일 때만.

    규칙 전략(이동평균 교차·MACD·볼린저 등)은 실측 결과 **음수 신호를
    한 번도 내지 않는다**(2026-08-21 스냅샷, 7종 전부 [0,1]). 그런 종목에
    숏을 만들려면 규칙을 새로 쓰는 것이고, 그건 '같은 규칙을 양방향으로
    돌린다'는 이 실험의 전제를 깨는 일이다.
    """
    return str((spec or {}).get("strategy") or "") == "ml"


def funding_cost(st: dict, prices: dict, hours: float,
                 rate_per_8h: float = FUNDING_RATE_PER_8H) -> float:
    """지난 구간의 자금조달 비용(USDT). 롱은 내고 숏은 받는다.

    ⚠️ 부호가 중요하다. 롱이 숏에 주는 것이 표준(양수 요율)이므로 롱
       포지션은 **비용**, 숏 포지션은 **수입**이다. 둘을 같은 부호로 하면
       숏 트랙의 성적이 조용히 부풀려진다.
    """
    if not (hours > 0):
        return 0.0
    periods = float(hours) / FUNDING_HOURS
    net = 0.0
    for sym, q in (st.get("positions") or {}).items():
        px = prices.get(sym)
        if px:
            net += float(q) * float(px)      # 롱은 +, 숏은 −
    return net * float(rate_per_8h) * periods


def leverage_for(signal, max_leverage: float = MAX_GROSS_EXPOSURE) -> float:
    """그 신호의 확신에 비례한 배율 (2026-08-22 사장님 지시).

        배율 = 1 + (최대배율 − 1) × |신호|

    ⚠️ **배율을 사람이 고르지 않는다.** 매일 똑같이 3배를 태우는 것은
       확신이 아니라 습관이다. 신호의 크기가 곧 모델의 확신이므로, 확신이
       없는 날은 1배 그대로고 크게 확신하는 날에만 올라간다.

    신호가 없거나 이상하면 **1배**로 떨어진다 — 모르는 날에 크게 태우는
    것이 이 트랙이 할 수 있는 가장 나쁜 일이다.
    """
    try:
        conviction = abs(float(signal))
    except (TypeError, ValueError):
        return 1.0
    if not (conviction == conviction) or conviction < 0:      # NaN 방어
        return 1.0
    conviction = min(1.0, conviction)
    top = max(1.0, float(max_leverage))
    return 1.0 + (top - 1.0) * conviction


def margin_ratio(st: dict, prices: dict) -> float | None:
    """자산 ÷ 총 노출. 못 재면 None(포지션이 없으면 잴 것이 없다)."""
    gross = gross_exposure(st, prices)
    if gross <= 0:
        return None
    return mark_equity(st, prices) / gross


def liquidation_check(st: dict, prices: dict,
                      rate: float = MAINTENANCE_MARGIN_RATE) -> dict | None:
    """증거금이 바닥났나 — 바닥났으면 **전량 강제 청산**한다.

    ⚠️ 배율을 쓰는 순간 생기는, 1배에는 없던 위험이다. 1배에서는 가격이
       반토막 나도 계좌가 반토막 날 뿐이지만 3배에서는 28%쯤 역행하면
       증거금이 바닥나고 거래소가 강제로 청산한다. 그 순간 손실이
       확정되고, **그 뒤 가격이 되돌아와도 회복할 것이 없다.**

       이걸 모델에 안 넣으면 이 트랙은 현실에 존재할 수 없는 성적을 낸다 —
       실제로는 이미 털렸을 자리에서 계속 버티는 계좌가 된다. 화면이 그런
       숫자를 자랑하면 그 페이지는 증거가 아니라 광고다.

    돌려주는 값: 청산이 일어났으면 그 내역, 아니면 None.
    """
    ratio = margin_ratio(st, prices)
    if ratio is None or ratio > float(rate):
        return None
    closed = sorted((st.get("positions") or {}).keys())
    equity_before = mark_equity(st, prices)
    # 남은 것을 전부 시장가로 덮는다 — 청산은 값을 고르지 않는다.
    st["cash"] = equity_before
    st["positions"] = {}
    st["avg_cost"] = {}
    st["liquidations"] = int(st.get("liquidations") or 0) + 1
    return {"at_ratio": round(ratio, 6), "closed": closed,
            "equity": round(equity_before, 4),
            "maintenance_rate": float(rate)}


def stopped_out(st: dict, prices: dict,
                stop_pct: float = SHORT_STOP_PCT) -> list[str]:
    """하드 스톱에 걸린 숏 종목들.

    롱에는 파산이라는 자연 바닥이 있다(가격이 0이면 −100%에서 멈춘다).
    숏에는 없다 — 가격이 두 배가 되면 그 슬라이스가 통째로 날아가고,
    세 배가 되면 슬라이스의 두 배를 잃는다. 그래서 숏에만 바닥을 만든다.
    """
    out = []
    avg = st.get("avg_cost") or {}
    for sym, q in (st.get("positions") or {}).items():
        if float(q) >= 0:                    # 롱은 여기서 다루지 않는다
            continue
        entry = float(avg.get(sym) or 0.0)
        px = prices.get(sym)
        if entry <= 0 or not px:
            continue
        if (float(px) - entry) / entry >= float(stop_pct):
            out.append(sym)
    return out


def execute_targets(st: dict, signals: dict, prices: dict, equity: float,
                    per_side: float, universe: list[str] | None = None,
                    max_gross: float = MAX_GROSS_EXPOSURE) -> list:
    """목표 방향·비중 → 체결. 롱과 숏을 **같은 한 곳**에서 처리한다.

    ⚠️ 장중 트랙의 `_execute_targets`를 빌려 오지 않고 여기 따로 둔 이유:
       그쪽은 매수에만 현금 한도를 걸고 매도에는 안 건다(롱 전용이라
       그것으로 충분했다). 숏은 **열면 현금이 늘어난다** — 그 코드에
       숏을 태우면 노출이 무한히 커진다. 같은 함수에 조건을 덧대면
       롱 트랙의 규칙까지 흔들리므로, 위험 성격이 다른 트랙은 체결기를
       나눈다. 대신 **비용 모델과 문턱은 그쪽에서 빌려 온다**(값이
       갈라지면 두 트랙 비교가 비용 비교로 오염된다).

    돌려주는 것: 체결 목록. 각 줄은 방향(롱/숏)과 실현 손익을 함께 적는다.
    """
    trades: list[dict] = []
    universe = universe if universe is not None else UNIVERSE
    if not universe:
        return trades
    slice_budget = equity / len(universe)
    avg = dict(st.get("avg_cost") or {})
    positions = dict(st.get("positions") or {})
    # 노출 한도는 **이 회차 전체**에 걸린다. 종목마다 따로 재면 다섯 종목이
    # 각각 한도를 채워 합이 다섯 배가 된다.
    #
    # ⚠️ 남은 한도를 미리 한 번 계산해 들고 다니지 **않는다**. 그러면 같은
    #    회차에서 앞 종목을 줄여 자리가 생겨도 그 사실이 반영되지 않아,
    #    뒤 종목이 이유 없이 막힌다(감사 304에서 실제로 그랬다). 매번
    #    지금의 장부에서 다시 센다 — 종목 수가 다섯이라 비용은 없다.
    cap = max(0.0, float(max_gross) * equity)

    def _used(exclude: str = "") -> float:
        out = 0.0
        for k, q in positions.items():
            if k == exclude:
                continue
            px_ = prices.get(k)
            if px_:
                out += abs(float(q) * float(px_))
        return out

    for sym in universe:
        sig = signals.get(sym)
        px = prices.get(sym)
        if sig is None or not px:
            continue
        cur_qty = float(positions.get(sym, 0.0))
        cur_notional = cur_qty * px
        # 배율은 **그 신호의 확신**이 정한다(2026-08-22 사장님 지시).
        # 확신이 없는 날은 1배 그대로다 — 모르는 날에 크게 태우는 것이
        # 이 트랙이 할 수 있는 가장 나쁜 일이다.
        target = slice_budget * float(sig) * leverage_for(sig, max_gross)
        delta = target - cur_notional
        if abs(delta) < max(MIN_TRADE_USDT, MIN_TRADE_FRAC * equity):
            continue
        # 노출이 **늘어나는 만큼**만 한도를 먹는다. 줄이는 거래(청산)는
        # 언제나 허용된다 — 위험을 줄이는 길을 막으면 스톱이 동작 못 한다.
        grow = abs(target) - abs(cur_notional)
        if grow > 0:
            # ⚠️ 남은 자리는 **음수가 될 수 있다** — 손실이 나서 이미 한도를
            #    넘긴 상태다. 그때 그 값을 그대로 쓰면 `-allowed`가 부호를
            #    뒤집어, 숏을 열려던 주문이 **롱을 여는 주문**이 된다.
            #    브레이크가 정반대 위험을 만드는 것이다(감사 304 — 더 센
            #    검사를 쓰다가 발견했다). 0에서 바닥을 치고 부호는 목표의
            #    것을 지킨다.
            allowed = max(0.0, cap - _used(exclude=sym))
            if abs(target) > allowed:
                target = allowed if target >= 0 else -allowed
                delta = target - cur_notional
                if abs(delta) < max(MIN_TRADE_USDT, MIN_TRADE_FRAC * equity):
                    continue
        fee = abs(delta) * per_side
        qty = delta / px
        prev_avg = float(avg.get(sym) or 0.0)
        new_qty = cur_qty + qty
        realized = None
        # 방향이 같은 쪽으로 커지면 평단을 섞고, 줄어들면 손익을 확정한다.
        # 부호가 뒤집히면(롱→숏) **뒤집힌 뒤의 값**이 새 진입가다.
        if cur_qty == 0 or (cur_qty > 0) == (qty > 0):
            if abs(new_qty) > 1e-12:
                avg[sym] = (abs(cur_qty) * prev_avg + abs(qty) * px) / abs(new_qty)
        else:
            closed = min(abs(qty), abs(cur_qty))
            if prev_avg > 0 and closed > 0:
                # 롱은 (판값−산값), 숏은 (판값−되산값) → 부호가 반대다.
                side_sign = 1.0 if cur_qty > 0 else -1.0
                realized = round(closed * (px - prev_avg) * side_sign - fee, 4)
            if abs(new_qty) <= 1e-12:
                avg.pop(sym, None)
            elif (new_qty > 0) != (cur_qty > 0):
                avg[sym] = px            # 방향이 뒤집혔다 — 새 진입가
        st["cash"] = float(st["cash"]) - delta - fee
        if abs(new_qty) * px < 1e-6:
            positions.pop(sym, None)
            avg.pop(sym, None)
        else:
            positions[sym] = new_qty
        st["cost_paid"] = float(st.get("cost_paid") or 0.0) + fee
        rec = {"symbol": sym, "side": "buy" if delta > 0 else "sell",
               "direction": ("숏" if new_qty < 0 else
                             ("롱" if new_qty > 0 else "청산")),
               "notional": round(delta, 2), "price": px,
               "cost": round(fee, 4), "signal": round(float(sig), 4)}
        if realized is not None:
            rec["realized_pnl"] = realized
            rec["avg_cost"] = round(prev_avg, 6)
        trades.append(rec)
    st["positions"] = positions
    st["avg_cost"] = avg
    return trades


def apply_funding(st: dict, prices: dict, hours: float,
                  rate_per_8h: float = FUNDING_RATE_PER_8H) -> float:
    """자금조달을 현금에 반영하고 누적에 더한다. 돌려주는 값은 이번 몫."""
    paid = funding_cost(st, prices, hours, rate_per_8h)
    st["cash"] = float(st["cash"]) - paid
    st["funding_paid"] = float(st.get("funding_paid") or 0.0) + paid
    return paid


def net_return_pct(st: dict) -> float | None:
    """비용·자금조달을 **전부 문 뒤**의 수익률(%). 못 재면 None."""
    base = float(st.get("start_cash") or 0.0)
    if not (base > 0):
        return None
    curve = st.get("curve") or []
    if not curve:
        return None
    last = curve[-1]
    eq = float((last or {}).get("equity") if isinstance(last, dict) else last)
    return round((eq / base - 1.0) * 100, 4)


def _spec(symbol: str, state_dir: str) -> dict:
    from quant.live.retrain import champion_spec
    return champion_spec("crypto", symbol, state_dir) or {}


def build_two_sided(symbol: str, state_dir: str):
    """그 종목의 챔피언 규칙을 **양방향으로** 세운 전략.

    ⚠️ 규칙을 다시 쓰지 않는다(FROZEN_IDEAS ①). 챔피언 스펙을 그대로
       빌려 오고 `allow_short`만 켠다 — 그래야 두 트랙의 차이가 '방향
       허용 여부' 하나로 좁혀진다. 다른 것을 하나라도 같이 바꾸면 성적
       차이가 무엇 때문인지 영영 모른다.

    숏을 못 내는 챔피언(규칙 전략)은 **그대로** 세운다. 억지로 숏을
    만들지 않고, 결과 기록이 그 종목은 롱 전용이라고 적는다.
    """
    from quant.live.retrain import build_strategy
    spec = _spec(symbol, state_dir)
    if not can_short(spec):
        return build_strategy(spec), False
    two = dict(spec)
    params = dict(two.get("params") or {})
    params["allow_short"] = True
    two["params"] = params
    return build_strategy(two), True


def run_futures_round(now_iso: str, *, state_dir: str = "state",
                      universe: list[str] | None = None,
                      per_side: float | None = None) -> dict:
    """한 회차 — 신호를 받아 양방향 목표를 잡고 체결한다.

    돌려주는 것은 그 회차 기록이다. **시세를 실데이터로 못 받은 종목은
    그 회차를 건너뛰고 그렇게 적는다** — 합성 시세로 가짜 체결을 만들지
    않는다(장중 트랙과 같은 규칙).
    """
    from quant.backtest.costs import CostModel
    universe = list(universe if universe is not None else UNIVERSE)
    if per_side is None:
        per_side = float(CostModel.for_market("crypto").total_one_way())
    st = load_state(state_dir)

    signals: dict = {}
    prices: dict = {}
    long_only: list[str] = []
    skipped: list[str] = []
    for sym in universe:
        try:
            df = _fetch_real(sym)
        except Exception as exc:                       # noqa: BLE001
            log.warning("선물 %s 시세 실패: %s", sym, exc)
            df = None
        if df is None or len(df) < MIN_BARS:
            skipped.append(sym)
            signals[sym] = None
            continue
        df = confirmed_bars(df, now_iso)
        if len(df) < MIN_BARS:
            skipped.append(sym)
            signals[sym] = None
            continue
        try:
            strat, two_sided = build_two_sided(sym, state_dir)
            sig = float(strat.generate_signals(df).iloc[-1])
        except Exception as exc:                       # noqa: BLE001
            log.warning("선물 %s 신호 실패: %s", sym, exc)
            skipped.append(sym)
            signals[sym] = None
            continue
        if not two_sided:
            long_only.append(sym)
            sig = max(0.0, sig)
        # ⚠️ [-1, 1]로 자른다 — 레버리지는 여기서도 안 만든다.
        signals[sym] = max(-1.0, min(1.0, sig))
        prices[sym] = float(df["close"].iloc[-1])

    # ⚠️ **청산이 가장 먼저다.** 증거금이 바닥났으면 그 자리에서 끝이고,
    #    그날의 판단은 의미가 없다. 순서를 바꾸면 이미 털렸어야 할 계좌가
    #    한 회차를 더 버티며 새 포지션을 여는, 현실에 없는 장부가 된다.
    liq = liquidation_check(st, prices)
    if liq:
        log.error("💀 선물 강제 청산 — 증거금률 %.4f · 종목 %s",
                  liq["at_ratio"], ", ".join(liq["closed"]) or "-")

    # 하드 스톱이 그다음 — 새 판단보다 위험 축소가 앞선다.
    stops = stopped_out(st, prices)
    for sym in stops:
        signals[sym] = 0.0

    equity = mark_equity(st, prices) if prices else float(st["cash"])
    hours = _hours_since(st.get("rounds") or [], now_iso)
    funding = apply_funding(st, prices, hours) if prices else 0.0
    trades = execute_targets(st, signals, prices, equity, per_side, universe)
    equity = mark_equity(st, prices) if prices else float(st["cash"])
    # 마지막으로 본 시세를 남긴다 — 종목별 손익을 그리려면 '지금 값'이
    # 있어야 한다. 이번 회차에 못 받은 종목은 **이전 값을 지우지 않는다**
    # (지우면 화면이 "모른다"로 바뀌는데, 실제로는 조금 낡았을 뿐이다).
    last = dict(st.get("last_prices") or {})
    last.update(prices)
    st["last_prices"] = last

    rec = {"at": now_iso, "equity": round(equity, 4),
           "cash": round(float(st["cash"]), 4),
           "gross_exposure": round(gross_exposure(st, prices), 4),
           "funding": round(funding, 6),
           "cost_paid": round(float(st.get("cost_paid") or 0.0), 4),
           "funding_paid": round(float(st.get("funding_paid") or 0.0), 6),
           "signals": {k: (round(v, 4) if v is not None else None)
                       for k, v in signals.items()},
           "positions": {k: round(v, 10)
                         for k, v in (st.get("positions") or {}).items()},
           "margin_ratio": (round(margin_ratio(st, prices), 6)
                            if margin_ratio(st, prices) is not None else None),
           "trades": trades, "skipped": skipped,
           "long_only": long_only, "stopped": stops}
    if liq:
        rec["liquidated"] = liq
    st["rounds"] = (st.get("rounds") or [])[-(ROUNDS_KEEP - 1):] + [rec]
    st["curve"] = (st.get("curve") or [])[-(CURVE_KEEP - 1):] + [
        {"at": now_iso, "equity": round(equity, 4)}]
    save_state(st, state_dir)
    return rec


def _hours_since(rounds: list, now_iso: str) -> float:
    """직전 회차로부터 몇 시간 지났나 — 자금조달은 **시간**에 비례한다.

    회차 수로 세면 크론이 밀린 날(감사 267 실측 최악 558분)에 자금조달이
    통째로 빠진다. 첫 회차는 0이다 — 포지션이 없었으므로 낼 것도 없다.
    """
    import datetime as dt
    if not rounds:
        return 0.0
    prev = str((rounds[-1] or {}).get("at") or "")
    if not prev:
        return 0.0
    try:
        a = dt.datetime.fromisoformat(prev.replace("Z", "+00:00"))
        b = dt.datetime.fromisoformat(str(now_iso).replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if a.tzinfo is None or b.tzinfo is None:
        a, b = a.replace(tzinfo=None), b.replace(tzinfo=None)
    gap = (b - a).total_seconds() / 3600.0
    # 음수(시계 되돌림)나 터무니없이 큰 값은 자금조달로 치지 않는다.
    return gap if 0.0 <= gap <= 72.0 else 0.0


def _holdings(st: dict) -> list:
    """종목별 손익 — 코인·미국 트랙과 **같은 계산**을 쓴다."""
    from quant.live.holdings import avg_cost_from_rounds, holdings_view
    avg = dict(avg_cost_from_rounds(st.get("rounds") or []))
    avg.update({k: v for k, v in (st.get("avg_cost") or {}).items() if v})
    return holdings_view(st.get("positions") or {},
                         st.get("last_prices") or {}, avg, currency="USDT")


def _holdings_total(st: dict) -> dict:
    from quant.live.holdings import totals
    return totals(_holdings(st))


def public_report(st: dict) -> dict:
    """사이트가 읽을 재료. **한계도 함께 싣는다** — 숫자만 실으면 거짓말이다."""
    rounds = st.get("rounds") or []
    last = rounds[-1] if rounds else {}
    curve = st.get("curve") or []
    eq = float((last or {}).get("equity") or st.get("cash") or 0.0)
    base = float(st.get("start_cash") or 0.0)
    longs = shorts = 0
    for _sym, q in (st.get("positions") or {}).items():
        if float(q) > 0:
            longs += 1
        elif float(q) < 0:
            shorts += 1
    trades = [{**t, "at": r.get("at")}
              for r in rounds for t in (r.get("trades") or [])][-40:]
    return {
        "kind": KIND,
        "updated": last.get("at"),
        "start_cash": round(base, 2),
        "equity": round(eq, 4),
        "return_pct": (round((eq / base - 1.0) * 100, 4) if base > 0 else None),
        "cost_paid": round(float(st.get("cost_paid") or 0.0), 4),
        "funding_paid": round(float(st.get("funding_paid") or 0.0), 6),
        "funding_rate_per_8h": FUNDING_RATE_PER_8H,
        "max_gross_exposure": MAX_GROSS_EXPOSURE,
        # 규칙이 바뀐 지점 — 곡선을 읽는 사람이 이유를 알 수 있게.
        "rule_changes": list(RULE_CHANGES),
        "maintenance_margin_rate": MAINTENANCE_MARGIN_RATE,
        "margin_ratio": last.get("margin_ratio"),
        "liquidations": int(st.get("liquidations") or 0),
        "liquidated": last.get("liquidated"),
        "short_stop_pct": SHORT_STOP_PCT,
        "gross_exposure": last.get("gross_exposure"),
        "long_positions": longs,
        "short_positions": shorts,
        "long_only_symbols": last.get("long_only") or [],
        "stopped": last.get("stopped") or [],
        "skipped": last.get("skipped") or [],
        "rounds": len(rounds),
        "observed_gap_minutes": observed_gap_minutes(rounds),
        "curve": curve[-CURVE_KEEP:],
        "positions": {k: round(float(v), 10)
                      for k, v in (st.get("positions") or {}).items()},
        # 종목마다 지금 얼마 벌고 있나 (2026-08-22 사장님 지시).
        # ⚠️ 여기는 숏이 섞인다 — 손익 부호가 반대인 줄이 있다. 계산은
        #    세 트랙이 같은 곳(quant.live.holdings)을 쓴다.
        "holdings": _holdings(st),
        "holdings_total": _holdings_total(st),
        "recent_trades": trades,
        "limits": list(HONEST_LIMITS),
    }


def write_public_report(st: dict, docs_dir: str = "docs") -> str:
    os.makedirs(docs_dir, exist_ok=True)
    p = os.path.join(docs_dir, "futures.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(public_report(st), f, ensure_ascii=False, indent=2)
    return p
