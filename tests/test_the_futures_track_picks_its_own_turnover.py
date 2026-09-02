"""선물 실험도 회전을 스스로 고르고, 수수료가 폭주하면 스스로 멈춘다.

2026-09-02 사장님 "모두 다 해" — 보류해 뒀던 제안 ②(수수료 예산 관문)를
착수하면서, 같은 날 본 계좌에 넣은 규율(회전은 기계가 고른다)을 선물에도
맞춘다.

여기서 지키는 약속:

  ① 밴드는 **사람이 정하지 않는다** — 코인 실측 비용 × 그 종목 챔피언의
     밴드 배수(밤 오디션이 고른 값)다.
  ② **청산(목표 0)은 밴드와 무관하게 항상 실행된다.** 백테스트 엔진과
     같은 규약이다. 갈리면 링에서 이긴 회전이 실계좌에서 재현되지 않고,
     신호가 관망으로 바뀐 종목의 잔여 포지션이 영원히 남는다.
  ③ 수수료 예산은 **자산 대비**로 잰다. 사장님 원안("총이득의 50%")은
     총이득이 음수인 주에 정의되지 않는데, 장부의 최근 두 주가 실제로
     그 상태였다 — 가장 걱정되는 자리에서 관문이 침묵한다.
  ④ 예산을 넘겨도 **줄이는 거래는 막지 않는다.** 위험을 줄이는 길을 막는
     안전장치는 그 자체가 위험이다.
  ⑤ 못 재는 상태는 위반이 아니다 — 모르는 것을 위반으로 세면 첫 회차부터
     계좌가 얼어붙는다.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live import futures_challenger as fc  # noqa: E402


def _state(cash=10_000.0, positions=None, rounds=None):
    return {"cash": cash, "start_cash": 10_000.0,
            "positions": dict(positions or {}), "avg_cost": {},
            "cost_paid": 0.0, "funding_paid": 0.0,
            "rounds": list(rounds or []), "curve": []}


# ── ① 밴드는 작은 조정을 거른다 ────────────────────────────────────────
def test_a_small_adjustment_below_the_band_does_not_trade():
    """슬라이스 예산 대비 비중 차가 밴드 미만이면 거래하지 않는다."""
    st = _state()
    uni = ["BTC/USDT"]
    # 슬라이스 = 10,000 (종목 1개). 신호 0.05 → 목표 500 = 비중 0.05.
    trades = fc.execute_targets(st, {"BTC/USDT": 0.05}, {"BTC/USDT": 100.0},
                                10_000.0, 0.0015, uni,
                                bands={"BTC/USDT": 0.15})
    assert trades == [], f"밴드 밑인데 체결됐다 — {trades}"
    # 밴드가 없으면 같은 주문이 나간다(밴드가 원인임을 못 박는다).
    st2 = _state()
    assert fc.execute_targets(st2, {"BTC/USDT": 0.05}, {"BTC/USDT": 100.0},
                              10_000.0, 0.0015, uni), "밴드 없이도 안 나갔다"


def test_a_move_above_the_band_still_trades():
    """밴드는 큰 조정을 막지 않는다 — 막으면 전략이 아니라 마비다."""
    st = _state()
    trades = fc.execute_targets(st, {"BTC/USDT": 0.60}, {"BTC/USDT": 100.0},
                                10_000.0, 0.0015, ["BTC/USDT"],
                                bands={"BTC/USDT": 0.15})
    assert len(trades) == 1 and trades[0]["notional"] > 0


# ── ② 청산은 밴드를 무시한다 (핵심 규약) ───────────────────────────────
def test_a_flat_signal_always_closes_even_inside_the_band():
    """목표 0(관망)은 밴드 안이어도 **반드시** 청산한다.

    이 검사가 없으면 밴드가 잔여 포지션을 영구히 붙잡는다 — 신호는 나가라고
    하는데 계좌는 들고 있는 상태가 되고, 화면과 실제가 갈린다.
    """
    st = _state(positions={"BTC/USDT": 1.0})       # 100 USDT 상당(비중 0.01)
    trades = fc.execute_targets(st, {"BTC/USDT": 0.0}, {"BTC/USDT": 100.0},
                                10_000.0, 0.0015, ["BTC/USDT"],
                                bands={"BTC/USDT": 0.90})   # 아주 넓은 밴드
    assert len(trades) == 1, f"관망인데 청산이 안 났다 — {trades}"
    assert not st["positions"], f"포지션이 남았다 — {st['positions']}"


# ── ③ 밴드 값은 기계가 고른다 ──────────────────────────────────────────
def test_the_band_follows_the_champion_multiplier(monkeypatch, tmp_path):
    """밴드 = 코인 실측 비용 밴드 × 챔피언의 밴드 배수.

    사람이 이 값을 적는 자리가 없어야 한다 — 배수는 밤 오디션이 고른다.
    """
    monkeypatch.setattr(fc, "_spec",
                        lambda sym, sd: {"strategy": "ml",
                                         "params": {"band_mult": 2.0}})
    base = fc.champion_band_rel("BTC/USDT", str(tmp_path))
    monkeypatch.setattr(fc, "_spec",
                        lambda sym, sd: {"strategy": "ml", "params": {}})
    one = fc.champion_band_rel("BTC/USDT", str(tmp_path))
    assert base == 2.0 * one, f"배수가 안 먹었다 — {base} vs {one}"
    assert one > 0, "기본 밴드가 0이면 회전 제어가 아예 없다"


def test_a_broken_champion_does_not_stop_trading(monkeypatch, tmp_path):
    """챔피언을 못 읽어도 체결은 멈추지 않는다 — 배수 1로 돌아간다."""
    def _boom(sym, sd):
        raise RuntimeError("장부 읽기 실패")
    monkeypatch.setattr(fc, "_spec", _boom)
    assert fc.champion_band_rel("BTC/USDT", str(tmp_path)) > 0


# ── ④ 수수료 예산은 총이득이 아니라 자산으로 잰다 ──────────────────────
def _rounds(fees, equity, days_apart=8):
    """창 밖 기준선 하나 + 창 안 마지막 하나."""
    return [{"at": "2026-08-20T00:00:00+09:00", "cost_paid": 0.0,
             "funding_paid": 0.0, "equity": equity},
            {"at": "2026-08-28T00:00:00+09:00", "cost_paid": fees,
             "funding_paid": 0.0, "equity": equity}]


def test_the_budget_is_measured_even_when_gross_pnl_is_negative():
    """총이득이 음수여도 판정이 난다.

    사장님 원안("수수료 > 총이득의 50%")은 이 자리에서 정의되지 않는다.
    장부의 9/1·9/2 7일 창이 실제로 총이득 −129·−153이었다.
    """
    st = _state(rounds=_rounds(fees=400.0, equity=9_000.0))
    st["rounds"][-1]["equity"] = 9_000.0      # 자산이 줄었다 = 총이득 음수
    out = fc.fee_budget(st)
    assert out["pct_of_equity"] is not None, "음수 이득에서 판정을 포기했다"
    assert out["breached"] is True, out


def test_a_calm_week_is_not_breached():
    st = _state(rounds=_rounds(fees=70.0, equity=9_500.0))
    out = fc.fee_budget(st)
    assert out["breached"] is False and out["pct_of_equity"] < 1.0, out


def test_what_cannot_be_measured_is_not_a_breach():
    """회차가 없으면 위반이 아니다 — 모르는 것을 위반으로 세지 않는다."""
    assert fc.fee_budget(_state())["breached"] is False


# ── ⑤ 예산을 넘겨도 줄이는 거래는 막지 않는다 ──────────────────────────
def test_a_breached_budget_blocks_growth_but_never_shrinking():
    st = _state(positions={"BTC/USDT": 50.0})     # 5,000 상당(비중 0.5)
    # 목표를 더 키우려는 주문 → 막힌다.
    grew = fc.execute_targets(st, {"BTC/USDT": 0.9}, {"BTC/USDT": 100.0},
                              10_000.0, 0.0015, ["BTC/USDT"],
                              allow_growth=False)
    assert grew == [], f"예산 초과인데 노출이 커졌다 — {grew}"
    assert st["positions"]["BTC/USDT"] == 50.0
    # 줄이려는 주문 → 나간다.
    shrank = fc.execute_targets(st, {"BTC/USDT": 0.1}, {"BTC/USDT": 100.0},
                                10_000.0, 0.0015, ["BTC/USDT"],
                                allow_growth=False)
    assert len(shrank) == 1 and shrank[0]["notional"] < 0, shrank


def test_a_breached_budget_still_lets_a_position_close():
    """예산 초과가 청산을 막으면 안 된다 — 안전장치가 위험이 된다."""
    st = _state(positions={"BTC/USDT": 50.0})
    out = fc.execute_targets(st, {"BTC/USDT": 0.0}, {"BTC/USDT": 100.0},
                             10_000.0, 0.0015, ["BTC/USDT"],
                             allow_growth=False)
    assert len(out) == 1 and not st["positions"], (out, st["positions"])


# ── ⑥ 장부가 말한다 ────────────────────────────────────────────────────
def test_the_round_records_the_budget_even_when_it_is_not_breached():
    """안 넘은 회차에도 칸이 남는다 — 안 남기면 '예산이 없던 때'와 같아진다."""
    import inspect
    src = inspect.getsource(fc.run_futures_round)
    assert 'rec["fee_budget"] = budget' in src
    assert 'rec["rebalance_bands"]' in src
    # 예산은 **체결 전에** 잰다 — 뒤에 재면 이번 회차 수수료가 섞인다.
    assert src.index("budget = fee_budget(st)") < src.index("trades = execute_targets")


def test_the_public_report_carries_the_budget_and_bands():
    st = _state(rounds=_rounds(fees=70.0, equity=9_500.0))
    st["rounds"][-1]["rebalance_bands"] = {"BTC/USDT": 0.15}
    rep = fc.public_report(st)
    assert rep["fee_budget"]["limit_pct"] == fc.FEE_BUDGET_PCT_OF_EQUITY
    assert rep["rebalance_bands"] == {"BTC/USDT": 0.15}
    # 규칙이 바뀐 날이 화면 재료에 남는다(곡선을 읽는 사람이 이유를 안다).
    assert any(str(c.get("on")) == "2026-09-02" for c in rep["rule_changes"])


# ── ⑦ 화면이 그 말을 영어로도 할 수 있어야 한다 ────────────────────────
#
# ⚠️ 예산을 **넘긴 날의 문구**는 평소 화면에 안 나온다. 그래서 영어 화면
#    검사가 그 문구를 영영 못 본다 — 실제로 넘긴 날 공개 페이지에서 처음
#    한국어가 뜬다. 여기서 미리 못 박는다.
_DICT = ROOT / "docs" / "assets" / "i18n-en.js"


def test_the_breach_wording_is_already_translated():
    d = _DICT.read_text("utf-8")
    for phrase in ("한도를 넘어",
                   "포지션을 키우는 거래를 멈췄습니다.",
                   "얼마나 자주 사고팔지는 밤 심사가 종목마다 고른 값을 따릅니다 — 지금"):
        assert f'"{phrase}"' in d, f"예산 초과 문구가 사전에 없다: {phrase}"


def test_the_dictionary_numbers_match_the_constants():
    """사전에 박힌 숫자와 실제 상수가 갈리지 않는다.

    화면 문구에 "최근 7일"·"한도 3%"가 글자로 들어 있다. 상수만 바꾸면
    화면은 새 값으로 그리는데 사전 열쇠는 옛 값이라 **영어에서만** 번역이
    끊긴다 — 한국어 화면은 멀쩡해서 아무도 모른다.
    """
    d = _DICT.read_text("utf-8")
    assert f'"최근 {fc.FEE_BUDGET_WINDOW_DAYS}일 수수료"' in d, (
        f"창 길이를 {fc.FEE_BUDGET_WINDOW_DAYS}일로 바꿨으면 사전도 바꿔야 한다")
    assert f'"(자산 대비 · 한도 {fc.FEE_BUDGET_PCT_OF_EQUITY:.0f}%)"' in d, (
        f"한도를 {fc.FEE_BUDGET_PCT_OF_EQUITY}%로 바꿨으면 사전도 바꿔야 한다")
