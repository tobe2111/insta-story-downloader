"""늘리기로 한 종목이 **계좌에 실제로 들어오는가** (감사 296).

2026-08-19에 규칙을 20종목 → 45종목으로 바꿨다. 금·국채·리츠·원자재처럼
주식이 빠질 때 다르게 움직이는 자산을 넣어 '실효 표본'을 키우려는 변경이다.

그런데 하루 뒤에 확인해 보니 **계좌는 여전히 20종목**이었다. 두 가지가
막고 있었다.

  ① 재계산 조건이 **달만** 봤다. 규칙이 바뀌어도 스냅샷이 같은 달이면
     안 돌아서, 새 규칙이 9월 1일에야 걸릴 참이었다.
  ② 순위 조회가 실패하면 그 시장을 통째로 '직전 유지'로 떨어뜨렸다.
     그런데 금·국채 같은 **고정 코어는 순위가 필요 없다.** 실측: 코인은
     403, 한국은 pykrx 컬럼 변경으로 실패했고, 그 바람에 새 자산군이
     하나도 안 들어왔다. 깨진 것은 순위인데 대가는 확장 전체였다.

여기서 지키는 것:
  · 규칙이 바뀌면 달을 안 기다린다. **그리고 규칙이 그대로면 안 돈다**
    (대조군 — 매월 1회라는 원칙까지 없애면 안 된다).
  · 순위가 깨져도 고정 코어는 들어온다. **그리고 순위가 멀쩡하면 순위대로
    뽑는다**(대조군 — 늘 직전 것을 쓰면 규칙이 죽은 것이다).
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import quant.universe as U  # noqa: E402


def _snap(tmp_path, targets, rule_version, asof="2026-08-19"):
    p = tmp_path / "universe.json"
    p.write_text(json.dumps({"asof": asof, "rule_version": rule_version,
                             "targets": targets, "rationale": {}, "history": []},
                            ensure_ascii=False), "utf-8")
    return str(tmp_path)


_OLD = [["crypto", "BTC/USDT"], ["kr_stock", "069500.KS"], ["us_stock", "SPY"]]


# ── ① 규칙이 바뀌면 달을 안 기다린다 ────────────────────────────────
def test_a_rule_change_does_not_wait_for_next_month(tmp_path):
    d = _snap(tmp_path, _OLD, rule_version="옛-규칙")
    assert U.due(d, today=dt.date(2026, 8, 20)) is True, (
        "규칙이 바뀌었는데 다음 달까지 기다린다 — 코드는 45종목이라 말하고 "
        "계좌는 20종목으로 돈다")


def test_the_same_rule_still_waits_for_next_month(tmp_path):
    """대조군 — 규칙이 그대로면 예전처럼 달만 본다.

    이게 없으면 "항상 재계산"도 위 검사를 통과한다. 잦은 회전은 그 자체가
    비용이고, 매월 1회는 사전 등록한 규칙이다.
    """
    d = _snap(tmp_path, _OLD, rule_version=U.RULE_VERSION)
    assert U.due(d, today=dt.date(2026, 8, 20)) is False, "같은 달인데 또 돈다"
    assert U.due(d, today=dt.date(2026, 9, 1)) is True, "달이 바뀌었는데 안 돈다"


# ── ② 고정 코어는 순위가 아니다 ─────────────────────────────────────
def _boom(*a, **k):
    raise RuntimeError("HTTP Error 403: Forbidden")


def test_the_fixed_core_lands_even_when_the_ranking_dies(tmp_path):
    d = _snap(tmp_path, _OLD, rule_version="옛-규칙")
    snap = U.rebuild(d, today=dt.date(2026, 8, 20),
                     rank_crypto=_boom, rank_kr=lambda asof: _boom(),
                     rank_us=_boom)
    got = {f"{m}:{s}" for m, s in snap["targets"]}
    for sym in U.US_ASSET_CORE:
        assert f"us_stock:{sym}" in got, (
            f"{sym}은 순위와 무관한 고정 코어인데 순위 실패로 빠졌다")
    for sym in U.KR_ASSET_CORE:
        assert f"kr_stock:{sym}" in got, f"{sym}(고정 코어)이 빠졌다"
    # 왜 그렇게 됐는지 스냅샷이 말해야 한다.
    for mk in ("crypto", "kr_stock", "us_stock"):
        r = snap["rationale"][mk]
        assert r.get("core_applied") and r.get("ranking_failed"), r
        assert "403" in r["reason"] or "Error" in r["reason"], r


def test_a_working_ranking_is_actually_used(tmp_path):
    """대조군 — 순위가 멀쩡하면 순위대로 뽑아야 한다.

    이게 없으면 "언제나 직전 꼬리를 쓴다"(=규칙이 죽었다)도 통과한다.
    """
    d = _snap(tmp_path, _OLD, rule_version="옛-규칙")
    snap = U.rebuild(d, today=dt.date(2026, 8, 20),
                     rank_crypto=lambda: ["ZZZ/USDT", "YYY/USDT"],
                     rank_kr=lambda asof: ["999999.KS"],
                     rank_us=lambda: ["ZZZZ"])
    got = {f"{m}:{s}" for m, s in snap["targets"]}
    assert "crypto:ZZZ/USDT" in got and "kr_stock:999999.KS" in got
    assert "us_stock:ZZZZ" in got
    assert snap["rationale"]["crypto"].get("ranking_failed") is None


def test_the_expansion_is_bigger_than_what_we_had(tmp_path):
    """숫자로 확인 — '늘렸다'는 말이 아니라 값으로."""
    d = _snap(tmp_path, _OLD, rule_version="옛-규칙")
    snap = U.rebuild(d, today=dt.date(2026, 8, 20),
                     rank_crypto=_boom, rank_kr=lambda asof: _boom(),
                     rank_us=_boom)
    # 순위가 셋 다 죽어도 고정 코어만으로 예전 20종목을 넘어야 한다.
    assert len(snap["targets"]) > 20, (
        f"순위가 다 죽으면 확장이 통째로 사라진다: {len(snap['targets'])}종목")
