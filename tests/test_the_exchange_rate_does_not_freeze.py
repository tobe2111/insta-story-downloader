"""환율 캐시가 늙지 않는다 — `refresh=True`가 이름뿐이었다 (감사 252).

`fx.usdkrw`는 감사 212가 만든 통로입니다. 해외 종목을 원화로 환산해
**환위험이 매일의 재평가로 장부에 잡히게** 하는 것이 목적이었습니다.

그런데 캐시가 프로세스가 사는 동안 그대로였고, 탈출구로 있던
`refresh=True`는 한 층 아래 `crossasset._bench_close`의 메모에 막혀
**아무 일도 하지 않았습니다.**

실측(2026-08-15):

    첫 조회        1416.46
    환율이 1500으로 움직인 뒤 usdkrw(refresh=True)  →  **1416.46**

하루 한 번 도는 배치에서는 문제가 없습니다(프로세스가 매번 새로 뜨고,
같은 배치 안에서는 한 환율을 쓰는 것이 오히려 옳습니다 — 감사 212).
문제는 **며칠 사는 프로세스** 둘입니다:

    실시간 루프   quant/live/engine.py·multi.py — 1시간 간격으로 며칠
    조종석 서버   quant/web/server.py — 요청마다 usdkrw()

거기서는 해외 평가 환율이 **첫 조회값에 영영 고정**됩니다. 원/달러가 3%
움직이면 미국·코인 보유 평가가 3% 틀어지고, 그 왜곡이 자산·수익률·낙폭·
킬스위치 판정까지 그대로 흘러갑니다. 감사 212가 뚫어 놓은 통로가 장수
프로세스에서만 막혀 있었습니다.

고친 방법: 캐시에 나이를 준다(1시간). 배치는 그 안에서 끝나므로 예전처럼
'한 배치에 한 환율'이고, 장수 프로세스는 한 시간마다 새로 받습니다.
`refresh=True`는 아래 메모까지 함께 비워 **진짜로** 다시 받습니다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import quant.data.crossasset as CA  # noqa: E402
import quant.data.fx as F  # noqa: E402
from quant.data.fx import FX_MAX, FX_MIN, needs_fx, to_krw, usdkrw  # noqa: E402


# ⚠️ 시계의 기준시각은 TTL보다 **한참 커야** 한다. 1000초에서 시작하면
#    `_MEMO_AT`가 0인 상태(= 시각을 안 남긴 고장)도 "1000초밖에 안 지났다"로
#    읽혀 신선해 보인다 — 변이 시험이 그 자리를 찔러 잡았다.
T0 = 1_000_000.0


def _feed(value):
    def _fetch(*a, **k):
        return pd.DataFrame(
            {"open": [value], "high": [value], "low": [value],
             "close": [value], "volume": [1.0]},
            index=pd.date_range("2026-08-14", periods=1))
    return _fetch


@pytest.fixture(autouse=True)
def _clean():
    """두 메모를 **함께** 비운다 — 하나만 비우면 검사가 헛돈다."""
    F._MEMO.clear()
    F._MEMO_AT = 0.0
    CA._MEMO.clear()
    yield
    F._MEMO.clear()
    F._MEMO_AT = 0.0
    CA._MEMO.clear()


# ── 캐시가 늙는가 ─────────────────────────────────────────────

def test_the_rate_is_reused_within_one_batch():
    """대조군 — 같은 배치 안에서는 한 환율이어야 한다(감사 212).

    종목마다 따로 받으면 같은 배치에서 종목별로 다른 환율이 적용돼
    자산이 미세하게 어긋난다.
    """
    t = [T0]
    assert usdkrw(fetch=_feed(1416.46), now=lambda: t[0]) == 1416.46
    assert usdkrw(fetch=_feed(1500.0), now=lambda: t[0] + 10) == 1416.46


def test_the_rate_ages_out_in_a_long_lived_process():
    """실측 그 장면 — 며칠 도는 프로세스에서 환율이 얼어 있었다."""
    t = [T0]
    usdkrw(fetch=_feed(1416.46), now=lambda: t[0])
    got = usdkrw(fetch=_feed(1500.0), now=lambda: t[0] + F.FX_TTL_SEC + 1)
    assert got == 1500.0, f"환율이 캐시에 얼어 있다: {got}"


def test_refresh_actually_refreshes():
    """탈출구가 이름뿐이면 없는 것과 같다."""
    t = [T0]
    usdkrw(fetch=_feed(1416.46), now=lambda: t[0])
    got = usdkrw(fetch=_feed(1500.0), refresh=True, now=lambda: t[0] + 10)
    assert got == 1500.0, f"refresh가 아무 일도 안 했다: {got}"


def test_the_lower_memo_is_cleared_too():
    """한 층 아래 메모를 안 비우면 위에서 무엇을 해도 소용없다."""
    t = [T0]
    usdkrw(fetch=_feed(1416.46), now=lambda: t[0])
    assert ("us_stock", "KRW=X", 30) in CA._MEMO
    usdkrw(fetch=_feed(1500.0), refresh=True, now=lambda: t[0] + 10)
    assert CA._MEMO[("us_stock", "KRW=X", 30)].iloc[-1] == 1500.0


def test_a_failure_is_still_not_remembered():
    """대조군 — 실패는 캐시하지 않는다(잠깐 끊긴 것이 영영 남으면 안 된다)."""
    def _boom(*a, **k):
        raise RuntimeError("일시 장애")

    assert usdkrw(fetch=_boom) is None
    assert "usdkrw" not in F._MEMO
    assert usdkrw(fetch=_feed(1416.46)) == 1416.46, "다음 시도가 살아나야 한다"


# ── 상식 범위 — 환율이 아니라 사고인 값들 ─────────────────────

@pytest.mark.parametrize("bad,why", [
    (0.0007, "계열이 뒤집혔다(달러/원)"),
    (1.4, "단위가 틀렸다"),
    (FX_MIN - 1, "하한 밖"),
    (FX_MAX + 1, "상한 밖"),
    (float("nan"), "계산 불가"),
    (float("inf"), "계산 불가"),
    (-1416.0, "음수"),
    (0.0, "0"),
])
def test_a_number_that_is_not_a_rate_is_refused(bad, why):
    assert usdkrw(fetch=_feed(bad)) is None, f"{why}({bad})를 환율로 썼다"


@pytest.mark.parametrize("good", [FX_MIN, 1416.46, FX_MAX])
def test_a_sane_rate_is_accepted(good):
    """대조군 — 범위 판정이 지나쳐 정상 환율까지 막으면 해외 종목이 멈춘다."""
    assert usdkrw(fetch=_feed(good)) == good


# ── 모르면 값을 만들지 않는가 ─────────────────────────────────

@pytest.mark.parametrize("market", ["us_stock", "crypto"])
def test_no_rate_means_no_price(market):
    """1.0으로 때우면 그것이 바로 감사 212가 고친 결함이다."""
    assert needs_fx(market)
    assert to_krw(market, 100.0, None) is None


@pytest.mark.parametrize("market", ["kr_stock", "synthetic"])
def test_a_krw_market_is_never_converted(market):
    """이미 원화인 값을 환산하면 오히려 틀린다."""
    assert not needs_fx(market)
    assert to_krw(market, 100.0, None) == 100.0
    assert to_krw(market, 100.0, 1416.46) == 100.0


def test_conversion_multiplies():
    assert to_krw("us_stock", 100.0, 1416.46) == pytest.approx(141646.0)
