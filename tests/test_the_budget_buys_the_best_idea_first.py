"""예산은 n등분이 아니라 좋은 아이디어부터 (사장님 결정 2026-08-13).

지시는 두 마디였다.

    *"예산이 있는대로 유연하게 하기로 했잖어. 만약 그런 경우 너가 판단했을 때
      기존 투자한 종목을 매도하고 사도 되고."*

    *"이건 비율로 따지는 게 아니야. 수익률이 더 높을 것이라 판단되는
      최우선 선택을 하는 거지."*

왜 필요했나 — 실측(2026-08-13, 원금 100만원 · 20종목 균등 5% = 50,000원):

    SK하이닉스   1주 1,504,000원   계좌의 150.4%   예산의 30.1배
    현대차         409,500원        41.0%          8.2배
    LG화학         275,500원        27.6%          5.5배
    삼성전자       255,500원        25.6%          5.1배
    NAVER          215,500원        21.6%          4.3배
    KB금융         166,000원        16.6%          3.3배
    KODEX 200      103,250원        10.3%          2.1배

**7종목 중 자기 예산으로 1주라도 살 수 있는 것이 0개다.** 즉 예전 규칙
(자기 배정금액 안에서만 정수 주 내림)에서는 국내주식이 통째로 미뤄진다.

그래서 정수 주 시장의 돈을 **한 주머니로 모으고 확신도 순으로 채운다.**
높은 종목이 1주를 사면 낮은 종목은 오늘 못 산다 — 이미 들고 있었다면
목표가 0이 되어 **팔린다.** 그것이 "팔아서라도 산다"의 실체다.

⚠️ 집중도 상한은 두지 않는다(사장님 결정). 주머니 총액이 원래 그 시장에
   배정된 돈이므로 **총노출은 그대로**다 — 한 종목이 커지면 다른 종목이
   그만큼 줄 뿐, 레버리지가 생기지 않는다. 그 대신 "오늘 국내주식은 한
   종목뿐"인 날이 생기고, 그 사실은 장부(`lot_priority`·`lot_infeasible`)에
   남는다. 이 파일이 그 두 가지를 함께 지킨다.

⚠️ SK하이닉스는 1주가 계좌 전체보다 비싸다 — **유연화로 풀리는 문제가
   아니라 원금의 문제다.** 억지로 사지 않고 미룬다.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.daily import _fit_to_budget  # noqa: E402

EQ = 1_000_000.0
# 2026-08-13 실측 종가
PX = {"kr_stock:069500.KS": 103_250.0,    # KODEX 200
      "kr_stock:105560.KS": 166_000.0,    # KB금융
      "kr_stock:035420.KS": 215_500.0,    # NAVER
      "kr_stock:005930.KS": 255_500.0,    # 삼성전자
      "kr_stock:051910.KS": 275_500.0,    # LG화학
      "kr_stock:005380.KS": 409_500.0,    # 현대차
      "kr_stock:000660.KS": 1_504_000.0}  # SK하이닉스
KODEX, KB, NAVER = ("kr_stock:069500.KS", "kr_stock:105560.KS",
                    "kr_stock:035420.KS")
LG, HYNIX = "kr_stock:051910.KS", "kr_stock:000660.KS"


def _lots(out: dict, key: str) -> int:
    return round(out.get(key, 0.0) * EQ / PX[key])


# ── ① 자기 예산을 넘겨서라도 1주는 산다 ───────────────────────


def test_the_best_idea_gets_its_share_even_over_its_own_budget():
    """확신도 1위는 자기 배정금액(5만원)의 5.5배짜리 1주를 산다."""
    targets = {k: 0.05 for k in PX}                     # 주머니 35만원
    conv = {LG: 0.9, KODEX: 0.8, KB: 0.7, HYNIX: 0.6,
            "kr_stock:005930.KS": 0.5, NAVER: 0.4, "kr_stock:005380.KS": 0.3}
    out, deferred = _fit_to_budget(dict(targets), PX, EQ, cap=1.0,
                                   conviction=conv)
    assert _lots(out, LG) == 1, f"확신도 1위가 1주도 못 샀다: {out}"
    assert LG not in deferred

    # 대조군 — 확신도를 뒤집으면 **다른 종목**이 산다. 이게 없으면 위 단언은
    # "항상 LG화학을 산다"는 고정 동작으로도 통과한다.
    flipped = {k: 1.0 - v for k, v in conv.items()}
    out2, _ = _fit_to_budget(dict(targets), PX, EQ, cap=1.0, conviction=flipped)
    assert _lots(out2, LG) == 0, "확신도를 뒤집었는데 같은 종목을 샀다"
    assert sum(_lots(out2, k) for k in PX) > 0, "아무것도 안 샀다"


def test_the_lower_conviction_names_give_way_and_are_recorded():
    """양보한 종목은 목표가 0이 되고(=보유분은 팔린다) 이유가 남는다."""
    targets = {k: 0.05 for k in PX}
    conv = {LG: 0.9, KODEX: 0.8, KB: 0.7, HYNIX: 0.6,
            "kr_stock:005930.KS": 0.5, NAVER: 0.4, "kr_stock:005380.KS": 0.3}
    out, deferred = _fit_to_budget(dict(targets), PX, EQ, cap=1.0,
                                   conviction=conv)
    for k in (KODEX, KB, NAVER):
        assert out[k] == 0.0, f"{k}가 양보하지 않았다"
        assert k in deferred, f"{k}를 왜 못 샀는지 기록이 없다"
        row = deferred[k]
        assert row["price"] == PX[k] and row["budget"] == 50_000.0
        assert "pool_left" in row, "주머니에 얼마 남았는지가 없다 — 판단 불가"


def test_the_pocket_is_never_overdrawn():
    """총노출이 늘어나지 않는가 — 유연화가 레버리지가 되면 안 된다.

    상한을 두지 않는 근거가 바로 이것이다. 주머니가 보존되므로 한 종목이
    커진 만큼 다른 종목이 줄어든다.
    """
    targets = {k: 0.05 for k in PX}
    out, _ = _fit_to_budget(dict(targets), PX, EQ, cap=1.0,
                            conviction={LG: 0.9})
    spent = sum(abs(v) for v in out.values())
    assert spent <= sum(targets.values()) + 1e-9, (
        f"주머니(35%)보다 많이 썼다: {spent:.4f}")


def test_a_share_costlier_than_the_whole_account_is_still_refused():
    """SK하이닉스 1주 = 계좌의 150% — 확신도 1위여도 못 산다.

    유연화는 '예산을 옮기는 것'이지 '없는 돈을 만드는 것'이 아니다.
    """
    out, deferred = _fit_to_budget({k: 0.05 for k in PX}, PX, EQ, cap=1.0,
                                   conviction={HYNIX: 9.9})
    assert out[HYNIX] == 0.0 and HYNIX in deferred
    assert deferred[HYNIX]["price"] > EQ


# ── ② 순서가 결과를 바꾸지 않는다(재현성) ─────────────────────


def test_the_same_inputs_give_the_same_answer():
    """dict 순서가 달라도 결과가 같아야 한다 — 확신도 동점이면 키 순.

    같은 날을 다시 돌렸을 때 다른 종목을 사면 장부를 검증할 수 없다.
    """
    a = {k: 0.05 for k in PX}
    b = {k: 0.05 for k in reversed(list(PX))}
    flat = {k: 0.5 for k in PX}                      # 전부 동점
    out_a, _ = _fit_to_budget(a, PX, EQ, cap=1.0, conviction=flat)
    out_b, _ = _fit_to_budget(b, PX, EQ, cap=1.0, conviction=flat)
    assert out_a == out_b, "입력 순서만 바뀌었는데 답이 달라졌다"


def test_without_conviction_it_falls_back_to_target_size():
    """확신도를 안 주면 |목표비중|이 순위다 — 조용히 임의 순서가 되면 안 된다."""
    targets = {KODEX: 0.02, LG: 0.30}      # 주머니 32만원
    out, _ = _fit_to_budget(dict(targets), PX, EQ, cap=1.0)
    assert _lots(out, LG) == 1, f"비중이 큰 쪽을 먼저 사지 않았다: {out}"


# ── ③ 예전 계약이 그대로인가 ──────────────────────────────────


def test_a_comfortable_budget_still_just_floors():
    """예산이 넉넉하면 예전과 똑같이 내림만 한다 — 유연화가 평소를 바꾸지 않는다."""
    out, deferred = _fit_to_budget({KODEX: 0.25}, {KODEX: 100_800.0}, EQ)
    assert not deferred
    assert abs(out[KODEX] - 0.2016) < 1e-6, out      # 2주


def test_short_targets_keep_their_sign():
    """공매도 방향도 부호가 유지돼야 한다 — 부호를 잃으면 반대로 산다."""
    out, _ = _fit_to_budget({KODEX: -0.25}, {KODEX: 100_800.0}, EQ)
    assert out[KODEX] < 0, out


def test_a_missing_price_is_left_alone():
    """가격을 모르면 손대지 않는다 — 모르면 숫자를 만들지 않는다."""
    out, deferred = _fit_to_budget({"kr_stock:X": 0.1}, {}, EQ)
    assert out["kr_stock:X"] == 0.1 and not deferred


# ── ④ 매도 선집행 ─────────────────────────────────────────────


def test_sells_go_out_before_buys(tmp_path, monkeypatch):
    """판 돈이 같은 사이클의 매수에 쓰이는가.

    순서를 정하지 않으면 dict 순서대로 나가고, 현금이 모자라 매수가 잘리거나
    다음 날로 밀린다. 예산을 유연하게 쓰기로 한 이상 — 한 종목의 1주를
    사려고 다른 종목을 파는 이상 — "먼저 팔고 그 돈으로 산다"가 지켜져야
    그 결정이 그날 안에 완성된다.
    """
    import json

    import quant.live.daily as D
    from quant.live.retrain import save_champions

    from quant.broker.paper import PaperBroker

    monkeypatch.setattr(D, "MIN_ORDER_KRW", 0.0)
    d = str(tmp_path)
    save_champions({f"synthetic:B{i}": {"strategy": "ma_cross",
                                        "params": {"fast": 10, "slow": 30},
                                        "promotions": 0}
                    for i in range(4)}, d)
    p = tmp_path / "paper"
    p.mkdir(parents=True, exist_ok=True)
    # ⚠️ 빈 계좌로 시작하면 **매수만** 나서 이 검사가 아무것도 확인하지
    #    못한다(처음에 그렇게 썼다가 건너뛰었다 — 건너뜀은 통과가 아니다).
    #    오늘 목표가 아닌 종목(B0·B2)을 미리 들고 있게 만들어, 같은
    #    사이클에 매도와 매수가 함께 나는 상황을 확정적으로 만든다.
    (p / "portfolio_ALL.json").write_text(json.dumps({
        "market": "portfolio", "symbol": "ALL", "start_cash": 100_000.0,
        "cash": 60_000.0,
        "positions": {"synthetic:B0": {"quantity": 200.0, "avg_price": 100.0,
                                       "last_price": 100.0,
                                       "last_price_bar": "x"},
                      "synthetic:B2": {"quantity": 200.0, "avg_price": 100.0,
                                       "last_price": 100.0,
                                       "last_price_bar": "x"}},
        "base_prices": {}, "last_bar": None, "history": [],
    }), encoding="utf-8")

    seen: list[str] = []
    real = PaperBroker.market_order

    def _spy(self, symbol, side, quantity, price):
        seen.append(str(side))
        return real(self, symbol, side, quantity, price)

    monkeypatch.setattr(PaperBroker, "market_order", _spy)
    D.run_daily_portfolio([("synthetic", f"B{i}") for i in range(4)],
                          lookback=200, state_dir=d, require_real_data=False)

    assert "sell" in seen and "buy" in seen, (
        f"전제가 깨졌다 — 매도·매수가 함께 나지 않았다: {seen}")
    # 한 사이클 안에서 **모든 매도가 모든 매수보다 앞**이어야 한다.
    assert seen.index("buy") > len(seen) - 1 - seen[::-1].index("sell"), (
        f"매수가 매도보다 먼저 나갔다: {seen}")
