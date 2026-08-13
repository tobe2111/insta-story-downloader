"""입금이 실력으로 보이지 않는가 — 조종석(감사 197).

사이트 입금 안내문은 **"입금이 실력처럼 보이지 않습니다"**라고 약속한다.
장부(`live/daily.py`)는 그 약속을 지키고 있었다 — `twr_index`가 입금액을
구간수익에서 빼고 연쇄 곱한다. **조종석만 그 약속 밖에 있었다.**

    pnl = cur / start - 1.0

자산 곡선을 그대로 읽으므로 원금을 넣으면 그게 통째로 수익이 된다.
실측(2026-08-13, 고치기 전):

    8만원 → (92만원 입금) → 95만원
    화면   : 손익 **+1087.50%**
    사실   : 100만 → 95만 = **-5.00%**

낙폭도 같이 거짓이 된다. 입금이 고점을 끌어올려 **그 직전의 손실이 낙폭에서
지워진다** — 감사 ㊿에서 킬스위치가 입금 때문에 풀리던 것과 같은 계열이고,
`twr_index` 독스트링이 "낙폭도 이 지수 위에서 재야 한다"고 이미 적어 둔
내용이다. 두 곳 중 한 곳만 그 말을 따르고 있었다.

이 파일은 8마일 챌린지에서 **실제로 일어날 일**을 검사한다: 원금 8만원 →
100만원 전환을 위한 92만원 매칭 입금.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.reporting.dashboard import build_dashboard_html  # noqa: E402

DEPOSIT = [{"date": "2026-08-12", "amount": 920_000}]


def _shown(state: dict) -> list[str]:
    """조종석 화면에 실제로 찍히는 퍼센트 값들(순서대로 손익·낙폭…)."""
    return re.findall(r'>\s*([+\-]?[\d,\.]+%)\s*<', build_dashboard_html(state))


def _hist(*pairs) -> list[dict]:
    return [{"time": t, "equity": e, "price": 1.0, "weight": 0.5}
            for t, e in pairs]


def test_a_deposit_is_not_profit():
    """92만원을 넣은 것이 +1087%짜리 실력으로 찍히면 안 된다."""
    state = {"history": _hist(("2026-08-11", 80_000),
                              ("2026-08-12", 1_000_000),
                              ("2026-08-13", 950_000)),
             "deposits": DEPOSIT}
    pnl = _shown(state)[0]
    assert pnl == "-5.00%", f"입금이 수익으로 잡혔다: {pnl}"

    # 대조군 — 같은 자산 곡선인데 입금 기록이 없으면 그건 진짜 실력이다.
    # 이게 없으면 위 단언은 "무조건 -5%를 찍는" 망가진 화면도 통과시킨다.
    real = _shown({"history": state["history"]})[0]
    assert real.startswith("+") and float(real.strip("+%").replace(",", "")) > 1000


def test_a_deposit_cannot_erase_a_drawdown():
    """입금이 고점을 끌어올려 그 전의 손실을 지우면 안 된다.

    8만 → 6만(-25%) → 92만원 입금 후 98만. 자산 고점으로 재면 98만이 새
    고점이라 낙폭이 0에 가깝게 보인다. 시간가중 지수 위에서는 -25%가 남는다.
    """
    state = {"history": _hist(("2026-08-10", 80_000),
                              ("2026-08-11", 60_000),
                              ("2026-08-12", 980_000)),
             "deposits": DEPOSIT}
    pnl, dd = _shown(state)[:2]
    assert pnl == "-25.00%", f"입금 뒤 손익이 실력을 안 보여준다: {pnl}"
    assert dd == "-25.00%", f"입금이 낙폭을 지웠다: {dd}"


def test_without_a_deposit_the_numbers_are_unchanged():
    """대조군 — 입금이 없으면 계산을 바꿀 이유가 없다.

    입금 기록이 없을 때 지수는 자산 곡선과 같으므로, 이 교정이 평소의
    수익률을 건드리지 않는다는 것을 못 박는다(고치면서 다른 걸 망가뜨리지
    않았는가).
    """
    hist = _hist(("2026-08-11", 100_000), ("2026-08-12", 120_000))
    assert _shown({"history": hist})[0] == "+20.00%"
    assert _shown({"history": hist, "deposits": []})[0] == "+20.00%"


def test_a_deposit_before_any_record_does_not_break_the_screen():
    """경계 — 첫 기록보다 앞선 입금, 기록 하나뿐, 빈 기록."""
    for state in (
        {"history": _hist(("2026-08-12", 1_000_000)), "deposits": DEPOSIT},
        {"history": _hist(("2026-08-01", 80_000)),
         "deposits": [{"date": "2026-07-01", "amount": 920_000}]},
        {"history": [], "deposits": DEPOSIT},
    ):
        html = build_dashboard_html(state)
        assert "nan" not in html.lower() and "inf" not in html.lower(), html[:200]


def test_the_cockpit_agrees_with_the_ledger():
    """장부와 조종석이 **같은 숫자**를 말하는가(㉞ — 갈라지면 언젠가 들킨다).

    조종석은 기록을 `{"time": ...}`로, 장부는 `{"date": ...}`로 쓴다. 모양이
    다르다는 이유로 각자 계산하면 두 화면이 다른 수익률을 말하게 된다.
    같은 사실에 대해 같은 답이 나오는지 직접 맞춰 본다.
    """
    from quant.live.daily import time_weighted_return
    rows = [("2026-08-11", 80_000), ("2026-08-12", 1_000_000),
            ("2026-08-13", 950_000)]
    cockpit = _shown({"history": _hist(*rows), "deposits": DEPOSIT})[0]
    ledger = time_weighted_return(
        [{"date": d, "equity": e} for d, e in rows], DEPOSIT, start_cash=80_000)
    assert cockpit == f"{ledger:+.2f}%", f"조종석 {cockpit} vs 장부 {ledger:+.2f}%"
