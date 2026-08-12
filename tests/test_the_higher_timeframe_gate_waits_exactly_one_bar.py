"""상위 시간봉 게이트가 한 봉이 아니라 **두 봉**을 기다렸다 (감사 166).

`MultiTimeframeFilter`는 하위 전략의 신호를 상위 시간봉 추세로 게이팅한다.
게이트가 꺼져 있는 동안 하위 전략의 롱은 **전부 0으로 지워진다.** 그래서
"얼마나 늦게 켜지는가"가 곧 "새 추세를 며칠 놓치는가"다.

    up = (htf_close > htf_ma).astype(float)
    up = up.shift(1)          # ← 의도: 완성된 봉만 쓰자
    return up.reindex(close.index, method="ffill")

의도는 맞았는데 **지연이 두 배가 됐다.** pandas의 기본 라벨 위치가 규칙마다
다르기 때문이다:

    'W' · 'ME'   →  label='right'   봉이 **끝나는** 날에 라벨
    '4h' 등 일중 →  label='left'    봉이 **시작하는** 시각에 라벨

오른쪽 라벨은 그 자체가 이미 '완성 시각'이다. 거기에 shift를 더하면 상위
봉을 하나 통째로 더 기다린다. 실측(주봉·추세 3주, 어느 월요일에 폭등):

    올바른 반응    폭등을 담은 주봉이 끝나는 날 (7일 뒤)
    실제 반응      그 다음 주 (13일 뒤)          ← 한 주를 더 쉰다

고침은 라벨 위치를 규칙에 맡기지 않고 오른쪽으로 **명시**하는 것이다.
그러면 라벨 시각 = 완성 시각이 되어 ffill이 저절로 '지금까지 완성된 마지막
상위 봉'을 집는다. shift가 필요 없어지고, **진행 중인 봉은 라벨이 미래라서
ffill이 닿지 못한다** — 룩어헤드가 구조적으로 불가능해진다.

──────────────────────────────────────────────────────────────
정직하게 — 이건 지금 돌고 있는 코드가 아니다

`MultiTimeframeFilter`는 `__init__`에서 export만 되고 **어디서도 만들어지지
않는다.** 전략 레지스트리에도 없고, 야간 오디션의 챌린저 목록
(regime_wrap·event_wrap·stop_wrap)에도 없다. `ADXFilter`·`LiquidityFilter`도
같은 처지다 — 셋 다 만들어만 놓고 배선하지 않았다(감사 135·157과 같은 계열).

그래서 이 결함은 오늘 돈을 잃게 하지 않는다. 다만 누군가 이 필터를 켜는
순간 곧바로 물게 되는 함정이라 고쳐 뒀고, 아래 마지막 검사로 '아직 안
배선됨'을 못 박아 둔다 — 배선하는 사람이 이 파일을 읽게 된다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.strategies.base import Strategy  # noqa: E402
from quant.strategies.multitimeframe import MultiTimeframeFilter  # noqa: E402


class _AlwaysLong(Strategy):
    """항상 롱 — 게이트가 무엇을 막는지만 보이게 한다."""

    name = "always"
    allow_short = False

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        return self._finalize(pd.Series(1.0, index=df.index), df.index)


def _frame(close: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({"open": close, "high": close, "low": close,
                         "close": close, "volume": 1e6}, index=close.index)


# 정답을 아는 데이터: 2024-02-05(월)에 폭등. 그 전은 완전히 평평하다.
JUMP = pd.Timestamp("2024-02-05")
DAILY = pd.date_range("2024-01-01", periods=70, freq="D")
_c = pd.Series(100.0, index=DAILY)
_c[_c.index >= JUMP] = 300.0
FLAT_THEN_JUMP = _frame(_c)

# 폭등을 담은 주봉이 끝나는 날 = 2024-02-11(일). 여기가 가장 이른 반응 시점이다.
WEEK_CLOSES = pd.Timestamp("2024-02-11")


def _first_long(df: pd.DataFrame, **kw) -> pd.Timestamp | None:
    sig = MultiTimeframeFilter(_AlwaysLong(), **kw).generate_signals(df)
    on = sig[sig > 0]
    return on.index.min() if len(on) else None


# ── 미래를 보지 않는가 ────────────────────────────────────────


def test_the_gate_does_not_open_before_the_move_happens():
    first = _first_long(FLAT_THEN_JUMP, htf="W", trend_window=3)
    assert first is not None and first >= JUMP, (
        f"폭등({JUMP.date()}) 전인 {first}에 게이트가 열렸다 — 미래를 봤다")


def test_an_unfinished_higher_bar_is_never_used():
    """데이터가 주 중간에 끝나면, 그 주는 아직 완성되지 않았다.

    라벨이 미래(그 주 일요일)라서 ffill이 닿지 못하는 것이 핵심이다.
    """
    idx = pd.date_range("2024-01-01", periods=45, freq="D")   # 2024-02-14(수)
    c = pd.Series(100.0, index=idx)
    c[c.index >= "2024-02-12"] = 900.0                        # 그 주 월요일 폭등
    sig = MultiTimeframeFilter(_AlwaysLong(), htf="W", trend_window=3) \
        .generate_signals(_frame(c))
    assert float(sig.iloc[-1]) == 0.0, (
        "아직 안 끝난 주봉의 폭등을 보고 게이트를 열었다")


# ── 정확히 한 봉만 기다리는가 ─────────────────────────────────


def test_the_gate_opens_when_the_bar_containing_the_move_completes():
    """이것이 감사 166 — 예전에는 여기서 한 주를 더 기다렸다."""
    first = _first_long(FLAT_THEN_JUMP, htf="W", trend_window=3)
    assert first == WEEK_CLOSES, (
        f"폭등을 담은 주봉은 {WEEK_CLOSES.date()}에 끝나는데 게이트가 "
        f"{first.date()}에 열렸다 — {(first - WEEK_CLOSES).days}일을 더 쉰다")


def test_the_extra_week_is_really_a_week_of_lost_exposure():
    """게이트가 늦으면 그만큼 하위 전략의 롱이 통째로 지워진다."""
    sig = MultiTimeframeFilter(_AlwaysLong(), htf="W", trend_window=3) \
        .generate_signals(FLAT_THEN_JUMP)
    window = sig.loc[WEEK_CLOSES:WEEK_CLOSES + pd.Timedelta(days=6)]
    assert (window > 0).all(), (
        f"주봉이 끝난 뒤 한 주 동안 롱이 막혀 있다:\n{window}")


def test_an_intraday_rule_does_not_read_the_future():
    """일중 규칙에서는 라벨 기본값이 반대쪽(left)이라 **진짜 룩어헤드**가 난다.

    ⚠️ 처음엔 폭등을 4h 봉 경계(00:00)에 딱 맞춰 놓고 검사했는데, 그러면
       두 라벨 방식의 답이 우연히 같아서 아무것도 못 잡았다. 폭등을 봉
       **한가운데**에 두어야 갈린다.

    실측(폭등 02:00, 4h 봉):
        pandas 기본(left) → 첫 롱 00:00   폭등 2시간 **전**
        오른쪽 라벨 명시  → 첫 롱 04:00   그 봉이 끝나는 시각

    왼쪽 라벨은 00:00~03:00 봉을 '00:00'이라 부른다. 그 봉의 종가는 03:00에야
    정해지는데, ffill이 00:00 시점에 그 값을 집어 준다 — 세 시간 뒤의 가격을
    미리 보는 것이다.
    """
    idx = pd.date_range("2024-01-01", periods=200, freq="h")
    jump = pd.Timestamp("2024-01-05 02:00")        # 4h 봉의 한가운데
    c = pd.Series(100.0, index=idx)
    c[c.index >= jump] = 300.0
    first = _first_long(_frame(c), htf="4h", trend_window=3)
    assert first is not None and first >= jump, (
        f"일중 규칙에서 게이트가 폭등({jump})보다 이른 {first}에 열렸다 — "
        "아직 정해지지 않은 종가를 미리 봤다")
    assert first <= jump + pd.Timedelta(hours=4), (
        f"상위 봉 하나보다 오래 기다린다: {first}")


# ── 게이트가 실제로 무언가를 막는가 (대조군) ──────────────────


def test_the_gate_blocks_longs_in_a_downtrend():
    c = pd.Series(range(200, 130, -1), index=DAILY, dtype=float)   # 계속 하락
    sig = MultiTimeframeFilter(_AlwaysLong(), htf="W", trend_window=3) \
        .generate_signals(_frame(c))
    assert float(sig.max()) == 0.0, (
        "하락 추세인데 롱을 허용한다 — 게이트가 아무것도 안 막는다")


def test_without_the_gate_the_base_strategy_is_long_all_along():
    """대조군 — 원래 신호가 계속 롱이어야 위 검사들이 의미가 있다."""
    base = _AlwaysLong().generate_signals(FLAT_THEN_JUMP)
    assert (base > 0).all()


def test_a_steady_uptrend_is_allowed():
    """대조군 — 상승장에서 계속 막으면 그건 고침이 아니라 파괴다."""
    c = pd.Series(range(100, 170), index=DAILY, dtype=float)
    sig = MultiTimeframeFilter(_AlwaysLong(), htf="W", trend_window=3) \
        .generate_signals(_frame(c))
    assert float(sig.tail(30).min()) > 0.0, "계속 오르는데 롱이 막힌다"


# ── 배선 상태 못 박기 ─────────────────────────────────────────


def test_which_filters_are_still_unwired():
    """만들어만 놓고 배선하지 않은 전략 필터를 고정한다.

    셋 다 레지스트리에도, 야간 오디션 챌린저에도 없어서 **어떤 경로로도
    만들어지지 않는다.** 이 검사가 깨지면 둘 중 하나다:
      · 누군가 배선했다  → 잘된 일이다. 이 파일을 읽고 목록에서 빼면 된다.
      · 누군가 지웠다    → 그것도 정답이다. 마찬가지로 목록에서 뺀다.
    어느 쪽이든 **조용히 지나가지는 않게** 한다(감사 135·157과 같은 계열).
    """
    import inspect

    import quant.strategies as S

    reachable = set(S._REGISTRY.values())
    retrain = (ROOT / "quant" / "live" / "retrain.py").read_text("utf-8")

    unwired = set()
    for name in S.__all__:
        obj = getattr(S, name, None)
        if not (inspect.isclass(obj) and issubclass(obj, Strategy)
                and obj is not Strategy):
            continue
        if obj in reachable or obj.__name__ in retrain:
            continue
        if obj.__name__ in ("StrategyEnsemble", "AdaptiveEnsemble"):
            continue                      # default_ensemble()로 실제로 쓰인다
        unwired.add(obj.__name__)

    assert unwired == {"ADXFilter", "MultiTimeframeFilter", "LiquidityFilter"}, (
        f"배선 안 된 전략 필터 목록이 바뀌었다: {sorted(unwired)}")
