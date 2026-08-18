"""장중 도전자가 **자기 차선을 지키는가** (2026-08-18, 사장님 지시).

"실시간으로 단타 매매를 하는 퍼포먼스도 보여져야 한다" — 만들었다. 단,
이 실험이 지켜야 할 선이 있고, 이 파일이 그 선을 지킨다:

  ① 분리 — 본 계좌 장부(state/paper)를 읽지도 쓰지도 않는다. 90일 공개
     측정에 한 글자라도 섞이면 그 측정은 거짓이 된다.
  ② 재사용 — 챔피언 규칙과 비용 모델을 실전 함수에서 빌려 온다
     (FROZEN_IDEAS ①). 여기 다시 적으면 "빈도의 효과"가 아니라
     "다른 규칙의 효과"를 재게 된다.
  ③ 비용 정직 — 모든 체결이 실전과 같은 비용을 문다. 비용 없는 단타
     실험은 실험이 아니라 광고다.
  ④ 통화 봉인 — USDT 하나만 쓴다. 감사 254(통화 혼합 → 100만원이
     7,249만원)의 재발 지점을 만들지 않는다.
  ⑤ 실측 — '15분마다'는 예약일 뿐, 실제 간격은 회차 기록에서 잰다.
  ⑥ 표식 — 산출물은 실험/가상 표식과 정직한 한계를 달고 나간다.
  ⑦ 배선 — guard 배치에 실제로 물려 있고, 실패해도 심장박동(안전장치)을
     죽이지 못한다(continue-on-error).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live import intraday_challenger as IC  # noqa: E402

SRC = (ROOT / "quant" / "live" / "intraday_challenger.py").read_text("utf-8")


def _df(closes, n=None):
    """합성 1h봉 — 검사 주입용."""
    closes = list(closes)
    idx = pd.date_range("2026-01-01", periods=len(closes), freq="h")
    return pd.DataFrame({"open": closes, "high": closes, "low": closes,
                         "close": closes, "volume": 1.0}, index=idx)


class _Const:
    """검사용 고정 신호 전략 — 실전 기본값은 챔피언 규칙이다."""

    def __init__(self, sig):
        self.sig = sig

    def generate_signals(self, df):
        return pd.Series(self.sig, index=df.index)


def _round(tmp_path, sig, when="2026-08-18T04:00:00+00:00", closes=None):
    data = {s: _df(closes or [100.0] * 100) for s in IC.UNIVERSE}
    return IC.run_intraday_round(
        when, state_dir=str(tmp_path / "state"),
        docs_dir=str(tmp_path / "docs"),
        data=data, strategy_factory=lambda s: _Const(sig))


# ── ① 분리 — 본 계좌에 손대지 않는다 ───────────────────────────

def test_the_lane_is_sealed_in_source():
    body = SRC.split('"""', 2)[-1]          # 모듈 머리말(약속)은 빼고 코드만
    assert "state/paper" not in body, (
        "도전자가 본 계좌 장부 경로를 안다 — 90일 측정에 섞일 문이 열렸다")
    assert "run_daily_portfolio" not in body and "run_daily_paper" not in body, (
        "도전자가 본 계좌 실행 함수를 부른다")


def test_a_round_writes_only_its_own_files(tmp_path):
    _round(tmp_path, 1.0)
    written = sorted(str(p.relative_to(tmp_path))
                     for p in tmp_path.rglob("*") if p.is_file())
    assert written == ["docs/intraday.json", "state/intraday/challenger.json"], (
        f"자기 장부 밖에 손을 댔다: {written}")


# ── ② 재사용 — 규칙·비용을 다시 적지 않는다 ────────────────────

def test_the_champion_rule_is_borrowed_not_rewritten():
    assert "champion_spec" in SRC and "build_strategy" in SRC, (
        "챔피언 규칙을 빌려 오지 않는다 — 다른 규칙을 재면 실험이 무효다")
    assert "measured_cost_model" in SRC, (
        "실전 비용 모델을 빌려 오지 않는다")
    # 비용 숫자를 여기 다시 적으면 실전과 갈라지는 날이 온다.
    body = SRC.split('"""', 2)[-1]
    assert "0.001" not in body and "0.0005" not in body, (
        "수수료·슬리피지 숫자가 도전자에 다시 적혀 있다")


