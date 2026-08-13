"""검사가 **있다**와 검사가 **무언가를 지킨다**는 다르다 (감사 214).

변이 항목이 파일당 1건뿐이던 파일 23개를 훑었다. 항목을 하나씩 더 걸어
돌려 보니 **8건이 그대로 빠져나갔다** — 그 계약들은 지키는 사람이 아무도
없었던 것이다. 통과하던 검사들은 그 파일을 '실행'하고 있었을 뿐이다.

여기 모은 것들은 전부 그렇게 드러난 빈자리다. 각각은 작지만, 작다는 것과
안 중요하다는 것은 다르다:

  · 켈트너가 돌파 상태를 못 이어가면 밴드 안에서 **매일 청산·재진입**한다
    — 신호는 그대로인데 비용만 나간다
  · 모멘텀의 숏 문턱에서 부호가 빠지면 **관망 구간이 사라져** 언제나 어느
    한쪽에 실린다
  · 공포탐욕을 0~1로 안 맞추면 ML 피처 하나만 크기가 100배가 된다
  · 스크리너가 top_n을 안 넘기면 '선별기'가 아무것도 선별하지 않는다
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent


def _ohlc(closes, highs=None, lows=None) -> pd.DataFrame:
    c = pd.Series([float(v) for v in closes],
                  index=pd.date_range("2026-01-01", periods=len(closes), freq="D"))
    h = pd.Series(highs, index=c.index) if highs is not None else c * 1.001
    lo = pd.Series(lows, index=c.index) if lows is not None else c * 0.999
    return pd.DataFrame({"open": c, "high": h, "low": lo, "close": c,
                         "volume": 1e6}, index=c.index)


# ── 켈트너: 돌파 상태를 이어가는가 ────────────────────────────

def test_keltner_holds_the_breakout_instead_of_re_entering_daily():
    """돌파 뒤 밴드 안으로 돌아와도 **보유가 이어져야** 한다.

    이어가지 않으면 밴드 안에 있는 동안 매일 청산·재진입한다 — 신호는
    같은데 왕복 비용만 계속 나간다.
    """
    from quant.strategies.keltner import KeltnerBreakout

    rng = np.random.default_rng(0)
    base = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.01, 300)))
    base[150:] *= 1.25                       # 한 번 크게 돌파시킨다
    out = KeltnerBreakout(ema_window=20, atr_window=10, mult=2.0
                          ).generate_signals(_ohlc(base))

    held = int((out > 0).sum())
    flips = int((out.diff().fillna(0.0) != 0).sum())
    assert held > 0, "돌파가 한 번도 안 잡혔다 — 검사가 헛돈다"
    # 실측: 상태를 이어가면 보유 210봉·전환 10회, 안 이어가면 103봉·전환 50회.
    # 신호는 같은데 왕복만 다섯 배가 된다 — 그 차이를 숫자로 못 박는다.
    assert flips <= 20, (
        f"보유 {held}봉 동안 방향이 {flips}번 바뀐다 — 돌파 상태를 "
        "이어가지 않아 밴드 안에서 매일 청산·재진입하고 있다")
    assert held >= 150, (
        f"보유 구간이 {held}봉뿐이다 — 돌파 상태가 이어지지 않는다")


# ── 모멘텀: 관망 구간이 살아 있는가 ───────────────────────────

def test_momentum_keeps_a_neutral_band_between_the_thresholds():
    """문턱이 대칭이어야 ±threshold 사이에 **관망**이 생긴다.

    숏 문턱에서 부호가 빠지면 두 조건이 겹쳐 늘 어느 한쪽에 실린다.
    """
    from quant.strategies.momentum import Momentum

    # 수익률이 문턱(±5%) 안에서만 움직이는 계열 → 전 구간 관망이어야 한다
    n = 200
    c = pd.Series(100 + np.sin(np.arange(n) / 8.0) * 1.0)
    out = Momentum(lookback=20, threshold=0.05, allow_short=True
                   ).generate_signals(_ohlc(c.to_numpy()))
    assert (out == 0.0).all(), (
        f"±5% 안쪽 움직임인데 포지션이 잡혔다 — 관망 구간이 사라졌다\n"
        f"  롱 {int((out > 0).sum())}봉 · 숏 {int((out < 0).sum())}봉")


def test_momentum_still_takes_a_side_when_the_move_is_big():
    """대조군 — 관망만 하면 전략이 아니다."""
    from quant.strategies.momentum import Momentum

    c = np.linspace(100, 200, 200)
    out = Momentum(lookback=20, threshold=0.05).generate_signals(_ohlc(c))
    assert (out > 0).sum() > 100, "큰 상승인데 롱을 안 잡는다"


# ── 스토캐스틱: 숏도 대칭으로 빠져나오는가 ────────────────────

def test_stochastic_exits_a_short_at_the_midline_too():
    """롱만 중심선에서 청산하고 숏은 안 나오면 비대칭이 생긴다."""
    from quant.strategies.stochastic import Stochastic

    # 급등(%D가 과매수 → 숏 진입) 뒤 하락시켜 %D를 중심선 아래로 되돌린다.
    # 숏 청산 조건은 "%D가 50 이하로 복귀"이므로, 내려오는 구간이 있어야
    # 계약을 확인할 수 있다.
    c = np.r_[np.linspace(100, 180, 60), np.linspace(180, 90, 60)]
    out = Stochastic(k_period=14, d_period=3, allow_short=True
                     ).generate_signals(_ohlc(c))
    assert int((out < 0).sum()) > 0, "숏이 한 번도 안 잡혔다 — 검사가 헛돈다"
    assert out.iloc[-1] >= 0.0, (
        f"%D가 중심선 아래로 내려왔는데 숏이 그대로다 — 숏 청산이 "
        f"동작하지 않는다\n  마지막 10봉: {list(out.iloc[-10:])}")
    # 대조군: 롱도 같은 규칙으로 빠져나온다(대칭이어야 한다)
    c2 = np.r_[np.linspace(180, 100, 60), np.linspace(100, 190, 60)]
    lo = Stochastic(k_period=14, d_period=3).generate_signals(_ohlc(c2))
    assert int((lo > 0).sum()) > 0 and lo.iloc[-1] <= 0.0, list(lo.iloc[-6:])


# ── MACD: 성립하지 않는 파라미터를 거절하는가 ─────────────────

def test_macd_rejects_a_fast_that_is_not_faster():
    """fast >= slow면 '빠른 선/느린 선'이라는 규칙 자체가 성립하지 않는다."""
    from quant.strategies.macd import MACD

    with pytest.raises(ValueError):
        MACD(fast=26, slow=26)
    with pytest.raises(ValueError):
        MACD(fast=30, slow=26)
    MACD(fast=12, slow=26)               # 대조군 — 정상 조합은 통과


# ── ADX: 방향성 0인 봉이 며칠을 오염시키지 않는가 ─────────────

def test_adx_does_not_let_a_flat_bar_poison_the_following_window():
    """dx가 NaN이면 뒤따르는 rolling 평균이 period봉 동안 통째로 NaN이 된다.

    그러면 추세강도가 며칠씩 '알 수 없음'이 되고, 게이트는 그 구간을 전부
    막는다 — 실제로는 추세가 있는데도.
    """
    from quant.strategies.adx import adx

    # 완전히 평평한 구간(방향성 0) 뒤에 뚜렷한 추세를 붙인다
    flat_bars = 40
    c = np.r_[np.full(flat_bars, 100.0), np.linspace(100, 160, 60)]
    got = adx(_ohlc(c), period=14)
    assert got.notna().all(), "ADX에 NaN이 남았다 — 게이트가 통째로 닫힌다"

    # 핵심은 '0이 있느냐'가 아니라 **언제 살아나느냐**다. 마지막 fillna(0)이
    # NaN을 0으로 바꿔 주므로 결측은 안 보이지만, 그 0이 rolling 평균을
    # period봉 동안 끌고 간다. 실측: 내부 fillna가 있으면 추세 시작 1봉 뒤
    # 회복, 없으면 14봉 뒤 — 그동안 게이트가 닫혀 추세 초입을 통째로 놓친다.
    first_alive = int(np.argmax(got.to_numpy() > 0))
    delay = first_alive - flat_bars
    assert 0 <= delay <= 3, (
        f"추세가 시작되고 {delay}봉이 지나서야 추세강도가 살아난다 — "
        "평평한 봉의 NaN이 뒤따르는 창을 오염시켰다")
    assert (got.iloc[-20:] > 0).all(), list(got.iloc[-5:])


# ── 공포탐욕: 0~1로 맞추는가 ─────────────────────────────────

def test_fear_greed_is_normalised_to_a_zero_one_scale(monkeypatch):
    """0~100 그대로 나가면 이 피처만 크기가 100배가 된다."""
    import quant.data.sentiment as sm

    idx = pd.date_range("2026-01-01", periods=3, freq="D")
    monkeypatch.setattr(sm, "fear_greed_history",
                        lambda timeout=10.0: pd.Series([0.0, 50.0, 100.0],
                                                       index=idx))
    out = sm.fear_greed_frame()
    assert list(out["fear_greed"]) == [0.0, 0.5, 1.0], (
        f"0~1로 정규화되지 않았다 — {list(out['fear_greed'])}")
    assert out["fear_greed"].max() <= 1.0


def test_an_empty_fear_greed_series_stays_empty(monkeypatch):
    """대조군 — 소스가 죽어도 ML이 기본 피처로 돌 수 있어야 한다."""
    import quant.data.sentiment as sm

    monkeypatch.setattr(sm, "fear_greed_history",
                        lambda timeout=10.0: pd.Series(dtype=float))
    assert sm.fear_greed_frame().empty


# ── 스크리너: 상위 N을 실제로 자르는가 ───────────────────────

def test_the_screener_actually_applies_the_top_n_limit():
    """top_n을 안 넘기면 '선별기'가 아무것도 선별하지 않는다."""
    from quant.portfolio.screener import screen_symbols

    ratios = {
        "AAA": {"pe": 5.0, "pb": 0.5, "roe": 0.30},
        "BBB": {"pe": 8.0, "pb": 0.8, "roe": 0.20},
        "CCC": {"pe": 12.0, "pb": 1.5, "roe": 0.10},
        "DDD": {"pe": 40.0, "pb": 6.0, "roe": 0.01},
    }
    out = screen_symbols(list(ratios), top_n=2, ratios_fn=ratios.get)
    assert len(out["selected"]) == 2, (
        f"상위 2종목만 골라야 하는데 {len(out['selected'])}개가 편입됐다 — "
        f"{out['selected']}")
    # 대조군: 제한이 없으면 더 많이 담긴다
    wide = screen_symbols(list(ratios), ratios_fn=ratios.get)
    assert len(wide["selected"]) > 2


# ── 리포트 차트: 가격선이 실제로 그려지는가 ───────────────────

def test_the_report_price_chart_actually_draws_the_line():
    """매매 마커만 있고 가격선이 비면 '언제 사고팔았는지'가 공중에 뜬다."""
    from quant.reporting.html_report import _price_marker_chart

    c = np.linspace(100, 130, 60)
    df = _ohlc(c)
    pos = pd.Series(0.0, index=df.index)
    pos.iloc[10:30] = 1.0                       # 진입 → 청산 한 번
    out = _price_marker_chart(df, pos)
    assert "polyline" in out and 'points=""' not in out, (
        f"가격 곡선이 비었다 — {out[:200]}")
    assert out.count(",") > 50, "좌표가 거의 없다 — 선이 그려지지 않았다"
    assert "circle" in out, "매매 시점 마커가 없다"


# ── 데이터 계약: 같은 봉이 두 번 들어가지 않는가 ──────────────

def test_a_duplicated_timestamp_is_collapsed_to_one_bar():
    """중복 봉이 남으면 같은 날 수익률이 두 번 계산된다.

    제공자가 재시도·페이지네이션 경계에서 같은 봉을 두 번 주는 일은 흔하다.
    남겨 두면 하루가 두 번 세어져 누적 수익률이 조용히 부풀거나 꺼진다.
    """
    from quant.data.base import DataProvider

    idx = pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-02",
                          "2026-01-03"])
    df = pd.DataFrame({"open": [1, 2, 99, 3], "high": [1, 2, 99, 3],
                       "low": [1, 2, 99, 3], "close": [1, 2, 99, 3],
                       "volume": [10, 10, 10, 10]}, index=idx)
    out = DataProvider._validate(df)
    assert len(out) == 3, f"중복 봉이 남았다 — {list(out.index)}"
    assert out.index.is_unique
    # 마지막 값을 남긴다(재전송이 정정본인 경우가 많다)
    assert float(out.loc["2026-01-02", "close"]) == 99.0


# ── 배치 시각과 시장 마감이 어긋나면 드러나는가 (감사 220) ─────

def test_the_ledger_records_how_stale_each_market_bar_was(monkeypatch, tmp_path):
    """시장별 '판단에 쓴 봉의 나이'가 장부에 남아야 한다.

    배치는 05:30 KST(20:30 UTC)에 돈다. 미국장 마감은
        여름(EDT) 05:00 KST → 30분 여유, 정상
        겨울(EST) 06:00 KST → **장이 아직 열려 있다**

    겨울에는 오늘 봉이 미완성이라 버려지고, 미국 신호만 **한 세션 전** 봉으로
    내려간다. 11월~3월 다섯 달을 그렇게 도는데 어디에도 표시가 없었다 —
    한국·코인은 최신인데 미국만 뒤처지니 종목 간 비교도 어긋난다.

    이건 코드 버그가 아니라 **일정 문제**다. 코드가 할 수 있는 일은 그
    사실을 숨기지 않는 것이다 — 로그만 남기면 아무도 안 보므로 장부에 적는다.
    """
    import datetime as _dt
    import json

    import quant.live.daily as dl
    from quant.live.retrain import save_champions

    class _P:
        def __init__(self, lag):
            self.lag = lag

        def get_ohlcv(self, symbol, tf="1d", limit=500, **k):
            rng = np.random.default_rng(len(symbol) * 13)
            n = 300
            c = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.015, n)))
            end = (pd.Timestamp(_dt.datetime.now(_dt.timezone.utc).date())
                   - pd.Timedelta(days=self.lag))
            ix = pd.date_range(end=end, periods=n, freq="D")
            return pd.DataFrame({"open": c * .99, "high": c * 1.02,
                                 "low": c * .98, "close": c,
                                 "volume": 1e7}, index=ix)

    d = str(tmp_path)
    save_champions({"synthetic:AAA": {"strategy": "ma_cross",
                                      "params": {"fast": 10, "slow": 30},
                                      "promotions": 0}}, d)
    monkeypatch.setattr(dl, "usdkrw", lambda *a, **k: 1400.0)
    monkeypatch.setattr("quant.data.get_provider", lambda m: _P(0))
    dl.run_daily_portfolio([("synthetic", "AAA")], state_dir=d,
                           require_real_data=False)
    rec = json.loads((tmp_path / "paper" / "portfolio_ALL.json")
                     .read_text("utf-8"))["history"][-1]
    assert rec.get("bar_age_days") is not None, (
        "판단 봉의 나이가 장부에 안 남는다 — 배치 시각이 어긋나도 아무도 "
        "모른다")
    assert rec["bar_age_days"].get("synthetic") == 0


def test_a_lagging_market_is_warned_about(monkeypatch, tmp_path, caplog):
    """한 시장만 뒤처지면 **경고가 나가야** 한다 — 조용하면 없는 것과 같다."""
    import datetime as _dt
    import logging

    import quant.live.daily as dl
    from quant.live.retrain import save_champions

    class _P:
        def __init__(self, lag):
            self.lag = lag

        def get_ohlcv(self, symbol, tf="1d", limit=500, **k):
            rng = np.random.default_rng(len(symbol) * 13)
            n = 300
            c = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.015, n)))
            end = (pd.Timestamp(_dt.datetime.now(_dt.timezone.utc).date())
                   - pd.Timedelta(days=self.lag))
            ix = pd.date_range(end=end, periods=n, freq="D")
            return pd.DataFrame({"open": c * .99, "high": c * 1.02,
                                 "low": c * .98, "close": c,
                                 "volume": 1e7}, index=ix)

    # 코인은 최신, 미국은 3일 묵은 봉 — 겨울 배치의 축소판
    def _prov(market):
        return _P(0) if market == "crypto" else _P(3)

    d = str(tmp_path)
    save_champions({k: {"strategy": "ma_cross",
                        "params": {"fast": 10, "slow": 30}, "promotions": 0}
                    for k in ("crypto:AAA", "us_stock:BBB")}, d)
    monkeypatch.setattr(dl, "usdkrw", lambda *a, **k: 1400.0)
    monkeypatch.setattr("quant.data.get_provider", _prov)

    logger = logging.getLogger("quant")
    handler = caplog.handler          # 이 저장소의 로거는 propagate=False다
    logger.addHandler(handler)
    try:
        with caplog.at_level(logging.WARNING):
            dl.run_daily_portfolio([("crypto", "AAA"), ("us_stock", "BBB")],
                                   state_dir=d, require_real_data=False)
    finally:
        logger.removeHandler(handler)

    assert any("신선도가 어긋납니다" in r.getMessage() for r in caplog.records), (
        "한 시장만 3일 뒤처졌는데 경고가 없다\n"
        + "\n".join(r.getMessage()[:100] for r in caplog.records[-5:]))


# ── 실계좌에서 재현할 수 없는 보유는 밝히는가 (감사 222) ───────

def test_a_fractional_korean_lot_is_disclosed(monkeypatch, tmp_path):
    """한국 주식은 소수점 매매가 없다 — 소수 주 보유는 재현 불가다.

    참고 계좌는 1만원으로 시작하는데 한국 주식은 1주가 10만~150만원이라,
    실측 3개 계좌가 전부 소수 주를 들고 있었다:

        LG화학    0.002475주 @ 275,500원
        KODEX200  0.005396주 @ 103,250원
        KB금융    0.012305주 @ 166,000원

    정수 주를 강제하면 대부분 영영 빈 계좌가 되어 **종목별 비교 자체가
    사라진다.** 그래서 막지 않고 밝힌다 — 통합 계좌의 `lot_infeasible`과
    같은 태도다. 숨기는 것과 못 하는 것은 다르다.
    """
    import datetime as _dt
    import json

    import quant.live.daily as dl

    class _P:
        """두 번째 호출은 하루 더 뻗은 프레임 — 주식은 '다음 세션 시가'
        체결이라, 끝 날짜가 같으면 대기 주문이 영영 안 채워진다."""

        def __init__(self):
            self.calls = 0

        def get_ohlcv(self, symbol, tf="1d", limit=500, **k):
            rng = np.random.default_rng(5)
            n = 300 + self.calls
            self.calls += 1
            c = 200_000 * np.exp(np.cumsum(rng.normal(0.0008, 0.015, n)))
            end = (pd.Timestamp(_dt.datetime.now(_dt.timezone.utc).date())
                   + pd.Timedelta(days=self.calls - 1))
            ix = pd.date_range(end=end, periods=n, freq="D")
            return pd.DataFrame({"open": c * .99, "high": c * 1.02,
                                 "low": c * .98, "close": c,
                                 "volume": 1e7}, index=ix)

    class _Buy:
        name, allow_short = "fixed", False

        def generate_signals(self, df):
            return pd.Series(0.9, index=df.index)

    _prov = _P()
    monkeypatch.setattr("quant.data.get_provider", lambda m: _prov)
    monkeypatch.setattr(dl, "champion_strategy", lambda *a, **k: _Buy())
    monkeypatch.setattr(dl, "champion_spec",
                        lambda *a, **k: {"strategy": "fixed", "params": {}})

    d = str(tmp_path)
    # 1만원 계좌가 20만원짜리 주식을 산다 → 반드시 소수 주가 된다.
    # 주식은 다음 시가 체결이라 두 번 돌려야 보유가 생긴다.
    for _ in range(2):
        p = tmp_path / "paper" / "kr_stock_TEST.json"
        if p.exists():
            st = json.loads(p.read_text("utf-8"))
            st["last_bar"] = "1999-01-01"
            p.write_text(json.dumps(st), encoding="utf-8")
        dl.run_daily_paper("kr_stock", "TEST", state_dir=d,
                           require_real_data=False)

    st = json.loads((tmp_path / "paper" / "kr_stock_TEST.json").read_text("utf-8"))
    qty = float(st.get("quantity") or 0)
    assert qty > 0, "보유가 안 생겼다 — 검사가 헛돈다"
    assert abs(qty - round(qty)) > 1e-9, f"소수 주가 아니다({qty})"
    assert st["history"][-1]["fractional_lot"] is True, (
        "실계좌에서 재현할 수 없는 보유인데 장부가 말하지 않는다")


def test_a_crypto_fraction_is_not_flagged(monkeypatch, tmp_path):
    """대조군 — 코인·미국 주식은 소수점 매매가 정상이다. 여기까지 경고하면
    경고가 의미를 잃는다."""
    import datetime as _dt
    import json

    import quant.live.daily as dl

    class _P:
        def get_ohlcv(self, symbol, tf="1d", limit=500, **k):
            rng = np.random.default_rng(5)
            n = 300
            c = 60_000 * np.exp(np.cumsum(rng.normal(0.0008, 0.02, n)))
            end = pd.Timestamp(_dt.datetime.now(_dt.timezone.utc).date())
            ix = pd.date_range(end=end, periods=n, freq="D")
            return pd.DataFrame({"open": c * .99, "high": c * 1.02,
                                 "low": c * .98, "close": c,
                                 "volume": 1e7}, index=ix)

    class _Buy:
        name, allow_short = "fixed", False

        def generate_signals(self, df):
            return pd.Series(0.9, index=df.index)

    monkeypatch.setattr("quant.data.get_provider", lambda m: _P())
    monkeypatch.setattr(dl, "champion_strategy", lambda *a, **k: _Buy())
    monkeypatch.setattr(dl, "champion_spec",
                        lambda *a, **k: {"strategy": "fixed", "params": {}})
    dl.run_daily_paper("crypto", "BTC/USDT", state_dir=str(tmp_path),
                       require_real_data=False)
    st = json.loads((tmp_path / "paper" / "crypto_BTC_USDT.json")
                    .read_text("utf-8"))
    assert float(st["quantity"]) > 0 and float(st["quantity"]) < 1
    assert st["history"][-1]["fractional_lot"] is False, (
        "코인 소수 보유까지 경고하면 경고가 의미를 잃는다")


def test_the_site_shows_the_fractional_warning():
    html = (ROOT / "docs" / "index.html").read_text("utf-8")
    assert "fractional_lot" in html, "사이트가 재현 불가 보유를 읽지 않는다"
    assert "소수 주" in html and "재현할 수 없습니다" in html
