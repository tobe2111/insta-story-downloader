"""자료에서 전략을 뽑을 때 **없는 규칙을 지어내지 않는지**.

⚠️ 왜 이 파일이 생겼나 (2026-08-14, 사장님 요청).

    "각 유저마다 투자 관련한 자료를 PDF든 유튜브 링크든 트레이딩뷰든 넣으면
     그 전략이 적용되게끔도 할 수 있어?"

이 기능의 가장 큰 위험은 **못 만드는데 만들어 내는 것**이다. 투자 자료 대부분에는
검증 가능한 규칙이 없다("시장의 흐름을 읽어라"). 거기서 억지로 규칙을 짜내면
그건 자료의 전략이 아니라 **우리가 지어낸 전략**이고, 사용자는 자기 아이디어가
검증됐다고 오해한다. 이 제품이 파는 게 정확히 그 반대다.

그래서 이 파일은 '뽑히는 것'만큼 **'안 뽑혀야 하는 것'을 무겁게 검사한다.**
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.ingest.extract import extract_spec           # noqa: E402
from quant.ingest.spec import (                          # noqa: E402
    SpecError,
    SpecStrategy,
    StrategySpec,
    Condition,
    spec_from_dict,
)


def _prices(n: int = 400, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0005, 0.02, n))),
                      index=idx)
    return pd.DataFrame({"open": close, "high": close * 1.01,
                         "low": close * 0.99, "close": close,
                         "volume": 1e6}, index=idx)


# ── ① 지어내지 않는다 ─────────────────────────────────────────────

@pytest.mark.parametrize("text,why", [
    ("시장의 흐름을 읽고 과감하게 진입하라.", "숫자 없는 조언"),
    ("손실은 짧게, 이익은 길게 가져가라.", "격언"),
    ("공포에 사서 탐욕에 팔아라.", "격언"),
    ("오늘 점심은 김치찌개입니다.", "투자와 무관"),
    ("이 종목은 정말 좋아 보입니다. 강력 추천합니다.", "근거 없는 추천"),
    ("RSI 30", "숫자는 있지만 사라는 건지 팔라는 건지 없다"),
    ("20일 이동평균선을 봅니다.", "지표만 있고 조건이 없다"),
    ("", "빈 자료"),
])
def test_material_without_a_rule_makes_no_strategy(text, why):
    """규칙이 없으면 **전략을 만들지 않는다.** 이게 이 기능의 핵심 기능이다."""
    r = extract_spec(text, title="시험")
    assert not r.ok, f"{why}인데 전략이 만들어졌다: {r.spec and r.spec.summary()}"
    assert r.reasons, "못 뽑았으면 이유를 말해야 한다 — 침묵은 고장으로 읽힌다"


def test_it_distinguishes_no_rule_from_unrunnable_rule():
    """'규칙이 없다'와 '규칙은 있는데 숫자가 없다'는 사용자가 할 일이 다르다.

    전자는 다른 자료를 찾아야 하고, 후자는 자기 규칙을 숫자로 다시 쓰면 된다.
    같은 말로 뭉뚱그리면 사용자는 무엇을 고쳐야 할지 알 수 없다.
    """
    vague = extract_spec("추세를 읽고 분위기를 봐서 들어간다.", title="a")
    plain = extract_spec("어제 비가 왔습니다.", title="b")
    assert not vague.ok and not plain.ok
    assert "숫자로 적힌 조건이 없습니다" in " ".join(vague.reasons)
    assert "숫자로 적힌 조건이 없습니다" not in " ".join(plain.reasons)


def test_direction_is_not_filled_in_by_convention():
    """'RSI 30'만 보고 매수라고 정하지 않는다 — 그건 자료가 아니라 우리 상식이다.

    관례로 채우기 시작하면 "당신 자료의 전략"이라는 말이 거짓이 된다.
    """
    assert not extract_spec("RSI가 30 이하입니다.", title="x").ok
    assert extract_spec("RSI가 30 이하로 내려가면 매수한다.", title="x").ok


def test_a_sell_sentence_does_not_become_a_buy_rule():
    """'하향 돌파하면 매도'가 **매수 조건**으로 들어가면 정반대로 매매한다.

    ⚠️ 만들자마자 실제로 이랬다 — 이평 교차 패턴이 문장의 매수/매도를 안 보고
       전부 진입으로 넣고 있었다.
    """
    r = extract_spec(
        "20일 이동평균선이 60일 이동평균선을 상향 돌파하면 매수한다.\n"
        "20일 이동평균선이 60일 이동평균선을 하향 돌파하면 매도한다.",
        title="교차")
    assert r.ok, r.reasons
    assert [c.op for c in r.spec.entry] == ["cross_above"]
    assert [c.op for c in r.spec.exit] == ["cross_below"]


# ── ② 실행 가능한 것만 전략이 된다 ──────────────────────────────

def test_a_cross_entry_without_an_exit_is_refused():
    """돌파는 **사건**이라, 파는 규칙이 없으면 하루 들고 파는 전략이 된다.

    ⚠️ 실측(400봉): 보유 0.8% · 진입 3회. 살아 있는 것처럼 보이지만 사실상
       아무것도 안 하고 수수료만 낸다. '골든크로스에 산다'는 보통 '데드크로스에
       판다'를 뜻하지만 **자료가 그렇게 안 적었으면 우리가 채우지 않는다.**
    """
    r = extract_spec("20일 이동평균선이 60일 이동평균선을 상향 돌파하면 매수한다.",
                     title="교차만")
    assert not r.ok
    assert "언제 파는지가 없습니다" in " ".join(r.reasons)


def test_a_state_entry_without_an_exit_is_fine():
    """반대로 **상태** 조건은 청산 규칙이 없어도 뜻이 통한다.

    '종가가 200일선 위일 때 보유'는 아래로 내려가면 파는 것이 자연스럽다.
    사건과 상태를 같게 다루면 둘 중 하나가 반드시 틀린다.
    """
    r = extract_spec("주가가 200일 이동평균선 위에 있을 때만 매수한다.", title="추세")
    assert r.ok, r.reasons
    sig = SpecStrategy(r.spec).generate_signals(_prices())
    assert 0.0 < float((sig > 0).mean()) < 1.0, "늘 사거나 늘 안 사면 규칙이 아니다"


def test_leverage_cannot_enter_through_a_spec():
    """명세로 레버리지를 들여올 수 없다 — 비중 상한은 코드가 지킨다."""
    with pytest.raises(SpecError, match="레버리지"):
        StrategySpec(name="x", weight=2.0,
                     entry=[Condition("close", ">", "sma:20", "근거")]).validate()


def test_a_condition_without_a_quote_is_refused():
    """근거를 못 대는 조건은 만들지 않는다.

    이 검사가 없으면 "자료에서 뽑았다"는 말과 실제가 갈라지고, 사용자는 자기
    자료가 검증됐다고 오해한다.
    """
    with pytest.raises(SpecError, match="근거 문장"):
        StrategySpec(name="x",
                     entry=[Condition("close", ">", "sma:20", "")]).validate()


def test_unknown_indicators_are_refused_not_guessed():
    """모르는 지표는 **모른다고 한다.** 비슷한 걸로 바꿔치기하지 않는다."""
    with pytest.raises(SpecError, match="모릅니다"):
        spec_from_dict({"version": 1, "name": "x",
                        "entry": [{"left": "supertrend:10", "op": ">",
                                   "right": "0", "quote": "근거"}]})


def test_a_spec_cannot_smuggle_code():
    """명세는 **데이터**다 — 실행 가능한 것이 들어올 자리가 없다.

    사용자가 100명이면 임의 코드 실행 경로도 100개가 된다. 명세가 연산자
    목록 밖으로 못 나가는 것이 그 통로를 막는다.
    """
    with pytest.raises(SpecError):
        spec_from_dict({"version": 1, "name": "x",
                        "entry": [{"left": "close", "op": "__import__",
                                   "right": "os", "quote": "근거"}]})


# ── ③ 미래를 훔쳐보지 않는다 ────────────────────────────────────

@pytest.mark.parametrize("text", [
    "20일 신고가를 뚫으면 매수한다.",
    "RSI가 30 이하로 내려가면 매수한다. RSI가 70 이상이면 매도한다.",
    "주가가 200일 이동평균선 위에 있을 때만 매수한다.",
    # 넓어진 사전(2026-08-17)도 같은 검사를 통과해야 한다 — 새 지표가
    # 미래를 보면 그 전략의 백테스트 전체가 거짓말이 된다.
    "볼린저밴드 하단에 닿으면 매수한다. 볼린저밴드 상단에 닿으면 매도한다.",
    "거래량이 20일 평균의 2배 이상이면 매수한다. RSI가 70 이상이면 매도한다.",
    "3일 연속 양봉이면 매수한다. 3일 연속 음봉이면 매도한다.",
    "MACD가 시그널선을 골든크로스하면 매수한다. MACD가 데드크로스하면 매도한다.",
    "주가가 20일 이동평균선 위에 있으면 매수한다. 손절은 -8%, 익절은 +20%로 잡는다.",
])
def test_specs_do_not_look_ahead(text):
    """미래를 잘라내도 **과거 신호가 그대로여야** 한다.

    문자열로 "shift(-1)이 없다"를 확인하는 대신 값으로 본다 — 룩어헤드는
    이 저장소에서 가장 비싼 결함이고, 뒤늦게 발견되면 그동안의 기록이 전부
    무의미해진다.
    """
    df = _prices()
    s = SpecStrategy(extract_spec(text, title="t").spec)
    full = s.generate_signals(df).iloc[:300].to_numpy()
    cut = s.generate_signals(df.iloc[:300]).to_numpy()
    assert np.allclose(full, cut), "미래를 자르니 과거 신호가 바뀐다 — 룩어헤드"


def test_the_breakout_high_excludes_today():
    """'최근 20봉 최고가'에 **오늘 고가**가 들어가면 조건이 늘 참이 된다.

    자기 자신과 비교하는 셈이라 "신고가 돌파" 전략이 매일 사는 전략이 된다.
    실제로 살 수 있는 것은 어제까지의 최고가를 넘는 순간이다.
    """
    df = _prices()
    sig = SpecStrategy(extract_spec("20일 신고가를 뚫으면 매수한다.", title="t").spec) \
        .generate_signals(df)
    held, entries = float((sig > 0).mean()), int((sig.diff() > 0).sum())
    # ⚠️ 위쪽만 보면(held < 0.5) **한 번도 안 사는 전략도 통과한다.**
    #    오늘 고가를 포함시키면 고가 > 종가라 조건이 영원히 거짓이 되고,
    #    보유 0%가 되어 '얌전한 전략'처럼 보인다. 아래쪽도 함께 못 박는다.
    assert entries > 0, ("신고가 돌파인데 한 번도 안 샀다 — 오늘 고가를 "
                         "최고가에 넣어 자기 자신과 비교하고 있다")
    assert held < 0.5, f"보유 비율이 {held:.0%} — 신고가 돌파치고 너무 잦다"


# ── ④ 워밍업 구간을 '팔아야 할 때'로 채점하지 않는다 ─────────────

def test_warmup_bars_take_no_position():
    """지표가 아직 없는 구간에서는 **포지션을 잡지 않는다.**

    ⚠️ 여기 원래 `known` 마스크가 있었고 "NaN을 불충족으로 읽으면 워밍업이
       '팔아야 할 때'가 된다"는 주석이 붙어 있었다. 변이 검사가 그 마스크를
       지워도 결과가 한 봉도 안 바뀌는 것을 잡았다 — pandas에서 NaN 비교는
       이미 False이고, 진입이면 '안 산다'라 그게 맞는 기본값이다.
       **하는 일이 없는데 막는다고 적힌 장치**는 이 저장소가 가장 경계하는
       것이라 마스크를 지웠다. 지키는 것은 마스크가 아니라 이 결과다.
    """
    df = _prices(n=250)
    s = SpecStrategy(extract_spec("주가가 200일 이동평균선 위에 있을 때만 매수한다.",
                                  title="t").spec)
    sig = s.generate_signals(df)
    assert float(sig.iloc[:199].abs().sum()) == 0.0, "워밍업 구간에 포지션이 있다"


# ── 못 옮긴 것을 말하는가 (감사 269) ────────────────────────────

def test_a_rule_we_cannot_translate_is_named_not_silently_dropped():
    """지어내지 않는 것과 **말하지 않는 것**은 다르다.

    실측(2026-08-16): 사장님 자료에 "손절은 -8%, 익절은 +20%로 잡습니다"가
    있었는데, 화면은 조건 두 개만 보여주고 그 문장은 **언급조차 하지
    않았다.** 사용자는 "✅ 이렇게 읽었습니다"를 보고 자기 규칙이 전부
    반영된 줄 안다 — 실제로는 위험 관리가 통째로 빠졌는데도.

    2026-08-17부터 손절/익절은 옮겨진다(아래 별도 검사). 그래서 이 검사의
    예시는 **여전히 못 옮기는** 분할매수로 바꿨다 — 사전이 넓어져도 이
    장치(못 옮긴 것을 말한다)는 계속 필요하다.
    """
    from quant.ingest.extract import extract_spec
    # ⚠️ 파는 규칙을 함께 넣는다. 안 넣으면 '돌파 매수인데 매도가 없다'는
    #    **다른** 가드에 먼저 걸려, 이 검사가 무엇을 보는지 흐려진다.
    out = extract_spec(
        "20일 이동평균선이 60일 이동평균선을 위로 돌파하면 매수합니다.\n"
        "RSI 70 위로 올라가면 정리합니다.\n"
        "매수는 3번에 나눠 분할매수로 진입합니다.\n")
    assert out.ok, out.reasons
    blob = "\n".join(out.reasons)
    assert "옮기지 못했습니다" in blob, (
        f"못 옮긴 규칙을 조용히 버린다: {out.reasons}")
    assert "분할" in blob, "어느 문장이 빠졌는지 안 알려준다"
    assert "반영되지 않습니다" in blob, (
        "빠졌다는 사실은 말하면서 '검증에 안 들어간다'는 결과를 안 말한다")


def test_a_fully_translated_note_stays_quiet():
    """다 옮겼는데도 경고하면 사용자가 경고를 무시하기 시작한다."""
    from quant.ingest.extract import extract_spec
    out = extract_spec(
        "20일 이동평균선이 60일 이동평균선을 위로 돌파하면 매수합니다.\n"
        "RSI 70 위로 올라가면 과열이므로 정리합니다.\n")
    assert out.ok, out.reasons
    assert "옮기지 못했습니다" not in "\n".join(out.reasons), (
        f"전부 옮겼는데 못 옮겼다고 한다: {out.reasons}")


# ── ⑥ 넓어진 사전 (2026-08-17) — 각 패턴은 '뽑혀야 할 것'과 '안 뽑혀야
#     할 것'을 함께 고정한다. 한쪽만 보면 아무거나 뽑는 사전도 통과한다. ──

def test_stop_and_target_are_translated_now():
    """감사 269의 바로 그 문장 — "손절 -8%, 익절 +20%"가 이제 옮겨진다."""
    from quant.ingest.extract import extract_spec
    out = extract_spec(
        "20일 이동평균선이 60일 이동평균선을 위로 돌파하면 매수합니다.\n"
        "RSI 70 위로 올라가면 정리합니다.\n"
        "손절은 -8%, 익절은 +20%로 잡습니다.\n")
    assert out.ok, out.reasons
    assert out.spec.stop and out.spec.stop["pct"] == 8.0, out.spec.stop
    assert out.spec.target and out.spec.target["pct"] == 20.0, out.spec.target
    assert "손절" in out.spec.stop["quote"], "근거 문장이 안 붙었다"
    assert "옮기지 못했습니다" not in "\n".join(out.reasons), (
        f"옮겨 놓고 못 옮겼다고 한다: {out.reasons}")


def test_a_stop_actually_cuts_the_loss_in_execution():
    """읽는 것과 도는 것은 다르다 — 손절이 **값으로** 자산을 지키는가."""
    import numpy as np
    import pandas as pd

    from quant.ingest.spec import Condition, SpecStrategy, StrategySpec
    spec = StrategySpec(
        "s", entry=[Condition("sma:2", "cross_above", "sma:4", "근거")],
        stop={"pct": 8.0, "quote": "손절 -8%"})
    idx = pd.date_range("2026-01-01", periods=40, freq="D")
    c = pd.Series(np.r_[np.linspace(100, 95, 10), np.linspace(95, 105, 5),
                        np.linspace(105, 60, 25)], index=idx)
    df = pd.DataFrame({"open": c, "high": c, "low": c, "close": c,
                       "volume": 1e6}, index=idx)
    sig = SpecStrategy(spec).generate_signals(df)
    entered = sig[sig > 0]
    assert len(entered) > 0, "진입 자체가 없다 — 픽스처가 잘못됐다"
    exit_i = sig.index.get_loc(entered.index[-1]) + 1
    entry_px = float(c.iloc[sig.index.get_loc(entered.index[0])])
    exit_px = float(c.iloc[exit_i - 1])
    loss = exit_px / entry_px - 1
    assert loss > -0.20, (
        f"손절 -8%인데 {loss:.0%}까지 들고 있었다 — 손절이 장식이다")
    assert float(sig.iloc[-1]) == 0.0, "폭락 끝까지 포지션을 들고 있다"


def test_an_event_entry_with_a_stop_is_not_a_one_day_trade():
    """돌파 매수 + 손절/익절만 있는 전략 — 예전엔 거부됐지만 이제 성립한다.

    단 '진입 조건이 깨지면 청산'으로 돌면 하루살이가 되므로, 나가는 길이
    손절/익절뿐인지 값으로 확인한다.
    """
    import numpy as np
    import pandas as pd

    from quant.ingest.extract import extract_spec
    from quant.ingest.spec import SpecStrategy
    out = extract_spec("20일 신고가를 뚫으면 매수한다. 손절은 8%로 한다.")
    assert out.ok, out.reasons
    # 픽스처: 40봉 횡보(100) → 하루 돌파(110) → 횡보(108). 돌파 다음 날부터
    # 진입 조건은 거짓이 되지만(108은 신고가가 아니다) 손절(-8%)에는 안
    # 걸린다(-1.8%). 그래서 '진입 조건이 깨지면 청산'으로 돌면 정확히
    # 하루살이가 되고, 나가는 길이 손절/익절뿐이면 계속 들고 있는다 —
    # 두 구현이 **다른 답**을 내는 경로라야 변이가 드러난다. (단조 상승
    # 픽스처는 진입 조건이 매일 참이라 두 구현이 같은 답을 냈다.)
    idx = pd.date_range("2026-01-01", periods=80, freq="D")
    c = pd.Series(np.r_[np.full(40, 100.0), [110.0],
                        np.full(39, 108.0)], index=idx)
    df = pd.DataFrame({"open": c, "high": c, "low": c,
                       "close": c, "volume": 1e6}, index=idx)
    sig = SpecStrategy(out.spec).generate_signals(df)
    entries = int((sig.diff() > 0).sum())
    assert entries > 0, "돌파가 설계된 픽스처인데 진입이 없다 — 픽스처 오류"
    held = float((sig > 0).sum()) / entries
    assert held > 1.5, (
        f"돌파+손절 전략이 평균 {held:.1f}일만 들고 판다 — 나가는 길이 "
        "손절/익절이어야 하는데 '진입 조건이 깨지면 청산'으로 돌고 있다")


def test_the_volume_average_excludes_today():
    """'평균의 2배'의 평균은 **어제까지**다 — 오늘을 넣으면 큰 날일수록
    분모가 커져 문턱이 스스로 올라간다(2배가 영원히 안 나온다)."""
    import pandas as pd

    from quant.ingest.spec import _series
    idx = pd.date_range("2026-01-01", periods=7, freq="D")
    df = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0,
                       "volume": [10.0] * 6 + [30.0]}, index=idx)
    assert float(_series("vol_ratio:5", df).iloc[-1]) == 3.0, (
        "어제까지 평균 10에 오늘 30이면 정확히 3.0배여야 한다 — 오늘이 "
        "분모에 섞이고 있다")


def test_the_stop_sign_is_actually_captured():
    """'손절은 -8%'의 부호가 캡처돼 절댓값 처리를 **실제로 거치는가**.

    빈틈 문자클래스에 -가 들어 있으면 탐욕 매칭이 부호를 삼켜 abs()가
    죽은 코드가 된다 — 변이 시험이 그 상태를 잡아서 이 검사를 만들었다.
    """
    from quant.ingest.extract import _STOP_RE
    m = _STOP_RE.search("손절은 -8%로 잡는다.")
    assert m and m.group(2) == "-8", (
        f"부호가 캡처되지 않는다: {m and m.group(2)!r} — 빈틈 클래스가 "
        "-를 삼키고 있다")


def test_bollinger_volume_streak_macd_are_translated():
    from quant.ingest.extract import extract_spec
    out = extract_spec(
        "볼린저밴드 하단에 닿으면 매수한다.\n"
        "거래량이 20일 평균의 2배 이상일 때만 매수한다.\n"
        "MACD가 시그널선을 골든크로스하면 매수한다.\n"
        "3일 연속 음봉이면 매도한다.\n")
    assert out.ok, out.reasons
    lefts = {c.left for c in out.spec.entry}
    assert "close" in lefts and "vol_ratio:20" in lefts and "macd" in lefts, (
        f"새 패턴이 안 뽑힌다: {lefts}")
    assert {c.left for c in out.spec.exit} == {"down_streak"}, out.spec.exit


@pytest.mark.parametrize("text,why", [
    ("거래량이 터지면 매수한다.", "배수 숫자가 없다 — '터지면'은 규칙이 아니다"),
    ("볼린저밴드 상단에 닿으면 매수한다.", "상단 터치 매수는 뜻이 갈린다(돌파인지 회귀인지)"),
    ("MACD가 좋아 보이면 매수한다.", "교차 방향이 없다"),
    ("연속 양봉이 나오면 매수한다.", "며칠 연속인지 숫자가 없다"),
    ("손절을 잘 잡아야 한다.", "손절 %가 없다"),
])
def test_the_wider_dictionary_still_refuses_vague_sentences(text, why):
    """사전이 넓어져도 **숫자 없는 문장은 여전히 거절**한다 — 넓힌다는 것이
    아무거나 받는다는 뜻이 되면 처음의 원칙이 무너진다."""
    from quant.ingest.extract import extract_spec
    out = extract_spec(text)
    assert not out.ok, f"{why} — 그런데 전략이 나왔다: {out.spec and out.spec.summary()}"


def test_conflicting_stop_values_are_reported_not_averaged():
    """손절이 두 값으로 나오면 첫 값을 쓰되 **둘째 문장을 못 옮김으로 보고**한다."""
    from quant.ingest.extract import extract_spec
    out = extract_spec(
        "주가가 20일 이동평균선 위에 있으면 매수한다.\n"
        "손절은 -8%로 잡는다.\n"
        "하락장에서는 손절을 -5%로 줄인다.\n")
    assert out.ok, out.reasons
    assert out.spec.stop["pct"] == 8.0
    blob = "\n".join(out.reasons)
    assert "-5%" in blob or "5%" in blob, (
        f"모순되는 둘째 손절 문장이 조용히 사라졌다: {out.reasons}")


def test_the_korean_verb_for_breaking_through_is_understood():
    """'뚫다'는 '돌파하다'만큼 흔하다 — 빠지면 파는 규칙만 사라진다.

    실측: 매수는 "위로 돌파", 매도는 "아래로 뚫으면"으로 적힌 자료에서
    **매도 규칙만 조용히 사라져** 사는 규칙뿐인 전략이 됐다.
    """
    from quant.ingest.extract import extract_spec
    out = extract_spec(
        "20일 이동평균선이 60일 이동평균선을 위로 돌파하면 매수합니다.\n"
        "반대로 20일선이 60일선을 아래로 뚫으면 전량 매도합니다.\n")
    assert out.ok, out.reasons
    ops = [c.op for c in out.spec.exit]
    assert "cross_below" in ops, (
        f"'아래로 뚫으면 매도'를 못 읽는다 — 파는 규칙이 사라진다: {ops}")
