"""배치 건강 계약 검사 — 절반이 마비된 날이 초록으로 보이면 안 된다.

배경(2026-08-11 감사): run_daily_paper_all / run_retrain_all은 **전 종목이
실패했을 때만** 예외를 올린다. 20종목 중 19개가 실패해도 잡은 성공이고,
그 종목들은 그날 판단·기록이 통째로 없는 채 옛 챔피언을 그대로 쓴다.
콘솔에만 남아 아무도 보지 않았다.

같은 감사에서 주간 보고서도 걸렸다: 주간 수익률을 자산 비율로만 계산해
**매칭입금이 수익으로 둔갑**했다 — 이 프로젝트가 원금과 손익을 분리해 온
원칙과 정면으로 어긋난다.

핵심 계약:
  ① 부분 실패가 장부(run_health.json)에 남는다
  ② 사이트 상태에 실려 나가고 경보가 울린다
  ③ 주간 수익률에서 입금이 제거된다
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import quant.live.daily as dl  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


# ── ① 부분 실패가 장부에 남는다 ───────────────────────────────


def test_partial_failure_is_recorded(tmp_path, monkeypatch):
    def fake(market, symbol, **kw):
        if symbol == "BAD":
            raise RuntimeError("데이터 없음")
        return {"date": "2026-08-11", "equity": 1.0, "return_pct": 0.0}

    monkeypatch.setattr(dl, "run_daily_paper", fake)
    dl.run_daily_paper_all(
        targets=[("synthetic", "OK1"), ("synthetic", "OK2"),
                 ("synthetic", "BAD")],
        state_dir=str(tmp_path), require_real_data=False)

    rh = json.loads((tmp_path / "run_health.json").read_text(encoding="utf-8"))
    assert rh["paper"]["ok"] == 2
    assert rh["paper"]["failed"] == 1
    assert rh["paper"]["failed_keys"] == ["synthetic:BAD"]
    assert "데이터 없음" in next(iter(rh["paper"]["errors"].values()))


def test_success_leaves_zero_failures(tmp_path, monkeypatch):
    monkeypatch.setattr(dl, "run_daily_paper",
                        lambda m, s, **kw: {"date": "x", "equity": 1.0})
    dl.run_daily_paper_all(targets=[("synthetic", "A")],
                           state_dir=str(tmp_path), require_real_data=False)
    rh = json.loads((tmp_path / "run_health.json").read_text(encoding="utf-8"))
    assert rh["paper"]["failed"] == 0


def test_retrain_records_its_own_health(tmp_path, monkeypatch):
    import quant.live.retrain as rt

    def fake(market, symbol, **kw):
        raise RuntimeError("모델 학습 실패")

    monkeypatch.setattr(rt, "run_retrain", fake)
    try:
        rt.run_retrain_all(targets=[("synthetic", "A")],
                           state_dir=str(tmp_path))
    except RuntimeError:
        pass                      # 전 종목 실패는 예외가 맞다 — 기록은 남아야
    rh = json.loads((tmp_path / "run_health.json").read_text(encoding="utf-8"))
    assert rh["retrain"]["failed"] == 1


# ── ② 사이트·경보로 흘러간다 ──────────────────────────────────


def test_status_carries_run_health(tmp_path):
    (tmp_path / "paper").mkdir()
    (tmp_path / "run_health.json").write_text(json.dumps(
        {"paper": {"date": "2026-08-11", "ok": 17, "failed": 3,
                   "failed_keys": ["a", "b", "c"], "errors": {}}}),
        encoding="utf-8")
    st = dl.write_docs_status(str(tmp_path),
                              docs_path=str(tmp_path / "status.json"))
    assert st["run_health"]["paper"]["failed"] == 3


def test_flag_watch_alerts_on_partial_failure(tmp_path, monkeypatch):
    from quant.live import flag_watch

    sent = []

    class _Spy:
        def send(self, m, level="info"):
            sent.append(m)
            return True

    monkeypatch.setattr("quant.live.notifications.get_notifier", lambda: _Spy())
    st = {"run_health": {"paper": {"date": "2026-08-11", "ok": 1, "failed": 19,
                                   "failed_keys": [f"m:{i}" for i in range(19)],
                                   "errors": {"m:0": "429 Too Many Requests"}}}}
    new = flag_watch.check_and_notify_flags(st, str(tmp_path))
    assert any(k.startswith("run_failed:paper:") for k in new)
    msg = next(m for m in sent if "부분 실패" in m)
    assert "19종목 실패" in msg and "429" in msg


def test_no_alert_when_nothing_failed(tmp_path, monkeypatch):
    from quant.live import flag_watch

    monkeypatch.setattr("quant.live.notifications.get_notifier",
                        lambda: type("S", (), {"send": lambda s, m, level="info": True})())
    st = {"run_health": {"paper": {"date": "2026-08-11", "ok": 20,
                                   "failed": 0, "failed_keys": []}}}
    new = flag_watch.check_and_notify_flags(st, str(tmp_path))
    assert not any(k.startswith("run_failed:") for k in new)


def test_failure_notice_survives_empty_record_list():
    """전 종목이 휴장·스킵이면 lines가 비는데, 그때 실패 목록까지 삼켰다."""
    src = (ROOT / "quant" / "cli.py").read_text("utf-8")
    assert 'if lines or out["failed"]:' in src


# ── ③ 주간 보고서에서 입금은 수익이 아니다 ────────────────────


def _state(tmp_path, hist, deposits=None):
    d = tmp_path / "paper"
    d.mkdir(exist_ok=True)
    (d / "portfolio_ALL.json").write_text(json.dumps(
        {"market": "portfolio", "symbol": "ALL", "history": hist,
         "deposits": deposits or []}), encoding="utf-8")


def test_weekly_return_excludes_deposits(tmp_path):
    hist = [{"date": "2026-08-05", "equity": 100_000.0, "return_pct": 0.0},
            {"date": "2026-08-06", "equity": 200_000.0, "return_pct": 0.0}]
    _state(tmp_path, hist, [{"date": "2026-08-06", "amount": 100_000.0}])
    out = dl.weekly_summary(str(tmp_path))
    m = out["markets"]["portfolio:ALL"]
    # 자산은 2배가 됐지만 전부 입금이다 — 주간 수익은 0이어야 한다
    assert abs(m["week_return_pct"]) < 0.01
    assert abs(m["worst_day"]["pct"]) < 0.01


def test_weekly_return_still_measures_real_gains(tmp_path):
    hist = [{"date": "2026-08-05", "equity": 100_000.0, "return_pct": 0.0},
            {"date": "2026-08-06", "equity": 110_000.0, "return_pct": 0.0}]
    _state(tmp_path, hist)
    m = dl.weekly_summary(str(tmp_path))["markets"]["portfolio:ALL"]
    assert abs(m["week_return_pct"] - 10.0) < 0.01


def test_weekly_return_chains_daily_moves(tmp_path):
    """구간수익의 연쇄 곱 — 단순 비율과 달라지는 경우를 고정한다."""
    hist = [{"date": "2026-08-05", "equity": 100.0, "return_pct": 0.0},
            {"date": "2026-08-06", "equity": 110.0, "return_pct": 0.0},
            {"date": "2026-08-07", "equity": 99.0, "return_pct": 0.0}]
    _state(tmp_path, hist)
    m = dl.weekly_summary(str(tmp_path))["markets"]["portfolio:ALL"]
    assert abs(m["week_return_pct"] - (-1.0)) < 0.01
    assert abs(m["best_day"]["pct"] - 10.0) < 0.01
    assert abs(m["worst_day"]["pct"] - (-10.0)) < 0.01


# ── ④ 종목 스킵 — '20종목 분산'이 거짓이 되는 날 ──────────────


def _pf(skipped, planned=20, symbols=None):
    n = planned - len(skipped) if symbols is None else symbols
    return {"paper": {"portfolio:ALL": {"history": [{
        "date": "2026-08-11",
        "champion": {"symbols": n, "skipped": skipped, "planned": planned,
                     "skipped_why": {k: "실데이터 없음" for k in skipped}
                     or None}}]}}}


def _spy(monkeypatch):
    sent = []

    class _S:
        def send(self, m, level="info"):
            sent.append(m)
            return True

    monkeypatch.setattr("quant.live.notifications.get_notifier", lambda: _S())
    return sent


def test_heavy_skip_is_alerted(tmp_path, monkeypatch):
    from quant.live import flag_watch
    sent = _spy(monkeypatch)
    st = _pf([f"m:{i}" for i in range(15)])
    new = flag_watch.check_and_notify_flags(st, str(tmp_path))
    assert any(k.startswith("symbols_skipped:") for k in new)
    msg = next(m for m in sent if "종목 스킵 과다" in m)
    assert "20종목 중 15개" in msg and "5종목으로 운용" in msg
    assert "실데이터 없음" in msg


def test_small_skip_stays_quiet(tmp_path, monkeypatch):
    """휴장·상장폐지로 한둘 빠지는 것은 정상이라 경보하지 않는다."""
    from quant.live import flag_watch
    _spy(monkeypatch)
    new = flag_watch.check_and_notify_flags(_pf(["m:1", "m:2"]), str(tmp_path))
    assert not any(k.startswith("symbols_skipped:") for k in new)


def test_no_skip_no_alert(tmp_path, monkeypatch):
    from quant.live import flag_watch
    _spy(monkeypatch)
    new = flag_watch.check_and_notify_flags(_pf([]), str(tmp_path))
    assert not any(k.startswith("symbols_skipped:") for k in new)


def test_record_carries_plan_and_reasons():
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert '"planned": len(targets)' in src
    assert '"skipped_why"' in src
