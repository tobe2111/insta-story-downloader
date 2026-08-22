"""2세대 그림자 — 다 사지 않고 좋은 것에 더 싣는다 (2026-08-19, 사장님 지시).

    "종목이 는다고 해서 그걸 다 살 필요는 없잖아. 그 많은 종목 중에서
     가장 수익이 높을 것이라 기대하는 것을 매매하는 거지."

본 계좌는 신호가 켜진 종목에 **똑같이** 나눠 담는다(균등 조각). 그래서
확신이 강한 종목이나 겨우 문턱을 넘은 종목이나 같은 금액을 받는다.
2세대는 줄을 세워 상위 K개만, 점수에 비례해 담는다.

지켜야 할 약속:
- 상위 K개만 담는다 — K+1등부터는 0이다(다 담으면 균등 조각과 같아진다).
- 점수에 비례한다 — 확신이 두 배면 금액도 두 배.
- 검증 '실패' 종목은 점수가 0이라 아예 안 들어간다. '미측정'은 절반이다
  ("통과가 아니라 모른다"를 점수에도 반영).
- 같은 입력이면 같은 포트폴리오다(동점도 이름순 고정) — 재현 불가능한
  실험은 실험이 아니다.
- 총합이 1을 넘지 않는다(빚 금지).
- 집중의 대가인 최대낙폭을 함께 기록한다 — 수익만 보여주면 유혹이 된다.
- 본 계좌 배치에 배선돼 있고, 실험 실패가 본 계좌를 못 죽인다.
- 판정 기준이 사전 등록돼 있고 공개 페이지에 실렸다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import quant.live.gen2 as G                                # noqa: E402

_W = {f"s{i}": 1.0 - i * 0.05 for i in range(20)}          # s0가 가장 확신
_M = {f"s{i}": 100.0 for i in range(20)}


def test_only_the_top_k_get_money():
    picks = G.concentrate(G.score_symbols(_W), top_k=5)
    assert len(picks) == 5, f"상위 5개만 담아야 하는데 {len(picks)}개다"
    assert set(picks) == {"s0", "s1", "s2", "s3", "s4"}, picks
    assert abs(sum(picks.values()) - 1.0) < 1e-9, "총합이 1이 아니다"


def test_more_conviction_gets_more_money():
    """균등 조각과 갈리는 지점 — 점수가 두 배면 금액도 두 배."""
    picks = G.concentrate({"a": 2.0, "b": 1.0}, top_k=2)
    assert abs(picks["a"] / picks["b"] - 2.0) < 1e-9, (
        f"확신이 두 배인데 금액 비율이 {picks['a'] / picks['b']} — 균등 조각과 같다")


def test_a_failed_validation_gets_nothing():
    """'실패'는 0, '미측정'은 절반 — 본 계좌 감쇠 규칙과 같은 뜻."""
    s = G.score_symbols({"a": 1.0, "b": 1.0, "c": 1.0},
                        {"a": {"grade": "통과"}, "b": {"grade": "미측정"},
                         "c": {"grade": "실패"}})
    assert "c" not in s, "검증 실패 종목이 후보에 남았다"
    assert abs(s["b"] / s["a"] - 0.5) < 1e-9, (
        f"'미측정'이 절반이 아니다: {s}")


def test_the_same_input_makes_the_same_portfolio():
    """동점이 있어도 순서가 흔들리면 안 된다 — 재현 불가능한 실험은 실험이 아니다."""
    tie = {f"x{i}": 1.0 for i in range(10)}
    a = G.concentrate(tie, top_k=3)
    b = G.concentrate(dict(reversed(list(tie.items()))), top_k=3)
    assert a == b, f"같은 점수인데 다른 종목을 골랐다: {a} vs {b}"


def test_it_records_the_price_of_concentration(tmp_path):
    """집중은 공짜가 아니다 — 낙폭을 함께 남기지 않으면 유혹이 된다."""
    G.run_gen2(bar="2026-08-19", weights=_W, marks=_M, state_dir=str(tmp_path))
    G.run_gen2(bar="2026-08-20", weights=_W,
               marks={k: 90.0 for k in _M}, state_dir=str(tmp_path))
    rec = G.run_gen2(bar="2026-08-21", weights=_W,
                     marks={k: 80.0 for k in _M}, state_dir=str(tmp_path))
    assert rec["mdd_pct"] < -5.0, f"연속 하락인데 낙폭이 {rec['mdd_pct']}%"
    pub = G.gen2_public(str(tmp_path))
    assert "최대낙폭" in pub["note"] and "집중" in pub["note"]
    assert pub["n_held"] == G.TOP_K


def test_same_bar_is_idempotent(tmp_path):
    G.run_gen2(bar="2026-08-19", weights=_W, marks=_M, state_dir=str(tmp_path))
    a = json.loads((tmp_path / "gen2.json").read_text("utf-8"))
    G.run_gen2(bar="2026-08-19", weights=_W, marks=_M, state_dir=str(tmp_path))
    b = json.loads((tmp_path / "gen2.json").read_text("utf-8"))
    assert a == b and len(b["history"]) == 1, "같은 봉에 두 번 움직였다"


def test_no_marks_writes_nothing(tmp_path):
    assert G.run_gen2(bar="2026-08-19", weights=_W, marks={},
                      state_dir=str(tmp_path)) is None
    assert not (tmp_path / "gen2.json").exists(), "시세 없는 날 가짜 기록을 만들었다"


def test_the_daily_batch_is_wired_and_cannot_be_killed_by_it():
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert "run_gen2(bar=bar" in src, "일일 배치에 배선이 없다"
    i = src.find("run_gen2(bar=bar")
    assert "try:" in src[max(0, i - 400):i], (
        "실험이 예외 방벽 없이 본 계좌 경로에 있다")
    assert 'status["gen2"]' in src, "status.json에 실리지 않는다"
    # 검증 등급을 **실제 변수**에서 받는가(없는 이름을 쓰면 조용히 등급 없이 돈다)
    assert "grades=valid_grades" in src, "검증 등급이 실전 값과 연결돼 있지 않다"


def test_the_goalposts_are_registered_and_public():
    from quant.live import prereg
    exp = prereg.PREREGISTERED["gen2_concentration"]
    assert exp["judge_on"] == "2026-12-17"
    assert "낙폭" in exp["extra_gate"], "집중의 대가를 관문에 안 걸었다"
    trust = (ROOT / "docs" / "trust.html").read_text("utf-8")
    assert "2세대 집중" in trust, "공개 페이지에 없다 — 코드에만 있는 등록은 등록이 아니다"