# ── ③ 비용 — 모든 체결이 실전 비용을 문다 ──────────────────────

def test_a_trade_pays_the_production_cost(tmp_path):
    from quant.live.daily import measured_cost_model
    v = _round(tmp_path, 1.0)
    assert v["trades"] == len(IC.UNIVERSE), v
    st = IC.load_state(str(tmp_path / "state"))
    per_side = float(measured_cost_model(
        "crypto", str(tmp_path / "state")).fee
        + measured_cost_model("crypto", str(tmp_path / "state")).slippage)
    spent = sum(abs(t["notional"]) for r in st["rounds"]
                for t in r["trades"])
    # 기록의 notional은 읽기 좋게 소수 2자리로 반올림돼 있어 ±0.01 허용.
    assert abs(st["cost_paid"] - spent * per_side) < 0.01, (
        f"비용이 실전 편도율과 다르다: {st['cost_paid']} vs {spent * per_side}")
    assert st["cost_paid"] > 0, "체결했는데 비용이 0이다 — 광고다"


def test_no_trade_pays_nothing(tmp_path):
    v = _round(tmp_path, 0.0)
    assert v["trades"] == 0
    st = IC.load_state(str(tmp_path / "state"))
    assert st["cost_paid"] == 0.0
    assert st["cash"] == IC.START_CASH_USDT


def test_dust_adjustments_are_held_back(tmp_path):
    """신호가 티끌만큼 움직였을 때 부스러기 매매로 비용을 태우지 않는다."""
    _round(tmp_path, 1.0)
    v2 = _round(tmp_path, 0.999, when="2026-08-18T04:15:00+00:00")
    assert v2["trades"] == 0, "0.1% 조정에 매매했다 — 비용만 태운다"


def test_no_leverage_cash_never_goes_negative(tmp_path):
    _round(tmp_path, 1.0)
    st = IC.load_state(str(tmp_path / "state"))
    assert st["cash"] > -1e-9, f"현금이 음수다(레버리지): {st['cash']}"


# ── ④ 통화 봉인 ────────────────────────────────────────────────

def test_the_currency_never_mixes():
    low = SRC.lower()
    assert "krw" not in low and "fx_usdkrw" not in low and "환산" not in SRC.split(
        '"""', 2)[0], "도전자가 통화 환산을 안다 — 감사 254의 재발 지점"


def test_the_ledger_says_its_currency(tmp_path):
    _round(tmp_path, 1.0)
    st = IC.load_state(str(tmp_path / "state"))
    assert st["currency"] == "USDT"


# ── ⑤ 실측 — 예약이 아니라 일어난 일 ───────────────────────────

def test_the_gap_is_measured_from_rounds_not_booked():
    rounds = [{"time": "2026-08-18T00:00:00+00:00"},
              {"time": "2026-08-18T00:15:00+00:00"},
              {"time": "2026-08-18T09:33:00+00:00"}]   # 9시간 18분 구멍
    gap = IC.observed_gap_minutes(rounds)
    assert gap is not None and abs(gap - 558.0) < 1.0, (
        f"관측 간격이 실측이 아니다: {gap} (감사 267의 실제 사고 간격)")
    assert IC.observed_gap_minutes(rounds[:1]) is None, (
        "기록 하나로 간격을 지어냈다")


def test_the_public_report_carries_both_booked_and_observed(tmp_path):
    _round(tmp_path, 1.0)
    _round(tmp_path, 1.0, when="2026-08-18T05:07:00+00:00")
    out = json.loads((tmp_path / "docs" / "intraday.json").read_text("utf-8"))
    assert out["booked_interval_minutes"] == IC.BOOKED_INTERVAL_MINUTES
    assert abs(out["observed_gap_minutes"] - 67.0) < 1.0, out


# ── ⑥ 표식 — 실험은 실험이라고 말한다 ──────────────────────────

