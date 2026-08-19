"""비용은 이미 빠지고 있었다 — 이제 **얼마나** 빠졌는지도 말한다.

사장님 질문(2026-08-19): "수수료도 계산한 결과값들 맞지?"

답은 예였다. 가짜 브로커가 살 때 현금에서 `금액 + 수수료`를 빼고, 팔 때
`금액 − 수수료`를 더한다. 자산도 수익률도 전부 비용을 뺀 뒤의 값이다.

그런데 확인하다 두 가지가 걸렸다.

  ① **그냥 보유 기준선이 비용을 한 푼도 안 물었다.** 화면은 그 숫자를
     실험 성적 바로 옆에 나란히 놓는데, 실험 쪽은 수수료·슬리피지를 전부
     문 뒤의 값이었다. 같은 자에 눈금이 둘이었다. (기울기는 우리 쪽에
     불리한 방향이었지만, 어느 쪽으로 기울든 비교는 비교다.)

  ② **얼마를 냈는지 아무도 세지 않았다.** 그래서 그 질문에 답하려면
     체결 기록을 되짚어 추정해야 했고, 되짚기는 틀릴 수 있다 —
     2026-08-15 장부에는 현금이 모자라 **거부된** 주문이 체결처럼 남아
     있다(감사 273). 그걸 세면 없던 비용 6백만원어치가 생긴다.

여기서 지키는 것:
  · 편도 비용률은 **한 자리**에서만 나온다(네 곳에 흩어져 있었다).
  · 그냥 보유도 사는 값을 문다. 그리고 **비용이 0이면 예전과 같다**(대조군).
  · 낸 수수료는 돈을 빼는 그 자리에서 센다.
  · 되짚기는 기록이 스스로 부인한 체결을 세지 않는다. 그리고 이미 센
    값이 있으면 되짚기가 덮어쓰지 않는다(대조군).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ───────────────────── 편도 비용률은 한 자리에서 ─────────────────────
def test_one_way_cost_has_a_single_home():
    from quant.backtest.costs import CostModel
    from quant.live.daily import _fill_cost

    for market in ("crypto", "us_stock", "kr_stock"):
        cm = CostModel.for_market(market)
        assert cm.total_one_way() == cm.fee + cm.slippage
        # 본 계좌 체결이 쓰는 값과 같아야 한다 — 갈라지면 장부와 실험이
        # 서로 다른 비용으로 굴러간다.
        assert _fill_cost(market) == cm.total_one_way(), market
    assert CostModel.for_market("crypto").total_one_way() > 0


# ───────────────────── ① 그냥 보유도 사는 값을 문다 ─────────────────────
_ST = {"first_prices": {"BTC/USDT": 100.0, "ETH/USDT": 200.0},
       "last_prices": {"BTC/USDT": 110.0, "ETH/USDT": 210.0}}
# 평균 총수익 = (+10% + 5%) / 2 = 7.5%


def test_the_hold_benchmark_pays_to_buy():
    from quant.live.intraday_challenger import hold_baseline_pct

    gross = hold_baseline_pct(_ST, 0.0)
    net = hold_baseline_pct(_ST, 0.0015)
    assert abs(gross - 7.5) < 1e-6, gross
    # 비용을 물면 반드시 낮아진다.
    assert net < gross, (net, gross)
    # 산 몫만 시장을 탄다: (1−0.0015) × 1.075 − 1
    # 장부에 적히는 값은 소수 넷째 자리까지 반올림된다 — 마지막 자리까지
    # 따지지 않는다. 지키는 것은 식이지 반올림 방향이 아니다.
    assert abs(net - ((1 - 0.0015) * 1.075 - 1) * 100) < 1e-3, net


def test_a_free_market_leaves_the_benchmark_alone():
    """대조군 — 비용이 0이면 예전 값 그대로여야 한다.

    이게 없으면 "항상 얼마쯤 깎는다"는 고장도 위 검사를 통과한다.
    """
    from quant.live.intraday_challenger import hold_baseline_pct

    assert hold_baseline_pct(_ST, 0.0) == 7.5
    assert hold_baseline_pct({}, 0.0015) is None      # 재료가 없으면 침묵


def test_both_intraday_tracks_charge_their_own_market():
    """코인과 미국주식은 비용률이 다르다 — 한쪽 값을 양쪽에 쓰면 안 된다."""
    coin = (ROOT / "quant" / "live" / "intraday_challenger.py").read_text("utf-8")
    stock = (ROOT / "quant" / "live" / "intraday_us.py").read_text("utf-8")
    assert 'measured_cost_model("crypto", state_dir).total_one_way()' in coin
    assert 'measured_cost_model("us_stock", state_dir).total_one_way()' in stock
    # 규칙은 한 벌 — 미국 트랙은 코인 트랙의 기준선 함수를 빌려 쓴다.
    assert "from quant.live.intraday_challenger import" in stock
    assert "hold_baseline_pct" in stock
    assert "def hold_baseline_pct" not in stock, (
        "기준선을 복사해 두 벌로 만들면 언젠가 갈라진다")


# ───────────────────── ② 낸 수수료를 그 자리에서 센다 ─────────────────────
def test_the_broker_counts_what_it_takes():
    from quant.broker.paper import PaperBroker

    b = PaperBroker(cash=10_000.0, fee=0.001)
    assert b.fee_paid == 0.0
    b.market_order("X", "buy", 10, 100)      # 1,000 × 0.001 = 1.0
    b.market_order("X", "sell", 10, 101)     # 1,010 × 0.001 = 1.01
    assert abs(b.fee_paid - 2.01) < 1e-9, b.fee_paid
    # 센 값과 실제로 빠진 돈이 맞아야 한다.
    assert abs(b.get_cash() - (10_000.0 - 1_000.0 + 1_010.0 - 2.01)) < 1e-6


def test_a_rejected_order_pays_nothing():
    """대조군 — 못 산 주문은 수수료도 안 낸다."""
    from quant.broker.paper import PaperBroker

    b = PaperBroker(cash=100.0, fee=0.001)
    order = b.market_order("X", "buy", 10, 100)      # 1,000원어치 — 현금 부족
    assert order.status == "rejected"
    assert b.fee_paid == 0.0


# ───────────────────── 되짚기는 기록이 부인한 체결을 세지 않는다 ─────────
_PAID = {"date": "2026-08-19",
         "fills": [{"key": "kr_stock:005930.KS", "amount": 100_000.0}]}
_PHANTOM = {"date": "2026-08-15",
            "fills": [{"key": "us_stock:AMZN", "amount": 6_361_687.93}],
            "cash_short": [{"key": "us_stock:AMZN", "need": 6_365_504.94,
                            "cash": 677_061.47}]}


def test_the_reconstruction_skips_what_the_record_denies():
    from quant.live.daily import _fill_cost
    from quant.live.ledger_costs import reconstruct_cost_paid

    out = reconstruct_cost_paid([_PHANTOM, _PAID])
    assert out["denied"] == 1, out
    # 진짜 체결분만 남는다.
    assert abs(out["amount"] - 100_000.0 * _fill_cost("kr_stock")) < 0.01, out


def test_a_clean_record_is_counted_in_full():
    """대조군 — 부인 표식이 없으면 전부 센다(무조건 빼는 고장 방지)."""
    from quant.live.daily import _fill_cost
    from quant.live.ledger_costs import reconstruct_cost_paid

    out = reconstruct_cost_paid([_PAID])
    assert out["denied"] == 0
    assert abs(out["amount"] - 100_000.0 * _fill_cost("kr_stock")) < 0.01


def test_the_seed_never_overwrites_a_counted_total():
    """실제로 센 값이 추정보다 언제나 옳다 — 씨앗이 덮어쓰면 안 된다."""
    from quant.live.ledger_costs import seed_cost_paid

    st = {"history": [_PAID]}
    assert seed_cost_paid(st)          # 처음에는 채운다
    before = st["cost_paid"]
    assert before > 0
    st["cost_paid"] = 999.0            # 그 뒤로는 실제로 센 값
    assert seed_cost_paid(st) == {}
    assert st["cost_paid"] == 999.0


# ───────────────────── 장부에 남고 화면에 나온다 ─────────────────────
def test_the_ledger_writes_both_numbers():
    """오늘 낸 값과 누적 — 둘 다 기록에 들어가야 한다."""
    import ast

    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    tree = ast.parse(src)
    fn = next(f for f in ast.walk(tree)
              if isinstance(f, ast.FunctionDef) and f.name == "run_daily_portfolio")
    body = "\n".join(src.splitlines()[fn.lineno - 1:fn.end_lineno])
    # 되짚기가 아니라 브로커가 실제로 뺀 값을 받아야 한다.
    assert 'getattr(broker, "fee_paid", 0.0)' in body
    assert '"cost": cost_today,' in body
    assert '"cost_paid": st["cost_paid"],' in body


def test_the_first_screen_shows_what_was_paid():
    page = (ROOT / "docs" / "index.html").read_text("utf-8")
    assert "이미 낸 비용" in page
    assert "pfLast.cost_paid!=null" in page, (
        "누적 비용이 없는 날에도 줄을 그리면 '0원 냈다'는 거짓이 된다")


def test_the_intraday_page_says_the_benchmark_pays_too():
    page = (ROOT / "docs" / "intraday.html").read_text("utf-8")
    assert "사는 비용 포함" in page
    assert "비용을 뺀 뒤" in page
