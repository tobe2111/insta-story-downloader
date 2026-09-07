"""그림자 실험 장부는 한 계좌만 담고, 시간은 앞으로만 간다.

2026-09-07 장부 실측. 이것도 **숫자가 멀쩡해 보이는** 종류의 고장이라
화면에 아무 이상이 안 뜬다.

■ 무엇이 일어나고 있었나

일일 배치의 통합 계좌 함수는 하루에 **두 번** 돈다 — 본 계좌(오디션이
고른 챔피언)와 섀도 대조군(진화 없이 최초 기본 챔피언으로 고정). 대조군은
"오디션이 실제로 가치를 더하는가"를 재려고 만든 계좌라 **신호 자체가
다르다.**

그런데 배분 사다리·사이징 사다리·2세대·무제약 네 실험이 **같은 장부
파일**에 썼다. 판정일이 같은 평일에는 멱등 가드(``== bar``)가 두 번째 줄을
삼켜 아무 일도 안 일어난다 — 그래서 몇 주 동안 표시가 없었다. 갈리는 것은
주말이다:

    ... 09-04 · 09-05 · **09-04** · 09-06 · **09-04**
                          ↑ 대조군의 줄

    실측: 장부 **10개 × 2줄**. 오염된 줄이 매번 **마지막 줄**이라
    화면의 대표 숫자 10개가 전부 **다른 계좌의 값**이었다
    (예: 배분 사다리 equal 1,000,825원 → 실제 본 계좌 1,000,975원).

다양성 그림자 둘만 깨끗했다(되감김 0). 그 재료를 줍는 자리가 이미
``use_champions`` 가드 안에 있었기 때문이다 — **필요한 가드가 어떤
모양인지는 저장소가 이미 알고 있었고, 나머지 넷에 안 붙였을 뿐이다.**

■ 고친 것 세 가지

  ① 호출부가 **본 계좌 회차에서만** 네 실험을 돌린다(다양성과 같은 가드).
  ② 뒤를 받치는 시계 — 본 계좌는 2026-08-16 실전 사고(감사 262) 뒤에
     "판정일이 과거로 가면 멈춘다"는 관문을 얻었는데 그림자 장부에는
     없었다. 다섯 장부가 이제 한 규칙을 같이 쓴다.
  ③ 이미 들어온 줄은 **고치지 않는다.** 대신 장부가 스스로 세어
     ``mixed_rows``로 말하고, 화면의 대표 숫자는 마지막으로 **쓴** 줄이
     아니라 가장 최신 **봉**의 줄을 고른다.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live import shadow_clock as clock  # noqa: E402
from quant.live.alloc_ladder import ladder_public, run_alloc_ladder  # noqa: E402
from quant.live.gen2 import gen2_public, run_gen2  # noqa: E402
from quant.live.sizing_ladder import run_sizing_ladder, sizing_public  # noqa: E402
from quant.live.unshackled import run_unshackled, unshackled_public  # noqa: E402

MARKS = {"us_stock:A": 100.0, "us_stock:B": 50.0}
W = {"us_stock:A": 0.5, "us_stock:B": 0.5}


def _ladder(d: str, bar: str):
    return run_alloc_ladder(bar=bar, weights=W, rets_map={}, marks=MARKS,
                            n_total=2, state_dir=d)


def _rows(d: str, method: str = "equal") -> list[str]:
    with open(os.path.join(d, "alloc_ladder", f"{method}.json"),
              encoding="utf-8") as f:
        return [r["date"] for r in json.load(f)["history"]]


# ── ② 시간은 앞으로만 ──────────────────────────────────────────────────
def test_a_ledger_refuses_a_bar_that_went_backwards():
    """이 검사가 이 파일의 존재 이유다 — 실제로 재현된 사고를 못 박는다."""
    d = tempfile.mkdtemp()
    _ladder(d, "2026-09-04")
    _ladder(d, "2026-09-05")
    _ladder(d, "2026-09-04")            # 대조군 회차가 뒤늦게 들어온다
    assert _rows(d) == ["2026-09-04", "2026-09-05"], (
        f"{_rows(d)} — 과거로 간 봉이 장부에 적혔다. 그 줄은 다른 계좌의 "
        "것이거나 시세가 뒤처졌다는 뜻이라 기록이 아니라 사고다")


def test_the_same_bar_is_still_idempotent():
    """같은 봉은 사고가 아니라 '이미 했다'다 — 이 둘을 갈라야 한다."""
    d = tempfile.mkdtemp()
    first = _ladder(d, "2026-09-04")
    again = _ladder(d, "2026-09-04")
    assert _rows(d) == ["2026-09-04"]
    assert again["equal"]["equity"] == first["equal"]["equity"], (
        "멱등 재실행이 값을 바꿨다")


def test_every_shadow_ledger_shares_the_one_clock():
    """다섯 장부가 **같은 규칙**을 쓴다 — 한 곳만 고치면 나머지가 남는다."""
    for mod in ("alloc_ladder", "sizing_ladder", "gen2", "unshackled",
                "diversity_shadow"):
        src = (ROOT / "quant" / "live" / f"{mod}.py").read_text("utf-8")
        assert "clock.step(" in src, f"{mod}: 시계를 안 쓴다"
        assert 'st["history"][-1].get("date") == bar' not in src, (
            f"{mod}: 옛 `==` 가드가 남아 있다 — 과거로 가는 봉이 그대로 통과한다")


def test_gen2_and_unshackled_refuse_too():
    d = tempfile.mkdtemp()
    for bar in ("2026-09-04", "2026-09-05"):
        run_gen2(bar=bar, weights=W, marks=MARKS, grades={}, tilt=None,
                 state_dir=d)
        run_unshackled(bar=bar, weights=W, slices={}, marks=MARKS, n_total=2,
                       state_dir=d)
    assert run_gen2(bar="2026-09-04", weights=W, marks=MARKS, grades={},
                    tilt=None, state_dir=d) is None
    assert run_unshackled(bar="2026-09-04", weights=W, slices={}, marks=MARKS,
                          n_total=2, state_dir=d) is None
    for name in ("gen2.json", "unshackled.json"):
        with open(os.path.join(d, name), encoding="utf-8") as f:
            assert [r["date"] for r in json.load(f)["history"]] == \
                ["2026-09-04", "2026-09-05"], f"{name}: 과거로 간 봉이 적혔다"
    assert gen2_public(d)["days"] == 2
    assert unshackled_public(d)["days"] == 2


def test_sizing_ladder_refuses_too():
    d = tempfile.mkdtemp()
    probs, th = {"us_stock:A": 0.7}, {"us_stock:A": 0.55}
    for bar in ("2026-09-04", "2026-09-05"):
        run_sizing_ladder(bar=bar, probs=probs, thresholds=th, marks=MARKS,
                          state_dir=d)
    run_sizing_ladder(bar="2026-09-04", probs=probs, thresholds=th,
                      marks=MARKS, state_dir=d)
    # ⚠️ 표본 일수(서로 다른 날짜)로만 보면 안 된다 — 되감긴 줄은 이미 있는
    #    날짜라 그 수가 안 변한다. 장부의 **줄 수**를 봐야 드러난다.
    with open(os.path.join(d, "sizing_ladder", "current.json"),
              encoding="utf-8") as f:
        assert [r["date"] for r in json.load(f)["history"]] == \
            ["2026-09-04", "2026-09-05"], "과거로 간 봉이 장부에 적혔다"
    assert sizing_public(d)["tracks"]["current"]["days"] == 2


# ── ③ 이미 들어온 줄은 고치지 않고 **말한다** ─────────────────────────
def test_rows_already_in_the_ledger_are_not_rewritten_but_named():
    """조용히 빼면 '원래 그런 곡선이었다'와 구별되지 않는다."""
    d = tempfile.mkdtemp()
    _ladder(d, "2026-09-04")
    _ladder(d, "2026-09-05")
    path = os.path.join(d, "alloc_ladder", "equal.json")
    with open(path, encoding="utf-8") as f:
        st = json.load(f)
    st["history"].append(dict(st["history"][0]))       # 옛 사고를 재현
    with open(path, "w", encoding="utf-8") as f:
        json.dump(st, f)

    pub = ladder_public(d)
    assert pub["mixed_rows"]["tracks"]["equal"]["rows"] == 1
    assert pub["mixed_rows"]["tracks"]["equal"]["dates"] == ["2026-09-04"]
    assert pub["mixed_rows"]["why"], "무엇이 어긋났는지 설명이 없다"
    with open(path, encoding="utf-8") as f:
        assert len(json.load(f)["history"]) == 3, "지난 줄을 고쳐 버렸다"


def test_a_clean_ledger_says_nothing():
    """깨끗한 장부에는 그 칸이 아예 없다 — 매일 켜진 표시는 표시가 아니다."""
    d = tempfile.mkdtemp()
    _ladder(d, "2026-09-04")
    _ladder(d, "2026-09-05")
    assert "mixed_rows" not in ladder_public(d)


def test_the_screen_reads_the_newest_bar_not_the_newest_write():
    """실측된 피해 그 자체 — 화면이 다른 계좌의 자산을 발표하고 있었다."""
    d = tempfile.mkdtemp()
    _ladder(d, "2026-09-04")
    _ladder(d, "2026-09-06")
    path = os.path.join(d, "alloc_ladder", "equal.json")
    with open(path, encoding="utf-8") as f:
        st = json.load(f)
    old = dict(st["history"][0])
    old["equity"] = 111.0                              # 다른 계좌의 값
    st["history"].append(old)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(st, f)
    got = ladder_public(d)["tracks"]["equal"]
    assert got["equity"] != 111.0, (
        "마지막으로 **쓴** 줄을 읽었다 — 그 줄은 더 과거의 봉이다")
    assert got["days"] == 2, (
        f"표본 일수가 {got['days']}일이다 — 같은 날짜를 두 번 세면 표본 "
        "크기를 부풀려 말하게 된다")


# ── ① 대조군 회차는 애초에 재료를 안 준다 ─────────────────────────────
def test_only_the_champion_run_feeds_the_experiments():
    """근본 원인 — 이 가드가 없으면 시계는 뒤를 받칠 뿐이다.

    같은 날 두 계좌가 각자의 봉으로 돌면 시계도 못 막는다(둘 다 앞으로
    가는 봉일 수 있다). 재료를 안 주는 것이 근본 처방이다.
    """
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    for fn in ("run_alloc_ladder(bar=bar", "run_sizing_ladder(bar=bar",
               "run_gen2(bar=bar", "run_unshackled(bar=bar"):
        i = src.index(fn)
        before = src[max(0, i - 1200):i]
        assert "if use_champions:" in before, (
            f"{fn}: 섀도 대조군 회차에서도 돈다 — 두 계좌가 한 장부에 쓴다")


# ── 시계 자체의 규칙 ───────────────────────────────────────────────────
def test_the_clock_tells_the_three_cases_apart():
    h = [{"date": "2026-09-04"}]
    assert clock.step(h, "2026-09-05") == clock.NEW
    assert clock.step(h, "2026-09-04") == clock.SAME
    assert clock.step(h, "2026-09-03") == clock.BACKWARDS
    assert clock.step([], "2026-09-04") == clock.NEW, "빈 장부는 사고가 아니다"


def test_the_clock_counts_days_not_rows():
    h = [{"date": "2026-09-04"}, {"date": "2026-09-05"}, {"date": "2026-09-04"}]
    assert clock.distinct_days(h) == 2
    assert clock.latest_row(h)["date"] == "2026-09-05"
    assert clock.out_of_order(h) == {"rows": 1, "dates": ["2026-09-04"]}
    assert clock.out_of_order(h[:2]) is None
