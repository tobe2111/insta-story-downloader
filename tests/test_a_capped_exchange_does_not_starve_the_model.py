"""거래소의 1회 응답 상한이 모델의 학습량을 조용히 깎지 않는가.

2026-08-14 발견. 코인 5종목이 전부 **300봉**으로 굴러가고 있었다. 주식은
800봉인데 코인만 300봉인 이유를 아무도 묻지 않았고, 장부에도 `bars: 300`이
사실로 적혀 있을 뿐 '모자라다'는 표시는 없었다.

원인 사슬:
    바이낸스 차단(운영 환경) → 보조 거래소 okx로 폴백 → okx는 한 번에
    **300봉이 상한** → 800봉을 요청해도 300봉만 온다.

그 300봉이 만든 결과:
    · 오디션 선발 구간이 300−120=180봉인데 챔피언의 학습창은 250봉이라
      **한 번도 학습하지 못했다.** 후보 19개 중 18개가 신호 0으로 챔피언과
      똑같았고, 코인 오디션은 매일 아무것도 검증하지 못한 채
      "챔피언 유지. 정상입니다"를 기록했다.
    · 실전에서도 예측 가능한 구간이 50봉뿐이라 코인 노출이 주식의 1/4이었다.
    · 300봉으로 잰 과최적화 지표(BTC PBO 0.78)도 표본 부족의 산물이다.

이 파일은 '상한이 있는 거래소에서도 요청한 만큼 받는다'를 못으로 박는다.
네트워크는 쓰지 않는다 — 상한만 다른 가짜 거래소를 주입한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.data.crypto import _fetch_paged, _MAX_PAGES  # noqa: E402

DAY = 86_400_000
BASE = int(pd.Timestamp("2023-01-01").timestamp() * 1000)
BARS = [[BASE + i * DAY, 100 + i, 101 + i, 99 + i, 100.5 + i, 1000.0]
        for i in range(1500)]


class _Capped:
    """한 번에 cap봉까지만 주는 거래소(okx=300, 바이낸스=1000 등)."""

    def __init__(self, cap: int):
        self.cap = cap
        self.calls = 0

    def fetch_ohlcv(self, symbol, timeframe="1d", since=None, limit=None):
        self.calls += 1
        rows = [r for r in BARS if since is None or r[0] >= since]
        return rows[:min(self.cap, limit or self.cap)]


# ── ① 상한을 넘어 요청한 만큼 받는다 ──────────────────────────


@pytest.mark.parametrize("cap", [100, 300, 500])
def test_a_capped_exchange_still_yields_the_requested_history(cap):
    ex = _Capped(cap)
    rows = _fetch_paged(ex, "BTC/USDT", "1d", BASE, 800)
    assert len(rows) == 800, (
        f"1회 상한 {cap}봉인 거래소에서 {len(rows)}봉만 받았다 — "
        "학습창(250봉)+오디션 결승(120봉)을 채우지 못한다")
    assert ex.calls > 1, "상한보다 많이 요청했는데 한 번만 불렀다"


def test_no_duplicate_or_unsorted_bars_across_pages():
    """페이지 경계에서 봉이 겹치거나 순서가 뒤집히면 수익률이 거짓이 된다."""
    rows = _fetch_paged(_Capped(300), "BTC/USDT", "1d", BASE, 800)
    ts = [r[0] for r in rows]
    assert len(ts) == len(set(ts)), "페이지 경계에서 같은 봉이 두 번 들어왔다"
    assert ts == sorted(ts), "봉 순서가 뒤섞였다"
    assert all(b - a == DAY for a, b in zip(ts, ts[1:])), "봉 사이에 구멍이 있다"


def test_an_uncapped_exchange_is_not_slowed_down():
    """넉넉한 거래소에서는 한 번에 끝난다 — 기존 동작이 바뀌지 않는다."""
    ex = _Capped(1000)
    rows = _fetch_paged(ex, "BTC/USDT", "1d", BASE, 800)
    assert len(rows) == 800
    assert ex.calls == 1, f"한 번이면 될 것을 {ex.calls}번 불렀다(레이트리밋 낭비)"


def test_recent_n_bars_without_a_start_date():
    """since 없이 '최근 800봉'을 원할 때도 상한을 넘어 받는다."""
    rows = _fetch_paged(_Capped(300), "BTC/USDT", "1d", None, 800)
    assert len(rows) == 800


# ── ② 병리적 거래소에서도 반드시 끝난다 ───────────────────────


def test_an_exchange_that_repeats_itself_cannot_hang_us():
    """같은 페이지만 돌려주는 거래소 — 무한루프가 되면 야간 배치가 죽는다."""
    class _Stuck:
        def __init__(self): self.calls = 0
        def fetch_ohlcv(self, *a, **k):
            self.calls += 1
            return BARS[:5]

    ex = _Stuck()
    rows = _fetch_paged(ex, "X", "1d", BASE, 800)
    assert len(rows) == 5
    assert ex.calls <= _MAX_PAGES, "진전이 없는데 계속 불렀다"


def test_an_exchange_that_returns_nothing_is_not_an_error():
    class _Empty:
        def fetch_ohlcv(self, *a, **k): return []

    assert _fetch_paged(_Empty(), "X", "1d", BASE, 800) == []


def test_page_count_is_bounded_even_for_a_one_bar_exchange():
    """한 봉씩 주는 거래소라도 호출 수에 상한이 있다(레이트리밋 보호)."""
    ex = _Capped(1)
    _fetch_paged(ex, "X", "1d", BASE, 800)
    assert ex.calls <= _MAX_PAGES


# ── ③ 제공자 전체 경로에 배선됐는가 ───────────────────────────


def test_the_provider_actually_uses_the_paged_fetch(monkeypatch):
    """헬퍼만 만들고 안 쓰면 아무것도 고쳐지지 않는다."""
    from quant.data.crypto import CryptoDataProvider

    p = CryptoDataProvider.__new__(CryptoDataProvider)
    p.exchange_id = "okx"
    p._client = None
    df = p._fetch(_Capped(300), "BTC/USDT", "1d", None, None, 800)
    assert len(df) == 800, (
        f"제공자를 통하면 {len(df)}봉이다 — 페이지네이션이 배선되지 않았다")
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]


def test_enough_bars_to_train_and_audit():
    """숫자로 못을 박는다 — 이 길이가 오디션을 성립시키는 최소선이다.

    학습창 250봉 + 결승 구간 120봉을 빼고도 선발전에 표본이 남아야
    '대결'이 성립한다. 300봉으로는 선발 구간이 180봉이라 학습조차 못 했다.
    """
    from quant.live.retrain import DEFAULT_CHAMPION

    train_window = DEFAULT_CHAMPION["params"]["train_window"]
    confirm_window = 120
    got = len(_fetch_paged(_Capped(300), "BTC/USDT", "1d", None, 800))
    assert got - confirm_window > train_window, (
        f"{got}봉 − 결승 {confirm_window}봉 = {got - confirm_window}봉으로는 "
        f"학습창 {train_window}봉을 채우지 못한다 — 오디션이 공회전한다")
