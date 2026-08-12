"""사지 않은 종목을 "매수"라고 방송하지 않는가 (감사 91).

포트폴리오 장부에는 비슷하게 생긴 숫자가 두 개 있다.

    "alloc":  {"us_stock:QQQ": 0.0802, ...}   ← **배분 예산**(슬라이스)
    "weight": 0.0684                          ← 실제 적용 총노출

`alloc`은 예산이라 **모델이 관망한 종목에도 붙어 있다.** 그런데 SNS 카드가
그 값을 그대로 "매수 8%"라고 찍었고, 캡션의 "오늘 배분 상위"도 alloc 상위를
그대로 불렀다.

2026-08-10 실제 장부:

    state/paper/us_stock_QQQ.json → weight 0.0, reason "관망 (현금)"
    portfolio_ALL fills           → us_stock:QQQ weight 0.0
    portfolio_ALL alloc           → us_stock:QQQ 0.0802

즉 **한 주도 사지 않은 종목이 "매수 8%"로 공개되는 구조**였다. 같은 게시물
캡션은 "총노출 7%"라고 말한다 — 한 종목이 전체 노출보다 크다는, 그 자체로
성립하지 않는 조합이다.

이 프로젝트는 "잘된 날만 골라 올리지 않는다"를 내세운다. 그 약속은 숫자의
**정의**가 정확할 때만 지켜진다. 여기서 고정하는 계약:

  ① 장부는 종목별 '실제 적용 노출'(`applied`)을 남긴다 — 합은 총노출이다.
  ② 캡션·카드는 그날 실제로 든 종목만 말한다. `applied`가 없는 옛 기록은
     종목 장부의 비중이 0인 종목을 뺀다(과거는 고치지 않는다).
  ③ 카드는 배분 예산을 "매수"라고 부르지 않는다.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.reporting.social import _today_numbers   # noqa: E402

CARD = ROOT / "docs" / "sns_card.html"


def _status(*, alloc, applied=None, per_symbol, date="2026-08-10"):
    paper = {"portfolio:ALL": {"history": [{
        "date": date, "equity": 80000.0, "return_pct": 0.0, "weight": 0.07,
        "alloc": alloc, "applied": applied, "risk_scale": 1.0,
    }]}}
    for k, w in per_symbol.items():
        paper[k] = {"history": [{"date": date, "weight": w}]}
    return {"updated": date + "T00:00:00Z", "paper": paper,
            "symbols": {k: {"name": k.split(":")[-1]} for k in alloc}}


# ── ② 관망 종목은 방송에 오르지 않는다 ─────────────────────────

def test_a_symbol_the_model_stood_aside_on_is_not_called_a_holding():
    """예산은 컸지만 비중 0(관망)인 종목 — 캡션에 이름이 오르면 안 된다."""
    st = _status(alloc={"us_stock:QQQ": 0.0802, "us_stock:AAPL": 0.15},
                 per_symbol={"us_stock:QQQ": 0.0, "us_stock:AAPL": 0.1235})
    names = _today_numbers(st)["top_names"]
    assert "QQQ" not in names, (
        "장부가 '관망 (현금)'이라 적은 종목을 '오늘 배분 상위'로 방송한다 — "
        f"한 주도 사지 않았다 ({names})")
    assert "AAPL" in names


def test_all_cash_days_say_so():
    """전 종목 관망이면 상위 목록은 비어야 한다(캡션이 '전 종목 관망'을 쓴다)."""
    st = _status(alloc={"us_stock:QQQ": 0.5, "us_stock:AAPL": 0.5},
                 per_symbol={"us_stock:QQQ": 0.0, "us_stock:AAPL": 0.0})
    assert _today_numbers(st)["top_names"] == []


def test_a_symbol_with_no_ledger_entry_is_not_claimed():
    """그날 기록이 없는 종목을 '샀다'고 말하지 않는다(모르면 말하지 않는다)."""
    st = _status(alloc={"us_stock:AAPL": 0.15}, per_symbol={})
    assert _today_numbers(st)["top_names"] == []


# ── ① applied가 있으면 그걸 쓴다 ────────────────────────────────

def test_applied_is_preferred_when_present():
    """새 장부에는 종목별 실제 노출이 있다 — 그게 우선이다."""
    st = _status(alloc={"us_stock:QQQ": 0.5, "us_stock:AAPL": 0.1},
                 applied={"us_stock:AAPL": 0.012},
                 per_symbol={"us_stock:QQQ": 0.0, "us_stock:AAPL": 0.1235})
    assert _today_numbers(st)["top_names"] == ["AAPL"]


def test_applied_sums_to_the_recorded_gross(tmp_path):
    """종목별 노출의 합은 총노출이어야 한다 — 아니면 둘 중 하나가 거짓말이다.

    ⚠️ 예전 판은 소스에 특정 식(`gross = sum(_applied(...))`)이 있는지만
       봤다. 그런 검사는 **식이 바뀌면 깨지고, 값이 어긋나도 모른다** —
       2026-08-12에 예산 규칙(_fit_to_budget)을 넣으며 계산을 한 곳으로
       모으자 이 검사가 깨졌는데, 정작 확인해야 할 '두 숫자가 같은가'는
       한 번도 보지 않고 있었다.
       이제 **진짜 배치를 돌려 장부의 두 숫자를 비교한다.**
    """
    import json

    from quant.live.daily import run_daily_portfolio
    from quant.live.retrain import save_champions
    d = str(tmp_path)
    save_champions({f"synthetic:G{i}": {"strategy": "ma_cross",
                                        "params": {"fast": 10, "slow": 30},
                                        "promotions": 0} for i in range(3)}, d)
    p = tmp_path / "paper"
    p.mkdir(parents=True, exist_ok=True)
    (p / "portfolio_ALL.json").write_text(json.dumps({
        "market": "portfolio", "symbol": "ALL", "start_cash": 1_000_000.0,
        "cash": 1_000_000.0, "positions": {}, "base_prices": {},
        "last_bar": None, "history": [],
    }), encoding="utf-8")
    rec = run_daily_portfolio([("synthetic", f"G{i}") for i in range(3)],
                              lookback=200, state_dir=d,
                              require_real_data=False)
    parts = sum((rec.get("applied") or {}).values())
    assert rec["weight"] > 0, "총노출이 0이면 이 비교가 헛것이 된다"
    assert abs(rec["weight"] - parts) < 1e-3, (
        f"총노출 {rec['weight']} vs 종목별 합 {parts:.4f} — 둘이 갈라졌다")


def test_the_record_carries_applied():
    """장부 스키마에 종목별 노출이 실제로 들어가는가."""
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert '"applied": applied or None,' in src


# ── ③ 카드가 예산을 '매수'라 부르지 않는다 ─────────────────────

def test_the_card_does_not_label_the_budget_as_a_purchase():
    card = CARD.read_text("utf-8")
    assert "'<span class=\"w\">매수 '" not in card, (
        "카드가 배분 예산을 '매수 N%'라고 찍는다 — 관망 종목까지 샀다고 말한다")
    assert "wLabel" in card, "카드가 숫자의 이름(노출/배분)을 구분하지 않는다"


def test_the_card_filters_by_the_symbol_ledger_for_old_records():
    """옛 기록 경로에도 '그날 실제로 들었나' 확인이 있어야 한다."""
    card = CARD.read_text("utf-8")
    assert "function heldOn(" in card
    assert "last.applied" in card


# ── 실제 저장된 장부로 한 번 더 ────────────────────────────────

def test_the_real_ledger_does_not_advertise_a_stand_aside():
    """저장된 진짜 기록으로 돌려도 관망 종목이 안 나가야 한다."""
    docs_status = ROOT / "docs" / "status.json"
    if not docs_status.exists():                     # 배포 전 체크아웃
        return
    st = json.loads(docs_status.read_text("utf-8"))
    port = (st.get("paper") or {}).get("portfolio:ALL") or {}
    hist = port.get("history") or []
    if not hist:
        return
    got = _today_numbers(st)
    date = got["date"]
    for name in got["top_names"]:
        keys = [k for k, v in (st.get("symbols") or {}).items()
                if (v.get("name") or k.split(":")[-1]) == name]
        for k in keys:
            h = ((st.get("paper") or {}).get(k) or {}).get("history") or []
            recs = [r for r in h if r.get("date") == date]
            if recs:
                assert float(recs[-1].get("weight") or 0) > 0, (
                    f"{date} 캡션이 '{name}'을 배분 상위로 말하는데 그 종목 "
                    f"장부의 비중은 {recs[-1].get('weight')}다 — 관망이었다")
