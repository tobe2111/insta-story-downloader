"""'외딴 봉우리' 경고가 **사람에게 닿는가** (감사 157).

`quant/optimize/stability.py`는 히트맵의 "넓은 초록 고원 = 견고, 외딴 초록
점 = 과최적화"를 눈이 아니라 숫자로 판정한다. 각 조합의 점수를 이웃(축마다
한 스텝) 점수와 함께 평균해 `robust_score`를 만들고, 원점수 1등과 견고성
1등이 다르면 "그 파라미터는 봉우리일 수 있다"고 말한다.

그런데 **부르는 곳이 한 곳도 없었다.** `__init__`에서 export만 되고
운영 코드·CLI 어디에서도 안 쓰였다 — 감사 135(제공자 소스)·139(거래소 규격)·
150(주문 감사 로그)과 같은 계열이다.

야간 오디션은 2단계 검증(선발전+결승전)과 폴드 일관성으로 봉우리를 막으니
거기에 넣을 일은 아니다. 문제는 **사장님이 손으로 그리드를 볼 때 쓸 창구가
없다는 것**이었다. `validate` 명령은 워크포워드·PBO·CPCV 셋을 돌리는데
파라미터 안정성만 빠져 있었다.

    [1/4] 워크포워드 + DSR   이 성적이 운인가(다중검정 보정)
    [2/4] PBO                IS 1등이 OOS에서 동전던지기인가
    [3/4] CPCV               여러 경로에서 일관된가
    [4/4] 파라미터 안정성     ← 이 **파라미터**가 운인가

넷은 다른 질문이다. 앞의 셋이 전부 통과해도 파라미터가 옆칸으로 한 스텝
옮기면 무너지는 설정일 수 있다.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.flag_watch import _current_flags as check_flags  # noqa: E402
from quant.optimize import robust_best, stability_report, stability_scores  # noqa: E402


# ── 정답을 아는 그리드 ────────────────────────────────────────
#
#   fast\slow   20     40     60
#      5       0.10   0.11   0.12
#     10       0.11   9.90   0.13      ← (10,40)만 혼자 9.90 = 외딴 봉우리
#     20       0.12   0.13   0.14      ← (20,60) 주변이 고르게 높음
#
# 원점수 1등은 (10,40)이지만 이웃이 전부 0.1대라 이웃 평균은 낮다.

PEAK_GRID = [
    {"fast": 5, "slow": 20, "sharpe": 0.10},
    {"fast": 5, "slow": 40, "sharpe": 0.11},
    {"fast": 5, "slow": 60, "sharpe": 0.12},
    {"fast": 10, "slow": 20, "sharpe": 0.11},
    {"fast": 10, "slow": 40, "sharpe": 9.90},
    {"fast": 10, "slow": 60, "sharpe": 0.13},
    {"fast": 20, "slow": 20, "sharpe": 0.12},
    {"fast": 20, "slow": 40, "sharpe": 0.13},
    {"fast": 20, "slow": 60, "sharpe": 0.14},
]

PLATEAU_GRID = [
    {"fast": 5, "slow": 20, "sharpe": 0.10},
    {"fast": 5, "slow": 40, "sharpe": 0.20},
    {"fast": 5, "slow": 60, "sharpe": 0.30},
    {"fast": 10, "slow": 20, "sharpe": 0.20},
    {"fast": 10, "slow": 40, "sharpe": 0.90},
    {"fast": 10, "slow": 60, "sharpe": 1.00},
    {"fast": 20, "slow": 20, "sharpe": 0.30},
    {"fast": 20, "slow": 40, "sharpe": 1.00},
    {"fast": 20, "slow": 60, "sharpe": 1.10},
]


# ── 판정이 옳은가 ─────────────────────────────────────────────


def test_a_lonely_peak_is_not_the_robust_winner():
    scored = stability_scores(PEAK_GRID)
    raw = max(PEAK_GRID, key=lambda r: r["sharpe"])
    rob = robust_best(scored)
    assert (raw["fast"], raw["slow"]) == (10, 40), "전제가 깨졌다"
    assert (rob["fast"], rob["slow"]) != (10, 40), (
        f"혼자 9.90인 봉우리를 견고성 1등으로 골랐다: {rob}")


def test_a_plateau_keeps_its_winner():
    """대조군 — 고원 위의 1등까지 갈아치우면 그건 다른 결함이다."""
    scored = stability_scores(PLATEAU_GRID)
    raw = max(PLATEAU_GRID, key=lambda r: r["sharpe"])
    rob = robust_best(scored)
    assert (rob["fast"], rob["slow"]) == (raw["fast"], raw["slow"]), (
        f"넓은 고원인데 1등을 바꿨다: 원점수 {raw} vs 견고성 {rob}")


def test_the_report_says_which_case_it_is():
    peak = stability_report(stability_scores(PEAK_GRID))
    flat = stability_report(stability_scores(PLATEAU_GRID))
    assert "외딴 봉우리" in peak, peak
    assert "고원" in flat and "외딴 봉우리" not in flat, flat


# ── 그 판정이 사람에게 닿는가 ─────────────────────────────────


def test_the_validate_command_runs_the_stability_gate():
    """CLI가 네 번째 관문으로 부르는가 — 안 부르면 도구가 없는 것과 같다."""
    src = (ROOT / "quant" / "cli.py").read_text("utf-8")
    body = src.split("def _cmd_validate")[1].split("\ndef ")[0]
    for token in ("stability_scores", "stability_report", "robust_best",
                  "[4/4]"):
        assert token in body, f"validate 명령이 {token}을 안 쓴다"


def test_the_verdict_is_saved_not_just_printed():
    """콘솔에만 찍히면 아무것도 막지 못한다 — 장부에 남아야 경보가 읽는다."""
    src = (ROOT / "quant" / "cli.py").read_text("utf-8")
    body = src.split("def _cmd_validate")[1].split("\ndef ")[0]
    assert '"peak_only": peak_only' in body, "판정이 장부에 안 남는다"


def test_the_flag_watch_raises_it():
    """장부에 남은 판정을 매일 도는 경보가 실제로 읽는가."""
    status = {"validation": {
        "kr_stock:069500.KS": {"strategy": "ma_cross", "bars": 400,
                               "dsr": 0.99, "pbo": 0.1, "peak_only": True}}}
    flags = check_flags(status)
    hit = [v for k, v in flags.items() if k.startswith("lonely_peak:")]
    assert hit, f"외딴 봉우리인데 경보가 없다: {list(flags)}"
    assert "한 칸만 옮겨도" in hit[0], hit[0]


def test_a_healthy_grid_raises_no_flag():
    """대조군 — 평시에 울리면 매일 울려서 아무도 안 본다."""
    status = {"validation": {
        "kr_stock:069500.KS": {"strategy": "ma_cross", "bars": 400,
                               "dsr": 0.99, "pbo": 0.1, "peak_only": False}}}
    flags = check_flags(status)
    assert not [k for k in flags if k.startswith("lonely_peak:")], flags


def test_it_is_a_separate_question_from_pbo_and_dsr():
    """PBO·DSR이 통과해도 봉우리는 따로 걸려야 한다 — 다른 질문이기 때문이다."""
    status = {"validation": {
        "crypto:BTC/USDT": {"strategy": "ml", "bars": 900,
                            "dsr": 0.99, "pbo": 0.05, "peak_only": True}}}
    flags = check_flags(status)
    assert not [k for k in flags if k.startswith(("overfit:", "dsr_low:"))], (
        "전제가 깨졌다 — PBO·DSR이 이미 걸렸다면 이 검사는 아무것도 안 본다")
    assert [k for k in flags if k.startswith("lonely_peak:")], flags
