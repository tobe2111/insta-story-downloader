"""사이트가 단언한 것이 코드에서 실제로 지켜지는가.

배경(2026-08-11 감사): trust.html은 "이 기록은 조작할 수 없습니다"라는
제목으로 시스템 동작을 여러 개 단언한다. 그 문장들이 코드와 어긋나면
사이트의 유일한 자산인 정직성이 무너진다. 실제로 두 건이 어긋나 있었다.

  · "낙폭 단계별 자동 킬스위치가 적용됩니다" → 스케일러가 되돌려 키워
    실제로는 아무 효과가 없었다(같은 감사에서 수정)
  · "누적 검증 횟수로 문턱을 높입니다" → 코드는 롤링 1년 + 상한 1.35.
    코드가 아니라 설명이 틀렸던 것이라 설명을 고쳤다.

핵심 계약: 사이트가 말하는 장치는 코드에 실재하고, 수치는 코드와 같다.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
TRUST = (ROOT / "docs" / "trust.html").read_text("utf-8")


def test_claimed_verify_command_exists():
    assert "python -m quant verify" in TRUST
    from quant.live.retrain import verify_retrain
    assert callable(verify_retrain)


def test_claimed_killswitch_actually_reduces_exposure():
    """사이트가 말하는 '자동 킬스위치'가 실제로 노출을 줄이는가."""
    assert "킬스위치" in TRUST
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    # 감쇠 전 비중으로 예산을 잡고, 감쇠는 그 뒤에 곱한다
    assert "vol_scale(base_w, rets_map, tgt_vol)" in src
    assert "vol_scale(pre_w" not in src


def test_claimed_next_open_fill_is_real():
    assert "다음 거래 세션의 시가" in TRUST
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert "IMMEDIATE_FILL_MARKETS" in src


def test_claimed_no_synthetic_records():
    assert "합성 데이터로 기록을 채우는 경로 자체가" in TRUST
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert 'df.attrs.get("synthetic_fallback")' in src
    assert "전 종목 데이터 실패 — 기록하지 않음" in src


def test_multiple_testing_numbers_match_the_code():
    """사이트에 적힌 문턱 수식·상한이 코드 상수와 같아야 한다."""
    from quant.live.retrain import CONFIRM_T_CAP, TRIALS_WINDOW_DAYS
    assert f"{CONFIRM_T_CAP}" in TRUST
    assert "최근 1년" in TRUST and TRIALS_WINDOW_DAYS == 365
    # 누적 총계로 문턱을 올린다는 옛 설명이 되살아나면 안 된다
    assert "누적 검증 횟수를 저장하고, 횟수가" not in TRUST


def test_shadow_control_and_parliament_exist():
    assert "섀도 대조군" in TRUST and "의회 운용" in TRUST
    src = (ROOT / "quant" / "cli.py").read_text("utf-8")
    assert "portfolio_SHADOW.json" in src
    from quant.live.parliament import ParliamentStrategy
    assert ParliamentStrategy is not None


def test_structure_epoch_describes_todays_changes():
    """구조 세대 설명이 실제 구조를 기술하는가(장부의 자기 기술)."""
    from quant.live.daily import STRUCTURE_WHY
    assert "안전장치 복구" in STRUCTURE_WHY


def test_parliament_explanation_discloses_the_mixture():
    """의원이 둘 이상이면 '리더 논리'가 곧 오늘의 비중이 아니다."""
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert "의석 1위 의원의" in src and "가중 평균한 값" in src


def test_parliament_summary_is_silent_for_single_member():
    from quant.live.parliament import parliament_summary
    assert parliament_summary({"parliament": [{"strategy": "ml",
                                               "weight": 1.0}]}) is None
    two = parliament_summary({"parliament": [
        {"strategy": "ml", "weight": 0.6},
        {"strategy": "ma_cross", "weight": 0.4}]})
    assert two and "60%" in two and "40%" in two


# ── 코인 미완결 봉 공개 (감사 63) ─────────────────────────────


def test_site_discloses_the_partial_crypto_bar():
    """코인이 미완결 봉으로 판단한다는 사실이 사이트에 적혀 있는가.

    trust.html은 "미완결 봉 제거는 이미 고쳐진 상태"라고 적고 있었다.
    주식 문맥에서는 맞지만, 코인은 여전히 진행 중인 봉으로 판단한다
    (실측 15/15). 읽는 사람은 '전부 고쳐졌다'로 읽는다. 사이트가 코드보다
    더 말하는 것을 막는 것이 이 파일의 목적이다.
    """
    t = (ROOT / "docs" / "trust.html").read_text(encoding="utf-8")
    assert "만들어지는 중인 봉" in t, "코인 미완결 봉 사실이 공개돼 있지 않다"
    assert "bar_partial" in t          # 장부 필드명까지 밝힌다
    assert "15개 중 15개" in t          # 추정이 아니라 실측 숫자
    assert "일봉 종가가 아닙니다" in t   # 공개 차트와 어긋나는 이유
    # 고친 사실과 그 대가까지 함께 적혀 있어야 한다(감사 71)
    assert "완성된 정보로 판단하고, 지금 가격에 체결한다" in t
    assert "보지 못합니다" in t          # 대가를 숨기지 않는다


def test_site_claim_matches_the_code_for_closed_bar_signals():
    """사이트가 "완성된 봉으로 판단한다"고 말하면 코드가 실제로 그래야 한다."""
    src = (ROOT / "quant" / "live" / "daily.py").read_text(encoding="utf-8")
    assert "def _signal_frame(" in src
    # 두 경로(종목별·통합) 모두 신호를 완성 봉 프레임으로 낸다.
    #
    # ⚠️ 여기는 원래 `src.count("_signal_frame(market, df)") >= 2`였다.
    #    감사 204에서 타임프레임을 인자로 넘기게 고치자 **글자가 달라져서**
    #    빨개졌다 — 계약은 그대로인데 문자열만 어긋난 것이다(감사 183·199에서
    #    반복해서 겪은 자리). 글자 대신 **호출 자체**를 센다.
    import ast

    calls = [n for n in ast.walk(ast.parse(src))
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id == "_signal_frame"]
    assert len(calls) >= 2, f"신호 프레임을 쓰는 경로가 {len(calls)}곳뿐이다"
    # 그리고 **재는 자(타임프레임)를 넘겨야 한다**(감사 204). 안 넘기면
    # 항상 일봉으로 재서, 1시간봉으로 돌 때 완성된 봉이 버려진다.
    for c in calls:
        assert len(c.args) >= 3, (
            f"daily.py:{c.lineno} — _signal_frame에 타임프레임을 안 넘긴다")
    assert "strat.generate_signals(df_sig)" in src
    assert "strategy.generate_signals(df_sig)" in src
    # 체결 가격은 여전히 현재가(원본 프레임의 **마지막** 종가)여야 한다.
    #
    # ⚠️ 여기도 원래 줄 전체를 글자로 박아 뒀다가 감사 212에서 빨개졌다
    #    — 원화 환산이 붙어 글자가 달라졌을 뿐 계약은 그대로였다(감사
    #    183·199·204·211에 이어 다섯 번째 같은 함정). 글자 대신 **무엇을
    #    읽는지**를 본다: 신호 프레임(df_sig)이 아니라 원본 df의 마지막 종가.
    assert 'float(df["close"].iloc[-1])' in src, (
        "체결가가 원본 프레임의 마지막 종가에서 나오지 않는다")
    assert 'float(df_sig["close"].iloc[-1])' not in src, (
        "체결가를 신호 프레임(확정 봉)에서 읽으면 어제 종가로 체결하는 것이다")


def test_partial_bar_field_exists_in_code():
    """사이트가 약속한 bar_partial이 실제로 기록되는가(주장-코드 대조)."""
    src = (ROOT / "quant" / "live" / "daily.py").read_text(encoding="utf-8")
    assert '"bar_partial"' in src
    assert (ROOT / "quant" / "data" / "barclock.py").exists()


# ── 돈이 지금 어디 있는지 화면이 말하는가 (2026-08-13) ────────────
#
# 사장님 지적: *"아직 그리고 80000원 전액은 투자를 안한 상태인건가? 어떤
# 상황이야? 그런 내용들이 홈페이지에서 확인하기 힘들어."*
#
# 실제로 사이트 어디에도 **"얼마가 투자됐고 얼마가 현금인지"**가 없었다.
# 수익률·낙폭·종목표는 다 있는데 그 하나가 빠져서, 답하려면 장부 JSON을
# 직접 파야 했다. 실측 당시 32%만 투자되고 68%가 현금이었는데 화면에는
# 그 말이 어디에도 없었다.
#
# 이 프로젝트는 "누구든 검증할 수 있다"고 내걸었다. 검증하려는 사람이 가장
# 먼저 물을 질문에 화면이 답하지 못하면 그 약속이 약해진다. 결함 감사와
# 별개로, **빠진 사실을 채우는 것도 정직성의 일부**다.


def test_the_site_says_how_much_is_invested_and_how_much_is_cash():
    html = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    assert 'id="side-cash"' in html, "자금 배치 카드가 사라졌다"
    assert "돈이 지금 어디 있나" in html
    assert "투자 중" in html and "현금" in html, "둘 다 적어야 답이 된다"
    # 숫자는 장부에서 온다 — 산문에 박아 두면 그날부터 거짓말이 된다
    assert "pfLast.weight" in html, "투자 비율을 장부의 총노출에서 읽어야 한다"
    assert "pfLast.equity" in html, "금액을 장부의 자산에서 읽어야 한다"


def test_the_site_explains_why_the_cash_is_sitting_there():
    """'현금이 많다'만 적으면 읽는 사람은 이유를 모른다.

    1주 값에 못 미쳐 못 산 종목, 목표 대비 실제로 담긴 종목 수 —
    둘 다 이미 장부에 있는 사실이므로 화면이 말할 수 있다.
    """
    html = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    assert "lot_infeasible" in html
    assert "1주 값에 못 미쳐" in html, "왜 못 샀는지가 화면에 없다"
    assert "곳만 담김" in html, "목표 대비 실제로 담긴 수가 화면에 없다"
