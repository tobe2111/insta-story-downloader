"""입금이 **손실로 보이지 않는가** (감사 211).

2026-08-13, 사장님이 실제로 920,000원을 넣었다. 장부는 맞았는데 화면이 이랬다:

    원금 80,000 → 1,000,000원   (입금은 즉시 현금이 된다)
    자산 79,250원                (마지막 새벽 배치가 남긴 08-12 기록 그대로)
    ─────────────────────────
    화면 손익  **-920,749원**
    사실       -749원

감사 197의 정확한 **거울상**이다. 그때는 입금이 수익(+1087.50%)으로 보였고,
여기서는 손실로 보인다. 원인은 같은 하나 — **자산과 원금을 서로 다른 시점에서
재는 것.** 197에서 수익률 계산은 고쳤지만, `원금 = 시작금 + 입금 전부`라는
식은 네 곳에 그대로 남아 있었다(장부 기록·status.json·조종석·후원 페이지).

날짜 비교로는 못 고친다. 기록 날짜는 **마지막 완성 봉**이라 달력보다 뒤처지고
(주말·휴장이면 며칠), 그렇다고 날짜로 잘라내면 배치가 그 현금을 포함해 자산을
계산한 뒤에도 원금에서 빠져 이번엔 **+1149%**가 뜬다. 그래서 날짜가 아니라
사실을 적는다 — 자산을 다시 잰 배치가 봉 이름을 찍는다(`settled_bar`).

이 파일은 양쪽 방향을 다 막는다: 반영 전엔 원금이 안 뛰고(손실 방지), 반영
후엔 반드시 뛴다(수익 착시 방지). 한쪽만 검사하면 나머지 한쪽으로 무너진다.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from quant.live.ledger_basics import (
    is_settled,
    pending_deposits,
    principal_of,
    settled_deposits,
    twr_index,
)

ROOT = Path(__file__).resolve().parent.parent


def _dep(amount, date, settled_bar=None):
    d = {"date": date, "amount": float(amount), "memo": ""}
    if settled_bar:
        d["settled_bar"] = settled_bar
    return d


# ── 원금의 시점 ────────────────────────────────────────────────

def test_an_unsettled_deposit_does_not_raise_the_principal():
    """반영 전 입금은 원금에 들어가지 않는다 — 들어가면 그대로 손실이 된다."""
    deps = [_dep(920_000, "2026-08-13")]
    assert principal_of(80_000, deps) == 80_000
    equity_of_record = 79_250.68            # 08-12 배치가 남긴 자산
    pnl = equity_of_record - principal_of(80_000, deps)
    assert -1000 < pnl < 0, f"입금이 손실로 잡혔다 — 손익 {pnl:,.0f}원"


def test_a_settled_deposit_does_raise_the_principal():
    """대조군 — 반영된 뒤에는 반드시 원금에 들어가야 한다.

    이게 없으면 위 검사는 "원금을 아예 안 세는" 코드도 통과시킨다. 그러면
    92만원이 통째로 수익으로 기록된다(감사 197이 잡았던 바로 그 거짓말).
    """
    deps = [_dep(920_000, "2026-08-13", settled_bar="2026-08-13")]
    assert principal_of(80_000, deps) == 1_000_000
    pnl = 999_250.0 - principal_of(80_000, deps)
    assert -1000 < pnl < 0, f"반영 후 원금이 안 올라갔다 — 손익 {pnl:,.0f}원"


def test_settled_and_pending_split_covers_every_deposit():
    deps = [_dep(1_000, "2026-08-01", settled_bar="2026-08-01"),
            _dep(920_000, "2026-08-13")]
    assert [d["amount"] for d in settled_deposits(deps)] == [1_000.0]
    assert [d["amount"] for d in pending_deposits(deps)] == [920_000.0]
    assert len(settled_deposits(deps)) + len(pending_deposits(deps)) == len(deps)
    assert is_settled(deps[0]) and not is_settled(deps[1])


# ── TWR도 같은 함정에 빠진다 ──────────────────────────────────

def test_twr_attributes_the_flow_to_the_bar_that_absorbed_it():
    """봉 날짜가 **입금 날짜보다 앞설 때** 흐름이 사라지면 안 된다.

    기록의 날짜는 마지막 **완성 봉**이라 달력보다 뒤처진다. 08-13 새벽에
    돌아간 배치가 08-12 봉으로 기록을 남기면, 같은 날 08-13에 접수된 입금은
    그 기록의 자산에 이미 들어가 있는데도 날짜상으론 '미래'다.

    옛 규칙(입금 날짜 이후 첫 기록일)으로는 귀속처를 **못 찾아** 흐름이
    통째로 무시되고, 자산만 92만원 뛴 것으로 보여 실력이 +1149%로 남는다.
    배치가 찍어 준 봉 이름을 쓰면 정확히 그 봉으로 들어간다.
    """
    hist = [{"date": "2026-08-11", "equity": 80_000.0},
            {"date": "2026-08-12", "equity": 999_250.0}]   # 입금 포함해 다시 잼
    deps = [_dep(920_000, "2026-08-13", settled_bar="2026-08-12")]
    idx = twr_index(hist, deps, start_cash=80_000.0)
    growth_pct = (idx[-1] - 1) * 100
    assert -3 < growth_pct < 3, (
        f"입금이 실력으로 기록됐다 — 성장 지수 {growth_pct:,.1f}%")


def test_twr_without_a_settled_bar_still_uses_the_date():
    """대조군 — 도장이 없는 옛 기록도 예전처럼 날짜로 귀속돼야 한다."""
    hist = [{"date": "2026-08-12", "equity": 80_000.0},
            {"date": "2026-08-13", "equity": 1_000_000.0}]
    deps = [_dep(920_000, "2026-08-13")]          # settled_bar 없음
    idx = twr_index(hist, deps, start_cash=80_000.0)
    assert abs((idx[-1] - 1) * 100) < 0.5, (idx, "옛 경로가 깨졌다")


# ── 정산 도장은 배치가 찍는다 ────────────────────────────────

def test_only_one_place_in_the_code_may_stamp_a_deposit():
    """도장을 찍는 자리는 **자산을 다시 재는 배치 한 곳뿐**이어야 한다.

    다른 데서 찍으면 아무도 안 센 돈이 원금이 되어 손실로 둔갑한다.
    """
    import ast

    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    stamps = [n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.Subscript)
              and isinstance(n.slice, ast.Constant)
              and n.slice.value == "settled_bar"
              and isinstance(getattr(n, "ctx", None), ast.Store)]
    assert len(stamps) == 1, (
        f"settled_bar를 찍는 자리가 {len(stamps)}곳이다 — 자산을 다시 재지 "
        "않는 곳에서 찍으면 반영되지 않은 돈이 원금이 된다")


def test_the_batch_actually_stamps_and_books_the_deposit(tmp_path):
    """**진짜 배치를 돌려서** 도장이 찍히고 원금이 오르는지 본다.

    위 검사는 '찍는 자리가 하나'인 것만 본다 — 그 자리를 통째로 죽여도
    통과한다. 그러면 입금이 영원히 '접수됨'으로 남아 현금은 늘었는데 원금은
    8만원 그대로, 즉 92만원이 **수익**으로 찍힌다(감사 197로 되돌아간다).
    한 방향만 막으면 반드시 반대쪽으로 무너진다.
    """
    from quant.live.daily import add_deposit, run_daily_portfolio
    from quant.live.retrain import save_champions

    d = str(tmp_path)
    save_champions({"synthetic:DEMO": {"strategy": "ma_cross",
                                       "params": {"fast": 10, "slow": 30},
                                       "promotions": 0}}, d)
    add_deposit(20_000, "배치 반영 시험", state_dir=d)
    led = tmp_path / "paper" / "portfolio_ALL.json"
    assert json.loads(led.read_text("utf-8"))["deposits"][0].get(
        "settled_bar") is None, "배치 전인데 이미 도장이 찍혀 있다"

    run_daily_portfolio([("synthetic", "DEMO")], lookback=200, state_dir=d,
                        require_real_data=False)

    st = json.loads(led.read_text("utf-8"))
    dep = st["deposits"][0]
    assert dep.get("settled_bar"), "배치가 돌았는데 입금이 반영 표시가 안 됐다"
    assert dep["amount"] == 20_000 and dep["memo"] == "배치 반영 시험", (
        "정산 표시가 금액·메모를 건드렸다 — 과거를 고치지 않는다")

    rec = st["history"][-1]
    assert dep["settled_bar"] == rec["date"], "도장이 그 봉 이름이 아니다"
    from quant.live.ledger_basics import PORTFOLIO_START_CASH as SC
    assert rec["principal"] == SC + 20_000, (
        f"반영 후 원금이 {SC + 20_000:,.0f}원이 아니다"
        f"({rec['principal']:,.0f}원) — 입금이 수익으로 찍힌다")
    # 하루 만에 크게 벌거나 잃을 리 없다. 원금이 틀리면 여기서 폭발한다.
    assert abs(rec["pnl"]) < 20_000, f"손익이 {rec['pnl']:,.0f}원이다"


def test_add_deposit_leaves_the_money_unsettled(tmp_path):
    """입금 명령 자체는 도장을 찍지 않는다 — 아직 아무도 자산을 안 쟀다."""
    from quant.live.ledger_basics import PORTFOLIO_START_CASH as SC
    from quant.live.ledger_basics import add_deposit

    (tmp_path / "paper").mkdir()
    out = add_deposit(10_000, memo="테스트", state_dir=str(tmp_path))
    st = json.loads((tmp_path / "paper" / "portfolio_ALL.json").read_text("utf-8"))
    assert st["deposits"][-1].get("settled_bar") is None
    assert st["cash"] == pytest.approx(SC + 10_000)   # 현금에는 즉시 들어간다
    # 화면용 원금(반영분)과 접수 총액을 구분해 돌려줘야 한다
    assert out["principal"] == SC and out["committed"] == SC + 10_000


# ── 네 화면이 같은 원금을 말하는가 ────────────────────────────

def test_no_screen_adds_up_every_deposit_by_hand():
    """`시작금 + 입금 전부`를 손으로 더하는 자리가 남아 있으면 안 된다.

    이 식이 네 곳에 복사돼 있었기 때문에 한 곳을 고쳐도 나머지가 거짓말을
    했다. 계산은 `principal_of` 하나로만 한다(형제 찾기).
    """
    import ast

    offenders = []
    for rel in ("quant/live/daily.py", "quant/web/app.py",
                "quant/reporting/dashboard.py"):
        p = ROOT / rel
        if not p.exists():
            continue
        for node in ast.walk(ast.parse(p.read_text("utf-8"))):
            # sum(... for d in <무언가>.deposits ...) 형태를 찾는다
            if not isinstance(node, ast.Call):
                continue
            if not (isinstance(node.func, ast.Name) and node.func.id == "sum"):
                continue
            src = ast.unparse(node)
            if "deposits" not in src:
                continue
            # 정산 여부를 거르지 않고 전부 더하는 것만 문제 삼는다
            if "settled" in src or "_flow_date" in src or "committed" in src:
                continue
            offenders.append(f"{rel}:{node.lineno} — {src}")
    assert not offenders, (
        "입금을 통째로 더해 원금을 만드는 자리가 남아 있다 "
        "(반영 전 입금이 손익에 섞인다):\n  " + "\n  ".join(offenders))


def test_the_site_discloses_a_pending_deposit():
    """반영 전 입금은 화면에서 **말해야** 한다 — 숨기면 '넣었는데 그대로'가 된다."""
    html = (ROOT / "docs" / "index.html").read_text("utf-8")
    assert "pending_deposits" in html, "사이트가 접수분을 읽지 않는다"
    assert "다음 새벽 배치" in html


def test_status_json_publishes_pending_deposits(tmp_path):
    """status.json이 접수분을 **실제로** 싣는가.

    글자가 소스에 있는지 보는 것으로는 부족하다 — 그 줄이 죽어 있어도
    글자는 남는다(감사 183·199·204에서 반복해 겪은 자리). 만들어 보고 읽는다.
    """
    import quant.live.daily as dl

    dl.add_deposit(920_000, "원금 증액", state_dir=str(tmp_path),
                   date="2026-08-13")
    p = tmp_path / "paper" / "portfolio_ALL.json"
    st = json.loads(p.read_text("utf-8"))
    st["history"] = [{"date": "2026-08-12", "equity": 79_250.68,
                      "return_pct": -0.94, "price": 98.96, "weight": 0.32}]
    p.write_text(json.dumps(st), encoding="utf-8")

    pf = dl.write_docs_status(str(tmp_path),
                              docs_path=str(tmp_path / "s.json"))
    pf = pf["paper"]["portfolio:ALL"]
    assert [d["amount"] for d in pf.get("pending_deposits") or []] == [920_000.0], (
        "접수된 입금이 사이트로 안 나간다 — 사장님 화면에는 '넣었는데 그대로'만 "
        "보이고 이유는 어디에도 없다")


def test_a_settled_deposit_is_not_advertised_as_pending(tmp_path):
    """대조군 — 반영이 끝난 입금까지 '대기 중'이라 하면 안 된다."""
    import quant.live.daily as dl

    dl.add_deposit(10_000, "옛 입금", state_dir=str(tmp_path), date="2026-08-05")
    p = tmp_path / "paper" / "portfolio_ALL.json"
    st = json.loads(p.read_text("utf-8"))
    st["deposits"][0]["settled_bar"] = "2026-08-05"
    SC = dl.PORTFOLIO_START_CASH
    st["history"] = [{"date": "2026-08-05", "equity": SC + 10_000 + 500,
                      "return_pct": 0.56, "price": 100, "weight": 0.5}]
    p.write_text(json.dumps(st), encoding="utf-8")

    pf = dl.write_docs_status(str(tmp_path),
                              docs_path=str(tmp_path / "s.json"))["paper"]["portfolio:ALL"]
    assert "pending_deposits" not in pf
    assert pf["principal"] == SC + 10_000 and pf["pnl"] == 500


# ── 이 계산도 무거운 의존성 없이 (감사 102 계열) ────────────────

def test_the_principal_math_needs_no_numpy():
    """입금 워크플로는 가벼운 경로로도 원금을 말할 수 있어야 한다."""
    blocker = textwrap.dedent("""
        import sys
        HEAVY = ("numpy", "pandas", "sklearn", "scipy")

        class _Block:
            def find_spec(self, name, path=None, target=None):
                if name.split(".")[0] in HEAVY:
                    raise ModuleNotFoundError(f"No module named '{name}'")
                return None

        sys.meta_path.insert(0, _Block())
        from quant.live.ledger_basics import principal_of, pending_deposits
        deps = [{"date": "2026-08-13", "amount": 920000.0, "memo": ""}]
        assert principal_of(80000, deps) == 80000
        assert len(pending_deposits(deps)) == 1
        print("OK")
    """)
    r = subprocess.run([sys.executable, "-c", blocker], cwd=str(ROOT),
                       capture_output=True, text=True, timeout=180)
    assert r.returncode == 0 and "OK" in r.stdout, r.stderr[-2000:]


# ── 잔고 표: 표가 스스로 모순되지 않는가 ──────────────────────

def test_the_holdings_table_adds_up_to_the_account(tmp_path):
    """보유 + 현금 = 자산. 표가 스스로 안 맞으면 아무도 안 믿는다.

    ⚠️ 감사 211이 **여기서 한 번 더** 나온다. 장부의 cash에는 아직 반영되지
    않은 입금이 이미 들어 있어서, 그대로 실으면 이렇게 된다:

        보유 37,341 + 현금 961,910 = 999,251  ≠  자산 79,251
        현금 비중 **1213%**

    같은 결함이 원금·TWR·현금 세 자리에서 나왔다 — 자산과 다른 시점의
    숫자를 나란히 놓으면 어디서든 터진다.
    """
    import quant.live.daily as dl

    dl.add_deposit(920_000, "원금 증액", state_dir=str(tmp_path),
                   date="2026-08-13")
    p = tmp_path / "paper" / "portfolio_ALL.json"
    st = json.loads(p.read_text("utf-8"))
    st["positions"] = {
        "us_stock:SPY": {"quantity": 12.0, "avg_price": 774.7,
                         "last_price": 772.49, "last_price_bar": "2026-08-12"},
        "crypto:XRP/USDT": {"quantity": 2000.0, "avg_price": 1.02,
                            "last_price": 1.0082,
                            "last_price_bar": "2026-08-12"}}
    held = 12.0 * 772.49 + 2000.0 * 1.0082
    st["cash"] = 41_909.59 + 920_000.0            # 입금이 이미 섞인 현금
    st["history"] = [{"date": "2026-08-12", "equity": round(41_909.59 + held, 2),
                      "return_pct": -0.94, "price": 98.96, "weight": 0.32}]
    p.write_text(json.dumps(st), encoding="utf-8")

    pf = dl.write_docs_status(str(tmp_path),
                              docs_path=str(tmp_path / "s.json"))["paper"]["portfolio:ALL"]
    total = sum(r["value"] for r in pf["holdings"]) + pf["cash"]
    assert abs(total - pf["equity"]) < 1.0, (
        f"잔고 표의 합({total:,.0f})이 자산({pf['equity']:,.0f})과 다르다")
    assert pf["cash"] == pytest.approx(41_909.59, abs=0.01), (
        "반영 전 입금이 현금에 섞여 나갔다 — 현금 비중이 100%를 넘는다")


def test_the_holdings_table_reports_cost_and_pnl_per_symbol():
    """종목마다 매입금액·평가금액·평가손익·수익률이 나와야 한다."""
    from quant.live.ledger_basics import holdings_view

    st = {"cash": 1000.0, "positions": {
        "us_stock:SPY": {"quantity": 10.0, "avg_price": 100.0,
                         "last_price": 110.0, "last_price_bar": "2026-08-12"}}}
    (row,) = holdings_view(st)
    assert row["cost"] == 1000.0 and row["value"] == 1100.0
    assert row["pnl"] == 100.0 and row["pnl_pct"] == 10.0
    assert row["weight"] == pytest.approx(1100.0 / 2100.0)
    assert row["as_of"] == "2026-08-12" and row["marked"] is True


def test_a_symbol_without_a_price_is_flagged_not_silently_flat():
    """시세를 못 받은 종목은 매입가로 평가된다 — 그 사실을 표시해야 한다.

    감사 152와 같은 자리다. 손익 0은 '안 움직였다'가 아니라 '모른다'일 수
    있는데, 표시가 없으면 둘을 구별할 방법이 없다.
    """
    from quant.live.ledger_basics import holdings_view

    st = {"cash": 0.0, "positions": {
        "kr_stock:005930.KS": {"quantity": 1.0, "avg_price": 236000.0}}}
    (row,) = holdings_view(st)
    assert row["marked"] is False and row["pnl"] == 0.0
    assert (ROOT / "docs" / "index.html").read_text("utf-8").count("r.marked") >= 2


def test_the_site_does_not_call_the_target_weight_a_balance():
    """'투자 중'은 **잔고**여야 한다 — 오늘의 목표 노출이 아니다.

    실측: 목표는 4종목 32.2%였는데 계좌가 실제로 들고 있던 것은 10종목
    47.1%였다. 잔돈·쿨다운·1주 미만으로 정리하지 못한 보유가 목표에는
    안 잡히기 때문이다. 목표를 잔고라고 부르면 15%p가 조용히 사라진다.
    """
    html = (ROOT / "docs" / "index.html").read_text("utf-8")
    start = html.find("사이드바: 돈이 지금 어디 있는가")
    end = html.find('side-cash").innerHTML')
    assert 0 < start < end, "'돈이 어디 있나' 카드를 찾지 못했다"
    card = html[start:end]
    assert "pf.holdings" in card, "카드가 잔고를 읽지 않는다"
    # 목표 노출(weight)을 쓰더라도 **'투자 중'으로는** 쓰면 안 된다 —
    # 차이를 설명하는 용도(const tgt)로만 허용한다.
    before_tgt = card.split("const tgt=")[0]
    assert "pfLast.weight" not in before_tgt, (
        "'돈이 어디 있나' 카드가 아직 목표 노출을 잔고로 쓰고 있다")


# ── 주간 리포트도 같은 자로 재는가 (감사 219) ──────────────────

def test_the_weekly_report_does_not_call_a_deposit_profit(tmp_path):
    """주간 요약이 입금 귀속 규칙의 **자기 복사본**을 갖고 있었다.

    감사 211에서 "입금은 날짜가 아니라 배치가 찍은 봉(settled_bar)으로
    귀속한다"로 바꾸며 `_flows_by_date` 한 곳에 모았는데, 주간 요약만
    옛 코드를 그대로 들고 있었고 **이미 갈라져 있었다.** 실측:

        주간 요약  : +1149.06%   ← 92만원 입금이 '수익'으로
        장부(TWR) :    -0.94%

    이 숫자는 매주 월요일 아침 주간 리포트로 나간다. 같은 판정을 두 곳에서
    하면 언젠가 갈라진다 — 이번엔 '언젠가'가 이틀이었다.
    """
    from quant.live.daily import weekly_summary
    from quant.live.ledger_basics import twr_index

    (tmp_path / "paper").mkdir()
    st = {"market": "portfolio", "symbol": "ALL", "currency": "KRW",
          "start_cash": 80_000.0, "cash": 0.0, "positions": {},
          "deposits": [{"date": "2026-08-13", "amount": 920_000.0,
                        "memo": "", "settled_bar": "2026-08-12"}],
          "history": [{"date": "2026-08-11", "equity": 80_000.0},
                      {"date": "2026-08-12", "equity": 999_250.0}]}
    (tmp_path / "paper" / "portfolio_ALL.json").write_text(
        json.dumps(st), encoding="utf-8")

    wk = weekly_summary(str(tmp_path))["markets"]["portfolio:ALL"]
    idx = twr_index(st["history"], st["deposits"], start_cash=80_000.0)
    twr = (idx[-1] - 1) * 100
    assert abs(wk["week_return_pct"] - twr) < 0.05, (
        f"주간 리포트 {wk['week_return_pct']:+.2f}% vs 장부 {twr:+.2f}% — "
        "입금이 주간 수익으로 둔갑했다")
    assert -3 < wk["week_return_pct"] < 3


def test_the_weekly_report_still_measures_a_real_gain(tmp_path):
    """대조군 — 입금을 빼느라 진짜 수익까지 지우면 리포트가 무의미하다."""
    from quant.live.daily import weekly_summary

    (tmp_path / "paper").mkdir()
    st = {"market": "portfolio", "symbol": "ALL", "currency": "KRW",
          "start_cash": 100_000.0, "cash": 0.0, "positions": {},
          "deposits": [],
          "history": [{"date": "2026-08-11", "equity": 100_000.0},
                      {"date": "2026-08-12", "equity": 110_000.0}]}
    (tmp_path / "paper" / "portfolio_ALL.json").write_text(
        json.dumps(st), encoding="utf-8")
    wk = weekly_summary(str(tmp_path))["markets"]["portfolio:ALL"]
    assert wk["week_return_pct"] == pytest.approx(10.0, abs=0.05), wk


def test_only_one_place_attributes_a_deposit_to_a_bar():
    """귀속 규칙을 손으로 다시 쓰는 자리가 생기면 언젠가 또 갈라진다."""
    import ast

    offenders = []
    for rel in ("quant/live/daily.py", "quant/web/app.py",
                "quant/reporting/social.py"):
        p = ROOT / rel
        if not p.exists():
            continue
        for node in ast.walk(ast.parse(p.read_text("utf-8"))):
            if not isinstance(node, ast.Compare):
                continue
            txt = ast.unparse(node)
            # `<무언가>["date"] >= d["date"]` 꼴 — 정산 봉을 안 보는 옛 규칙
            if '"date"' in txt and ">=" in txt and "_flow_date" not in txt \
                    and txt.count('["date"]') >= 2:
                offenders.append(f"{rel}:{node.lineno} — {txt}")
    assert not offenders, (
        "입금 귀속을 손으로 다시 계산하는 자리가 있다 — `_flows_by_date`를 "
        "쓸 것:\n  " + "\n  ".join(offenders))
