"""조기 판정은 **등록된 대로** 돌아야 한다 (2026-09-07).

■ 무엇이 갈라져 있었나 (실측)

사전 등록은 이 제품의 정직성의 뿌리다 — *"결과를 보고 기준을 정하면 그 선택
자체가 결과에 오염된다."* 그런데 등록과 실제가 세 군데 갈라져 있었다.

  ① **등록된 본페로니 보정이 경계에 안 걸려 있었다.** 배분 사다리·주기
     사다리는 등록에 "본페로니 3"이라고 적혀 있는데 경계는 α=0.05를 그대로
     썼다. 보정이 빠지면 경계가 **낮아진다** — 거짓 승리 쪽이다. 조기 판정이
     존재하는 이유가 "매일 봐도 5%를 안 넘는다"인데 그 약속이 깨져 있었다.
     ⚠️ 오늘 뒤집히는 판정은 없었다(가장 가까운 쌍이 진도 0.566 → 0.489).
        고친 것은 "지금 틀린 판정"이 아니라 **"넘는 날이 왔을 때 보정 없이
        넘을 수 있다"**는 것이다.

  ② **``applies_to`` 6개 중 4개가 한 번도 계산된 적이 없었다** — 지정가
     그림자 둘 · 2세대 집중 · 사이징 사다리. 그중 2세대 집중은 등록 문구가
     **"조기 판정 경계 적용"**이라고 직접 적고 있다. 주기 사다리도 등록된
     3쌍 중 2쌍만 돌았다(15m-5m 누락) — **재지도 않는 비교의 보정 값을
     치르면서** 정작 그 비교는 없는 상태였다.
     ⚠️ 붙이자마자 하나가 이미 경계를 넘어 있었다(지정가 그림자, n=20).

  ③ 반대로 미국 주기 사다리는 **등록에 없는데** 돌고 있었다. 등록은 그것을
     "참고 진단"이라 부른다 — 등록된 판정과 같은 칸에 이름표 없이 두면
     읽는 사람이 구별할 수 없다.

■ 그래서 손 목록을 두지 않는다

유의수준을 코드에 손으로 적으면 등록과 갈린다. **등록 문구에서 센다.**
그리고 등록된 실험은 빠짐없이 계산을 지나며, 재료가 없으면 ``missing``에
이름을 남긴다 — 조용히 빠지면 "그런 비교가 원래 없었다"로 읽힌다.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live import sequential as seq            # noqa: E402
from quant.live.prereg import PREREGISTERED, SEQUENTIAL as CFG   # noqa: E402

PAPER = (ROOT / "docs" / "paper.html").read_text("utf-8")


# ── ① 보정은 등록에서 센다 ────────────────────────────────────────
def test_the_correction_count_is_read_from_the_registration():
    assert seq.registered_comparisons({"correction": "본페로니 3(대안 3개)"}) == 3
    assert seq.registered_comparisons({"correction": "본페로니 2(트랙 2개)"}) == 2
    assert seq.registered_comparisons({"correction": "단일 비교 — 보정 없음"}) == 1


def test_an_unreadable_correction_is_loud_not_silent():
    """못 읽으면 **1로 넘어가면 안 된다** — 그건 보정을 조용히 버리는 것이다."""
    try:
        seq.registered_comparisons({"correction": "알 수 없는 문구"})
    except ValueError:
        return
    raise AssertionError("보정 문구를 못 읽었는데 조용히 통과했다")


def test_every_registration_states_a_correction_this_code_can_read():
    for key, exp in PREREGISTERED.items():
        assert seq.registered_comparisons(exp) >= 1, key


def test_the_boundary_actually_tightens_with_the_correction():
    """보정이 값에 닿는가 — 문구만 읽고 안 쓰면 아무 일도 안 일어난다."""
    diffs = [0.001 * (1 if i % 3 else -1) for i in range(40)]
    loose = seq.verdict(diffs, alpha=0.05)
    tight = seq.verdict(diffs, alpha=0.05 / 3)
    assert tight["boundary"] > loose["boundary"], (
        "보정을 걸었는데 경계가 안 올라갔다 — 거짓 승리 쪽으로 느슨하다")


def test_the_registered_pairs_carry_their_correction(tmp_path):
    st = seq.sequential_status(str(ROOT / "state"))
    assert st, "조기 판정 진도를 못 만들었다"
    for name, v in st["pairs"].items():
        exp = v.get("experiment")
        assert exp, f"{name}: 어느 실험의 비교인지 안 적혀 있다"
        want = seq.registered_comparisons(PREREGISTERED[exp])
        if v.get("reference"):
            # 참고 진단은 형제(주기 사다리)의 보정을 빌려 쓴다 — 참고라고
            # **더 느슨한 자**를 쓰면 그 숫자가 더 자주 '이겼다'고 말한다.
            assert v["comparisons"] >= want, (
                f"{name}: 참고 진단이 자기 등록보다 느슨하다")
            continue
        assert v["comparisons"] == want, (
            f"{name}: 보정 {v['comparisons']} ≠ 등록 {want}")
        if "alpha" in v:
            assert abs(v["alpha"] - float(CFG["alpha"]) / want) < 1e-12, (
                f"{name}: 유의수준이 등록된 보정과 다르다")


# ── ② 등록된 실험은 빠짐없이 지난다 ──────────────────────────────
def test_every_registered_experiment_is_either_measured_or_named():
    """이 검사가 이 파일의 존재 이유다 — 4개가 아무 말 없이 빠져 있었다."""
    st = seq.sequential_status(str(ROOT / "state")) or {}
    seen = {v.get("experiment") for v in (st.get("pairs") or {}).values()}
    named = set(st.get("missing") or {})
    for key in CFG["applies_to"]:
        assert key in seen or key in named, (
            f"{key}: 등록은 조기 판정이 적용된다고 적어 두었는데 계산도 안 하고 "
            "못 잤다는 말도 없다 — 화면에서는 '그런 비교가 원래 없었다'와 "
            "똑같이 보인다")


def test_an_empty_state_names_every_experiment_it_could_not_measure(tmp_path):
    """재료가 하나도 없을 때 **이름을 말하는가.**

    ⚠️ 이 검사가 없으면 위 형제 검사가 오늘 상태에서만 초록이다 — 지금은
       6개 모두 재료가 있어 ``missing``이 비어 있고, 그래서 "조용히 뺀다"는
       고장이 검사를 그대로 통과한다(2026-09-07 변이 시험이 잡아냈다).
    """
    st = seq.sequential_status(str(tmp_path)) or {}
    assert set(st.get("missing") or {}) == set(CFG["applies_to"]), (
        f"{sorted(st.get('missing') or {})} — 재료가 없는데 이름을 안 말한다. "
        "조용히 빠지면 '그런 비교가 원래 없었다'와 구별되지 않는다")
    assert not st.get("pairs"), "재료가 없는데 비교가 생겼다"
    for why in (st.get("missing") or {}).values():
        assert why, "못 잰 이유가 비어 있다"


def test_the_cadence_ladder_runs_all_three_registered_pairs():
    """등록이 3쌍이라 보정도 3인데 2쌍만 돌고 있었다."""
    got = set(seq._pairs_for("cadence_ladder", str(ROOT / "state")))
    assert got == {"cadence:1h-15m", "cadence:1h-5m", "cadence:15m-5m"}, got


def test_the_shadow_series_comes_from_the_same_rounds():
    """지정가 그림자는 본 트랙과 **같은 회차 기록 안**에 산다."""
    rounds = [{"time": "2026-09-01T00:00:00", "equity": 100.0,
               "limit_shadow": {"equity": 101.0}},
              {"time": "2026-09-02T00:00:00", "equity": 110.0,
               "limit_shadow": {"equity": 99.0}},
              {"time": "2026-09-03T00:00:00", "equity": 121.0}]
    got = seq._shadow_rows(rounds)
    assert [r["equity"] for r in got] == [101.0, 99.0], (
        "그림자 자산이 없는 회차를 0으로 채우면 가짜 폭락이 생긴다")


# ── ③ 참고 진단은 이름표를 단다 ──────────────────────────────────
def test_the_reference_diagnostic_says_it_is_not_a_verdict():
    st = seq.sequential_status(str(ROOT / "state")) or {}
    refs = [k for k, v in (st.get("pairs") or {}).items() if v.get("reference")]
    for k in refs:
        assert st["pairs"][k].get("why"), f"{k}: 참고라고만 하고 이유가 없다"
    for k, v in (st.get("pairs") or {}).items():
        if v.get("experiment") in CFG["applies_to"]:
            assert not v.get("reference"), f"{k}: 등록된 판정에 참고 표를 달았다"


# ── 등록이 미리 심어 둔 채택 조건 ────────────────────────────────
def test_a_win_carries_its_adoption_condition():
    """'우세'만 싣고 조건을 안 실으면 화면에서 곧 채택으로 읽힌다."""
    st = seq.sequential_status(str(ROOT / "state")) or {}
    for key in ("limit_shadow", "us_limit_shadow", "gen2_concentration",
                "sizing_ladder"):
        got = [v for v in (st.get("pairs") or {}).values()
               if v.get("experiment") == key]
        if not got:
            continue
        for v in got:
            h = v.get("adoption_hold")
            assert h and h.get("rule"), f"{key}: 등록된 채택 조건이 안 실렸다"
            assert ("held" in h) or h.get("why"), (
                f"{key}: 조건을 재지도 못했다는 말도 없다")


def test_the_drawdown_gate_reads_the_curve_not_the_daily_field():
    """장부의 낙폭 칸은 **그날의 낙폭**이지 최대낙폭이 아니다.

    실측(2026-09-07): 본 계좌 계열이 0 → −0.53 → −0.28로 오르내린다.
    그 값을 등록의 '최대낙폭'으로 쓰면 배수가 매일 달라진다.
    """
    rows = [{"date": "2026-09-01", "equity": 100.0},
            {"date": "2026-09-02", "equity": 90.0},
            {"date": "2026-09-03", "equity": 95.0}]
    assert round(seq._max_drawdown_pct(rows), 6) == -10.0


def test_the_drawdown_gate_only_uses_overlapping_days():
    """기간이 다르면 낙폭 비교가 '누가 더 오래 굴렀나' 비교가 된다."""
    cand = [{"date": "2026-09-01", "equity": 100.0},
            {"date": "2026-09-02", "equity": 50.0},      # 겹치지 않는 날
            {"date": "2026-09-03", "equity": 100.0},
            {"date": "2026-09-04", "equity": 98.0}]
    base = [{"date": "2026-09-03", "equity": 100.0},
            {"date": "2026-09-04", "equity": 99.0}]
    h = seq._mdd_hold("규칙", cand, base)
    assert h["days"] == 2 and h["mdd_pct"] == 2.0, h


# ── 화면까지 간다 (감사 105의 규약) ──────────────────────────────
def test_the_screen_reads_every_new_field():
    for token in ("adoption_hold", "reference", "q.missing", "comparisons"):
        assert token in PAPER, (
            f"{token}: 장부에 넣고 화면이 안 읽는다 — 감사 105와 같은 모양")


def test_the_screen_names_every_pair_in_human_words():
    """장부 열쇠(`alloc:hrp-erc`)를 그대로 띄우면 코드가 화면에 나온다."""
    st = seq.sequential_status(str(ROOT / "state")) or {}
    for name in (st.get("pairs") or {}):
        assert f'"{name}"' in PAPER, (
            f"{name}: 화면에 사람 말 이름이 없어 장부 열쇠가 그대로 나간다")
