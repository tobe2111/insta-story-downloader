"""패널 관문이 **다중검정 값을 치른다** — 부트스트랩이 관문에 연결된다.

■ 코드가 스스로 남긴 숙제였다 (2026-09-07 확인)

`shared_panel_specs`에 이렇게 적혀 있었다:

    "⚠️ 나중에 이것이 관문이 될 때 다시 볼 것(작업 #56): 지금 다중검정
     보정은 그날 밤 명단 크기에만 걸린다. … 승격을 패널로 정하는 순간에는
     날짜를 가로질러 누적된 시도 수로 보정해야 한다."

**그 순간은 2026-09-02에 왔다**(패널이 AND 관문이 되었다, gate_version 4).
그런데 확인해 보니 승격 조회기는 `pass`(= t > PANEL_T_REF) **하나만** 읽고
있었고, 밤마다 계산되던 부트스트랩은 **콘솔 로그로만 나가고 아무 관문도
읽지 않았다.**

CLAUDE.md는 이렇게 적어 두었다: *"패널의 다중검정 보정은 문턱이 아니라
**부트스트랩**이 맡는다 — 설정을 늘리면 귀무 세계의 최고 t가 같이 커져 p가
정직하게 커진다."* 그 장치가 관문에 **연결돼 있지 않았다.**

■ ⚠️ 오늘 이것이 막는 것은 없다 (실측)

패널 판정 15건에 **통과 0건**이라, 부트스트랩을 볼 차례 자체가 아직 온 적이
없다. 고치는 것은 "지금 틀린 판정"이 아니라 **"통과하는 날이 왔을 때 보정
없이 통과할 수 있다"**는 것이다. 이 저장소가 반복해서 지키는 규율 그대로다 —
*"넓힌 만큼 관문이 따라 올라가는지 매번 확인한다. 그 연결이 끊긴 자동화는
개선 장치가 아니라 과최적화 기계다."*

■ ⚠️ 그리고 정직하게 — 이 보정은 **부분적이다**

부트스트랩은 그 밤에 담긴 설정(하루 3개)을 센다. 회전 때문에 며칠에 걸쳐
46개를 다 재므로 누적 시도 수로는 여전히 덜 세는 셈이다. 그 한계를 숨기지
않고 `n_cand`로 장부에 남긴다 — 숫자로 적어 두지 않으면 "보정이 걸려 있다"는
말만 남는다.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.retrain import (  # noqa: E402
    PANEL_T_REF, RC_ALPHA, _night_reality_check, panel_gate_lookup,
    panel_nights, spec_key,
)

SPEC = {"strategy": "ml", "params": {"model": "gb"}}


def _row(night: str, *, t_stat: float, rc: dict, n_symbols: int = 10,
         n_dates: int = 120) -> dict:
    """패널 장부 한 줄 — 합치기가 되도록 날짜별 재료를 함께 담는다."""
    import datetime as _dt
    import math as _m

    base = _dt.date(2026, 5, 1)
    dates = [(base + _dt.timedelta(days=i)).isoformat() for i in range(n_dates)]
    syms = [f"us_stock:S{i}" for i in range(n_symbols)]
    # ⚠️ **상수 계열을 쓰면 안 된다.** 분산이 0이면 `degenerate_spread`가
    #    t를 0으로 못 박아(감사 146·149·159) 원하는 판정을 만들 수 없다 —
    #    조회기는 `daily`에서 판정을 **다시 계산**하므로 위의 `t_stat` 값은
    #    쓰이지 않는다. 그래서 실제로 그 t가 나오는 계열을 짓는다.
    sd = 0.001
    noise = [sd * _m.sin(i * 1.7) * _m.sqrt(2.0) for i in range(n_dates)]
    mean = float(t_stat) * sd / _m.sqrt(n_dates)
    vals = [mean + z for z in noise]
    return {
        "asof": night, "roster_asof": night,
        "n_specs_collected": 1, "n_specs_judged": 1,
        "roster_size": 3, "n_symbols_seen": n_symbols, "t_ref": PANEL_T_REF,
        "specs": [{
            "spec_key": spec_key(SPEC),
            "n_symbols": n_symbols, "n_dates": len(dates),
            "mean_diff": mean, "t_stat": t_stat, "pass_t": t_stat > PANEL_T_REF,
            "symbol_wins": n_symbols, "symbol_win_rate": 1.0,
            "daily": {"dates": dates,
                      "sums": [v * n_symbols for v in vals],
                      "counts": [n_symbols] * len(dates),
                      "symbols": syms},
            "symbol_terms": {s: [1.0, mean] for s in syms},
        }],
        "skipped": [], "reality_check": rc,
    }


def _ledger(rows: list[dict]) -> str:
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "panel_history.jsonl"), "w",
              encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return d


def _verdict(rows: list[dict]) -> dict | None:
    return panel_gate_lookup(_ledger(rows))(SPEC)


# ── 이 검사가 이 파일의 존재 이유다 ────────────────────────────────────
def test_a_passing_setting_is_still_blocked_when_the_bootstrap_says_luck():
    """패널 t는 넘겼는데 동시검정이 "우연과 구별 안 된다"면 **막는다.**

    이게 없으면 패널 관문은 `t > 1.35` 하나로만 판정한다 — 다중검정 보정이
    통째로 빠진 채 승격에 관여하는 것이다.
    """
    v = _verdict([_row("2026-09-07", t_stat=3.0,
                       rc={"p": 0.9, "n_cand": 3, "skipped": False})])
    assert v and v["blocked"] is True, v
    assert "우연으로 나올 확률" in str(v.get("reality_block")), v
    assert v["reality_check"]["p"] == 0.9


def test_a_passing_setting_survives_when_the_bootstrap_agrees():
    """대조군 — 동시검정도 통과하면 막지 않는다(관문이 전부를 막으면 안 된다)."""
    v = _verdict([_row("2026-09-07", t_stat=3.0,
                       rc={"p": 0.01, "n_cand": 3, "skipped": False})])
    assert v and v["blocked"] is False, v
    assert v.get("reality_block") is None


def test_the_threshold_is_the_shared_one_not_a_new_number():
    """문턱은 결승 관문과 **같은 값**을 쓴다 — 여기서 따로 정하면 관문이 아니라 편의다."""
    src = (ROOT / "quant" / "live" / "retrain.py").read_text("utf-8")
    i = src.index("def panel_gate_lookup(")
    body = src[i:i + 6000]
    assert "> RC_ALPHA" in body, "패널이 자기만의 알파를 쓰고 있다"
    assert RC_ALPHA == 0.10


# ── 생략과 고장은 다른 사건이다 (결승 관문과 같은 규약) ────────────────
def test_a_bootstrap_that_broke_blocks_the_promotion():
    """**재려다 실패**했으면 막는다 — 관문을 못 건 채로 승격시키지 않는다."""
    v = _verdict([_row("2026-09-07", t_stat=3.0,
                       rc={"skipped": True, "broken": True,
                           "reason": "행렬을 못 만들었습니다"})])
    assert v and v["blocked"] is True, v
    assert "재려다 실패" in str(v.get("reality_block")), v


def test_a_bootstrap_skipped_for_a_short_sample_does_not_block():
    """표본이 짧아 **생략**한 것은 위반이 아니다 — 못 잰 것을 막음으로 세지 않는다."""
    v = _verdict([_row("2026-09-07", t_stat=3.0,
                       rc={"skipped": True, "reason": "표본 부족"})])
    assert v and v["blocked"] is False, v
    assert v.get("reality_block") is None
    # 다만 그 사실은 실어 보낸다 — 안 실으면 "보정이 걸렸다"로 읽힌다.
    assert v["reality_check"]["skipped"] is True


def test_a_failing_setting_is_blocked_regardless_of_the_bootstrap():
    """t를 못 넘으면 동시검정을 볼 것도 없이 막힌다(순서가 바뀌면 안 된다)."""
    v = _verdict([_row("2026-09-07", t_stat=0.1,
                       rc={"p": 0.001, "n_cand": 3, "skipped": False})])
    assert v and v["blocked"] is True, v
    assert v.get("reality_block") is None, "탈락인데 동시검정 사유가 붙었다"


# ── 한 밤의 여러 회차를 접는 규칙 ──────────────────────────────────────
def test_the_night_takes_the_most_conservative_bootstrap():
    """회차가 둘이면 **가장 보수적인 값**을 쓴다 — 좋은 쪽을 고르면 안 된다."""
    got = _night_reality_check([
        {"reality_check": {"p": 0.2, "n_cand": 3, "skipped": False}},
        {"reality_check": {"p": 0.8, "n_cand": 3, "skipped": False}},
    ])
    assert got["p"] == 0.8, got
    assert got["runs"] == 2


def test_one_broken_run_makes_the_whole_night_broken():
    got = _night_reality_check([
        {"reality_check": {"p": 0.01, "n_cand": 3, "skipped": False}},
        {"reality_check": {"skipped": True, "broken": True}},
    ])
    assert got.get("broken") is True, got


def test_a_night_with_no_bootstrap_says_so():
    got = _night_reality_check([{"specs": []}])
    assert got["skipped"] is True and got.get("reason"), got


def test_panel_nights_carries_the_bootstrap():
    """밤 단위 읽기가 동시검정을 들고 와야 조회기가 볼 수 있다.

    안 들고 오면 관문은 부트스트랩을 **볼 방법이 없다** — 장치는 돌지만
    아무 데도 연결되지 않은 상태가 된다(이 파일이 고치는 그 상태다).
    """
    d = _ledger([_row("2026-09-07", t_stat=1.0,
                      rc={"p": 0.4, "n_cand": 3, "skipped": False})])
    night = panel_nights(d)[-1]
    assert (night.get("reality_check") or {}).get("p") == 0.4, night


# ── 한계를 숫자로 남긴다 ───────────────────────────────────────────────
def test_the_partial_correction_is_recorded_not_claimed_away():
    """부트스트랩이 **몇 개를 셌는지**가 판정과 함께 남아야 한다.

    회전 때문에 그 밤에 담긴 설정(3개)만 세고 명단 전체(46개)는 못 센다.
    그 한계를 숫자로 안 남기면 "보정이 걸려 있다"는 말만 남는다.
    """
    v = _verdict([_row("2026-09-07", t_stat=3.0,
                       rc={"p": 0.9, "n_cand": 3, "skipped": False})])
    assert v["reality_check"]["n_cand"] == 3, v
    src = (ROOT / "quant" / "live" / "retrain.py").read_text("utf-8")
    assert "누적 시도 수로는" in src, (
        "부분 보정이라는 사실이 코드에 안 적혀 있다 — 적지 않으면 다음 "
        "사람이 '보정이 다 걸려 있다'로 읽는다")


def test_the_generation_says_which_rule_decided():
    """관문이 바뀌었으므로 세대를 올린다 — 옛 기록은 옛 규칙으로 재현한다."""
    src = (ROOT / "quant" / "live" / "retrain.py").read_text("utf-8")
    assert '"gate_version": 5,' in src, "관문을 바꿨는데 세대가 그대로다"
    # 재현기는 그날 장부의 판정을 되먹이므로 v4·v5가 같은 길로 재생된다.
    assert 'int(rec.get("gate_version", 1)) >= 4' in src
