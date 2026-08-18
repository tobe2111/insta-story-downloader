"""수동 킬스위치 — 사장님이 당길 수 있는 핸드브레이크 (2026-08-18, 사례 채택).

자동 브레이크(킬스위치·서킷브레이커)는 숫자만 본다. 뉴스로만 아는 사고,
데이터가 이상하다는 직감 — 사람이 먼저 본 이상을 멈출 수단이 없었다.

지켜야 할 약속:
- 정지는 한 번에 걸리고, 해제는 확인 단어를 정확히 타이핑해야 한다.
- 정지 중에는 일일 배치도, 장중 실험도 **아무 매매를 하지 않는다.**
- 정지 사실은 status.json에 실린다 — 조용한 공백은 고장과 구별이 안 된다.
- 파일이 깨져 있으면 **꺼짐**이다 — 고장이 정지로 위장하면 안 된다.
- 포지션을 강제 청산하지 않는다 — 멈추기만 한다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.manual_halt import (          # noqa: E402
    RESUME_WORD, gate_message, set_halt, status)


def test_the_switch_toggles_and_keeps_history(tmp_path):
    d = str(tmp_path)
    assert status(d) is None, "아무것도 안 했는데 켜져 있다"
    set_halt(d, True, who="cockpit", reason="거래소 해킹 뉴스")
    st = status(d)
    assert st and st["on"] and st["reason"] == "거래소 해킹 뉴스"
    set_halt(d, False, who="cockpit")
    assert status(d) is None
    hist = json.loads((tmp_path / "manual_halt.json").read_text("utf-8"))["history"]
    assert len(hist) == 2 and hist[0]["on"] and not hist[1]["on"], (
        "켜고 끈 이력이 남지 않는다 — 성적을 읽을 때 각주가 사라진다")


def test_a_broken_file_means_off(tmp_path):
    """고장이 정지로 위장하면 안 된다 — 애매하면 꺼짐."""
    (tmp_path / "manual_halt.json").write_text("{깨진 파일", "utf-8")
    assert status(str(tmp_path)) is None
    assert gate_message(str(tmp_path)) is None


def _args(state_dir, **kw):
    base = dict(timeframe="1d", lookback=400, state_dir=state_dir,
                allow_synthetic=False, all=True, docs=False,
                market="crypto", symbol="BTC/USDT", docs_dir="docs")
    base.update(kw)
    return SimpleNamespace(**base)


def test_the_daily_batch_obeys_the_halt(tmp_path, monkeypatch, capsys):
    """정지 중의 일일 배치는 매매 함수를 **부르지도 않는다.**"""
    import quant.cli as cli
    import quant.live.daily as daily
    set_halt(str(tmp_path), True, reason="점검")
    for fn in ("run_daily_paper_all", "run_daily_paper", "run_daily_portfolio"):
        monkeypatch.setattr(daily, fn, lambda *a, **k: pytest.fail(
            "정지 중인데 매매 배치가 돌았다"), raising=True)
    cli._cmd_paper_daily(_args(str(tmp_path)))
    out = capsys.readouterr().out
    assert "수동 킬스위치" in out and "점검" in out, (
        f"멈춘 이유를 말하지 않는다: {out!r}")


def test_the_intraday_round_obeys_the_halt(tmp_path, monkeypatch, capsys):
    """본 계좌만 멈추고 실험이 계속 돌면, '다 멈췄다'는 믿음이 거짓이 된다."""
    import quant.cli as cli
    import quant.live.intraday_challenger as ic
    set_halt(str(tmp_path), True)
    monkeypatch.setattr(ic, "run_intraday_round", lambda *a, **k: pytest.fail(
        "정지 중인데 장중 실험이 돌았다"), raising=True)
    cli._cmd_intraday_round(_args(str(tmp_path)))
    assert "수동 킬스위치" in capsys.readouterr().out


def test_engage_is_one_click_but_resume_needs_the_word(tmp_path):
    from quant.web.app import run_halt_toggle
    d = str(tmp_path)
    run_halt_toggle({"on": "1", "reason": "이상 감지"}, state_dir=d)
    assert status(d) and status(d)["reason"] == "이상 감지", "한 번에 안 걸린다"
    # 틀린 단어로는 재개되지 않는다 — 클릭·오타 실수 방어.
    html = run_halt_toggle({"on": "0", "confirm": "resume"}, state_dir=d)
    assert status(d) is not None, "아무 글자로나 재개됐다"
    assert RESUME_WORD in html, "무엇을 입력해야 하는지 알려주지 않는다"
    run_halt_toggle({"on": "0", "confirm": RESUME_WORD}, state_dir=d)
    assert status(d) is None, "정확한 단어를 넣어도 재개되지 않는다"


def test_the_status_file_carries_the_switch(tmp_path):
    """정지는 status.json에 실린다 — 사이트가 '왜 오늘 기록이 없는지' 말할 재료."""
    from quant.live.daily import write_docs_status
    set_halt(str(tmp_path), True, reason="수동 점검")
    docs = tmp_path / "status.json"
    st = write_docs_status(str(tmp_path), docs_path=str(docs))
    assert st["manual_halt"] and st["manual_halt"]["on"], (
        "status.json이 정지 사실을 모른다")
    on_disk = json.loads(docs.read_text("utf-8"))
    assert on_disk["manual_halt"]["reason"] == "수동 점검"
    set_halt(str(tmp_path), False)
    st2 = write_docs_status(str(tmp_path), docs_path=str(docs))
    assert st2["manual_halt"] is None, "해제됐는데 계속 멈췄다고 말한다"


def test_the_switch_never_liquidates():
    """이 스위치는 멈추기만 한다 — 강제 청산 코드가 섞이면 새 위험이 된다."""
    src = (ROOT / "quant" / "live" / "manual_halt.py").read_text("utf-8")
    for banned in ("flatten", "sell(", "place_order", "market_sell"):
        assert banned not in src, f"수동 킬스위치가 청산까지 한다: {banned}"


def test_the_halt_route_is_gated_as_mutating():
    """켜고 끄기는 POST 전용 목록에 있어야 한다 — 쿼리 한 줄로 멈추게 하지 않는다."""
    from quant.web import server as ws
    assert "/halt/run" in ws.QuantHandler._MUTATING
