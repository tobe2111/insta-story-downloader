"""배치가 죽어도 **살아 있는 채널**이 장부의 죽음을 알리는가 (2026-08-19).

2026-08-16~18 실측: 새벽 배치가 사흘 연속 실패하는 동안 어떤 경보도
사람에게 닿지 않았다. 실패 경보는 죽은 배치의 워크플로가 보내고,
flag_watch(계좌 지각 경보)는 그 배치 안에서 돈다 — 감시가 감시 대상과
같은 배에 타고 있었다. 사흘 내내 5분 장중 감시만 살아 있었다.

지켜야 할 약속:
- 살아 있는 5분 루프가 본 계좌 장부 나이를 재고, 이틀 넘으면 알린다.
- 하루 한 번만 — 288번 울리는 경보는 꺼진 것과 같다.
- 경보 중복 방지 표식은 커밋되는 자리(state/paper/)에 남는다.
- 첫 화면은 서버가 아니라 읽는 순간의 시계로 장부 나이를 계산한다
  (배치가 죽으면 status.json도 함께 낡기 때문).
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import quant.live.guard as G                            # noqa: E402


class _Spy:
    def __init__(self):
        self.sent = []

    def send(self, message, level="info"):
        self.sent.append((level, message))
        return True


def _ledger(tmp_path, last_date: str):
    (tmp_path / "paper").mkdir(parents=True, exist_ok=True)
    (tmp_path / "paper" / "portfolio_ALL.json").write_text(json.dumps({
        "history": [{"date": "2026-08-14", "equity": 1e6},
                    {"date": last_date, "equity": 1e6}]}), "utf-8")


_NOW = dt.datetime(2026, 8, 19, 0, 0, tzinfo=dt.timezone.utc)


def test_a_fresh_ledger_stays_quiet(tmp_path):
    _ledger(tmp_path, "2026-08-18")                      # 나이 1일 — 정상
    spy = _Spy()
    assert G.check_ledger_freshness(str(tmp_path), now=_NOW, notify=spy) is None
    assert not spy.sent, "정상인데 울렸다 — 매일 울리는 경보는 무시당한다"


def test_a_dead_ledger_reaches_a_human_once_a_day(tmp_path):
    _ledger(tmp_path, "2026-08-15")                      # 나이 4일 — 사흘 정지 모양
    spy = _Spy()
    out = G.check_ledger_freshness(str(tmp_path), now=_NOW, notify=spy)
    assert out and out["age_days"] >= 3.9
    assert spy.sent and spy.sent[0][0] == "error"
    assert "묵었습니다" in spy.sent[0][1] and "Daily Paper" in spy.sent[0][1]
    # 같은 날 두 번째 회차(5분 뒤) — 조용해야 한다
    again = G.check_ledger_freshness(
        str(tmp_path), now=_NOW + dt.timedelta(minutes=5), notify=spy)
    assert again is None and len(spy.sent) == 1, "5분마다 다시 울린다"
    # 다음 날 — 여전히 죽어 있으면 다시 알린다(한 번 알리고 영영 침묵 금지)
    third = G.check_ledger_freshness(
        str(tmp_path), now=_NOW + dt.timedelta(days=1), notify=spy)
    assert third is not None and len(spy.sent) == 2, "다음 날은 다시 알려야 한다"


def test_the_marker_lives_where_the_workflow_commits(tmp_path):
    """표식이 커밋 안 되는 자리면 회차마다 초기화돼 288번 울린다.

    ⚠️ 그리고 state/paper/ **안이면 안 된다** — 장부 스캔(ledger_paths)이
    그 폴더의 모든 .json을 계좌로 보므로 표식이 유령 계좌가 된다.
    """
    _ledger(tmp_path, "2026-08-15")
    G.check_ledger_freshness(str(tmp_path), now=_NOW, notify=_Spy())
    assert (tmp_path / "ledger_stale_alert.json").exists()
    from quant.live.ledger_basics import ledger_files
    assert not any("ledger_stale_alert" in p for p in ledger_files(str(tmp_path))), (
        "경보 표식이 계좌 장부로 스캔된다 — 유령 계좌가 화면에 뜬다")
    wf = (ROOT / ".github" / "workflows" / "guard.yml").read_text("utf-8")
    assert "state/ledger_stale_alert.json" in wf, (
        "guard 워크플로가 표식을 커밋하지 않는다 — 5분마다 다시 울린다")
    assert "DISCORD_WEBHOOK_URL" in wf.split("장중 감시 1회")[1].split("run:")[0], (
        "감시 스텝에 웹훅 시크릿이 없다 — 경보를 보낼 채널이 없다")


def test_no_ledger_is_not_an_alarm(tmp_path):
    """장부 파일이 아예 없으면(새 환경) 사고가 아니라 미가동이다."""
    assert G.check_ledger_freshness(str(tmp_path), now=_NOW, notify=_Spy()) is None


def test_the_guard_cli_actually_calls_the_check():
    """함수만 있고 안 부르면 소용없다 — 5분 루프의 배선."""
    src = (ROOT / "quant" / "cli.py").read_text("utf-8")
    assert "check_ledger_freshness(args.state_dir)" in src, (
        "guard 명령이 장부 신선도를 재지 않는다")


def test_the_front_page_computes_the_age_with_the_readers_clock():
    """status.json이 낡으면 서버 계산도 낡는다 — 나이는 읽는 순간의 시계로."""
    index = (ROOT / "docs" / "index.html").read_text("utf-8")
    flags = index.split("const flags=[]", 1)[1].split("side-flags", 1)[0]
    assert "Date.now()" in flags and "pfLast.date" in flags, (
        "첫 화면이 장부 나이를 읽는 순간의 시계로 계산하지 않는다")
    assert "묵음" in flags, "장부 나이 경고 문구가 없다"
