"""선물 운용 계좌가 갈아타는 비용으로 자산의 6배를 뗐다 (2026-11-09 감사 355).

10/13 엔진 → 현금으로 갈아탈 때 회차 기록의 `gross_exposure`(USDT **금액**)를
노출 **배수**로 썼다. 8,720 USDT 계좌가 56,604 USDT를 냈고, 공개 화면에
−578%가 한 달 내내 떠 있었다. 검사는 노출을 배수(0.8)로 먹여서 못 봤다 —
배치가 만드는 진짜 모양으로 먹인다.
"""
from __future__ import annotations

from quant.live import futures_mode as F
from quant.live.futures_challenger import gross_exposure


def _real_round(equity: float, positions: dict, prices: dict) -> dict:
    st = {"positions": positions}
    return {"at": "2026-10-12T15:00:00+09:00", "equity": equity,
            "gross_exposure": round(gross_exposure(st, prices), 4), "prices": prices}


def test_exposure_is_a_ratio_of_the_account_not_an_amount():
    r = _real_round(8_000.0, {"BTC/USDT": 0.04}, {"BTC/USDT": 100_000.0})
    assert r["gross_exposure"] == 4_000.0           # 기록은 금액이다
    assert abs(F._exposure("follow", [r]) - 0.5) < 1e-9
    assert F._exposure("follow", [{**r, "equity": 0.0}]) == 0.0


def test_the_real_10_13_switch_is_repaired_from_the_record_alone():
    op = {"start_cash": 10_000.0, "equity": -47_883.96, "cost_paid": 56_603.7613,
          "peak": 10_000.0, "mode": "cash",
          "switches": [{"on": "2026-10-13", "from": "follow", "to": "cash",
                        "t": 1.378, "cost": 56_603.7613}],
          "history": [{"date": "2026-10-12", "equity": 8_719.8013, "mode": "follow"},
                      {"date": "2026-10-13", "equity": -47_883.96, "mode": "cash", "day_ret": 0.0},
                      {"date": "2026-10-14", "equity": -47_883.96, "mode": "cash", "day_ret": 0.0}]}
    F.repair_switch_costs(op)
    fixed = 56_603.7613 / 8_719.8013
    assert abs(op["equity"] - (8_719.8013 - fixed)) < 1e-6
    assert all(h["equity"] > 0 for h in op["history"])
    assert op["switches"][0]["cost"] == round(fixed, 4)
    assert op["corrections"] and op["corrections"][0]["was_cost"] == 56_603.7613
    again = dict(op)
    F.repair_switch_costs(op)
    assert op["equity"] == again["equity"] and len(op["corrections"]) == 1, "두 번 고쳤다"


def test_a_normal_switch_is_left_alone():
    op = {"start_cash": 10_000.0, "equity": 9_995.0, "cost_paid": 5.0,
          "switches": [{"on": "2026-10-13", "cost": 5.0}],
          "history": [{"date": "2026-10-12", "equity": 10_000.0},
                      {"date": "2026-10-13", "equity": 9_995.0, "day_ret": 0.0}]}
    F.repair_switch_costs(op)
    assert op["equity"] == 9_995.0 and not op.get("corrections")


def test_the_card_says_it_was_corrected():
    from pathlib import Path
    js = (Path(__file__).resolve().parent.parent / "docs" / "assets" / "operated.js").read_text("utf-8")
    assert "op.corrections" in js and "c.was_cost" in js and "c.switch_on" in js
