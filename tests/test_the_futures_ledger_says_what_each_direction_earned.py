"""선물 트랙은 **롱과 숏이 각각 얼마를 벌고 잃었는지**를 기록한다.

2026-09-07 사장님 질문("선물투자 시, 롱숏 포지션 고려도 잘 하는거지?")에서
시작해 장부를 열어 보니, 방향을 **고르는** 장치는 다 돌고 있는데 방향별
**성적은 어디에도 기록돼 있지 않았다.**

화면에는 롱 포지션 수와 숏 포지션 수가 나란히 떠 있었다. 나란히 보이는
것이 비교는 아니다 — 이 트랙이 이미 한 번 걸린 바로 그 모양이다(선물 모듈
첫머리가 "나란히 돌려서 잰다"고 약속해 놓고 반대쪽이 없던 일, 2026-09-03).
개수는 "숏을 몇 번 잡았나"이지 "숏이 돈이 됐나"가 아니다.

여기서 지키는 약속:

  ① **항등식이 맞는다** — 자산 변화 = 롱 몫 + 숏 몫 − 수수료 − 자금조달.
     맞지 않으면 어느 한쪽이 틀린 것이고, 틀린 채로 화면에 나가면 그
     숫자는 없느니만 못하다.
  ② **평가로 가른다**(확정만 세지 않는다). 확정만 세면 아직 안 판 자리의
     성적이 통째로 빠져, 회전이 심한 방향이 성적이 있는 방향처럼 보인다.
  ③ **총이득과 순이득을 둘 다** 적는다(사장님 2026-09-02 지시).
  ④ 수수료는 **닫는 몫과 여는 몫**으로 갈라 단다. 뒤집는 주문을 통째로 새
     방향에 달면 숏 수수료가 부풀고 롱이 공짜로 돌아 보인다.
  ⑤ 자금조달의 **부호는 방향마다 반대다**(롱은 내고 숏은 받는다). 절댓값으로
     바꾸면 숏이 부당하게 불리해진다.
  ⑥ 마크 가격을 못 받은 종목은 **0으로 세지 않는다** — 이름을 남긴다.
     조용한 실패와 진짜 무동작이 장부에서 같아지면 안 된다.
  ⑦ 옛 회차의 재구성은 **재구성이라고 말하고**, 못 가른 몫을 **숫자로**
     적는다. 한계를 주의 문구로만 남기면 읽는 사람이 크기를 알 수 없다.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live import futures_challenger as fc  # noqa: E402


# ── ① 항등식 ───────────────────────────────────────────────────────────
def test_the_directions_and_the_costs_add_up_to_the_equity_change():
    """롱 + 숏 − 수수료 − 자금조달 = 자산 변화. 잔차는 0이어야 한다.

    이것이 이 장치의 유일한 자기 검산이다. 항등식이 깨지면 방향별 숫자를
    믿을 근거가 없어진다.
    """
    prev_pos = {"A": 2.0, "B": -3.0}
    prev_px = {"A": 100.0, "B": 50.0}
    px = {"A": 110.0, "B": 55.0}
    st = {"cash": 1000.0, "positions": dict(prev_pos), "avg_cost": {},
          "cost_paid": 0.0, "funding_paid": 0.0}
    eq_before = fc.mark_equity(st, prev_px)
    hours = 8.0
    funding = fc.apply_funding(st, px, hours)
    trades = [{"symbol": "A", "cost": 4.0,
               "fee_by_direction": {"long": 4.0, "short": 0.0}}]
    st["cash"] -= 4.0                      # 체결 수수료만 (수량 변화 없음)
    eq_after = fc.mark_equity(st, px)

    split = fc.direction_split(prev_pos, prev_px, px)
    fees = fc.fee_split(trades)
    fund = fc.funding_split(prev_pos, px, hours)

    lhs = eq_after - eq_before
    rhs = (split["long"] + split["short"]
           - fees["long"] - fees["short"] - fund["long"] - fund["short"])
    assert abs(lhs - rhs) < 1e-6, (
        f"항등식이 깨졌다 — 자산 변화 {lhs:.6f} vs 방향별 합 {rhs:.6f}. "
        "방향별 숫자를 화면에 올릴 근거가 없다")
    # 자금조달 총액도 방향별 합과 같아야 한다(부호 포함).
    assert abs(funding - (fund["long"] + fund["short"])) < 1e-9


def test_the_split_is_marked_to_market_not_only_realised():
    """안 판 포지션의 손익도 그 방향에 달린다.

    확정만 세면 "많이 사고판 방향"이 "성적이 있는 방향"처럼 보인다 — 그건
    방향을 비교하는 자가 아니라 회전을 비교하는 자다.
    """
    out = fc.direction_split({"A": 1.0}, {"A": 100.0}, {"A": 120.0})
    assert out["long"] == 20.0, out
    assert out["short"] == 0.0


def test_a_short_gains_when_the_price_falls():
    """숏은 수량이 음수라 값이 내리면 번다 — 부호를 손으로 뒤집지 않는다."""
    out = fc.direction_split({"A": -2.0}, {"A": 100.0}, {"A": 90.0})
    assert out["short"] == 20.0, out
    assert out["long"] == 0.0


# ── ⑥ 못 잰 것은 0이 아니다 ────────────────────────────────────────────
def test_a_symbol_without_a_mark_is_named_not_counted_as_zero():
    """시세를 못 받은 종목은 이름을 남긴다.

    0으로 세면 "그 방향은 아무 일도 없었다"가 되고, 조용한 실패와 진짜
    무동작이 장부에서 똑같이 보인다.
    """
    out = fc.direction_split({"A": 1.0, "B": 2.0},
                             {"A": 100.0}, {"A": 110.0, "B": 50.0})
    assert out["long"] == 10.0
    assert out["unpriced"] == ["B"], out
    # 반대 방향(지금 가격만 없는 경우)도 같다.
    out2 = fc.direction_split({"B": 2.0}, {"B": 50.0}, {})
    assert out2["unpriced"] == ["B"]


# ── ④ 수수료는 닫는 몫과 여는 몫으로 갈린다 ───────────────────────────
def test_a_flip_pays_the_fee_on_both_sides():
    """롱을 닫고 그대로 숏으로 뒤집는 주문은 두 방향이 나눠 낸다."""
    # 롱 10을 들고 있는데 −30을 체결 → 10은 닫고 20은 새로 연다.
    by = fc._fee_by_direction(cur_qty=10.0, qty=-30.0, fee=30.0)
    assert abs(by["long"] - 10.0) < 1e-9, by     # 닫는 몫 10/30
    assert abs(by["short"] - 20.0) < 1e-9, by    # 여는 몫 20/30


def test_closing_a_long_charges_the_long_not_the_new_direction():
    """롱을 통째로 닫는 주문의 수수료는 **롱**의 것이다.

    ⚠️ 체결 기록의 ``direction``은 **체결 뒤** 방향이라 통째 청산이면
       "청산"이다. 그걸로 세면 이 수수료가 어느 방향에도 안 달린다.
    """
    by = fc._fee_by_direction(cur_qty=5.0, qty=-5.0, fee=7.0)
    assert by["long"] == 7.0 and by["short"] == 0.0, by


def test_opening_a_short_charges_the_short():
    by = fc._fee_by_direction(cur_qty=0.0, qty=-4.0, fee=6.0)
    assert by["short"] == 6.0 and by["long"] == 0.0, by


def test_the_fee_split_reads_what_the_trade_wrote():
    """체결이 스스로 적어 둔 방향별 몫을 쓴다(추측하지 않는다)."""
    trades = [{"direction": "청산", "cost": 9.0,
               "fee_by_direction": {"long": 9.0, "short": 0.0}}]
    assert fc.fee_split(trades) == {"long": 9.0, "short": 0.0}


def test_an_old_trade_without_the_split_still_counts_somewhere():
    """옛 기록에는 방향별 몫이 없다 — 거칠게라도 단다(0으로 버리지 않는다)."""
    trades = [{"direction": "숏", "cost": 3.0}]
    assert fc.fee_split(trades) == {"long": 0.0, "short": 3.0}


# ── ⑤ 자금조달의 부호 ──────────────────────────────────────────────────
def test_funding_keeps_its_sign_per_direction():
    """롱은 내고(양수) 숏은 받는다(음수). 절댓값으로 바꾸지 않는다."""
    out = fc.funding_split({"A": 1.0, "B": -1.0}, {"A": 100.0, "B": 100.0}, 8.0)
    assert out["long"] > 0, out
    assert out["short"] < 0, out
    assert abs(out["long"] + out["short"]) < 1e-9, (
        "같은 금액의 롱·숏이면 자금조달이 상쇄돼야 한다")


def test_funding_is_zero_without_elapsed_time():
    assert fc.funding_split({"A": 1.0}, {"A": 100.0}, 0.0) == {
        "long": 0.0, "short": 0.0}


# ── ③ 총이득과 순이득을 둘 다 ─────────────────────────────────────────
def test_the_round_record_carries_both_gross_and_net():
    """총만 적으면 광고이고, 순만 적으면 "수수료가 먹었다"가 사라진다."""
    one = fc._round_direction_pnl(
        {}, {"A": 1.0}, {"A": 100.0}, {"A": 110.0},
        [{"cost": 2.0, "fee_by_direction": {"long": 2.0, "short": 0.0}}], 8.0)
    assert set(one) >= {"gross", "fee", "funding", "net", "positions"}
    assert one["gross"]["long"] == 10.0
    assert one["net"]["long"] < one["gross"]["long"], (
        "순이득이 총이득보다 크면 비용이 어디론가 샜다")
    assert one["positions"] == {"long": 1, "short": 0}


def test_the_first_round_says_it_had_no_prior_marks():
    """첫 회차는 직전 가격이 없다 — 그 사실을 적는다.

    안 적으면 "아무 일도 없던 회차"와 구별되지 않는다.
    """
    one = fc._round_direction_pnl({}, {"A": 1.0}, {}, {"A": 100.0}, [], 0.0)
    assert one.get("no_prior_marks") is True, one


# ── 회차 기록에 마크 가격이 남는가 (되살릴 수 없는 재료) ───────────────
def test_the_round_record_stores_the_marks_it_used():
    """가격을 안 남기면 방향별 성적을 나중에 못 되살린다.

    지나간 시세를 다시 받아올 수 없으므로, 이건 **지나가면 영영 못 되살리는
    재료**다(밤 패널의 날짜별 합·개수와 같은 종류다).
    """
    src = (ROOT / "quant" / "live" / "futures_challenger.py").read_text("utf-8")
    assert '"prices": {k: round(float(v), 10) for k, v in prices.items()}' in src, (
        "회차 기록에서 마크 가격이 빠졌다 — 방향별 성적이 되살릴 수 없는 "
        "값이 된다")


def test_the_marks_are_captured_before_the_liquidation_check():
    """청산 검사보다 **앞에서** 직전 포지션을 붙잡는다.

    청산은 포지션을 닫으므로 뒤에서 붙잡으면 청산으로 잃은 몫이 어느
    방향에도 안 달리고, 항등식이 조용히 깨진다.
    """
    src = (ROOT / "quant" / "live" / "futures_challenger.py").read_text("utf-8")
    i_cap = src.index("prev_positions = dict(st.get(\"positions\") or {})")
    i_liq = src.index("liq = liquidation_check(st, prices)")
    assert i_cap < i_liq, (
        "직전 포지션을 청산 검사 뒤에서 붙잡고 있다 — 청산 손실이 "
        "어느 방향에도 안 달린다")


# ── ⑦ 재구성은 재구성이라고 말한다 ────────────────────────────────────
def test_backfilled_rounds_say_they_were_reconstructed():
    """마크 가격이 없던 옛 회차는 체결가로 짜 맞춘 값이다 — 그렇게 적는다."""
    st = {"cash": 0.0, "start_cash": 10_000.0, "positions": {}, "curve": [],
          "rounds": [
              {"at": "t1", "equity": 10_000.0, "positions": {"A": 1.0},
               "trades": [{"symbol": "A", "price": 100.0, "cost": 0.0}]},
              {"at": "t2", "equity": 10_010.0, "positions": {"A": 1.0},
               "trades": [{"symbol": "A", "price": 110.0, "cost": 0.0}]}]}
    res = fc.backfill_direction_pnl(st)
    assert res["filled"] == 2
    assert st["rounds"][1]["direction_pnl"]["reconstructed"] is True
    assert st["rounds"][1]["direction_pnl"]["gross"]["long"] == 10.0


def test_backfill_does_not_touch_a_round_that_already_has_a_record():
    """옛 기록은 고치지 않는다 — 이 저장소의 규약이다."""
    kept = {"gross": {"long": 1.0, "short": 0.0}, "fee": {},
            "funding": {}, "net": {"long": 1.0, "short": 0.0}}
    st = {"cash": 0.0, "start_cash": 100.0, "positions": {}, "curve": [],
          "rounds": [{"at": "t1", "equity": 100.0, "positions": {},
                      "direction_pnl": dict(kept), "trades": []}]}
    fc.backfill_direction_pnl(st)
    assert st["rounds"][0]["direction_pnl"] == kept


def test_the_public_report_says_how_much_it_could_not_attribute():
    """못 가른 몫을 **숫자로** 적는다.

    한계를 주의 문구로만 남기면 읽는 사람이 그 크기를 알 수 없다. 그리고
    이 값이 0으로 수렴하는 것이 이 작업이 끝났다는 유일한 증거다.
    """
    st = {"cash": 0.0, "start_cash": 10_000.0, "positions": {}, "curve": [],
          "rounds": [
              {"at": "t1", "equity": 10_000.0, "positions": {"A": 1.0},
               "trades": [{"symbol": "A", "price": 100.0, "cost": 0.0}]},
              # B는 이 회차에 체결이 없어 가격을 모른다 → 못 가른 몫이 생긴다.
              {"at": "t2", "equity": 10_050.0, "positions": {"A": 1.0, "B": 1.0},
               "trades": [{"symbol": "A", "price": 110.0, "cost": 0.0}]}]}
    fc.backfill_direction_pnl(st)
    pub = fc._direction_public(st)
    assert pub["measured"] is True
    assert pub["reconstructed_rounds"] == 2
    assert "unattributed" in pub, "못 가른 몫을 안 적었다"
    assert abs(pub["unattributed"] - 40.0) < 1e-6, pub


def test_the_public_report_distinguishes_unmeasured_from_zero():
    """아직 안 잰 상태를 빈 칸으로 두지 않는다.

    비우면 "0이다"와 "아직 안 잰다"가 화면에서 같아진다 — 이 저장소가
    반복해서 잡아 온 병이다.
    """
    pub = fc._direction_public({"rounds": [], "start_cash": 100.0})
    assert pub["measured"] is False and pub.get("why"), pub


def test_the_public_report_carries_amounts_not_only_counts():
    """화면이 읽는 재료에 **금액**이 있어야 한다 — 개수만으로는 비교가 아니다."""
    st = {"cash": 0.0, "start_cash": 10_000.0, "curve": [],
          "positions": {"A": 1.0, "B": -1.0},
          "rounds": [
              {"at": "t1", "equity": 10_000.0, "positions": {"A": 1.0},
               "trades": [{"symbol": "A", "price": 100.0, "cost": 0.0}]},
              {"at": "t2", "equity": 10_010.0, "positions": {"A": 1.0},
               "trades": [{"symbol": "A", "price": 110.0, "cost": 0.0}]}]}
    fc.backfill_direction_pnl(st)
    pub = fc.public_report(st)["direction_pnl"]
    assert pub["gross"]["long"] == 10.0
    # 개수도 함께 — 금액과 개수를 같이 놓아야 "숏이 적어서 작은 것"인지
    # "숏이 나빠서 작은 것"인지 구별할 수 있다.
    assert pub["open_positions"] == {"long": 1, "short": 1}


def test_the_cumulative_total_survives_the_round_window():
    """누적은 회차 보관 한도를 넘겨도 살아남는다.

    회차 목록만 보고 합산하면 오래된 회차가 잘린 뒤 누적이 조용히 줄고,
    화면이 "숏이 덜 잃었다"로 바뀌는데 아무 빨간불도 안 뜬다.
    """
    st = {}
    one = {"gross": {"long": 5.0, "short": -2.0},
           "fee": {"long": 1.0, "short": 0.5},
           "funding": {"long": 0.1, "short": -0.1},
           "net": {"long": 3.9, "short": -2.4}}
    fc._accumulate_direction(st, one)
    fc._accumulate_direction(st, one)
    tot = st["direction_totals"]
    assert tot["gross"]["long"] == 10.0 and tot["gross"]["short"] == -4.0
    assert tot["rounds"] == 2
    # 회차 목록이 비어도 누적은 그대로다.
    assert "rounds" not in st
