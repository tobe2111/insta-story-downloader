"""못 도는 후보는 '찾아본 것'이 아니다 (감사 297).

다중검정 문턱은 "얼마나 뒤졌나"에 비례해 올라간다. 그런데 풀을 못 만들어
챔피언과 신호가 한 봉도 다르지 않은 후보는 **뒤진 것이 아니라 같은 답을
낸 것**이다. 그 후보를 시도 수에 넣으면 문턱만 올라가, 진짜로 뒤져서 찾은
결과까지 같이 깎인다.

실측 2026-08-19: 후보 802개 중 35개가 무동작, 그중 13개가 `pool="peers"`.
스냅샷이 14일치뿐이라 학습 블록 대부분이 자기 시점의 폴더를 못 찾는다.

⚠️ **후보 목록에서 빼는 것이 아니다.** 사장님 지적(2026-08-20):
   *"죽은 peers도 나중엔 성과 좋을 수 있는 거 아니야?"* 맞다 — peers는
   성과가 나쁜 게 아니라 아직 못 도는 것이고, `universe`와 달리 생존 편향이
   없어 장기적으로는 더 정직한 쪽이다. 스냅샷이 쌓이면 저절로 깨어난다.

여기서 지키는 것:
  · 스냅샷이 모자라면 풀링 후보는 잠든다(시도 수에 안 들어간다).
  · **쌓이면 깨어난다**(대조군) — 영영 빼 버리면 이 검사가 잡는다.
  · 풀을 안 쓰는 후보는 절대 잠들지 않는다(대조군).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.retrain import POOL_WAKE_DAYS, _split_sleeping  # noqa: E402
from quant.strategies.ml import pool_ready  # noqa: E402


def _snaps(tmp_path, n: int) -> str:
    base = tmp_path / "snapshots"
    base.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        (base / f"2026-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}").mkdir(exist_ok=True)
    return str(tmp_path)


_PLAIN = {"strategy": "ml", "params": {"model": "logreg", "threshold": 0.55}}
_PEERS = {"strategy": "ml", "params": {"model": "gb", "pool": "peers"}}
_UNIV = {"strategy": "ml", "params": {"model": "gb", "pool": "universe"}}


def test_peers_sleeps_while_the_snapshots_are_thin(tmp_path):
    d = _snaps(tmp_path, 14)          # 2026-08-19 실측과 같은 두께
    assert pool_ready("peers", d, POOL_WAKE_DAYS) is False
    live, asleep = _split_sleeping([_PLAIN, _PEERS, _UNIV], d)
    assert _PEERS in asleep, "못 도는 peers가 시도 수에 그대로 들어간다"
    assert _PLAIN in live and _UNIV in live


def test_peers_wakes_up_once_the_snapshots_pile_up(tmp_path):
    """대조군 — 영영 빼 버리면 안 된다.

    peers는 인과성이 완벽한 쪽이라, 스냅샷이 쌓이면 돌아와야 한다. 이
    검사가 없으면 "그냥 지웠다"도 위 검사를 통과한다.
    """
    d = _snaps(tmp_path, POOL_WAKE_DAYS + 5)
    assert pool_ready("peers", d, POOL_WAKE_DAYS) is True
    live, asleep = _split_sleeping([_PLAIN, _PEERS, _UNIV], d)
    assert asleep == [], f"조건이 찼는데도 잠들어 있다: {asleep}"
    assert _PEERS in live


def test_a_candidate_without_pooling_never_sleeps(tmp_path):
    """대조군 — 풀과 무관한 후보까지 재우면 링이 통째로 멈춘다."""
    d = _snaps(tmp_path, 0)           # 스냅샷이 아예 없어도
    assert pool_ready(None, d) is True
    live, asleep = _split_sleeping([_PLAIN, _PLAIN, _PLAIN], d)
    assert asleep == [] and len(live) == 3


def test_universe_pooling_only_needs_one_snapshot(tmp_path):
    """universe는 '가장 최근 폴더' 하나면 돈다 — peers와 조건이 다르다."""
    assert pool_ready("universe", _snaps(tmp_path, 0)) is False
    assert pool_ready("universe", _snaps(tmp_path, 1)) is True


def test_the_ring_counts_only_what_it_actually_ran(tmp_path):
    """시도 수 = 링에 실제로 선 후보 수여야 한다."""
    d = _snaps(tmp_path, 14)
    ring = [_PLAIN, _PEERS, _PEERS, _UNIV]
    live, asleep = _split_sleeping(ring, d)
    assert len(live) + len(asleep) == len(ring), "후보가 사라졌다"
    assert len(live) == 2 and len(asleep) == 2


def test_the_count_is_taken_after_the_split_not_before():
    """**배선**을 지킨다 — 헬퍼가 맞아도 안 부르면 소용없다.

    앞의 검사들은 `_split_sleeping`이 옳은지만 본다. 그런데 재학습 쪽에서
    그 호출을 지워도 헬퍼는 여전히 옳으므로 전부 초록이다 — 이 저장소가
    반복해서 당한 모양이다(낱말이 있는 것 ≠ 실제로 도는 것).

    그래서 시도 수를 세는 줄이 **가른 뒤에** 오는지를 순서로 확인한다.
    """
    import ast

    src = (ROOT / "quant" / "live" / "retrain.py").read_text("utf-8")
    lines = src.splitlines()
    # ⚠️ 호출이 한 줄이라고 가정하지 않는다 — 인자가 늘어 줄바꿈이 생기면
    #    이 검사가 "호출이 없다"로 죽는다(계약은 그대로인데 검사만 낡은 경우).
    split_at = [i for i, l in enumerate(lines)
                if "_split_sleeping(challengers, state_dir" in l]
    count_at = [i for i, l in enumerate(lines)
                if l.strip() == "n_cand = len(challengers)"]
    assert split_at, ("잠든 후보를 가르는 호출이 없다 — 헬퍼만 있고 아무도 "
                      "안 부르면 못 도는 후보가 그대로 시도 수에 들어간다")
    assert count_at, "시도 수를 세는 줄을 못 찾았다 — 검사가 낡았다"
    assert split_at[0] < count_at[0], (
        f"시도 수를 가르기 전에 센다(L{count_at[0] + 1} < L{split_at[0] + 1}) "
        "— 잠든 후보가 문턱을 올린다")
    # 그 사이에 challengers를 다시 부풀리는 줄이 없어야 한다.
    between = "\n".join(lines[split_at[0]:count_at[0]])
    assert "challengers =" not in between.replace(
        "challengers, asleep = _split_sleeping", ""), between
    ast.parse(src)      # 구문이 깨진 채로 통과하지 않게
