"""실계좌에서 **살 수 없는 보유**를 장부가 인정하는가 (감사 137).

2026-08-12, 실제 페이퍼 계좌의 보유를 열어 봤다.

    kr_stock:000660 (SK하이닉스)   0.0000주   평가 41원   · 1주 1,443,000원
    kr_stock:005930 (삼성전자)     0.0001주   평가 18원   · 1주   236,000원
    kr_stock:051910 (LG화학)       0.0006주   평가 153원  · 1주   272,000원
    kr_stock:069500 (KODEX 200)    0.0018주   평가 182원  · 1주   100,800원
    kr_stock:105560 (KB금융)       0.0039주   평가 690원  · 1주   174,600원

**국내주식은 소수점 매매가 없다.** 이 다섯 줄은 실계좌에서 단 한 주도
살 수 없다. 그런데 장부에는 보유로 적히고, 사이트 '종목별 현황'에 나가고,
손익에 반영된다. 숫자는 맞지만 **무엇의 숫자인지**가 현실과 다르다 —
오늘 반복해서 나온 계열이다(FROZEN_IDEAS ⑳).

'8만원으로 20종목 분산'이라는 이 실험의 전제가 어디까지 현실인지의 문제라,
고치는 방식(유니버스 조정·정수 주 강제)은 **운영자의 결정**이다. 감사가 할
일은 그 사실을 숨기지 않는 것이다: 장부에 남기고, 읽는 사람을 둔다.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.daily import FRACTIONAL_MARKETS, _lot_infeasible  # noqa: E402


# ── 판정 규칙 ─────────────────────────────────────────────────


def test_a_korean_stock_below_one_share_is_flagged():
    got = _lot_infeasible({"kr_stock:005930.KS": 0.0002},
                          {"kr_stock:005930.KS": 236_000.0}, 80_000.0)
    assert "kr_stock:005930.KS" in got
    row = got["kr_stock:005930.KS"]
    assert row["shares"] < 1.0
    assert row["price"] == 236_000.0
    assert abs(row["budget"] - 16.0) < 0.01      # 0.0002 × 80,000


def test_one_whole_share_is_not_flagged():
    """대조군 — 살 수 있는 것까지 깃발이 서면 매일 울려 아무도 안 본다.

    ⚠️ 처음 쓴 픽스처(비중 0.5 · 1주 100,800원 · 자산 8만원)는 사실
       0.397주라 **정당하게 깃발이 섰다.** 검사가 내 픽스처를 잡았다 —
       이 실험에서 국내주식 1주를 사려면 자산의 절반을 넘겨야 한다는
       사실 자체가 감사 137의 본론이다.
    """
    # 4만원 배정 / 1주 2만원 → 2주. 이 정도 저가 종목이라야 성립한다.
    assert _lot_infeasible({"kr_stock:CHEAP": 0.5},
                           {"kr_stock:CHEAP": 20_000.0},
                           80_000.0) == {}


def test_the_experiment_cannot_buy_a_single_share_of_its_own_universe():
    """실측 고정 — 현 유니버스의 국내주식은 8만원 전액으로도 못 사는 것이 있다.

    2026-08-12 종가 기준. 이 값이 바뀌면(액면분할·주가 하락) 검사가 깨지고,
    그때 다시 판단하면 된다 — 조용히 지나가지 않게 못 박아 둔다.
    """
    # SK하이닉스 1주 = 1,443,000원 > 계좌 전체(8만원)의 18배
    got = _lot_infeasible({"kr_stock:000660.KS": 1.0},
                          {"kr_stock:000660.KS": 1_443_000.0}, 80_000.0)
    assert got, "계좌 전액을 걸어도 1주를 못 사는데 깃발이 안 선다"
    assert got["kr_stock:000660.KS"]["shares"] < 0.06


def test_fractional_markets_are_exempt():
    """코인·미국주식은 소수점 매매가 되므로 1주 미만이 정상이다."""
    assert "crypto" in FRACTIONAL_MARKETS
    assert "us_stock" in FRACTIONAL_MARKETS
    assert "kr_stock" not in FRACTIONAL_MARKETS, (
        "국내주식은 소수점 매매가 없다 — 면제 대상이 아니다")
    assert _lot_infeasible({"crypto:BTC/USDT": 0.02, "us_stock:AAPL": 0.02},
                           {"crypto:BTC/USDT": 63_656.0,
                            "us_stock:AAPL": 306.0}, 80_000.0) == {}


def test_missing_price_is_not_a_verdict():
    """가격을 모르면 판정하지 않는다 — 모르면 숫자를 만들지 않는다."""
    assert _lot_infeasible({"kr_stock:X": 0.1}, {}, 80_000.0) == {}
    assert _lot_infeasible({"kr_stock:X": 0.1}, {"kr_stock:X": 0.0},
                           80_000.0) == {}
    assert _lot_infeasible({"kr_stock:X": 0.1}, {"kr_stock:X": 100.0}, 0.0) == {}


# ── 장부에 남는가 ─────────────────────────────────────────────


def test_the_ledger_field_exists_and_is_quiet_on_a_clean_day(tmp_path):
    from quant.live.daily import run_daily_portfolio
    from quant.live.retrain import save_champions
    d = str(tmp_path)
    save_champions({f"synthetic:L{i}": {"strategy": "ma_cross",
                                        "params": {"fast": 10, "slow": 30},
                                        "promotions": 0} for i in range(3)}, d)
    rec = run_daily_portfolio([("synthetic", f"L{i}") for i in range(3)],
                              lookback=200, state_dir=d,
                              require_real_data=False)
    assert "lot_infeasible" in rec, "장부에 필드 자체가 없다"
    assert rec["lot_infeasible"] is None, (
        f"합성 시장은 소수점이 정상인데 깃발이 섰다: {rec['lot_infeasible']}")


def test_a_real_infeasible_day_reaches_the_ledger(tmp_path, monkeypatch):
    """살 수 없는 날이 실제로 장부에 적히는가.

    ⚠️ 위 검사만 있으면 `"lot_infeasible": None`으로 고정해도 통과한다 —
       변이 시험이 그것을 잡았다. '없을 때 없다'와 '있을 때 있다'는
       **다른 문장**이고, 둘 다 확인해야 한다.

    소수점 매매가 안 되는 시장을 흉내내기 위해 합성 시장을 면제 목록에서
    빼고, 자산을 아주 작게(50원) 잡아 1주도 못 사는 상황을 만든다.
    """
    import json

    import quant.live.daily as D
    from quant.live.retrain import save_champions
    monkeypatch.setattr(D, "FRACTIONAL_MARKETS", {"crypto"})
    d = str(tmp_path)
    save_champions({f"synthetic:P{i}": {"strategy": "ma_cross",
                                        "params": {"fast": 10, "slow": 30},
                                        "promotions": 0} for i in range(3)}, d)
    p = tmp_path / "paper"
    p.mkdir(parents=True, exist_ok=True)
    # 자산 50원 — 100원짜리 종목 1주도 못 산다. 시작금도 같이 낮춰야
    # 낙폭 킬스위치가 걸려 노출이 0이 되는 것을 피한다.
    (p / "portfolio_ALL.json").write_text(json.dumps({
        "market": "portfolio", "symbol": "ALL",
        "start_cash": 50.0, "cash": 50.0, "positions": {},
        "base_prices": {}, "last_bar": None, "history": [],
    }), encoding="utf-8")

    rec = D.run_daily_portfolio([("synthetic", f"P{i}") for i in range(3)],
                                lookback=200, state_dir=d,
                                require_real_data=False)
    bad = rec.get("lot_infeasible")
    assert bad, (
        "자산 50원으로 100원짜리 주식을 들고 있다고 기록하면서 "
        "'살 수 없다'는 사실은 장부에 없다")
    row = next(iter(bad.values()))
    for field in ("budget", "price", "shares"):
        assert field in row, f"{field}가 없다 — 읽는 사람이 판단할 수 없다"
    assert row["shares"] < 1.0


# ── 읽는 사람이 있는가 (감사 135의 반복 방지) ─────────────────


def test_someone_actually_reads_it():
    """기록만 남기고 아무도 안 읽으면 감사 135와 같은 결함이 된다."""
    from quant.live.flag_watch import _current_flags
    status = {"paper": {"portfolio:ALL": {"history": [{
        "date": "2026-08-12",
        "lot_infeasible": {"kr_stock:005930.KS": {
            "budget": 18.0, "price": 236000.0, "shares": 0.000076}},
    }]}}}
    flags = _current_flags(status)
    hit = [k for k in flags if k.startswith("lot_infeasible")]
    assert hit, f"실현 불가 보유가 경보로 이어지지 않는다: {sorted(flags)}"
    assert "005930" in flags[hit[0]]
    assert "236,000" in flags[hit[0]]        # 1주 값을 같이 보여준다


def test_a_clean_ledger_raises_no_flag():
    from quant.live.flag_watch import _current_flags
    status = {"paper": {"portfolio:ALL": {"history": [
        {"date": "2026-08-12", "lot_infeasible": None}]}}}
    assert not [k for k in _current_flags(status)
                if k.startswith("lot_infeasible")]
