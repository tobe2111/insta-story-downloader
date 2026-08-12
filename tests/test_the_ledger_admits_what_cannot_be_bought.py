"""예산에 맞게 투자하는가 — 못 사면 미루고, 남은 예산은 재배분 (감사 137).

2026-08-12, 실제 페이퍼 계좌의 보유를 열어 봤다.

    kr_stock:000660 (SK하이닉스)   0.0000주   평가 41원   · 1주 1,443,000원
    kr_stock:005930 (삼성전자)     0.0001주   평가 18원   · 1주   236,000원
    kr_stock:069500 (KODEX 200)    0.0018주   평가 182원  · 1주   100,800원

**국내주식은 소수점 매매가 없다.** 이 줄들은 실계좌에서 단 한 주도 살 수
없는데 장부에는 보유로 적히고 손익에 반영됐다. 8만원으로 가장 싼 종목
1주를 사려면 자산의 126%가 필요하다 — 레버리지 없이는 불가능하다.

운영자 결정: *"금액이 문제면 비싼 건 미루면 되잖아. 예산에 맞게 투자하면
되지."* 그래서 `_fit_to_budget`이

    ① 정수 주 시장은 내림 → ② 1주도 못 사면 미룸 → ③ 남은 예산은 살 수
    있는 종목에 재배분 → ④ 재배분해도 과집중 상한은 안 넘음

을 한다. ③이 핵심이다 — 미룬 예산을 현금으로 놀리면 총노출이 목표보다
낮아져 위험 예산이 샌다.

그리고 이 결과가 **주문과 장부 양쪽의 유일한 출처**다. 예전에는 주문 루프와
기록(_applied)이 같은 식을 따로 적어, 한쪽만 고치면 장부가 실제 주문과 다른
값을 말했다(감사 92가 그 사고였다).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.daily import FRACTIONAL_MARKETS, _fit_to_budget  # noqa: E402


# ── ① 정수 주 내림 ────────────────────────────────────────────


def test_a_korean_stock_is_floored_to_whole_shares():
    # 1,000,000원 계좌 · 25% 배정(250,000원) · 1주 100,800원 → 2주(201,600원)
    out, deferred = _fit_to_budget({"kr_stock:069500.KS": 0.25},
                                   {"kr_stock:069500.KS": 100_800.0},
                                   1_000_000.0)
    assert not deferred, deferred
    assert abs(out["kr_stock:069500.KS"] - 0.2016) < 1e-6, out


def test_fractional_markets_are_untouched():
    """코인·미국주식은 소수점 매매가 되므로 그대로 둔다."""
    assert "kr_stock" not in FRACTIONAL_MARKETS
    t = {"crypto:BTC/USDT": 0.3, "us_stock:AAPL": 0.2}
    out, deferred = _fit_to_budget(dict(t), {"crypto:BTC/USDT": 63_656.0,
                                             "us_stock:AAPL": 306.0},
                                   1_000_000.0)
    assert out == t and not deferred


# ── ② 못 사면 미룬다 ──────────────────────────────────────────


def test_what_cannot_be_bought_is_deferred_not_faked():
    """1주 값이 배정금액보다 크면 0으로 두고, 왜인지 남긴다."""
    out, deferred = _fit_to_budget({"kr_stock:000660.KS": 0.05},
                                   {"kr_stock:000660.KS": 1_443_000.0},
                                   1_000_000.0)      # 배정 5만원 / 1주 144만원
    assert out["kr_stock:000660.KS"] == 0.0, "못 사는데 보유로 적었다"
    row = deferred["kr_stock:000660.KS"]
    assert row["budget"] == 50_000.0 and row["price"] == 1_443_000.0, row


# ── ③ 남은 예산은 재배분 ──────────────────────────────────────


def test_the_freed_budget_goes_to_what_can_be_bought():
    """미룬 예산이 현금으로 놀지 않는다 — 총노출이 목표를 지킨다."""
    targets = {"kr_stock:000660.KS": 0.10,     # 못 산다(1주 144만원)
               "crypto:BTC/USDT": 0.30,
               "us_stock:AAPL": 0.10}
    out, deferred = _fit_to_budget(
        dict(targets),
        {"kr_stock:000660.KS": 1_443_000.0, "crypto:BTC/USDT": 63_656.0,
         "us_stock:AAPL": 306.0},
        1_000_000.0, cap=1.0)
    assert deferred, "못 사는 종목을 못 알아봤다"
    before, after = sum(map(abs, targets.values())), sum(map(abs, out.values()))
    assert abs(after - before) < 1e-9, (
        f"총노출이 {before:.4f} → {after:.4f}로 샜다 — 미룬 예산이 놀고 있다")
    # 재배분은 원래 비중에 비례한다(3:1)
    assert out["crypto:BTC/USDT"] > 0.30 and out["us_stock:AAPL"] > 0.10
    assert abs((out["crypto:BTC/USDT"] - 0.30)
               - 3 * (out["us_stock:AAPL"] - 0.10)) < 1e-6, out


def test_redistribution_respects_the_concentration_cap():
    """재배분이 한 종목 과집중 상한을 넘지 않는다 — 상한이 뒷문으로 뚫리면 안 된다."""
    out, _ = _fit_to_budget(
        {"kr_stock:000660.KS": 0.40, "crypto:BTC/USDT": 0.10},
        {"kr_stock:000660.KS": 1_443_000.0, "crypto:BTC/USDT": 63_656.0},
        1_000_000.0, cap=0.15)
    assert out["crypto:BTC/USDT"] <= 0.15 + 1e-9, (
        f"재배분이 상한 0.15를 넘겼다: {out}")


def test_nothing_to_redistribute_to_is_not_an_error():
    """살 수 있는 종목이 하나도 없으면 그냥 현금으로 둔다(억지로 사지 않는다)."""
    out, deferred = _fit_to_budget({"kr_stock:000660.KS": 0.05},
                                   {"kr_stock:000660.KS": 1_443_000.0},
                                   1_000_000.0)
    assert out["kr_stock:000660.KS"] == 0.0 and deferred


def test_short_targets_keep_their_sign():
    """공매도 방향도 부호가 유지돼야 한다 — 부호를 잃으면 반대로 산다."""
    out, _ = _fit_to_budget({"kr_stock:069500.KS": -0.25},
                            {"kr_stock:069500.KS": 100_800.0}, 1_000_000.0)
    assert out["kr_stock:069500.KS"] < 0, out


def test_a_missing_price_is_left_alone():
    """가격을 모르면 손대지 않는다 — 모르면 숫자를 만들지 않는다."""
    out, deferred = _fit_to_budget({"kr_stock:X": 0.1}, {}, 1_000_000.0)
    assert out["kr_stock:X"] == 0.1 and not deferred


# ── 장부·주문이 같은 값을 쓰는가 ──────────────────────────────


def _run(tmp_path, *, cash=1_000_000.0, syms=3):
    import json

    from quant.live.daily import run_daily_portfolio
    from quant.live.retrain import save_champions
    d = str(tmp_path)
    save_champions({f"synthetic:B{i}": {"strategy": "ma_cross",
                                        "params": {"fast": 10, "slow": 30},
                                        "promotions": 0}
                    for i in range(syms)}, d)
    p = tmp_path / "paper"
    p.mkdir(parents=True, exist_ok=True)
    (p / "portfolio_ALL.json").write_text(json.dumps({
        "market": "portfolio", "symbol": "ALL", "start_cash": cash,
        "cash": cash, "positions": {}, "base_prices": {},
        "last_bar": None, "history": [],
    }), encoding="utf-8")
    return run_daily_portfolio([("synthetic", f"B{i}") for i in range(syms)],
                               lookback=200, state_dir=d,
                               require_real_data=False)


def test_the_ledger_total_equals_the_sum_of_its_parts(tmp_path):
    """총노출(weight)이 종목별 적용 노출(applied)의 합과 같은가.

    둘을 따로 계산하던 시절에는 이것이 어긋날 수 있었다(감사 92).
    """
    rec = _run(tmp_path)
    parts = sum((rec.get("applied") or {}).values())
    assert abs(rec["weight"] - parts) < 1e-3, (
        f"총노출 {rec['weight']} vs 종목 합 {parts:.4f} — 두 숫자가 갈라졌다")


def test_the_ledger_has_the_deferred_field(tmp_path):
    rec = _run(tmp_path)
    assert "lot_infeasible" in rec, "미룬 종목 필드가 장부에 없다"
    assert rec["lot_infeasible"] is None, (
        f"합성 시장은 소수점이 정상인데 미뤘다: {rec['lot_infeasible']}")


def test_a_real_deferral_reaches_the_ledger_and_the_alert(tmp_path,
                                                          monkeypatch):
    """살 수 없는 날이 장부에도 경보에도 닿는가.

    ⚠️ '없을 때 없다'만 확인하면 `"lot_infeasible": None` 고정으로도
       통과한다 — 변이 시험이 실제로 그것을 잡았다.
    """
    import quant.live.daily as D
    monkeypatch.setattr(D, "FRACTIONAL_MARKETS", {"crypto"})
    rec = _run(tmp_path, cash=50.0)          # 100원짜리 1주도 못 산다
    bad = rec.get("lot_infeasible")
    assert bad, "자산 50원인데 '살 수 없다'는 사실이 장부에 없다"
    row = next(iter(bad.values()))
    for field in ("budget", "price"):
        assert field in row, f"{field}가 없다 — 읽는 사람이 판단할 수 없다"

    from quant.live.flag_watch import _current_flags
    flags = _current_flags({"paper": {"portfolio:ALL": {"history": [rec]}}})
    assert [k for k in flags if k.startswith("lot_infeasible")], (
        f"미룬 종목이 경보로 이어지지 않는다: {sorted(flags)}")


def test_the_orders_obey_the_budget_not_just_the_ledger(tmp_path, monkeypatch):
    """**주문**도 예산 규칙을 따르는가 — 장부만 줄이고 실제로는 사면 안 된다.

    감사 91·92 계열: 장부와 주문이 갈라지는 사고가 이 저장소에서 반복해서
    났다. 여기서도 기록만 `fitted_w`를 읽고 주문은 예산 전 값을 쓰면,
    사이트는 "안 샀다"는데 계좌에는 포지션이 생긴다.

    ⚠️ 이 검사는 처음에 헛돌았다. 합성 시장은 소수점 매매가 되는 것으로
       분류돼 예산 조정 자체가 일어나지 않았고, 변이 시험이 그것을 잡았다.
       그래서 ① 합성을 정수 주 시장으로 만들고 ② 잔돈 차단을 꺼서
       (안 그러면 두 경우 다 주문이 안 나가 구별이 안 된다) 한 변수만
       다르게 만든다.
    """
    import quant.live.daily as D
    monkeypatch.setattr(D, "FRACTIONAL_MARKETS", {"crypto"})
    monkeypatch.setattr(D, "MIN_ORDER_KRW", 0.0)
    rec = _run(tmp_path, cash=1_000.0)       # 1주 값이 배정금액보다 크다

    assert rec.get("lot_infeasible"), "전제가 깨졌다 — 미룬 종목이 없다"
    assert not (rec.get("applied") or {}), (
        f"미뤘는데 장부에 노출이 남았다: {rec.get('applied')}")

    import json
    st = json.loads((tmp_path / "paper" / "portfolio_ALL.json")
                    .read_text("utf-8"))
    held = {k: v for k, v in (st.get("positions") or {}).items()
            if abs(float(v.get("quantity", 0.0))) > 0}
    assert not held, (
        f"장부는 '안 샀다'는데 실제로는 샀다: {held} — "
        "주문이 예산 규칙을 무시하고 조정 전 비중을 쓴다")
