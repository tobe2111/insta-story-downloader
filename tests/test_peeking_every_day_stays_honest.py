"""조기 판정 — 매일 봐도 거짓 승리가 늘지 않는가 (2026-08-19, 사장님 지시).

사장님 질문: "석달보다 기간을 최대한 단축시킬 수 있는 방법은?"

단축의 유일한 정직한 길은 **훔쳐볼 권리를 미리 사 두는 것**이다. 그 권리가
진짜인지는 말이 아니라 시뮬레이션이 답해야 한다 — 차이가 **없는** 데이터를
수백 번 만들어 매일 들여다봤을 때, "이겼다"가 약속한 5%를 넘지 않아야 한다.

지켜야 할 약속:
- 차이가 없을 때(귀무), 매일 훔쳐봐도 거짓 승리율 ≤ 약속한 유의수준.
- 차이가 있을 때(대립), 고정 판정일보다 **먼저** 경계를 넘는다(단축이 실제로 된다).
- 최소 관찰일수 아래에서는 어떤 판정도 내리지 않는다(3일 우연으로 승리 선언 금지).
- 짝은 **같은 날짜끼리** 맞춘다 — 날짜를 섞으면 잡음 감소가 사라진다.
- 조율값·유의수준은 사전 등록에서 온다(결과를 보고 고르면 보장이 깨진다).
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live import sequential as SQ                    # noqa: E402

ALPHA = 0.05
DAYS = 200            # 고정 판정일(90일)보다 길게 봐도 새는지 확인
PATHS = 400


def _peek_until_verdict(diffs, alpha=ALPHA):
    """매일 들여다보며 첫 판정이 나는 시점 — 안 나면 None."""
    for t in range(SQ.MIN_DAYS_DEFAULT, len(diffs) + 1):
        v = SQ.verdict(diffs[:t], alpha=alpha)
        if v["state"].startswith("조기 판정"):
            return t, v["state"]
    return None, None


def test_peeking_every_day_does_not_inflate_false_wins():
    """**이 파일의 핵심.** 차이가 없는데 이겼다고 말하는 비율이 약속 이하인가."""
    rng = random.Random(42)
    false_wins = 0
    for _ in range(PATHS):
        diffs = [rng.gauss(0.0, 0.01) for _ in range(DAYS)]   # 진짜 차이 없음
        t, _state = _peek_until_verdict(diffs)
        if t is not None:
            false_wins += 1
    rate = false_wins / PATHS
    # 이 경계는 보수적이라 실제 오경보율은 약속치보다 낮게 나온다.
    # 약속치를 넘으면 '매일 봐도 된다'는 말이 거짓이 된다.
    assert rate <= ALPHA, (
        f"매일 훔쳐본 거짓 승리율 {rate:.1%} > 약속 {ALPHA:.0%} — "
        "조기 판정 권리가 실제로는 없다")


def test_a_real_edge_is_found_before_the_fixed_date():
    """단축이 실제로 되는가 — 진짜 차이가 있으면 90일 전에 잡혀야 한다."""
    rng = random.Random(7)
    early = 0
    for _ in range(120):
        # 하루 평균 +0.6%p 우위 · 변동 1% — 실측 중앙 판정 시점 32일.
        # (참고 실측: 0.35%p→66일 · 0.5%p→41일 · 0.8%p→22일. 우위가 작을수록
        #  느려지는 것이 정상이다 — 속도는 효과 크기로 산다.)
        diffs = [rng.gauss(0.006, 0.01) for _ in range(DAYS)]
        t, state = _peek_until_verdict(diffs)
        if t is not None and t < 60 and state.endswith("우세"):
            early += 1
    assert early >= 100, (
        f"뚜렷한 우위인데 60일 안에 잡힌 경우가 {early}/120뿐 — "
        "조기 판정이 이름뿐이다")


def test_it_refuses_to_judge_on_a_thin_sample():
    rng = random.Random(1)
    v = SQ.verdict([rng.gauss(0.05, 0.001) for _ in range(5)])
    assert v["state"] == "표본 부족", (
        f"닷새 기록으로 판정했다: {v} — 우연을 승리로 읽는 길이 열린다")


def test_the_pairing_is_by_date_not_by_position():
    """날짜가 어긋난 두 계좌를 위치로 짝지으면 비교 자체가 거짓이 된다."""
    a = [{"date": "2026-08-01", "equity": 100.0},
         {"date": "2026-08-02", "equity": 110.0},
         {"date": "2026-08-03", "equity": 121.0}]
    b = [{"date": "2026-08-02", "equity": 200.0},      # 8-01 기록이 없다
         {"date": "2026-08-03", "equity": 210.0}]
    d = SQ.paired_daily_returns(a, b)
    assert len(d) == 1, f"짝이 맞는 날은 하루뿐인데 {len(d)}개를 만들었다: {d}"
    assert abs(d[0] - ((121 / 110 - 1) - (210 / 200 - 1))) < 1e-12


def test_the_knobs_come_from_the_registry_not_from_the_result():
    """조율값을 결과 보고 고르면 '언제 봐도 유효'가 깨진다."""
    from quant.live import prereg
    seq = prereg.SEQUENTIAL
    assert seq["alpha"] == 0.05 and seq["rho"] == SQ.RHO_DEFAULT
    assert seq["min_days"] == SQ.MIN_DAYS_DEFAULT
    assert seq["registered_on"], "등록일이 없다 — 언제 박은 골대인지 알 수 없다"


def test_the_amendment_is_public():
    """골대를 바꿨으면 공개한다 — 조용한 수정만 금지다."""
    from quant.live import prereg
    assert prereg.AMENDMENTS, "판정 방식을 바꿨는데 수정 이력이 비어 있다"
    trust = (ROOT / "docs" / "trust.html").read_text("utf-8")
    for a in prereg.AMENDMENTS:
        assert a["on"] in trust, f"{a['on']} 수정이 공개 페이지에 없다"
    assert "조기 판정" in trust, "조기 판정 규칙이 공개돼 있지 않다"


def test_it_is_wired_and_reads_only_the_ledger():
    """배선 — 배치가 실어 보내고, 화면은 장부에서만 읽는다."""
    daily = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert 'status["sequential"]' in daily, "status.json에 진도가 안 실린다"
    i = daily.find('status["sequential"] = sequential_status')
    assert "try:" in daily[max(0, i - 200):i], (
        "진도 표시가 예외 방벽 없이 배치 경로에 있다")
    page = (ROOT / "docs" / "paper.html").read_text("utf-8")
    assert "st.sequential" in page, "화면이 진도를 장부에서 읽지 않는다"
    assert "아직 모른다" in (ROOT / "quant" / "live" / "sequential.py").read_text(
        "utf-8"), "'진행 중'과 '차이 없음'의 구별이 문구에 없다"


def test_the_live_wiring_survives_thin_data():
    """오늘처럼 기록이 얇은 날에도 죽지 않고 '얇다'고 말해야 한다."""
    out = SQ.sequential_status("state")
    if out is None:
        return                      # 아직 어떤 쌍도 없다 — 그것도 정상
    for k, v in out["pairs"].items():
        assert v["state"] in ("표본 부족", "진행 중") or \
            v["state"].startswith("조기 판정"), f"{k}: 알 수 없는 상태 {v}"


# ── 짝비교가 두 계좌의 자산을 이어 붙이지 않는다 (2026-09-07) ─────────
#
# 그림자 실험 장부에는 한때 본 계좌와 섀도 대조군 **두 계좌**가 함께 썼고,
# 대조군의 줄은 **더 과거 날짜인데 뒤에 적혔다**. 짝비교가 "하루 여러 회차면
# 마지막 값"을 쓰므로 그 날짜의 자산이 다른 계좌의 값이 되고, 앞뒤 날과 이어
# 붙인 일수익은 **지어낸 수익률**이 된다.
#
# 실측(2026-09-07): 배분 사다리 짝비교 16개 관측 중 **2개**가 그랬다
# (최대 8.3bp). 오늘 판정은 안 바뀌지만, 그 줄들은 사전 등록된 판정일
# (2026-12-17)에도 창 안에 남아 있다 — 판정이 지어낸 수익률 위에서 난다.
#
# ⚠️ 같은 날짜의 여러 회차(장중 트랙)는 **정상**이다. 뒤로 간 것만 사고다.
#    이 구별이 없으면 장중 트랙의 하루 여러 회차가 통째로 날아간다.
def test_a_row_written_out_of_order_is_not_spliced_into_a_return():
    from quant.live.sequential import paired_daily_returns
    good = [{"date": "2026-09-04", "equity": 100.0},
            {"date": "2026-09-05", "equity": 110.0},
            {"date": "2026-09-06", "equity": 121.0}]
    other = [{"date": "2026-09-04", "equity": 100.0},
             {"date": "2026-09-05", "equity": 100.0},
             {"date": "2026-09-06", "equity": 100.0}]
    clean = paired_daily_returns(good, other)

    # 같은 장부에 **다른 계좌의 줄**이 뒤늦게 끼어든다(더 과거 날짜).
    dirty = good + [{"date": "2026-09-04", "equity": 55.0}]
    assert paired_daily_returns(dirty, other) == clean, (
        "뒤로 간 줄이 09-04의 자산을 55로 바꿔, 04→05 수익률이 두 계좌를 "
        "이어 붙인 값이 됐다")


def test_several_rounds_in_one_day_still_keep_the_last_one():
    """장중 트랙은 하루에 여러 번 돈다 — 그건 사고가 아니다."""
    from quant.live.sequential import paired_daily_returns
    a = [{"time": "2026-09-04T09:00:00", "equity": 100.0},
         {"time": "2026-09-04T15:00:00", "equity": 105.0},   # 같은 날 뒤 회차
         {"time": "2026-09-05T15:00:00", "equity": 110.0}]
    b = [{"time": "2026-09-04T15:00:00", "equity": 100.0},
         {"time": "2026-09-05T15:00:00", "equity": 100.0}]
    d = paired_daily_returns(a, b)
    assert len(d) == 1, d
    # 04의 값이 105(마지막 회차)로 잡혀야 05 수익률이 110/105-1 이다.
    assert abs(d[0] - (110.0 / 105.0 - 1.0)) < 1e-12, d


def test_the_real_ladders_have_no_spliced_returns_left():
    """실제 장부로 확인 — 되감긴 줄이 남아 있어도 판정 재료는 깨끗하다."""
    import json
    import os
    from quant.live.sequential import paired_daily_returns
    root = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "state", "alloc_ladder")
    if not os.path.isdir(root):
        return

    def hist(m):
        with open(os.path.join(root, f"{m}.json"), encoding="utf-8") as f:
            return json.load(f)["history"]

    def drop_backwards(rows):
        out, hi = [], None
        for r in rows:
            d = str(r.get("date"))[:10]
            if hi is not None and d < hi:
                continue
            hi = d if hi is None or d > hi else hi
            out.append(r)
        return out

    base = hist("hrp")
    for alt in ("erc", "equal", "inv_vol"):
        other = hist(alt)
        assert (paired_daily_returns(base, other)
                == paired_daily_returns(drop_backwards(base),
                                        drop_backwards(other))), (
            f"hrp-{alt}: 되감긴 줄이 아직 수익률에 섞인다")
