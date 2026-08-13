"""조종석이 사이트와 **같은 사실**을 말하는가 (감사 223·224).

조종석(`quant/web/app.py`)은 사이트와 **같은 장부를 각자 읽는 두 번째
화면**이다. 그래서 사이트에서 고친 결함이 여기 그대로 남아 있기 쉽다 —
감사 197도 "조종석과 감시 탭이 각자 계산해서" 났던 건이다.

오늘 사이트에서 고친 두 결함을 조종석에서 다시 찾았다:

  · 감사 223 — 실제 보유 옆에 **오늘의 결정**을 "비중"이라 붙였다.
        us_stock:META → "매수 보유 · 비중 0%"   (실제로 1.77주 보유)
    보유가 있다면서 비중은 0이라는, 그 자체로 모순인 문장이다.

  · 감사 224 — 낙폭 차트를 **원자산**으로 그렸다. 입금이 고점을 끌어올려
    그 직전 손실이 그림에서 사라진다. 실측(80,000 → -5% → 92만원 입금):
        원자산 낙폭   :  0.00%  ← 입금이 '회복'으로 보인다
        성장지수 낙폭 : -0.94%  ← 실제로는 아직 물려 있다
    감사 197에서 KPI는 고쳤는데 차트 오버레이가 남아 있었다.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
APP = (ROOT / "quant" / "web" / "app.py").read_text("utf-8")


# ── 감사 223: 보유와 결정을 구분하는가 ────────────────────────

def _symbol_ledger(tmp_path, *, held_weight=None, weight=0.0,
                   qty=1.7714, price=578.85, equity=9987.5):
    """실제 장부 한 벌 — 조종석이 읽는 그 파일."""
    import json

    (tmp_path / "paper").mkdir(exist_ok=True)
    rec = {"date": "2026-08-12", "price": price, "equity": equity,
           "weight": weight, "return_pct": -0.12}
    if held_weight is not None:
        rec["held_weight"] = held_weight
    (tmp_path / "paper" / "us_stock_META.json").write_text(json.dumps({
        "market": "us_stock", "symbol": "META", "quantity": qty,
        "avg_price": 601.1, "cash": 100.0, "history": [rec]}),
        encoding="utf-8")


def _position(tmp_path, monkeypatch):
    """조종석의 종목 패널 payload를 **실제로 만들어** 본다."""
    import json

    import pandas as pd

    import quant.web.app as app

    class _P:
        def get_ohlcv(self, symbol, tf="1m", limit=90, **k):
            ix = pd.date_range("2026-08-12", periods=5, freq="min")
            return pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0,
                                 "close": 1.0, "volume": 1.0}, index=ix)

    monkeypatch.setattr("quant.data.get_provider", lambda m: _P())
    monkeypatch.setattr(app, "_CANDLE_CACHE", {})
    out = json.loads(app.candles_json("us_stock:META", "1m",
                                      state_dir=str(tmp_path)))
    return out["position"]


def test_the_position_panel_shows_the_holding_not_the_plan(tmp_path,
                                                           monkeypatch):
    """"매수 보유 · 비중 0%"는 그 자체로 모순이다.

    실측: us_stock:META가 1.7714주를 들고 있는데 화면은 "비중 0%"였다.
    기록의 `weight`가 **오늘의 결정**(전량 매도 예정)이기 때문이다.
    """
    _symbol_ledger(tmp_path, held_weight=0.1027, weight=0.0)
    pos = _position(tmp_path, monkeypatch)
    assert pos is not None, "보유가 있는데 패널이 비었다"
    assert pos["weight"] == 0.1027, (
        f"화면이 보유(10.27%) 대신 오늘의 결정을 보여준다 — {pos}")
    assert pos["plan"] == 0.0, "오늘의 결정을 따로 담지 않는다"
    assert "예정" in APP, "결정이 다를 때 그 사실을 말하지 않는다"


def test_an_old_record_is_counted_not_guessed(tmp_path, monkeypatch):
    """옛 기록에는 held_weight가 없다 — 짐작하지 말고 그 기록으로 센다.

    수량·가격·자산이 전부 그 기록에 있다. '모름'으로 두는 것은 있는 정보를
    버리는 것이고, 임의로 채우는 것은 지어내는 것이다. 세는 것이 맞다.
    """
    _symbol_ledger(tmp_path, held_weight=None, weight=0.0,
                   qty=1.7714, price=578.85, equity=9987.5)
    pos = _position(tmp_path, monkeypatch)
    expected = round(1.7714 * 578.85 / 9987.5, 4)
    assert pos["weight"] == expected, (
        f"옛 기록의 보유 비중을 세지 않았다 — 기대 {expected}, 실제 "
        f"{pos['weight']}")
    assert expected > 0.1, "전제 확인 — 실제로 10% 넘게 들고 있다"


def test_the_kpi_tile_is_honest_about_being_a_target():
    """대조군 — '현재 목표비중' 타일은 원래부터 정직했다. 흐리면 안 된다."""
    dash = (ROOT / "quant" / "reporting" / "dashboard.py").read_text("utf-8")
    assert "현재 목표비중" in dash, (
        "목표비중 타일의 라벨이 흐려졌다 — 목표를 '비중'이라 부르면 감사 "
        "217·223이 되돌아온다")


# ── 감사 224: 낙폭을 입금 제거 지수로 재는가 ──────────────────

def test_the_broadcast_payload_carries_the_deposit_free_index(tmp_path):
    """방송 payload를 **실제로 만들어** 성장 지수가 들어가는지 본다."""
    import json

    import quant.web.app as app

    (tmp_path / "paper").mkdir()
    (tmp_path / "paper" / "portfolio_ALL.json").write_text(json.dumps({
        "market": "portfolio", "symbol": "ALL", "currency": "KRW",
        "start_cash": 80_000.0, "cash": 0.0, "positions": {},
        "deposits": [{"date": "2026-08-13", "amount": 920_000.0,
                      "settled_bar": "2026-08-13"}],
        "history": [{"date": "2026-08-11", "equity": 80_000.0},
                    {"date": "2026-08-12", "equity": 76_000.0},
                    {"date": "2026-08-13", "equity": 999_250.0}]}),
        encoding="utf-8")

    d = json.loads(app.broadcast_json(str(tmp_path), with_live=False))
    pf = next(a for a in d["accounts"] if a["key"].startswith("portfolio:"))
    idx = pf.get("spark_twr")
    assert idx, "입금 제거 성장 지수가 payload에 없다 — 낙폭 차트가 원자산으로 돈다"
    assert len(idx) == 3
    # 92만원이 들어왔는데 지수는 뛰지 않아야 한다(입금은 실력이 아니다)
    assert idx[-1] < 1.0, f"입금이 성장으로 잡혔다 — 지수 {idx[-1]}"


def test_the_drawdown_overlay_uses_the_deposit_free_index():
    """원자산으로 그리면 입금이 고점을 끌어올려 손실이 지워진다."""
    assert "spark_twr" in APP, (
        "조종석이 입금 제거 성장 지수를 만들지 않는다")
    # 낙폭을 그리는 자리가 둘이다 — **둘 다** 지수를 써야 한다
    assert APP.count("o.twr&&o.twr.length===v.length") == 2, (
        "낙폭 차트 두 곳 중 한 곳만 고쳤다 — 나머지가 계속 거짓말을 한다")
    assert "twr:hero.spark_twr" in APP, "차트에 지수를 넘기지 않는다"


def test_nobody_computes_the_drawdown_from_raw_equity_anymore():
    """`peak = max(peak, x)`를 원자산 위에서 돌리는 자리가 남으면 안 된다."""
    import re

    bad = []
    for m in re.finditer(r"let peak=(\w+)\[0\]", APP):
        src = m.group(1)
        if src != "dv":
            line = APP[:m.start()].count("\n") + 1
            bad.append(f"app.py:{line} — peak={src}[0]")
    assert not bad, (
        "낙폭을 원자산에서 재는 자리가 있다 — 입금이 고점을 끌어올려 그 "
        "직전 손실이 그림에서 사라진다:\n  " + "\n  ".join(bad))


def test_the_deposit_does_not_erase_the_drawdown():
    """실측 재현 — 입금일에 낙폭이 0으로 '회복'되면 안 된다."""
    from quant.live.ledger_basics import twr_index

    equity = [80_000.0, 76_000.0, 79_250.0, 999_250.0]   # -5% 뒤 92만원 입금
    hist = [{"date": f"2026-08-{10 + i}", "equity": e}
            for i, e in enumerate(equity)]
    deps = [{"date": "2026-08-13", "amount": 920_000.0,
             "settled_bar": "2026-08-13"}]

    def _dd(series):
        peak, out = series[0], []
        for x in series:
            peak = max(peak, x)
            out.append(x / peak - 1 if peak else 0.0)
        return out

    raw = _dd(equity)
    adjusted = _dd(twr_index(hist, deps, start_cash=80_000.0))
    assert abs(raw[-1]) < 1e-9, "전제가 바뀌었다 — 원자산 낙폭이 0이 아니다"
    assert adjusted[-1] < -0.005, (
        f"성장 지수 낙폭도 0이다({adjusted[-1]:.4f}) — 입금이 손실을 지운다")
    # 대조군: 입금 없는 구간은 두 방식이 같아야 한다
    assert abs(raw[1] - adjusted[1]) < 1e-6, (raw[1], adjusted[1])


def test_a_symbol_chart_without_deposits_is_unchanged():
    """대조군 — 종목 계좌엔 입금이 없다. 거기까지 바뀌면 과한 변경이다."""
    from quant.live.ledger_basics import twr_index

    equity = [10_000.0, 10_500.0, 9_800.0]
    hist = [{"date": f"2026-08-{10 + i}", "equity": e}
            for i, e in enumerate(equity)]
    idx = twr_index(hist, [], start_cash=10_000.0)
    ratio = [e / equity[0] for e in equity]
    for a, b in zip(idx, ratio):
        assert abs(a - b) < 1e-9, (idx, ratio)
