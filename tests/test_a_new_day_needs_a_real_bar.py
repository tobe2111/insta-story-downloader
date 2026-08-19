"""갓 시작한 봉이 하루를 열어 버린다 (2026-08-14 감사 232).

**실제로 일어난 일이다.** 예비 배치가 23:15 UTC에 걸려 있었는데 GitHub
Actions가 43분 늦게 띄워 23:58에 시작했고, 도중에 UTC 자정을 넘겼다.
코인 일봉은 UTC 자정에 롤오버한다 — 그래서 완성도 **0.03%**짜리 봉이
'2026-08-14'라는 새 날을 열었다. 장부에 그대로 남아 있다:

    08-13 기록  bar_partial 0.9619  bar_age {crypto 0, us 0, kr 0}   정상
    08-14 기록  bar_partial 0.0003  bar_age {crypto 0, us 1, kr 1}   ← 이것

08-14 기록의 주식은 **하루 묵은 봉**으로 판단한 것이다. 그리고 계좌의
`last_bar`가 이미 '2026-08-14'이므로, 그날 저녁 정규 배치(22:15 UTC)는
같은 날짜를 보고 **건너뛴다** — 재시도가 다음 날을 선점해, 묵은 판단으로
그 날을 확정해 버린다. 하루치 판단이 통째로 한 세션 뒤처지는 것이다.

고친 방법은 두 겹이다:
  ① 크론을 자정에서 멀리 뒀다(23:15 → 22:30). 검사는
     `test_the_batch_runs_after_the_markets_it_trades.py`에 있다.
  ② **하루의 이름은 형태를 갖춘 봉만 정한다** — 이 파일이 그 계약이다.

①만으로는 부족하다. Actions 지연은 상한이 없어서 크론을 어디에 두든
언젠가 자정을 넘긴다. 시각으로 막은 것은 코드로도 막아 둔다.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.live import daily as dl  # noqa: E402
from quant.live.daily import NEW_DAY_MIN_ELAPSED, judgement_day  # noqa: E402

# 그날 밤 장부에 실제로 남은 값 (state/paper/portfolio_ALL.json, 08-14 기록).
CRYPTO = ["crypto:BTC/USDT", "crypto:ETH/USDT", "crypto:SOL/USDT",
          "crypto:BNB/USDT", "crypto:XRP/USDT"]
STOCKS = ["us_stock:SPY", "kr_stock:105560.KS"]


def _midnight_scene():
    """자정 직후 — 코인 봉은 08-14로 넘어갔고, 주식은 아직 08-13이다."""
    last_bars = {k: "2026-08-14 00:00:00" for k in CRYPTO}
    last_bars.update({k: "2026-08-13 00:00:00" for k in STOCKS})
    partial = {k: 0.0003 for k in CRYPTO}     # 주식은 완성 봉 → 항목 없음
    return last_bars, partial


def _normal_scene():
    """정규 시각(22:15 UTC) — 코인 봉은 92.7% 형성됐다."""
    last_bars = {k: "2026-08-13 00:00:00" for k in CRYPTO}
    last_bars.update({k: "2026-08-13 00:00:00" for k in STOCKS})
    return last_bars, {k: 0.9271 for k in CRYPTO}


def test_a_bar_that_just_opened_does_not_open_a_new_day():
    """감사 232 그 장면 — 08-14이 아니라 08-13이 나와야 한다."""
    last_bars, partial = _midnight_scene()
    assert judgement_day(last_bars, partial) == "2026-08-13", (
        "완성도 0.03%짜리 코인 봉이 새 날을 열었다 — 그러면 다음 날 정규 "
        "배치가 건너뛴다")


def test_the_guard_makes_the_retry_idempotent_again():
    """그래서 자정을 넘긴 재시도는 '건너뜀'이 된다 — 이것이 목적이다.

    정규 배치가 08-13을 기록해 `last_bar='2026-08-13'`이 된 뒤, 늦게 뜬
    재시도가 자정을 넘겨 돌아도 같은 날짜를 돌려주므로 멱등 가드에 걸린다.
    """
    normal_bars, normal_partial = _normal_scene()
    recorded = judgement_day(normal_bars, normal_partial)

    late_bars, late_partial = _midnight_scene()
    assert judgement_day(late_bars, late_partial) == recorded


def test_the_ordinary_batch_still_opens_its_day():
    """대조군 — 막는 것만 검사하면 '항상 막는' 코드도 통과한다.

    다음 날 정규 배치(코인 봉 92.7% 형성)는 새 날을 열어야 한다. 안 그러면
    이 가드는 결함을 막는 대신 배치를 영영 멈춰 세운다.
    """
    last_bars = {k: "2026-08-14 00:00:00" for k in CRYPTO}
    last_bars.update({k: "2026-08-14 00:00:00" for k in STOCKS})
    partial = {k: 0.9271 for k in CRYPTO}
    assert judgement_day(last_bars, partial) == "2026-08-14"


def test_the_weekend_is_not_collateral_damage():
    """주말에도 코인은 돈다 — 이 가드가 토·일을 죽이면 안 된다.

    토요일 22:15 UTC: 코인 봉은 토요일자로 92.7% 형성돼 있고, 주식 봉은
    금요일에 멈춰 있다. 하루의 이름은 **토요일**이어야 한다 — 그래야
    금요일 기록과 달라서 코인 재조정이 돈다.
    """
    last_bars = {k: "2026-08-15 00:00:00" for k in CRYPTO}       # 토
    last_bars.update({k: "2026-08-14 00:00:00" for k in STOCKS})  # 금
    partial = {k: 0.9271 for k in CRYPTO}
    assert judgement_day(last_bars, partial) == "2026-08-15"


def test_a_completed_bar_needs_no_partial_entry():
    """`bar_status`는 완성된 봉에 None을 준다 — 그 종목은 항목이 없다.

    없는 것을 '0'으로 읽으면 주식만으로 도는 계좌가 하루도 열지 못한다.
    """
    last_bars = {"us_stock:SPY": "2026-08-14 00:00:00"}
    assert judgement_day(last_bars, {}) == "2026-08-14"


def test_when_nothing_is_formed_we_still_record():
    """전 종목이 자정 직후 코인인 극단 — 판단을 멈추지 않는다.

    기록을 아예 안 남기는 것보다, 남기고 `bar_partial`로 드러내는 편이 낫다
    (이 저장소의 규칙: 조용히 멈추는 것이 가장 나쁘다).
    """
    last_bars = {k: "2026-08-14 00:00:00" for k in CRYPTO}
    assert judgement_day(last_bars, {k: 0.0003 for k in CRYPTO}) == "2026-08-14"


def test_no_bars_at_all_is_an_error_not_a_guess():
    with pytest.raises(ValueError):
        judgement_day({}, {})


@pytest.mark.parametrize("elapsed,opens", [
    (0.0003, False),   # 자정 직후 — 실제 사고 값
    (0.0310, False),   # 00:45 UTC — Actions가 45분 늦어도 여기까지다
    (0.0999, False),   # 문턱 바로 아래
    (0.1000, True),    # 문턱
    (0.9271, True),    # 정규 배치 22:15 UTC
])
def test_the_threshold_is_where_it_says_it_is(elapsed, opens):
    """문턱을 어디에 뒀는지 값으로 못박는다 — 주석은 코드를 지키지 못한다."""
    last_bars = {"crypto:BTC/USDT": "2026-08-14 00:00:00",
                 "us_stock:SPY": "2026-08-13 00:00:00"}
    got = judgement_day(last_bars, {"crypto:BTC/USDT": elapsed})
    assert got == ("2026-08-14" if opens else "2026-08-13")


def test_the_threshold_clears_the_worst_observed_delay():
    """문턱은 '실측 최악 지연'보다 넉넉해야 뜻이 있다.

    2026-08-13 밤 실측: 예약 대비 39~48분 지연. 자정 직후 45분이면 코인
    일봉 완성도는 45/1440 = 0.031이다. 문턱은 그보다 충분히 위여야
    '자정을 넘겨 뜬 배치'를 확실히 걸러 낸다.
    """
    worst_delay_min = 60          # 실측 48분에 여유를 얹은 값
    assert NEW_DAY_MIN_ELAPSED > worst_delay_min / 1440.0 * 2
    # 그러면서 정규 시각(22:15 UTC → 0.927)과는 멀리 떨어져 있어야 한다
    assert NEW_DAY_MIN_ELAPSED < 0.5


# ── 계좌를 실제로 돌려서 확인한다 ──────────────────────────────
#
# 위 검사들은 `judgement_day` 하나만 본다. 그것이 **불려야** 뜻이 있다 —
# 실제로 이 저장소는 "함수는 맞는데 아무도 안 부른다"로 여러 번 당했다
# (감사 229가 그랬다). 그래서 계좌를 돌려서 값으로 확인한다.


class _P:
    def __init__(self, frames):
        self._frames = frames

    def get_ohlcv(self, symbol, *a, **k):
        return self._frames[symbol].copy()


class _Buy:
    name, allow_short = "fixed", False

    def generate_signals(self, df):
        return pd.Series(0.9, index=df.index)


def _frame(end_date: str, n: int = 300, seed: int = 7):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.02, n)))
    idx = pd.date_range(end=pd.Timestamp(end_date), periods=n, freq="D")
    return pd.DataFrame({"open": close * 0.99, "high": close * 1.03,
                         "low": close * 0.97, "close": close,
                         "volume": 1e6}, index=idx)


def _run_account(monkeypatch, tmp_path, *, crypto_elapsed: float):
    """코인 봉은 하루 앞서 있고(자정 롤오버), 주식 봉은 어제에 멈춰 있다.

    `bar_status`를 고정한다 — 안 그러면 이 검사가 **벽시계에 매달린다**.
    그런 검사는 특정 시간대에만 빨개져서, 결국 무시당한다(감사 204·232의
    같은 교훈).
    """
    today = dt.date.today().isoformat()
    yday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    frames = {"BTC/USDT": _frame(today), "SPY": _frame(yday, seed=11)}
    monkeypatch.setattr(dl, "usdkrw", lambda *a, **k: 1400.0)
    monkeypatch.setattr("quant.data.get_provider", lambda m: _P(frames))
    monkeypatch.setattr(dl, "champion_strategy", lambda *a, **k: _Buy())
    monkeypatch.setattr(dl, "champion_spec",
                        lambda *a, **k: {"strategy": "fixed", "params": {}})
    monkeypatch.setattr(
        dl, "bar_status",
        lambda market, bar, tf=None, now=None: (
            {"elapsed": crypto_elapsed} if market == "crypto" else None))

    # 어제 정규 배치가 이미 기록을 남긴 상태로 시작한다
    (tmp_path / "paper").mkdir(parents=True, exist_ok=True)
    path = tmp_path / "paper" / "portfolio_ALL.json"
    path.write_text(json.dumps({
        "cash": 1_000_000.0, "positions": {}, "base_prices": {},
        "last_bar": yday, "history": [],
    }), "utf-8")

    out = dl.run_daily_portfolio([("crypto", "BTC/USDT"), ("us_stock", "SPY")],
                                 state_dir=str(tmp_path),
                                 require_real_data=False)
    # 날짜를 **여기서 만든 값 그대로** 돌려준다(2026-08-19 자정 실측).
    # 검증부가 dt.date.today()를 다시 부르면, CI가 23:59에 시작해 검사
    # 도중 자정을 넘는 날 '오늘'이 둘로 갈라져 거짓 빨강이 된다 —
    # 이 파일 머리의 교훈("벽시계에 매달린 검사는 무시당한다") 그대로다.
    return out, json.loads(path.read_text("utf-8")), today, yday


def test_a_midnight_retry_is_skipped_by_the_real_account(monkeypatch, tmp_path):
    """자정을 넘겨 뜬 재시도는 계좌를 건드리지 못해야 한다."""
    out, st, _today, yday = _run_account(monkeypatch, tmp_path,
                                         crypto_elapsed=0.0003)
    assert out.get("skipped") is True, (
        f"자정 직후 코인 봉으로 새 날을 열었다 — {out.get('last_bar')}")
    assert st["last_bar"] == yday, "다음 날을 선점해 버렸다"
    assert not st["history"], "묵은 판단으로 기록을 하나 만들었다"


def test_the_same_account_does_open_a_normal_day(monkeypatch, tmp_path):
    """대조군 — 정규 시각(코인 봉 92.7%)에는 그날이 열려야 한다.

    이 대조군이 없으면 '무조건 건너뛰는' 코드도 위 검사를 통과한다.
    """
    out, st, today, _yday = _run_account(monkeypatch, tmp_path,
                                         crypto_elapsed=0.9271)
    assert not out.get("skipped"), "정상 배치까지 막아 버렸다"
    assert st["last_bar"] == today
    assert st["history"], "그날 기록이 남지 않았다"
