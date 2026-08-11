"""합성 폴백 데이터로는 절대 매매하지 않는다 (감사 85).

거래소 API가 전부 실패하면 `CryptoDataProvider._fallback`이 **GBM 난수 걷기**를
돌려준다. 시작가 100.0짜리 완전한 가짜 시세다. 진짜 시세가 아니라는 표식으로
`df.attrs["synthetic_fallback"] = True`가 붙는다.

`daily.py`(새벽 배치)는 이 표식을 보고 매매를 거부한다 — 사이트가 "실데이터로만
판단한다"고 말하는 근거다. 그런데 **연속 실행 루프(LiveTrader·MultiTrader)와
웹훅은 이 표식을 읽지 않았다.**

결과가 어떤지 보자. 실제 BTC가 6천만 원인데 폴백 시세는 100이다. 주문 수량은
`비중 × 자산 ÷ 가격`이므로 **60만 배** 틀린다. `quant live --real`은 그 수량을
진짜 거래소에 낸다.

이건 '조금 나쁜 데이터로 매매한다'가 아니라 **존재하지 않는 시장에 대고
매매한다**는 뜻이다. 오늘 찾은 것 중 가장 심각하다.

⚠️ 표식은 **실패한 실조회**에만 붙는다. 사용자가 일부러 고른 합성 시장
   (`--market synthetic`)에는 붙지 않으므로, 막아도 그쪽은 정상 동작한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.engine import LiveTrader          # noqa: E402
from quant.live.multi import MultiTrader          # noqa: E402


def _bars(n=60, px=100.0, synthetic=False, seed=5):
    import numpy as np
    rng = np.random.default_rng(seed)
    close = px * np.cumprod(1 + rng.normal(0.0005, 0.01, n))
    idx = pd.date_range("2026-01-01", periods=n, freq="h")
    df = pd.DataFrame({"open": close, "high": close * 1.001,
                       "low": close * 0.999, "close": close,
                       "volume": [1000.0] * n}, index=idx)
    if synthetic:
        df.attrs["synthetic_fallback"] = True     # 실조회 실패 → 가짜 시세
    return df


class _Data:
    def __init__(self, synthetic=False):
        self.synthetic = synthetic

    def get_ohlcv(self, symbol="X", *_a, **_k):
        return _bars(synthetic=self.synthetic,
                     seed=abs(hash(symbol)) % 997)


class _Strat:
    name = "fixed"
    allow_short = False

    def generate_signals(self, df):
        return pd.Series(1.0, index=df.index)


class _Risk:
    def size_positions(self, df, target):
        return target


class _Pos:
    def __init__(self, s, q=0.0):
        self.symbol, self.quantity, self.avg_price = s, q, 0.0


class _Broker:
    def __init__(self):
        self.orders: list[tuple[str, float]] = []
        self.order_log: list = []

    def equity(self, _p=None):
        return 10_000.0

    def get_cash(self):
        return 10_000.0

    def get_position(self, s):
        return _Pos(s)

    def target_weight(self, symbol, weight, *_a, **_k):
        self.orders.append((symbol, float(weight)))
        return None


# ── 단일 종목 루프 ──────────────────────────────────────────────

def test_single_loop_refuses_synthetic_fallback():
    """quant live --real 이 가짜 시세로 주문을 내면 안 된다."""
    b = _Broker()
    LiveTrader(data=_Data(synthetic=True), strategy=_Strat(), broker=b,
               risk=_Risk(), symbol="BTC/USDT").step()
    assert b.orders == [], (
        "거래소 조회가 전부 실패해 합성 시세가 왔는데 주문을 냈다 — "
        "존재하지 않는 시장에 대고 매매한 것이다")


def test_single_loop_still_trades_on_real_data():
    """반대로 진짜 데이터까지 막으면 기능이 죽는다."""
    b = _Broker()
    LiveTrader(data=_Data(synthetic=False), strategy=_Strat(), broker=b,
               risk=_Risk(), symbol="BTC/USDT").step()
    assert b.orders, "진짜 데이터인데 주문이 막혔다"


# ── 다종목 루프 ─────────────────────────────────────────────────

def test_multi_loop_refuses_synthetic_fallback(tmp_path):
    b = _Broker()
    MultiTrader(data=_Data(synthetic=True), strategy=_Strat(), broker=b,
                symbols=["BTC/USDT", "ETH/USDT"],
                state_path=str(tmp_path / "s.json")).step()
    assert b.orders == [], "다종목 루프가 합성 시세로 주문을 냈다"


def test_multi_loop_still_trades_on_real_data(tmp_path):
    b = _Broker()
    MultiTrader(data=_Data(synthetic=False), strategy=_Strat(), broker=b,
                symbols=["BTC/USDT", "ETH/USDT"],
                state_path=str(tmp_path / "s.json")).step()
    assert b.orders, "진짜 데이터인데 다종목 주문이 막혔다"


def test_multi_loop_drops_only_the_bad_symbol(tmp_path):
    """한 종목만 폴백이면 그 종목만 빠지고 나머지는 정상 매매한다."""

    class _Mixed(_Data):
        def get_ohlcv(self, symbol="X", *_a, **_k):
            return _bars(synthetic=(symbol == "ETH/USDT"),
                         seed=abs(hash(symbol)) % 997)

    b = _Broker()
    MultiTrader(data=_Mixed(), strategy=_Strat(), broker=b,
                symbols=["BTC/USDT", "ETH/USDT"],
                state_path=str(tmp_path / "s.json")).step()
    ordered = {s for s, _w in b.orders}
    assert "ETH/USDT" not in ordered, "합성 시세 종목에 주문이 나갔다"
    assert "BTC/USDT" in ordered, "멀쩡한 종목까지 막혔다"


# ── 표식의 의미가 뒤집히지 않았는가 ────────────────────────────

def test_the_marker_only_marks_failed_real_fetches():
    """일부러 고른 합성 시장(--market synthetic)은 막히면 안 된다.

    표식을 SyntheticDataProvider 자신이 달면 그 시장이 통째로 죽는다.
    """
    from quant.data.synthetic import SyntheticDataProvider
    df = SyntheticDataProvider().get_ohlcv("BTC/USDT", "1d", limit=30)
    assert not df.attrs.get("synthetic_fallback"), (
        "합성 제공자가 스스로 폴백 표식을 달았다 — 합성 시장이 통째로 막힌다")


def test_the_crypto_fallback_does_mark_itself():
    """반대로 폴백 경로가 표식을 빠뜨리면 이 방어가 통째로 무의미해진다."""
    from quant.data.crypto import CryptoDataProvider
    df = CryptoDataProvider._fallback("BTC/USDT", "1h", None, None, 30)
    assert df.attrs.get("synthetic_fallback") is True


# ── 웹훅 시세 조회 경로 ─────────────────────────────────────────
#
# 웹훅은 페이로드에 price가 없으면 시세를 조회해 그 값으로 주문 수량을
# 정한다. 그 조회가 합성 폴백을 돌려주면 가짜 가격으로 실주문이 나간다.

class _Provider:
    def __init__(self, synthetic=False, empty=False, boom=False):
        self.synthetic, self.empty, self.boom = synthetic, empty, boom

    def get_ohlcv(self, symbol, *_a, **_k):
        if self.boom:
            raise RuntimeError("네트워크 실패(모의)")
        if self.empty:
            return pd.DataFrame()
        return _bars(synthetic=self.synthetic)


def test_price_lookup_refuses_synthetic_data():
    from quant.data.guard import last_real_price
    assert last_real_price(_Provider(synthetic=True), "BTC/USDT") == 0.0, (
        "합성 폴백 가격을 그대로 돌려줬다 — 그 값으로 주문 수량이 정해진다")


def test_price_lookup_returns_a_real_price():
    from quant.data.guard import last_real_price
    assert last_real_price(_Provider(), "BTC/USDT") > 0.0


def test_price_lookup_survives_a_broken_provider():
    from quant.data.guard import last_real_price
    assert last_real_price(_Provider(boom=True), "BTC/USDT") == 0.0
    assert last_real_price(_Provider(empty=True), "BTC/USDT") == 0.0


def test_zero_price_makes_the_webhook_refuse_the_order():
    """0.0이 실제로 주문 거부로 이어지는가 — 배선까지 확인한다."""
    from quant.live.webhook import WebhookExecutor
    b = _Broker()
    ex = WebhookExecutor(b, price_fn=lambda _s: 0.0)
    res = ex.execute({"symbol": "BTC/USDT", "action": "buy", "weight": 1.0})
    assert b.orders == [], "현재가를 못 얻었는데 주문이 나갔다"
    assert res.get("ok") is False and "현재가" in str(res.get("error"))


def test_the_webhook_cli_uses_the_guarded_lookup():
    """CLI가 가드 없는 조회로 되돌아가면 막는다."""
    src = (ROOT / "quant" / "cli.py").read_text(encoding="utf-8")
    block = src.split("def price_fn")[1].split("\n\n")[0]
    assert "last_real_price" in block, "웹훅이 가드 없는 시세 조회로 되돌아갔다"
