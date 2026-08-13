"""데이터 장애가 **손실을 지워서는 안 된다** (감사 152).

포트폴리오 배치는 종목별로 시세를 받고, 실패한 종목은 `prices`에서 빠진다
(그 사실은 `skipped`에 남는다 — 거기까진 정직하다). 그런데 **포지션은 상태
파일에서 그대로 복원된다.** 그리고 자산을 이렇게 계산했다.

    equity = broker.equity(prices)          # ← 실패한 종목이 없는 dict

`PaperBroker.equity`는 marks에 없는 종목을 **매입가**로 평가한다. 즉
"산 뒤로 한 푼도 안 움직였다"고 친다.

그 자산 숫자가 어디로 가는가.

    · 장부의 자산·수익률
    · 킬스위치가 읽는 낙폭(twr_index)
    · 사이트에 나가는 TWR

그래서 **폭락한 종목이 하필 그날 데이터 장애를 만나면 손실이 장부에서
사라지고, 브레이크도 안 걸린다.** 두 사건이 같이 일어날 이유도 충분하다 —
거래정지·상장폐지·거래소 장애는 급락과 함께 온다.

고침: 마지막으로 알던 시장가로 평가하고, 그렇게 평가한 종목을 장부
(`stale_marks`)에 남긴다. 그 값도 틀렸지만 '손실 0'보다 훨씬 덜 틀리고
무엇보다 **틀렸다는 사실이 보인다.**
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.broker import PaperBroker  # noqa: E402
from quant.broker.base import Position  # noqa: E402


def _book(qty: float = 10.0, avg: float = 100.0) -> PaperBroker:
    b = PaperBroker(cash=0.0)
    b._positions["kr_stock:A"] = Position("kr_stock:A", qty, avg)
    return b


# ── 함정 자체를 못 박는다 ─────────────────────────────────────


def test_a_missing_mark_is_valued_at_cost_which_hides_the_loss():
    """이것이 함정이다 — 고친 게 아니라 **성질을 기록**하는 검사다.

    marks가 비면 매입가(100)로 평가돼 손실이 0이 된다. 이 성질 자체는
    PaperBroker의 계약이므로 그대로 두되, 호출자가 반드시 채워야 한다는
    사실을 여기 못 박는다. 이 값이 바뀌면 호출자 쪽 전제도 다시 봐야 한다.
    """
    assert _book().equity({}) == 1000.0, (
        "marks 없이 부른 equity가 매입가 평가가 아니다 — 호출자 전제가 바뀐다")
    assert _book().equity({"kr_stock:A": 40.0}) == 400.0


def test_the_docstring_warns_about_it():
    """계약을 아는 사람만 안전한 함수라면, 계약이 코드 옆에 있어야 한다."""
    src = (ROOT / "quant" / "broker" / "paper.py").read_text("utf-8")
    body = src.split("def equity")[1].split("def market_order")[0]
    assert "매입가" in body and "감사 152" in body, (
        "equity의 기본값이 위험하다는 경고가 사라졌다")


# ── 배치가 그 함정을 밟지 않는가 ──────────────────────────────


def _run_with_outage(tmp_path, monkeypatch, crashed_to: float | None):
    """A는 시세를 못 받고 B만 받는 하루를 돌린다.

    crashed_to: A의 어제 종가(=last_price). None이면 상태에 last_price가
    없던 옛 장부를 흉내 낸다.
    """
    import numpy as np
    import pandas as pd

    import quant.data as qd
    import quant.live.daily as D
    import quant.utils.settings as us

    idx = pd.date_range("2025-01-01", periods=300, freq="D")
    rng = np.random.default_rng(0)
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.001, 0.01, len(idx))))
    good = pd.DataFrame({"open": close, "high": close * 1.01,
                         "low": close * 0.99, "close": close,
                         "volume": 1e6}, index=idx)

    class _P:
        def get_ohlcv(self, symbol, *a, **k):
            if symbol == "AAA":                 # A만 데이터 장애
                raise RuntimeError("실데이터 수신 실패")
            return good.copy()

    monkeypatch.setattr(qd, "get_provider", lambda *a, **k: _P())
    monkeypatch.setattr("quant.data.krx.attach_krx_flows", lambda d, s: d)
    monkeypatch.setattr("quant.data.crossasset.attach_cross_asset",
                        lambda d, m, s, **k: d)
    monkeypatch.setattr(us, "load_settings", lambda *a, **k: {
        "trading_paused": False, "exposure_scale": 1.0, "social_post": False,
        "note": "", "portfolio_target_vol": None})

    pos = {"quantity": 10.0, "avg_price": 100.0}
    if crashed_to is not None:
        pos["last_price"] = crashed_to
        pos["last_price_bar"] = "2025-10-25"
    state = {"cash": 0.0, "positions": {"kr_stock:AAA": pos},
             "base_prices": {}, "history": [], "start_cash": 1000.0,
             "currency": "KRW",
             "last_bar": None}
    import json
    # 상태 파일은 state_dir/paper/<state_file>에 있다.
    path = tmp_path / "paper" / "portfolio.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state), encoding="utf-8")

    return D.run_daily_portfolio(
        targets=[("kr_stock", "AAA"), ("kr_stock", "BBB")],
        state_dir=str(tmp_path), state_file="portfolio.json")


def test_a_crashed_symbol_keeps_its_loss_through_an_outage(tmp_path,
                                                           monkeypatch):
    """A가 100 → 20으로 폭락한 뒤 데이터 장애. 손실이 남아 있어야 한다."""
    rec = _run_with_outage(tmp_path, monkeypatch, crashed_to=20.0)
    assert rec and not rec.get("skipped"), rec
    assert rec["stale_marks"], (
        "시세를 못 받은 보유 종목이 있는데 stale_marks가 비었다 — "
        "장부가 '정상 평가'라고 말한다")
    assert rec["stale_marks"]["kr_stock:AAA"]["price"] == 20.0
    # 10주 × 20 = 200. 매입가로 평가했다면 1,000이 된다.
    assert rec["equity"] < 400.0, (
        f"자산 {rec['equity']:,.0f} — 폭락한 종목이 매입가(10주×100=1,000)로 "
        "평가되고 있다. 손실이 장부에서 사라졌다")


def test_the_ledger_says_which_prices_were_stale(tmp_path, monkeypatch):
    """'틀린 값'을 쓰는 건 괜찮다 — 틀렸다는 사실을 감추는 게 문제다."""
    rec = _run_with_outage(tmp_path, monkeypatch, crashed_to=20.0)
    row = rec["stale_marks"]["kr_stock:AAA"]
    assert row["as_of"] == "2025-10-25", (
        f"언제 시세인지가 없다 — 하루 전인지 한 달 전인지 알 수 없다: {row}")


def test_a_normal_day_records_no_stale_marks(tmp_path, monkeypatch):
    """대조군 — 평시에 stale_marks가 차 있으면 경보가 매일 울려 무의미해진다."""
    import quant.data as qd
    import quant.live.daily as D
    import quant.utils.settings as us

    import numpy as np
    import pandas as pd

    idx = pd.date_range("2025-01-01", periods=300, freq="D")
    rng = np.random.default_rng(0)
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.001, 0.01, len(idx))))
    good = pd.DataFrame({"open": close, "high": close * 1.01,
                         "low": close * 0.99, "close": close,
                         "volume": 1e6}, index=idx)

    class _P:
        def get_ohlcv(self, *a, **k):
            return good.copy()

    monkeypatch.setattr(qd, "get_provider", lambda *a, **k: _P())
    monkeypatch.setattr("quant.data.krx.attach_krx_flows", lambda d, s: d)
    monkeypatch.setattr("quant.data.crossasset.attach_cross_asset",
                        lambda d, m, s, **k: d)
    monkeypatch.setattr(us, "load_settings", lambda *a, **k: {
        "trading_paused": False, "exposure_scale": 1.0, "social_post": False,
        "note": "", "portfolio_target_vol": None})

    import json
    path = tmp_path / "paper" / "portfolio.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "cash": 1000.0, "positions": {}, "base_prices": {}, "history": [],
        "start_cash": 1000.0, "currency": "KRW",
        "last_bar": None}), encoding="utf-8")
    rec = D.run_daily_portfolio(
        targets=[("kr_stock", "AAA"), ("kr_stock", "BBB")],
        state_dir=str(tmp_path), state_file="portfolio.json")
    assert rec and not rec.get("skipped"), rec
    assert not rec.get("stale_marks"), (
        f"전 종목 시세를 받았는데 stale_marks가 남았다: {rec['stale_marks']}")


def test_yesterdays_price_is_saved_so_tomorrow_can_use_it(tmp_path,
                                                          monkeypatch):
    """이틀을 실제로 돌린다 — 첫날 시세를 남겨야 둘째 날 쓸 수 있다.

    ⚠️ 위 검사들은 `last_price`를 상태에 **미리 심어 두고** 시작한다.
       그래서 '심어 둔 값을 읽는가'만 확인할 뿐, **쓰는 쪽**은 한 번도
       지나가지 않는다. 변이 시험이 그걸 잡아냈다(쓰기를 지워도 통과).
       읽기와 쓰기는 다른 코드다 — 둘 다 지나가야 배선 검사다.
    """
    import json

    import numpy as np
    import pandas as pd

    import quant.data as qd
    import quant.live.daily as D
    import quant.utils.settings as us

    idx = pd.date_range("2025-01-01", periods=301, freq="D")
    rng = np.random.default_rng(0)
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.001, 0.01, len(idx))))
    full = pd.DataFrame({"open": close, "high": close * 1.01,
                         "low": close * 0.99, "close": close,
                         "volume": 1e6}, index=idx)

    state = {"day": 1}

    class _P:
        def get_ohlcv(self, symbol, *a, **k):
            if state["day"] == 2 and symbol == "AAA":
                raise RuntimeError("실데이터 수신 실패")   # 둘째 날만 장애
            return full.iloc[:300].copy() if state["day"] == 1 else full.copy()

    monkeypatch.setattr(qd, "get_provider", lambda *a, **k: _P())
    monkeypatch.setattr("quant.data.krx.attach_krx_flows", lambda d, s: d)
    monkeypatch.setattr("quant.data.crossasset.attach_cross_asset",
                        lambda d, m, s, **k: d)
    monkeypatch.setattr(us, "load_settings", lambda *a, **k: {
        "trading_paused": False, "exposure_scale": 1.0, "social_post": False,
        "note": "", "portfolio_target_vol": None})

    path = tmp_path / "paper" / "portfolio.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "cash": 0.0,
        "positions": {"kr_stock:AAA": {"quantity": 10.0, "avg_price": 100.0}},
        "base_prices": {}, "history": [], "start_cash": 1000.0,
             "currency": "KRW",
        "last_bar": None}), encoding="utf-8")

    kw = dict(targets=[("kr_stock", "AAA"), ("kr_stock", "BBB")],
              state_dir=str(tmp_path), state_file="portfolio.json")
    first = D.run_daily_portfolio(**kw)
    assert first and not first.get("skipped"), first

    saved = json.loads(path.read_text(encoding="utf-8"))
    lp = saved["positions"].get("kr_stock:AAA", {}).get("last_price")
    assert lp, (
        "첫날 시세를 상태에 안 남겼다 — 둘째 날 장애가 나면 매입가로 떨어진다")
    assert abs(float(lp) - float(full["close"].iloc[299])) < 1e-6

    state["day"] = 2
    second = D.run_daily_portfolio(**kw)
    assert second and not second.get("skipped"), second
    assert second["stale_marks"], "둘째 날 장애인데 stale_marks가 비었다"
    assert abs(second["stale_marks"]["kr_stock:AAA"]["price"] - float(lp)) < 1e-6
