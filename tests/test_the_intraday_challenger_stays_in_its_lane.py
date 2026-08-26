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


# ── ③b 재현성 — 미완성 봉은 판단하지 않는다 ────────────────────

def test_an_unfinished_bar_never_decides(tmp_path):
    """지금 만들어지는 중인 봉으로 판단하면 같은 회차를 10분 뒤 재현했을 때
    다른 결정이 나온다 — 재현 불가능한 결정은 이 저장소에 없다."""
    closes = [100.0] * 99 + [999.0]              # 마지막 봉이 터무니없이 다르다
    data = {s: _df(closes) for s in IC.UNIVERSE}
    # '지금'을 마지막 봉이 **방금 열린** 시각으로 둔다 — 그 봉은 미완성이다.
    now = data["BTC/USDT"].index[-1].isoformat() + "+00:00"
    IC.run_intraday_round(now, state_dir=str(tmp_path / "state"),
                          docs_dir=str(tmp_path / "docs"),
                          data=data, strategy_factory=lambda s: _Const(1.0))
    st = IC.load_state(str(tmp_path / "state"))
    assert st["last_prices"]["BTC/USDT"] == 100.0, (
        f"미완성 봉(999)의 값으로 판단·평가했다: {st['last_prices']['BTC/USDT']}")
    # 재현 지문 — 어느 봉으로 판단했는지 회차에 남아야 한다.
    assert st["rounds"][-1]["bar_times"], "판단에 쓴 봉의 시각이 기록에 없다"


def test_the_same_round_reproduces_later(tmp_path):
    """같은 데이터로 10분 뒤 다시 돌려도 같은 가격·같은 신호여야 한다."""
    closes = [100.0] * 99 + [999.0]
    data = {s: _df(closes) for s in IC.UNIVERSE}
    open_t = data["BTC/USDT"].index[-1]
    px = []
    for offset in ("00:05:00", "00:25:00"):      # 봉이 닫히기 전의 두 시점
        d = tmp_path / offset.replace(":", "")
        h, m, s = offset.split(":")
        now = (open_t + pd.Timedelta(hours=int(h), minutes=int(m))
               ).isoformat() + "+00:00"
        IC.run_intraday_round(now, state_dir=str(d / "state"),
                              docs_dir=str(d / "docs"),
                              data=data, strategy_factory=lambda s: _Const(1.0))
        px.append(IC.load_state(str(d / "state"))["last_prices"]["BTC/USDT"])
    assert px[0] == px[1], f"같은 봉인데 시점에 따라 판단 가격이 다르다: {px}"


# ── ③c 브레이크 — 실전과 같은 킬스위치를 빌려 건다 ─────────────

def test_a_crash_pulls_the_borrowed_kill_switch(tmp_path):
    """폭락에서 실험 계좌만 맨몸이면 성적 차이가 '빈도의 효과'가 아니라
    '브레이크 유무의 효과'가 된다 — 실험이 오염된다."""
    _round(tmp_path, 1.0)                        # 100에 전량 매수
    v = _round(tmp_path, 1.0, when="2026-08-18T05:00:00+00:00",
               closes=[100.0] * 99 + [80.0])     # -20% 폭락
    st = IC.load_state(str(tmp_path / "state"))
    assert st["risk_scale"] == 0.5, (
        f"낙폭 -20%인데 킬스위치가 안 걸렸다: scale={st['risk_scale']}")
    sells = [t for t in st["rounds"][-1]["trades"] if t["side"] == "sell"]
    assert sells, "노출을 줄이라는데 아무것도 안 팔았다 — 선언만 남은 브레이크다"
    assert st["rounds"][-1]["kill_switch"]["drawdown"] <= -0.15, v


def test_the_kill_switch_thresholds_are_not_restated():
    """-25%·-15% 문턱이 여기 다시 적히면 실전과 갈라지는 날이 온다."""
    body = SRC.split('"""', 2)[-1]
    assert "_kill_switch_scale" in SRC, "실전 킬스위치를 빌려 오지 않는다"
    for banned in ("-0.25", "-0.15"):
        assert banned not in body, f"킬스위치 문턱({banned})이 다시 적혀 있다"


# ── ③d 점수판 — 기준선·사전 등록 판정·체결 내역 ────────────────