def test_the_output_is_labeled_an_experiment(tmp_path):
    _round(tmp_path, 1.0)
    out = json.loads((tmp_path / "docs" / "intraday.json").read_text("utf-8"))
    assert out["kind"] == "challenger-experiment", (
        "실험 표식이 없다 — 가상 성적이 실측처럼 읽히는 순간 정체성이 무너진다")
    assert "실제 돈이 아닙니다" in out["label"]
    text = " ".join(out["honest_limits"])
    for word in ("가상", "비용", "예약", "분리"):
        assert word in text, f"정직한 한계에 '{word}'가 빠졌다: {text}"


def test_a_skipped_symbol_is_reported_not_faked(tmp_path):
    """시세를 못 받은 종목은 건너뛰고 **그렇게 적는다** — 지어내지 않는다."""
    data = {s: _df([100.0] * 100) for s in IC.UNIVERSE}
    data["XRP/USDT"] = None
    v = IC.run_intraday_round(
        "2026-08-18T04:00:00+00:00", state_dir=str(tmp_path / "state"),
        docs_dir=str(tmp_path / "docs"),
        data=data, strategy_factory=lambda s: _Const(1.0))
    assert v["skipped"] == 1
    out = json.loads((tmp_path / "docs" / "intraday.json").read_text("utf-8"))
    assert "XRP/USDT" in out["last_skipped"], out["last_skipped"]


def test_synthetic_fallback_prices_are_refused():
    """실데이터 확인 — 합성 폴백 시세로 가짜 체결을 만들지 않는다."""
    assert 'attrs.get("source")' in SRC, (
        "시세 출처를 확인하지 않는다 — 거래소 전부 실패한 날 합성 시세로 "
        "체결이 만들어진다")


# ── ⑦ 배선 — 만들어 두고 안 돌리면 없는 장치다 ─────────────────

def test_wired_into_the_guard_batch_without_hostage():
    wf = (ROOT / ".github" / "workflows" / "guard.yml").read_text("utf-8")
    assert "intraday-round" in wf, "장중 도전자가 어느 배치에도 배선돼 있지 않다"
    step = wf.split("intraday-round")[0].rsplit("- name:", 1)[1]
    assert "continue-on-error: true" in step, (
        "실험 실패가 심장박동(안전장치) 잡을 죽일 수 있다 — 실험이 안전장치를 "
        "볼모로 잡으면 안 된다")
    assert "state/intraday" in wf and "docs/intraday.json" in wf, (
        "회차 기록을 커밋하지 않는다 — 만료되는 증거는 감시가 아니다")


def test_the_public_page_reads_the_json_and_links_back():
    page = (ROOT / "docs" / "intraday.html").read_text("utf-8")
    assert "intraday.json" in page, "공개 페이지가 장부를 안 읽는다"
    assert "가상 자금" in page and "실제 돈이 아니" in page, (
        "실험 표식 없이 숫자만 보여준다")
    index = (ROOT / "docs" / "index.html").read_text("utf-8")
    assert "intraday.html" in index, (
        "첫 화면에서 실험 페이지로 가는 길이 없다 — 공개가 아니라 은닉이다")


# ── 회계 — 자산은 스스로 맞아야 한다 ───────────────────────────

def test_the_equity_adds_up(tmp_path):
    _round(tmp_path, 1.0)
    st = IC.load_state(str(tmp_path / "state"))
    eq = st["cash"] + sum(q * 100.0 for q in st["positions"].values())
    want = IC.START_CASH_USDT - st["cost_paid"]
    assert abs(eq - want) < 1e-6, (
        f"자산이 안 맞는다: 현금+보유 {eq} vs 시드-비용 {want}")


def test_a_price_move_moves_the_equity(tmp_path):
    _round(tmp_path, 1.0)
    up = [100.0] * 99 + [110.0]
    v = _round(tmp_path, 1.0, when="2026-08-18T05:00:00+00:00", closes=up)
    st = IC.load_state(str(tmp_path / "state"))
    assert v["equity"] > IC.START_CASH_USDT, (
        "가격이 10% 올랐는데 자산이 안 움직였다 — 평가가 장식이다")
    assert v["return_pct"] > 0
