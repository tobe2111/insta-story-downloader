"""플러스 62%인데 보유를 이긴 건 31% — 대조군 없는 성적표는 스스로를 속인다.

세 가지가 맞물려 있습니다.

**① 긴 검증에 대조군이 없었습니다.** 어제 만든 보고서는 "125구간 중 플러스
78개(62%)"라고 말했습니다. 좋아 보입니다. 그런데 **같은 구간을 그냥 들고만
있었다면** 어땠는지 옆에 놓으면 숫자가 뒤집힙니다:

    보유를 이긴 구간   **39개(31%)**
    SK하이닉스        전략 +21.6%  vs  보유 **+852.4%**
    삼성전자          전략 +11.5%  vs  보유 **+259.0%**

신뢰 페이지는 이미 *"그냥 보유했다면을 나란히 보여줍니다"*라고 약속하고
있었습니다 — 새로 만든 보고서만 그 약속에서 빠져 있었습니다.

**② 자본을 얼마나 굴리는지 아무 데도 없었습니다.** 종목별 참고 계좌의 평균
노출은 **9%**, 시장에 들어가 있던 시간은 45%였습니다. 통합 계좌는 20종목을
합쳐 총노출 42~51%입니다 — 두 숫자는 다르며, 뭉뚱그리면 "자본의 91%가
현금"이라는 **틀린** 결론이 나옵니다. 그래서 라벨에 기준을 적습니다.

**③ 사이징 축을 오디션이 한 번도 안 흔들었습니다.** 노출이 낮은 이유는
설정 한 줄입니다(`sizing="proba"`, 확신도 비례). 문턱 0.55에서 모델이 "60%"
라고 해도 사는 것은 자본의 11%입니다. 그런데 야간 오디션의 탐색 축 일곱 개에
`sizing`이 없었습니다 — **없는 축은 영원히 집니다.**
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.retrain import DEFAULT_CHALLENGERS, mutate_champion  # noqa: E402
from quant.live.walkforward import (  # noqa: E402
    format_walkforward,
    segment_scores,
    walkforward_report,
)

CHAMP = {"strategy": "ml", "params": {"model": "logreg", "threshold": 0.55,
                                      "train_window": 250, "retrain_every": 20}}


def _series(vals, start="2020-01-01"):
    return pd.Series(vals, index=pd.date_range(start, periods=len(vals),
                                               freq="D"))


# ── ① 대조군 ─────────────────────────────────────────────────

def test_the_segment_carries_what_holding_would_have_done():
    strat = _series([0.001] * 200)
    hold = _series([0.002] * 200)
    segs = segment_scores(strat, 0, "us_stock", 2, hold=hold)
    assert segs and all("hold_return" in s for s in segs)
    assert all(s["beat_hold"] is False for s in segs), (
        "보유가 두 배로 벌었는데 전략이 이겼다고 적었다")


def test_beating_hold_is_recorded_as_beating():
    """대조군 — 판정이 늘 False면 대조군이 있으나 마나다."""
    segs = segment_scores(_series([0.003] * 200), 0, "us_stock", 2,
                          hold=_series([0.001] * 200))
    assert segs and all(s["beat_hold"] is True for s in segs)


def test_a_losing_market_can_still_be_beaten():
    """실측 그 장면 — LG화학은 전략 -3.0%, 보유 -28.5%였다.

    마이너스여도 보유보다 덜 잃었으면 이긴 것이다. 부호만 보면 이 구간을
    '실패'로 적게 되고, 그것은 방어형 전략의 값어치를 통째로 지운다.
    """
    segs = segment_scores(_series([-0.0005] * 200), 0, "us_stock", 1,
                          hold=_series([-0.002] * 200))
    assert segs[0]["total_return"] < 0 and segs[0]["beat_hold"] is True


def test_no_control_arm_means_no_claim():
    """대조군을 안 주면 지어내지 않는다 — 없는 값을 0으로 채우면 거짓말이다."""
    segs = segment_scores(_series([0.001] * 200), 0, "us_stock", 2)
    assert segs and all("hold_return" not in s and "beat_hold" not in s
                        for s in segs)


def test_the_hold_series_is_aligned_not_just_appended():
    """길이가 달라도 **같은 날짜**끼리 비교해야 한다.

    어긋난 채 비교하면 대조군 자체가 거짓말이 된다.
    """
    strat = _series([0.001] * 100, start="2020-03-01")
    hold = _series([0.002] * 300, start="2020-01-01")     # 앞뒤로 더 길다
    segs = segment_scores(strat, 0, "us_stock", 1, hold=hold)
    assert segs[0]["hold_return"] == pytest.approx(
        (1.002 ** len(strat)) - 1, rel=1e-6)


# ── 실제 보고서에 닿는가 ──────────────────────────────────────

def _offline():
    rep = walkforward_report("state", fetch=False, bars=800)
    if not rep:
        pytest.skip("스냅샷 없음")
    return rep


def test_the_report_states_both_numbers():
    """플러스 비율만 있고 보유 대비가 없으면 상승장에서 늘 잘해 보인다."""
    rep = _offline()
    assert rep["beat_hold_rate"] is not None
    assert 0 < rep["beat_hold_segments"] <= rep["n_segments"]
    # ⚠️ 합계만 보면 안 된다 — 대조군을 통째로 안 넘겨도 합계는 0으로 채워져
    #    "이긴 구간 0개(0%)"라는 **그럴듯한** 숫자가 나온다. 구간마다 보유
    #    수익이 실제로 실려 있는지 본다(변이 시험이 이 구멍을 찔러 잡았다).
    for r in rep["symbols"]:
        for s in r["segments"]:
            assert "hold_return" in s and "beat_hold" in s, (
                f"{r['key']} 구간에 대조군이 없다: {sorted(s)}")
    text = format_walkforward(rep)
    assert "보유를 이긴 구간" in text, "사람이 읽는 문장에 대조군이 없다"


def test_the_headline_number_is_not_flattering_by_omission():
    """실측 그 장면 — 플러스 62% vs 보유 이김 31%.

    두 숫자가 같으면 이 검사는 아무것도 안 지킨다. 실제로 갈리는지 본다.
    """
    rep = _offline()
    assert rep["beat_hold_rate"] < rep["win_rate"], (
        f"플러스 {rep['win_rate']} vs 보유이김 {rep['beat_hold_rate']} — "
        "전제가 바뀌었으면 문서의 숫자도 함께 고쳐야 한다")


# ── ② 굴린 자본이 보이는가 ───────────────────────────────────

def test_the_report_says_how_much_capital_was_deployed():
    rep = _offline()
    assert 0.0 < rep["avg_exposure"] < 1.0
    assert 0.0 < rep["time_in_market"] <= 1.0
    for r in rep["symbols"]:
        assert r["avg_exposure"] is not None


def test_the_exposure_label_names_which_account():
    """⚠️ 종목별 참고 계좌(9%)와 통합 계좌(42~51%)는 다른 숫자다.

    뭉뚱그리면 "자본의 91%가 현금"이라는 틀린 결론이 나온다.
    """
    text = format_walkforward(_offline())
    assert "종목당 평균 노출" in text
    assert "참고 계좌 기준" in text, "어느 계좌 기준인지 안 밝혔다"


def test_the_weekly_report_shows_deployed_capital(tmp_path):
    """통합 계좌 쪽 숫자 — 장부에 계속 있었지만 아무도 안 읽었다."""
    import json

    from quant.live.daily import format_weekly, weekly_summary

    (tmp_path / "paper").mkdir()
    (tmp_path / "paper" / "portfolio_ALL.json").write_text(json.dumps({
        "market": "portfolio", "symbol": "ALL",
        "history": [
            {"date": "2026-08-13", "equity": 1_000_000, "return_pct": 0.0,
             "weight": 0.50},
            {"date": "2026-08-14", "equity": 1_000_000, "return_pct": 0.0,
             "weight": 0.42},
        ]}), "utf-8")
    dep = weekly_summary(str(tmp_path))["health"]["deployed"]
    assert dep["gross_mean"] == pytest.approx(0.46)
    assert dep["gross_last"] == pytest.approx(0.42)
    assert "굴린 자본" in format_weekly(weekly_summary(str(tmp_path)))


def test_a_ledger_without_the_number_says_nothing(tmp_path):
    """대조군 — 옛 기록에는 노출이 없다. 0%로 때우면 '아무것도 안 샀다'가 된다."""
    import json

    from quant.live.daily import weekly_summary

    (tmp_path / "paper").mkdir()
    (tmp_path / "paper" / "portfolio_ALL.json").write_text(json.dumps({
        "market": "portfolio", "symbol": "ALL",
        "history": [{"date": "2026-08-13", "equity": 1_000_000,
                     "return_pct": 0.0},
                    {"date": "2026-08-14", "equity": 1_000_000,
                     "return_pct": 0.0}]}), "utf-8")
    assert "deployed" not in weekly_summary(str(tmp_path))["health"]


# ── ③ 사이징이 링에 서는가 ───────────────────────────────────

def test_sizing_is_a_fixed_challenger():
    """없는 축은 영원히 진다 — 탐색 공간에 없으면 이길 기회조차 없다.

    ⚠️ 한 개만 있는지 보면 안 된다. 사이징은 모델·문턱과 얽혀서, 하나만
       세우면 "그 조합이 나빴다"와 "사이징이 나빴다"를 구별할 수 없다.
       모델 둘 이상 · 문턱 둘 이상에 걸쳐 세운다(변이 시험이 이 자리를
       한 개 지웠을 때 예전 검사는 그냥 통과했다).
    """
    ring = [c for c in DEFAULT_CHALLENGERS
            if isinstance(c, dict) and c.get("sizing") == "binary"]
    assert len(ring) >= 3, f"사이징 후보가 {len(ring)}개뿐이다"
    assert len({c.get("model") for c in ring}) >= 2, "모델이 한 종류뿐이다"
    assert len({c.get("threshold") for c in ring}) >= 2, "문턱이 한 값뿐이다"


def test_sizing_is_a_mutation_axis():
    """돌연변이 축에도 있어야 문턱·모델과 조합해 탐색된다."""
    hit = sum(1 for i in range(40)
              if any("sizing" in m["params"]
                     for m in mutate_champion(CHAMP, seed=f"s{i}")))
    assert hit > 0, "40개 시드에서 사이징 변이가 한 번도 안 나왔다"


def test_the_sizing_challenger_actually_changes_the_signal():
    """후보가 챔피언과 같은 신호를 내면 링에 세워도 대결이 성립하지 않는다."""
    from quant.live.walkforward import _snapshot_frame
    from quant.strategies import get_strategy

    # ⚠️ 지어낸 톱니 계열로는 못 잰다 — 모델 확률이 문턱을 한 번도 못 넘어
    #    두 설정이 나란히 0을 낸다(처음 이 검사를 그렇게 썼다가 걸렸다).
    #    진짜 시세로 잰다.
    df = _snapshot_frame("state", "us_stock", "SPY")
    if df is None or len(df) < 400:
        pytest.skip("스냅샷 없음")
    base = dict(CHAMP["params"])
    a = get_strategy("ml", **base).generate_signals(df)
    b = get_strategy("ml", **{**base, "sizing": "binary"}).generate_signals(df)
    assert not a.equals(b), "사이징을 바꿨는데 신호가 한 봉도 안 달라졌다"
    assert b.abs().mean() > a.abs().mean(), (
        "binary가 proba보다 노출이 크지 않다 — 전제 확인 필요")


def test_promotion_still_has_to_be_earned():
    """사이징을 손으로 갈아치우지 않는다 — 2단계 관문을 이겨야 한다.

    실측이 좋아 보여도 인샘플 한 구간이다. 여기서 기본값을 바꾸면 이 제품이
    막으려는 바로 그 행동이 된다.
    """
    from quant.strategies.ml import MLStrategy

    assert MLStrategy().sizing == "proba", (
        "기본 사이징이 손으로 바뀌었다 — 승격은 오디션이 결정한다")
