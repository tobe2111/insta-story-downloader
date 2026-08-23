"""판 시점에 얼마를 벌었는지 말한다 (감사 300).

사장님 요청(2026-08-22): *"매도 시점에 얼마의 수익 혹은 손해가 났는지도
써줘야지 최근 체결 부분에다가."*

예전 체결 기록에는 "얼마어치 샀다/팔았다"만 있었다. 그래서 체결 표를 봐도
**그 매도가 이익 실현인지 손절인지 알 수가 없었다.** 장부가 평균 매입가를
안 들고 다녔기 때문이다.

    실현 손익 = 판 수량 × (판 가격 − 평균 매입가) − 그 거래의 비용

⚠️ **비용을 뺀 뒤**의 값이다. "팔아서 100 벌었는데 수수료로 120을 냈다"면
   그 매도는 이익이 아니다.
⚠️ 옛 기록에는 이 값이 없다 — 그때 안 셌으므로. 과거는 고치지 않고 화면이
   '—'로 비운다. 0과 '모른다'는 다른 사건이다.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.intraday_challenger import _execute_targets  # noqa: E402

_SIDE = 0.0015          # 편도 비용


def _account(cash=10_000.0):
    return {"cash": cash, "positions": {}, "cost_paid": 0.0}


def test_a_profitable_sale_reports_the_profit_after_cost():
    st = _account()
    buy = _execute_targets(st, {"X": 1.0}, {"X": 100.0}, 10_000.0, 1.0,
                           _SIDE, universe=["X"])[0]
    assert "realized_pnl" not in buy, "매수에는 실현 손익이 없다(아직 확정 전)"
    assert st["avg_cost"]["X"] == 100.0

    sell = _execute_targets(st, {"X": 0.0}, {"X": 110.0}, 11_000.0, 1.0,
                            _SIDE, universe=["X"])[0]
    # ⚠️ 기록의 notional은 소수 2자리로 반올림돼 있다 — 장부는 반올림 없이
    #    굴러가므로, 되짚은 값과 마지막 자리가 다를 수 있다. 지키는 것은
    #    식이지 반올림이 아니다.
    qty = buy["notional"] / 100.0
    want = qty * (110.0 - 100.0) - sell["cost"]
    assert abs(sell["realized_pnl"] - want) < 0.01, (sell["realized_pnl"], want)
    assert sell["realized_pnl"] > 0
    assert sell["avg_cost"] == 100.0, "무엇과 비교했는지도 남겨야 한다"


def test_a_losing_sale_reports_the_loss():
    st = _account()
    _execute_targets(st, {"X": 1.0}, {"X": 100.0}, 10_000.0, 1.0,
                     _SIDE, universe=["X"])
    sell = _execute_targets(st, {"X": 0.0}, {"X": 90.0}, 9_000.0, 1.0,
                            _SIDE, universe=["X"])[0]
    assert sell["realized_pnl"] < 0, sell


def test_a_tiny_gain_eaten_by_cost_is_not_a_gain():
    """대조군 — 비용을 못 넘는 상승은 **손해**로 적혀야 한다.

    이 검사가 없으면 '판 가격 > 산 가격'만 보고 이익이라 적는 고장이
    통과한다. 그게 이 저장소가 계속 잡아 온 착시다.
    """
    st = _account()
    _execute_targets(st, {"X": 1.0}, {"X": 100.0}, 10_000.0, 1.0,
                     _SIDE, universe=["X"])
    # +0.1% 상승 — 왕복 0.3%를 못 넘는다
    sell = _execute_targets(st, {"X": 0.0}, {"X": 100.1}, 10_010.0, 1.0,
                            _SIDE, universe=["X"])[0]
    assert sell["price"] > 100.0, "전제: 가격은 올랐다"
    assert sell["realized_pnl"] < 0, (
        f"올랐다고 이익으로 적었다 — 비용을 안 뺐다: {sell}")


def test_the_average_cost_follows_repeated_buys():
    """두 번 나눠 사면 평균이 잡혀야 한다 — 마지막 가격이 아니라."""
    st = _account(cash=100_000.0)
    _execute_targets(st, {"X": 1.0}, {"X": 100.0}, 10_000.0, 1.0,
                     _SIDE, universe=["X"])
    assert st["avg_cost"]["X"] == 100.0
    # 목표를 키워 **더 산다** — 이번엔 120원에.
    _execute_targets(st, {"X": 1.0}, {"X": 120.0}, 30_000.0, 1.0,
                     _SIDE, universe=["X"])
    avg = st["avg_cost"]["X"]
    assert 100.0 < avg < 120.0, f"평균이 아니라 한쪽 값이다: {avg}"


def test_selling_everything_forgets_the_average():
    """다 팔면 단가도 지운다 — 다음에 살 때 옛 단가가 섞이면 안 된다."""
    st = _account()
    _execute_targets(st, {"X": 1.0}, {"X": 100.0}, 10_000.0, 1.0,
                     _SIDE, universe=["X"])
    _execute_targets(st, {"X": 0.0}, {"X": 110.0}, 11_000.0, 1.0,
                     _SIDE, universe=["X"])
    assert "X" not in (st.get("avg_cost") or {}), st.get("avg_cost")


def test_the_screen_has_a_place_to_show_it():
    """화면에 실현 손익 칸이 있고, **공용 렌더러**가 그것을 그린다.

    ⚠️ 예전의 이 검사는 페이지 소스에서 글자를 찾았다("t.realized_pnl이
       있나", "(r==null)이 있나"). 그리기가 공용 렌더러로 옮겨 간 순간
       (2026-08-23) 그 검사는 통째로 헛짚었다 — 화면은 멀쩡한데 검사만
       빨간불이었다. 소스를 읽는 검사는 코드가 움직이면 따라오지 못한다.

    그래서 여기서는 **칸이 있는지와 렌더러를 부르는지**만 본다. 값이
    없을 때 '—'로 비우는지는 실제로 브라우저에서 그려 보는 검사가
    확인한다(tests/test_every_track_shows_what_it_bought.py).
    """
    page = (ROOT / "docs" / "intraday.html").read_text("utf-8")
    assert "실현 손익" in page, "체결 표에 실현 손익 열이 없다"
    assert "assets/trades.js" in page, "공용 체결 렌더러를 안 부른다"
    assert (ROOT / "docs" / "assets" / "trades.js").exists(), (
        "공용 체결 렌더러 파일이 없다 — 페이지가 부르는 것이 빈 파일이다")
