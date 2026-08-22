"""사이징 축 — 3년 만에 처음으로 재기 시작한다 (2026-08-22).

사장님 질문: *"왜 이렇게 단타도 조금씩만 하는거야?"* 미국 장중 21회차를
뜯어 금액 사슬을 실측했다:

    $10,000 ÷ 종목 8 = $1,248 → × 신호 0.086 = **$107** (자본의 약 1%)

범인은 종목 나누기가 아니라 신호 세기였고, 그 값은 확률→비중 한 줄에서
나온다: `(p − 0.55) / 0.45`. 실측 중앙 확률은 0.589 — 즉 **모델이 59%만
확신하니까 9%만 거는 것**이다.

그리고 그 규칙은 생각보다 방어 가능하다. 같은 확률에서 현행 0.087,
켈리 절반 0.089 — 사실상 같다. 문제는 "값이 틀렸다"가 아니라 저장소가
스스로 적어 둔 것처럼 **"오디션이 184회 동안 한 번도 안 흔든 축"**이라는
점이다.

지켜야 할 약속:
- 데드존(진입 조건)은 네 규칙이 **공유**한다 — 크기 축만 격리해야 무엇이
  이겼는지 말할 수 있다.
- 확률을 못 받은 종목은 넷 다 그날 통째로 뺀다. 0.5로 채우면 '모른다'가
  '관망 판단'으로 둔갑한다.
- 같은 봉을 다시 돌려도 기록이 늘지 않는다(멱등).
- 본 계좌에는 적용하지 않는다 — 크기 규칙은 판정 시계의 축이다.
- 사전 등록이 돼 있고 공개 페이지에 같은 판정일이 실린다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live import sizing_ladder as SL                  # noqa: E402


# ── ① 크기 규칙 자체 ────────────────────────────────────────────

def test_every_rule_shares_the_same_dead_zone():
    """진입 조건까지 바뀌면 '자주 사서 이겼는지 크게 사서 이겼는지'를 못 가른다."""
    for s in SL.SIZERS:
        assert SL.size_of(s, 0.549, 0.55) == 0.0, f"{s}가 문턱 아래에서 샀다"
        assert SL.size_of(s, 0.20, 0.55) == 0.0, f"{s}가 하락 확률에 샀다"


def test_the_current_rule_is_about_half_kelly_where_the_model_actually_lives():
    """실측 확률 구간에서 현행 ≈ 켈리 절반 — '틀린 값'이 아니라 '안 재본 값'.

    이 검사가 있는 이유: 사장님께 "현행 사이징이 임의값"이라고 말할 뻔했다.
    숫자를 대면해 보니 관측 구간에서는 표준 관행(절반 켈리)과 거의 같다.
    """
    p = 0.589                                    # 실측 중앙 확률
    cur = SL.size_of("current", p, 0.55)
    half = SL.size_of("half", p, 0.55)
    assert abs(cur - half) < 0.01, (
        f"현행 {cur:.3f} vs 켈리 절반 {half:.3f} — 이 문서의 근거가 바뀌었다")
    # 그러나 확신이 커지면 갈라진다 — 그래서 잴 값어치가 있다.
    assert SL.size_of("current", 0.95, 0.55) > SL.size_of("half", 0.95, 0.55) * 1.5


def test_more_confidence_never_means_a_smaller_bet():
    for s in ("current", "kelly", "half"):
        prev = -1.0
        for p in (0.55, 0.6, 0.7, 0.8, 0.9, 1.0):
            w = SL.size_of(s, p, 0.55)
            assert w >= prev, f"{s}: 확률이 오르는데 비중이 줄었다 ({p})"
            prev = w


def test_no_rule_ever_borrows():
    for s in SL.SIZERS:
        for p in (0.55, 0.7, 0.99, 1.0):
            assert 0.0 <= SL.size_of(s, p, 0.55) <= 1.0, s


def test_a_nonsense_probability_buys_nothing():
    for bad in (-0.1, 1.4, 2.0):
        assert SL.size_of("current", bad, 0.55) == 0.0
    assert SL.size_of("current", 0.9, 0.4) == 0.0, "문턱이 0.5 이하면 계산 불가"


# ── ② 계좌를 굴리는 규약 ────────────────────────────────────────

def _marks(v=100.0):
    return {"crypto:BTC/USDT": v, "us_stock:SPY": v}


def test_a_symbol_without_a_probability_is_dropped_by_all_four(tmp_path):
    """'모른다'를 0.5로 채우면 관망 판단으로 둔갑한다."""
    out = SL.run_sizing_ladder(
        bar="2026-08-22",
        probs={"crypto:BTC/USDT": 0.7, "us_stock:SPY": None},
        thresholds={"crypto:BTC/USDT": 0.55, "us_stock:SPY": 0.55},
        marks=_marks(), state_dir=str(tmp_path))
    assert out
    for sizer, rec in out.items():
        assert rec["symbols"] == 1, f"{sizer}가 확률 없는 종목을 셌다"


def test_nothing_is_written_on_a_day_without_prices(tmp_path):
    assert SL.run_sizing_ladder(bar="2026-08-22", probs={"a": 0.7},
                                thresholds={}, marks={},
                                state_dir=str(tmp_path)) is None
    assert not (tmp_path / SL.DIR).exists(), (
        "시세도 없는 날 빈 회차를 남겼다 — 곡선이 가짜 평평함을 얻는다")


def test_running_the_same_bar_twice_does_not_grow_the_record(tmp_path):
    args = dict(probs={"crypto:BTC/USDT": 0.7},
                thresholds={"crypto:BTC/USDT": 0.55},
                marks=_marks(), state_dir=str(tmp_path))
    SL.run_sizing_ladder(bar="2026-08-22", **args)
    SL.run_sizing_ladder(bar="2026-08-22", **args)
    for s in SL.SIZERS:
        st = json.loads(
            (tmp_path / SL.DIR / f"{s}.json").read_text("utf-8"))
        assert len(st["history"]) == 1, f"{s}: 같은 봉이 두 줄 적혔다"


def test_the_bolder_rule_actually_carries_more(tmp_path):
    """전량이 현행보다 크게 실어야 실험이 뜻이 있다."""
    SL.run_sizing_ladder(bar="2026-08-22",
                         probs={"crypto:BTC/USDT": 0.6},
                         thresholds={"crypto:BTC/USDT": 0.55},
                         marks=_marks(), state_dir=str(tmp_path))
    g = {}
    for s in SL.SIZERS:
        st = json.loads((tmp_path / SL.DIR / f"{s}.json").read_text("utf-8"))
        g[s] = st["history"][-1]["gross"]
    assert g["allin"] > g["kelly"] > g["current"], g
    assert g["current"] > 0, "현행이 아무것도 안 샀다 — 비교가 성립하지 않는다"


def test_a_rise_pays_the_bolder_rule_more(tmp_path):
    """전일 목표를 오늘 수익에 적용 — 크게 실은 쪽이 오르는 날 더 번다."""
    common = dict(probs={"crypto:BTC/USDT": 0.7},
                  thresholds={"crypto:BTC/USDT": 0.55},
                  state_dir=str(tmp_path))
    SL.run_sizing_ladder(bar="2026-08-22", marks=_marks(100.0), **common)
    SL.run_sizing_ladder(bar="2026-08-23", marks=_marks(110.0), **common)
    pub = SL.sizing_public(str(tmp_path))
    assert pub
    t = pub["tracks"]
    assert t["allin"]["equity"] > t["current"]["equity"], t
    assert t["current"]["equity"] > SL.START_CASH, t


# ── ③ 배선·등록·공개 ───────────────────────────────────────────

def test_the_batch_collects_the_probability_and_runs_it():
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert "probs[key] = float(_p)" in src, "확률을 안 주워 둔다"
    assert "run_sizing_ladder(bar=bar, probs=probs" in src, "사다리를 안 돌린다"
    # 실험 실패가 본 계좌를 죽이면 안 된다.
    i = src.find("run_sizing_ladder(bar=bar")
    assert "본 계좌 무관" in src[i:i + 400], "예외를 삼키지 않는다"


def test_it_is_registered_before_the_data():
    from quant.live.prereg import PREREGISTERED, SEQUENTIAL
    e = PREREGISTERED["sizing_ladder"]
    assert e["start"] == "2026-08-22"
    assert "본페로니" in e["correction"], "트랙이 넷인데 다중비교 보정이 없다"
    assert "1.5배" in e["extra_gate"], "낙폭 관문이 없다"
    assert "판정 시계" in e["note"], "본 계좌 적용이 시계를 리셋한다는 경고가 없다"
    assert "sizing_ladder" in SEQUENTIAL["applies_to"]
    page = (ROOT / "docs" / "trust.html").read_text("utf-8")
    assert e["judge_on"] in page, "판정일이 공개 페이지에 없다"


def test_the_public_summary_admits_what_it_is_not():
    """절대 성적을 본 계좌와 비교하면 안 된다는 사실을 스스로 말해야 한다."""
    note = SL.sizing_public.__doc__ or ""
    assert note
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        SL.run_sizing_ladder(bar="2026-08-22",
                             probs={"crypto:BTC/USDT": 0.7},
                             thresholds={"crypto:BTC/USDT": 0.55},
                             marks=_marks(), state_dir=td)
        pub = SL.sizing_public(td)
    assert "상대 비교 전용" in pub["note"]
    assert "데드존" in pub["note"], "진입 조건이 같다는 사실을 안 밝힌다"
    assert "4배" in pub["note"], "다중검정 경고가 없다"
