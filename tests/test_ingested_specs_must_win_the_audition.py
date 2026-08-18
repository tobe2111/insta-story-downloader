"""가져온 전략이 **심사를 건너뛰지 않는지**.

⚠️ 이 파일이 지키는 것은 제품의 정체성이다.

    사용자가 넣은 전략을 바로 쓰면 이 제품은 "남이 시키는 대로 사는 봇"이 된다.
    검증이 제품의 전부인데 **새 전략만 그 검증을 건너뛰면** 앞뒤가 안 맞고,
    그때부터 "우리는 검증한 것만 씁니다"는 거짓말이 된다.

⚠️ 그리고 더 조용한 위험이 하나 더 있다 — **다중검정**.

    후보를 늘리면 '우연히 좋아 보이는 승자'가 나올 확률이 올라간다(DSR이
    존재하는 이유). 사용자 자료로 후보를 늘리면서 그 사실을 검정에 안 넘기면
    검증이 통째로 틀리고, 이 기능은 제품을 돕는 게 아니라 **제품의 심장을 끄는
    기능**이 된다. 문턱이 실제로 올라가는지를 값으로 확인한다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.ingest.registry import (                       # noqa: E402
    MAX_USER_CHALLENGERS,
    load_specs,
    save_spec,
    user_challengers,
)
from quant.ingest.spec import Condition, StrategySpec     # noqa: E402
from quant.live.retrain import (                          # noqa: E402
    DEFAULT_CHAMPION,
    build_challengers,
    build_strategy,
    confirm_threshold,
)

RETRAIN = (ROOT / "quant" / "live" / "retrain.py").read_text("utf-8")


def _spec(name: str = "내전략") -> StrategySpec:
    return StrategySpec(
        name=name,
        entry=[Condition("close", ">", "sma:20", "종가가 20일선 위면 매수한다")],
        exit=[Condition("close", "<", "sma:60", "60일선 아래면 판다")],
    )


# ── ① 도전자로만 들어온다 ───────────────────────────────────────

def test_a_saved_spec_enters_the_ring_as_a_challenger(tmp_path):
    save_spec(_spec(), state_dir=str(tmp_path))
    ring = build_challengers(DEFAULT_CHAMPION, seed="2026-08-14:t",
                             state_dir=str(tmp_path))
    specs = [c for c in ring if c.get("strategy") == "spec"]
    assert len(specs) == 1, "저장한 전략이 링에 안 섰다"
    assert build_strategy(specs[0]).name == "내전략"


def test_a_spec_never_becomes_champion_without_winning():
    """명세를 챔피언 자리에 **직접 넣는 길이 없어야** 한다.

    승격은 오직 nightly_retrain의 판정으로만 일어난다. 등록 경로가 챔피언
    파일을 건드리면 그 순간 심사는 장식이 된다.
    """
    src = (ROOT / "quant" / "ingest").rglob("*.py")
    for fp in src:
        body = fp.read_text("utf-8")
        assert "save_champions" not in body, (
            f"{fp.name}이 챔피언 파일을 직접 쓴다 — 등록이 승격이 돼 버린다")
        assert "champions.json" not in body, f"{fp.name}이 챔피언 파일을 만진다"


def test_the_spec_strategy_is_built_from_data_not_code():
    """명세는 데이터로만 전략이 된다 — eval/exec이 끼어들 자리가 없다."""
    for bad in ("eval(", "exec(", "__import__", "importlib"):
        for fp in (ROOT / "quant" / "ingest").rglob("*.py"):
            assert bad not in fp.read_text("utf-8"), f"{fp.name}에 {bad}"


# ── ② 후보가 늘면 문턱도 오른다 ─────────────────────────────────

def test_adding_user_specs_raises_the_promotion_bar(tmp_path):
    """**이 검사가 이 기능의 안전핀이다.**

    사용자 전략을 넣으면 그날 후보 수가 늘고, 후보가 늘면 결승 문턱이
    올라가야 한다. 안 올라가면 "많이 던져서 하나 맞히기"가 가능해진다.
    """
    base = len(build_challengers(DEFAULT_CHAMPION, seed="s", state_dir=str(tmp_path)))
    for i in range(5):
        save_spec(_spec(f"전략{i}"), state_dir=str(tmp_path))
    after = len(build_challengers(DEFAULT_CHAMPION, seed="s",
                                  state_dir=str(tmp_path)))
    assert after == base + 5, f"후보가 안 늘었다: {base} → {after}"
    # 후보 수가 시도 수로 넘어가면 문턱이 오른다(호출부가 len(challengers)를 센다).
    #
    # ×10 = 링 열흘치 시도. 처음에는 ×100(백일치)이었는데, 2026-08-18에
    # 링이 46개로 크면서 두 값 모두 상한(CONFIRM_T_CAP) 위로 넘어가
    # 1.35 == 1.35로 깨졌다. 상한에서 문턱이 멈추는 것은 **의도된 설계**다
    # (영원히 오르면 진화가 완전히 멈춘다 — retrain.py의 주석과
    # test_rigor.py의 상한 검사가 그 사실을 지킨다). 이 검사의 몫은
    # 상한 **아래** 구간에서 보정이 살아 있는가이므로, 비교 지점이 상한을
    # 넘지 않는지 함께 못박는다 — 링이 또 커지면 여기서 시끄럽게 깨진다.
    from quant.live.retrain import CONFIRM_T_CAP
    assert confirm_threshold(after * 10) < CONFIRM_T_CAP, (
        f"링 {after}개 × 열흘이면 벌써 문턱 상한에 붙는다 — 이 검사의 비교"
        " 구간과 상한 설계를 다시 살필 때다")
    assert confirm_threshold(after * 10) > confirm_threshold(base * 10), (
        "후보가 늘었는데 결승 문턱이 그대로다 — 다중검정 보정이 안 걸린다")


def test_the_caller_counts_the_whole_ring_as_trials():
    """문턱을 올리는 배선이 실제로 있는지 — 함수만 맞고 안 부르면 소용없다."""
    assert "n_cand = len(challengers)" in RETRAIN, (
        "시도 수를 링 전체에서 세지 않는다 — 사용자 전략이 다중검정에서 빠진다")
    i = RETRAIN.find("challengers = build_challengers(current_spec")
    j = RETRAIN.find("n_cand = len(challengers)")
    assert 0 < i < j, "링을 다 만들기 전에 시도 수를 센다"


def test_too_many_user_specs_are_capped_and_said_so(tmp_path):
    """한 사람의 자료 더미가 **다른 모든 전략의 승격을 막을 수** 있다.

    후보 500개면 문턱이 치솟아 진화가 통째로 멈춘다. 자르되 **자른 사실을
    남긴다** — 조용히 버리면 사용자는 자기 전략이 다 링에 선 줄 안다.
    """
    for i in range(7):
        save_spec(_spec(f"많은전략{i:02d}"), state_dir=str(tmp_path))
    # ⚠️ 상한을 **명시해서** 부른다. 예전에는 MAX_USER_CHALLENGERS로 파일을
    #    만들고 같은 상수와 비교했다 — 상수를 100000으로 바꿔도 통과하는
    #    자기참조 검사였고, 변이 검사가 그걸 잡았다(2026-08-14).
    cands, notes = user_challengers(str(tmp_path), limit=4)
    assert len(cands) == 4, "상한을 넘겨 링에 세운다"
    assert notes and "빠진 전략" in " ".join(notes), "자른 사실을 안 알린다"


def test_the_cap_is_small_enough_to_not_stall_evolution():
    """상한 자체가 **실제로 작아야** 한다 — 있으나 마나 한 숫자면 소용없다.

    기본 링이 30개 안팎인데 사용자 전략이 수백 개면 그날 시도 수가 폭증해
    결승 문턱이 상한(CONFIRM_T_CAP)에 붙고, 그러면 **누구도 승격 못 한다.**
    사용자 전략이 기본 링을 압도하지 않는 크기여야 한다.
    """
    from quant.live.retrain import DEFAULT_CHALLENGERS

    assert 0 < MAX_USER_CHALLENGERS <= len(DEFAULT_CHALLENGERS), (
        f"사용자 전략 상한 {MAX_USER_CHALLENGERS}개가 기본 후보 "
        f"{len(DEFAULT_CHALLENGERS)}개를 압도한다 — 한 사람의 자료가 "
        f"시스템 전체의 진화를 멈출 수 있다")


# ── ③ 깨진 명세를 조용히 넘기지 않는다 ──────────────────────────

def test_a_broken_spec_file_is_reported_not_skipped(tmp_path):
    """조용히 건너뛰면 사용자는 자기 전략이 매일 링에 선다고 믿는다.

    실제로는 한 번도 안 선다 — 이 저장소가 계속 잡아온 바로 그 침묵이다.
    """
    save_spec(_spec("멀쩡한전략"), state_dir=str(tmp_path))
    d = tmp_path / "specs_user"
    (d / "깨진것.json").write_text("{이건 JSON이 아님", encoding="utf-8")
    (d / "규칙없음.json").write_text(
        json.dumps({"version": 1, "name": "x", "entry": []}), encoding="utf-8")

    specs, problems = load_specs(str(tmp_path))
    assert [s.name for s in specs] == ["멀쩡한전략"]
    assert len(problems) == 2, f"문제를 다 안 알린다: {problems}"
    assert any("깨진것.json" in p for p in problems)
    assert any("규칙없음.json" in p for p in problems)


def test_no_spec_folder_is_not_an_error(tmp_path):
    """전략을 하나도 안 넣은 사람에게 오류를 보이면 안 된다 — 기본 상태다."""
    cands, notes = user_challengers(str(tmp_path))
    assert cands == [] and notes == []


# ── ④ 어제의 링은 어제의 명세로 재현한다 ────────────────────────

def test_verify_replays_the_specs_from_the_ledger_not_the_folder():
    """사용자가 자료를 지우면 폴더는 바뀌지만 **어제 결정은 어제 링에서** 나왔다.

    폴더를 다시 읽어 재현하면 "재현 실패"가 뜨는데 원인은 결함이 아니라 폴더
    변경이다. 그러면 재현 검사가 늑대소년이 되고, 진짜 결함이 묻힌다.
    """
    assert '"user_specs":' in RETRAIN, "그날의 사용자 명세를 장부에 안 남긴다"
    assert 'rec.get("user_specs")' in RETRAIN, (
        "재현할 때 장부가 아니라 폴더를 읽는다")
    # 재현 경로가 폴더를 읽지 않는지 — verify 블록에 state_dir이 흘러들면 안 된다.
    i = RETRAIN.find('challengers = build_challengers(before, seed=rec[')
    assert i > 0, "재현 경로를 찾지 못했다 — 검사가 낡았다"
    assert "state_dir" not in RETRAIN[i:i + 200], (
        "재현이 오늘 폴더를 읽는다 — 어제를 오늘 자료로 재현하게 된다")


def test_old_records_without_specs_replay_as_empty():
    """이 기능이 없던 날의 기록에는 이 칸이 없다 — 그때는 빈 목록이 맞다."""
    assert 'rec.get("user_specs") or []' in RETRAIN, (
        "옛 기록에서 None이 나오면 재현이 터진다")
