"""계좌가 **한 가지 통화로** 말하는가 (감사 212).

무엇이 있었나 — 잔고 표를 만들다 드러났다. 통합 계좌의 자산은
`현금 + Σ(수량 × 가격)`인데, 그 '가격'이 시장마다 다른 통화였다:

    삼성전자   239,500   ← 진짜 원화
    S&P500 ETF    772   ← 달러인데 원화처럼 더해졌다
    비트코인   63,576   ← USDT인데 원화처럼 더해졌다

그래서 장부에 "S&P500 ETF 12.25주 = 9,466원"이 남았다. 실제로 그 12주는
1,300만원어치다. 두 가지가 사실이 아니었다:

  ① 자산 "79,251원"은 진짜 원화 금액이 아니다 — 단위가 섞인 합계다.
  ② **환위험이 통째로 빠져 있었다.** 원화가 10% 절상되면 실제로는 10%를
     잃는데 장부에는 그 손실이 존재하지 않는다.

수익률이 내부적으로는 일관돼서(모든 계산이 같은 왜곡을 겪는다) 오래
드러나지 않았다. 숫자가 서로 맞는다는 것과 사실이라는 것은 다르다.

여기서 지키는 계약:
  · 달러 표시 시장(us_stock·crypto)은 **원화로 환산해서** 체결·평가한다
  · 원화 시장(kr_stock)은 건드리지 않는다 — 환산하면 오히려 틀린다
  · **환율을 모르면 1.0으로 때우지 않는다.** 그게 지금 고치는 그 결함이다
  · 소급 환산은 하지 않는다 — 옛 현금까지 단위가 섞였고, 곱해서 만들어낸
    과거는 기록이 아니라 창작이다
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.data.fx import (  # noqa: E402
    FX_MAX,
    FX_MIN,
    needs_fx,
    to_krw,
    usdkrw,
)
from quant.live import daily as dl  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FX = 1400.0


# ── 어느 시장을 환산하는가 ────────────────────────────────────

def test_dollar_markets_are_converted_and_won_markets_are_not():
    assert needs_fx("us_stock") and needs_fx("crypto")
    assert not needs_fx("kr_stock"), "원화 종목을 또 곱하면 1,470배가 된다"
    assert not needs_fx("upbit"), "업비트는 원화 시세다"
    assert to_krw("us_stock", 772.49, FX) == pytest.approx(772.49 * FX)
    assert to_krw("kr_stock", 239_500.0, FX) == 239_500.0


def test_a_missing_rate_never_becomes_one():
    """환율을 모를 때 1.0을 쓰면 **결함이 그대로 복원된다.**"""
    assert to_krw("us_stock", 772.49, None) is None
    # 원화 종목은 환율이 없어도 값을 매길 수 있다 — 막을 이유가 없다
    assert to_krw("kr_stock", 239_500.0, None) == 239_500.0


def test_an_implausible_rate_is_refused(monkeypatch):
    """계열이 뒤집혀 오면(0.0007) 자산이 100만 배 틀어진다 — 거절한다."""
    def _fake(market, symbol, limit=800, fetch=None):
        return pd.Series([0.00071], index=pd.to_datetime(["2026-08-12"]))

    monkeypatch.setattr("quant.data.crossasset._bench_close", _fake)
    assert usdkrw(refresh=True) is None


def test_a_plausible_rate_is_accepted(monkeypatch):
    """대조군 — 멀쩡한 값까지 거절하면 해외 종목이 영영 안 돈다."""
    def _fake(market, symbol, limit=800, fetch=None):
        return pd.Series([1_412.5], index=pd.to_datetime(["2026-08-12"]))

    monkeypatch.setattr("quant.data.crossasset._bench_close", _fake)
    assert usdkrw(refresh=True) == pytest.approx(1_412.5)
    assert FX_MIN < 1_412.5 < FX_MAX


def test_a_failure_is_not_remembered(monkeypatch):
    """실패를 캐시하면 잠깐의 장애가 프로세스 내내 남는다(`live`는 며칠 돈다)."""
    from quant.data import fx as fxmod

    monkeypatch.setattr(fxmod, "_MEMO", {})      # 앞선 검사의 성공값을 지운다
    calls = {"n": 0}

    def _fail(market, symbol, limit=800, fetch=None):
        calls["n"] += 1
        return None

    monkeypatch.setattr("quant.data.crossasset._bench_close", _fail)
    assert usdkrw() is None
    assert usdkrw() is None
    assert calls["n"] == 2, "실패를 기억해 다시 시도하지 않았다"


# ── 계좌가 실제로 원화로 기록하는가 ────────────────────────────

class _P:
    def __init__(self, df):
        self._df = df

    def get_ohlcv(self, *a, **k):
        return self._df.copy()


class _Buy:
    name, allow_short = "fixed", False

    def generate_signals(self, df):
        return pd.Series(0.9, index=df.index)


def _frame(n=300, seed=7):
    import datetime as _dt
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.02, n)))
    end = pd.Timestamp(_dt.datetime.now(_dt.timezone.utc).date())
    idx = pd.date_range(end=end, periods=n, freq="D")
    return pd.DataFrame({"open": close * 0.99, "high": close * 1.03,
                         "low": close * 0.97, "close": close,
                         "volume": 1e6}, index=idx)


def _run(monkeypatch, tmp_path, market, rate=FX):
    df = _frame()
    monkeypatch.setattr(dl, "usdkrw", lambda *a, **k: rate)
    monkeypatch.setattr("quant.data.get_provider", lambda m: _P(df))
    monkeypatch.setattr(dl, "champion_strategy", lambda *a, **k: _Buy())
    monkeypatch.setattr(dl, "champion_spec",
                        lambda *a, **k: {"strategy": "fixed", "params": {}})
    out = dl.run_daily_portfolio([(market, "AAA")], state_dir=str(tmp_path),
                                 require_real_data=False)
    p = tmp_path / "paper" / "portfolio_ALL.json"
    st = json.loads(p.read_text("utf-8")) if p.exists() else {}
    return df, st, out


def test_a_dollar_symbol_is_booked_in_won(monkeypatch, tmp_path):
    """미국 주식의 값이 **원화**로 적혀야 한다.

    주식은 '다음 세션 시가' 체결이라 첫날에는 보유가 아직 없다. 계좌가
    그날 적어 둔 가격(base_prices)이 곧 체결·평가에 쓰는 값이다.
    """
    df, st, _ = _run(monkeypatch, tmp_path, "us_stock")
    live = float(df["close"].iloc[-1])
    got = st["base_prices"]["us_stock:AAA"]
    assert got == pytest.approx(live * FX), (
        f"가격이 달러 그대로다({got:,.2f}) — 원화 계좌에 달러 금액이 섞인다")


def test_a_won_symbol_is_not_multiplied_again(monkeypatch, tmp_path):
    """대조군 — 한국 주식을 환산하면 1,470배가 된다."""
    df, st, _ = _run(monkeypatch, tmp_path, "kr_stock")
    live = float(df["close"].iloc[-1])
    got = st["base_prices"]["kr_stock:AAA"]
    assert got == pytest.approx(live), (
        "원화 종목에 환율을 곱했다 — 자산이 1,470배로 부풀어 오른다")


def test_a_crypto_symbol_is_booked_in_won(monkeypatch, tmp_path):
    """코인은 즉시 체결이라 보유 단가까지 바로 확인할 수 있다."""
    df, st, _ = _run(monkeypatch, tmp_path, "crypto")
    live = float(df["close"].iloc[-1])
    pos = st["positions"]["crypto:AAA"]
    assert pos["last_price"] == pytest.approx(live * FX), (
        "USDT 가격이 그대로 원화 계좌에 들어갔다")
    assert pos["avg_price"] == pytest.approx(live * FX, rel=0.01)


def test_without_a_rate_the_batch_refuses_rather_than_guessing(
        monkeypatch, tmp_path):
    """환율이 없으면 해외 종목을 **기록하지 않는다** — 1.0으로 때우지 않는다.

    조용한 폴백이 이 저장소에서 반복해 사고를 냈다(감사 102·152·198·205).
    모르면 모른다고 말하고 그날을 건너뛰는 것이 맞다.
    """
    with pytest.raises(RuntimeError, match="전 종목 데이터 실패"):
        _run(monkeypatch, tmp_path, "us_stock", rate=None)
    p = tmp_path / "paper" / "portfolio_ALL.json"
    st = json.loads(p.read_text("utf-8")) if p.exists() else {}
    assert not st.get("history"), "환율 없이 해외 종목을 기록했다"
    assert not st.get("base_prices"), (
        "환율이 없는데 달러 가격을 그대로 원화로 적었다(=1.0 폴백)")


def test_the_won_market_still_runs_without_a_rate(monkeypatch, tmp_path):
    """대조군 — 환율이 없다고 한국 주식까지 멈추면 과잉 차단이다."""
    _, st, out = _run(monkeypatch, tmp_path, "kr_stock", rate=None)
    assert st.get("history"), "원화 종목은 환율과 무관한데 기록이 멈췄다"
    assert not out.get("skipped")


# ── 과거는 소급 환산하지 않는다 ────────────────────────────────

def test_reopening_the_account_keeps_the_old_ledger_untouched(tmp_path):
    """옛 장부는 한 글자도 안 고치고 파일로 남긴다."""
    from quant.live.ledger_basics import redenominate_to_krw

    (tmp_path / "paper").mkdir()
    old = {"market": "portfolio", "symbol": "ALL", "start_cash": 80_000.0,
           "cash": 41_909.59,
           "positions": {"us_stock:SPY": {"quantity": 12.0,
                                          "avg_price": 774.7}},
           "history": [{"date": "2026-08-12", "equity": 79_250.68}],
           "deposits": [{"date": "2026-08-13", "amount": 920_000.0,
                         "memo": ""}]}
    p = tmp_path / "paper" / "portfolio_ALL.json"
    p.write_text(json.dumps(old), encoding="utf-8")

    new = redenominate_to_krw(str(tmp_path), 1_000_000.0, today="2026-08-13")

    kept = json.loads((tmp_path / "paper" / "portfolio_ALL.pre-krw.json")
                      .read_text("utf-8"))
    assert kept == old, "옛 장부가 바뀌었다 — 과거를 고치지 않는다"

    assert new["currency"] == "KRW"
    assert new["start_cash"] == 1_000_000.0 and new["cash"] == 1_000_000.0
    assert new["positions"] == {} and new["history"] == []
    # 왜 새로 열었는지 장부 자신이 말해야 한다
    assert "환산" in new["restarted"]["why"]
    assert new["restarted"]["prior_days"] == 1

    saved = json.loads(p.read_text("utf-8"))
    assert saved["currency"] == "KRW"


def test_the_account_cannot_be_reopened_twice(tmp_path):
    """두 번 돌면 지금 계좌가 통째로 사라진다 — 거절해야 한다."""
    from quant.live.ledger_basics import redenominate_to_krw

    (tmp_path / "paper").mkdir()
    (tmp_path / "paper" / "portfolio_ALL.json").write_text(
        json.dumps({"market": "portfolio", "symbol": "ALL",
                    "start_cash": 80_000.0, "cash": 80_000.0,
                    "positions": {}, "history": []}), encoding="utf-8")
    redenominate_to_krw(str(tmp_path), 1_000_000.0, today="2026-08-13")
    with pytest.raises(RuntimeError, match="이미 원화"):
        redenominate_to_krw(str(tmp_path), 1_000_000.0, today="2026-08-13")


def test_nobody_converts_stored_history_after_the_fact():
    """소급 환산 코드가 생기면 안 된다 — 곱해서 만든 과거는 기록이 아니다."""
    import ast

    src = (ROOT / "quant" / "live" / "ledger_basics.py").read_text("utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "redenominate_to_krw")
    body = ast.unparse(fn)
    assert "history" not in body or '"history": []' in body.replace("'", '"'), (
        "새 계좌가 옛 기록을 옮기거나 환산하고 있다")


# ── 판정 시계가 실제로 리셋되는가 ─────────────────────────────

def test_the_structure_epoch_moved_for_this_change():
    """계좌 통화가 바뀌면 그 전후 수익률은 같은 통계가 아니다."""
    assert dl.STRUCTURE_EPOCH >= "2026-08-13"
    assert "원화" in dl.STRUCTURE_WHY and "환" in dl.STRUCTURE_WHY


# ── 보관본이 산 계좌를 덮어쓰지 않는가 ────────────────────────

def test_the_archived_ledger_never_shows_up_as_the_live_account(tmp_path):
    """보관된 옛 장부가 사이트의 계좌를 **덮어쓰면** 안 된다.

    실측(감사 212를 고치자마자): 장부를 읽는 곳들이 `state/paper/*.json`을
    통째로 훑는데, 보관본 `portfolio_ALL.pre-krw.json`은 안에
    `market: "portfolio"`가 그대로 있고 이름이 알파벳순으로 **뒤**라 같은
    키(`portfolio:ALL`)를 덮어썼다. 새 원화 계좌를 열었는데 사이트는 닫힌
    옛 계좌(7일치·자산 79,251원)를 계속 보여줬다.

    보관본은 안에 "나는 보관본"이라고 적을 수가 없다 — 바이트 복사본이라
    적는 순간 과거를 고치는 것이 된다. 그래서 이름으로 가른다.
    """
    import quant.live.daily as dl
    from quant.live.ledger_basics import is_archive

    assert is_archive("portfolio_ALL.pre-krw.json")
    assert not is_archive("portfolio_ALL.json")
    assert not is_archive("kr_stock_005930.KS.json"), (
        "종목 파일 이름에도 점이 있다 — 점 개수로 가르면 안 된다")

    (tmp_path / "paper").mkdir()
    live = {"market": "portfolio", "symbol": "ALL", "currency": "KRW",
            "start_cash": 1_000_000.0, "cash": 1_000_000.0,
            "positions": {}, "history": [], "deposits": []}
    dead = {"market": "portfolio", "symbol": "ALL",
            "start_cash": 80_000.0, "cash": 41_909.59, "positions": {},
            "history": [{"date": "2026-08-12", "equity": 79_250.68,
                         "return_pct": -0.94, "price": 98.96, "weight": 0.32}],
            "deposits": []}
    (tmp_path / "paper" / "portfolio_ALL.json").write_text(
        json.dumps(live), encoding="utf-8")
    (tmp_path / "paper" / "portfolio_ALL.pre-krw.json").write_text(
        json.dumps(dead), encoding="utf-8")

    pf = dl.write_docs_status(str(tmp_path),
                              docs_path=str(tmp_path / "s.json"))["paper"]["portfolio:ALL"]
    assert pf["start_cash"] == 1_000_000.0, (
        "사이트가 닫힌 옛 계좌를 살아 있는 계좌로 보여준다")
    assert pf["history"] == [], "보관본의 기록이 새 계좌 기록으로 섞였다"


def test_every_reader_of_the_ledger_folder_skips_archives():
    """장부 폴더를 훑는 곳은 전부 보관본을 걸러야 한다(형제 찾기).

    한 곳만 고치면 나머지가 계속 옛 계좌를 보여준다 — 실제로 세 곳이었다.
    """
    import ast

    offenders = []
    for rel in ("quant/live/daily.py", "quant/web/app.py"):
        src = (ROOT / rel).read_text("utf-8")
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.Call):
                continue
            txt = ast.unparse(node)
            if "paper_dir" not in txt:
                continue
            if "listdir" not in txt and "glob" not in txt:
                continue
            # 그 호출을 감싸는 30줄 안에 보관본 거르기가 있어야 한다
            seg = "\n".join(src.splitlines()[max(0, node.lineno - 3):
                                             node.lineno + 12])
            if "is_archive" not in seg:
                offenders.append(f"{rel}:{node.lineno} — {txt[:70]}")
    assert not offenders, (
        "장부 폴더를 훑으면서 보관본을 안 거르는 곳이 있다 — 닫힌 계좌가 "
        "산 계좌를 덮어쓴다:\n  " + "\n  ".join(offenders))