def test_the_report_carries_the_hold_baseline(tmp_path):
    """가격이 10% 오르면 그냥 보유는 **사는 값을 뺀** 만큼 번다.

    ⚠️ 2026-08-19에 기댓값이 바뀌었다. 예전에는 정확히 10.0%를 요구했다 —
       그냥 보유가 수수료를 한 푼도 안 문다는 뜻이었고, 화면은 그 숫자를
       비용을 다 문 실험 성적 옆에 나란히 놓고 있었다(사장님 지적).
       이제 편도 한 번을 문다: (1 − 0.0015) × 1.10 − 1 = 9.835%.
    """
    from quant.live.daily import measured_cost_model

    _round(tmp_path, 1.0)
    _round(tmp_path, 1.0, when="2026-08-18T05:00:00+00:00",
           closes=[100.0] * 99 + [110.0])
    out = json.loads((tmp_path / "docs" / "intraday.json").read_text("utf-8"))
    one_way = measured_cost_model("crypto", str(tmp_path / "state")).total_one_way()
    want = ((1.0 - one_way) * 1.10 - 1.0) * 100
    assert abs(out["hold_return_pct"] - want) < 0.01, (
        f"그냥 보유 기준선이 틀렸다: {out['hold_return_pct']} (기대 {want:.4f})")
    assert out["hold_return_pct"] < 10.0, (
        "그냥 보유가 사는 값을 안 물고 있다 — 실험 쪽만 비용을 무는 비교가 된다")


def test_the_judgement_is_preregistered_and_strict(tmp_path):
    """판정 기준은 결과가 쌓이기 **전에** 등록돼 있어야 한다."""
    _round(tmp_path, 1.0)
    out = json.loads((tmp_path / "docs" / "intraday.json").read_text("utf-8"))
    j = out["judgement"]
    assert j["registered_on"] == "2026-08-18" and j["min_days"] == 90, (
        "판정 기간이 90일이 아니다 — 외부 검토(2026-08-18) 반영: 수익률 "
        "차이의 신뢰구간은 봉 수가 아니라 기간이 지배한다")
    # 수정은 숨기지 않는다 — 무엇을 왜 언제 바꿨는지가 기준과 함께 실린다.
    assert j["amended"]["on"] == "2026-08-18" and "30일" in j["amended"]["what"]
    assert "골대 이동" in j["amended"]["why"]
    text = " ".join(j["criteria"])
    for word in ("신뢰구간", "낙폭", "본 계좌", "90일"):
        assert word in text, f"판정 기준에 '{word}'가 빠졌다: {text}"
    assert out["elapsed_days"] is not None
    page = (ROOT / "docs" / "intraday.html").read_text("utf-8")
    assert "수정 공지" in page, "수정 사실이 공개 페이지에 안 나간다"


def test_the_report_lists_recent_trades(tmp_path):
    _round(tmp_path, 1.0)
    out = json.loads((tmp_path / "docs" / "intraday.json").read_text("utf-8"))
    assert out["recent_trades"], "체결 내역이 공개되지 않는다 — 장부가 아니다"
    t = out["recent_trades"][-1]
    assert t["cost"] > 0 and t["time"], t


def test_the_page_shows_judgement_comparison_and_trades():
    page = (ROOT / "docs" / "intraday.html").read_text("utf-8")
    for word in ("사전 등록", "본 계좌", "최근 체결", "그냥 보유"):
        assert word in page, f"공개 페이지에 '{word}' 구획이 없다"
    assert "status.json" in page, (
        "본 계좌 비교가 공개 장부(status.json)를 안 읽는다 — 비교 없는 "
        "실험 점수판은 구경거리다")


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
    # 첫 화면에서 실험 페이지로 가는 길 — **바가 홈에 그려 주는 것도 길이다.**
    # ⚠️ 2026-08-26에 홈이 자기 상단 바를 버리고 공용 바(assets/nav.js)를
    #    쓰게 되면서 index.html 소스에서 이 링크가 사라졌다. 화면에는 그대로
    #    있는데(공용 바가 그린다) 검사만 빨개졌다 — 검사가 지키려던 것은
    #    "index.html 파일에 글자가 있다"가 아니라 "첫 화면에서 닿는다"였다.
    index = (ROOT / "docs" / "index.html").read_text("utf-8")
    nav = (ROOT / "docs" / "assets" / "nav.js").read_text("utf-8")
    assert 'src="assets/nav.js"' in index, "홈이 공용 바를 안 싣는다"
    assert "intraday.html" in index or "intraday.html" in nav, (
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
