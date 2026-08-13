"""건너뜀은 통과가 아니다 — 배치 건강 기록 (감사 226).

배경:
  이 규칙은 이미 이 저장소의 변이 시험 규칙으로 적혀 있다("건너뜀은 통과가
  아니다"). 그런데 정작 **새벽 배치 건강 기록**에서는 지키지 않고 있었다.

  재학습·페이퍼 둘 다 멱등 가드가 있다 — 같은 봉을 다시 받으면 아무 일도
  하지 않고 돌아간다. 그런데 그 종목이 `ok`에 그대로 쌓여서, 장부에는
  "성공 20 · 실패 0"이 남았다. 시세 공급이 얼어붙어 며칠째 같은 봉을 받아도
  화면은 매일 초록이고, 주말과 구별되지 않는다. 그동안 챔피언은 한 번도
  재검증되지 않은 채 계속 돈을 굴린다 — 감사 220이 매매 쪽에서 잡은 병이
  학습 쪽에 그대로 남아 있었다.

핵심 계약:
  · 실제로 돈 것 / 건너뛴 것 / 실패한 것은 서로 다른 칸에 들어간다
  · 건너뜀은 실패도 아니다 — 예비(재시도) 크론은 정상적으로 전부 건너뛴다
  · 주말·연휴로 설명되는 정체는 경보를 울리지 않고, 그 이상만 울린다
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.live.daily import _write_run_health  # noqa: E402
from quant.live.retrain import STALE_SKIP_DAYS, stale_targets  # noqa: E402


# ── ① 세 칸은 서로 다른 칸이다 ────────────────────────────────


def test_skipped_symbols_do_not_inflate_the_success_count(tmp_path):
    _write_run_health(str(tmp_path), "retrain", ok=["crypto:BTC/USDT"],
                      failed={}, skipped=["us_stock:SPY", "kr_stock:005930.KS"])
    r = json.loads((tmp_path / "run_health.json").read_text("utf-8"))["retrain"]
    assert r["ok"] == 1, "건너뛴 종목이 성공으로 세어졌다"
    assert r["skipped"] == 2
    assert r["failed"] == 0
    assert r["skipped_keys"] == ["kr_stock:005930.KS", "us_stock:SPY"]


def test_a_normal_day_still_reports_everything_as_ok(tmp_path):
    """대조군 — 평소에는 건너뜀 0이고 성공 수가 줄지 않는다."""
    _write_run_health(str(tmp_path), "paper", ok=["a", "b", "c"], failed={})
    r = json.loads((tmp_path / "run_health.json").read_text("utf-8"))["paper"]
    assert r["ok"] == 3 and r["skipped"] == 0 and r["failed"] == 0
    assert "stale" not in r


def test_failures_are_still_recorded_separately(tmp_path):
    _write_run_health(str(tmp_path), "paper", ok=["a"],
                      failed={"b": "데이터 수신 실패"}, skipped=["c"])
    r = json.loads((tmp_path / "run_health.json").read_text("utf-8"))["paper"]
    assert (r["ok"], r["skipped"], r["failed"]) == (1, 1, 1)
    assert r["failed_keys"] == ["b"]


# ── ② 주말과 고장을 가른다 ────────────────────────────────────


def _champions(tmp_path, **last_run):
    (tmp_path / "champions.json").write_text(json.dumps(
        {k: {"strategy": "ml", "params": {}, "last_run_asof": v}
         for k, v in last_run.items()}), "utf-8")


def test_a_weekend_gap_is_not_reported_as_stale(tmp_path):
    """금요일 봉으로 일·월요일을 건너뛰는 것은 정상이다 — 울리면 안 된다."""
    _champions(tmp_path, **{"us_stock:SPY": "2026-08-10"})
    assert stale_targets(["us_stock:SPY"], str(tmp_path),
                         today="2026-08-12") == {}


def test_a_frozen_feed_is_reported_with_how_many_days(tmp_path):
    """대조군의 반대편 — 주말로 설명 안 되는 간격은 숫자와 함께 드러난다."""
    _champions(tmp_path, **{"us_stock:SPY": "2026-08-01"})
    assert stale_targets(["us_stock:SPY"], str(tmp_path),
                         today="2026-08-13") == {"us_stock:SPY": 12}


def test_the_threshold_survives_a_long_holiday(tmp_path):
    """문턱은 정확히 STALE_SKIP_DAYS '초과'에서만 걸린다(경계 고정)."""
    _champions(tmp_path, **{"k": "2026-08-01"})
    at = stale_targets(["k"], str(tmp_path), today="2026-08-06")   # 5일
    over = stale_targets(["k"], str(tmp_path), today="2026-08-07")  # 6일
    assert at == {} and over == {"k": 6}
    assert STALE_SKIP_DAYS == 5


def test_symbols_that_actually_ran_are_never_stale(tmp_path):
    """건너뛰지 않은 종목은 아무리 오래된 장부라도 정체가 아니다."""
    _champions(tmp_path, **{"k": "2020-01-01"})
    assert stale_targets([], str(tmp_path), today="2026-08-13") == {}


def test_an_unknown_symbol_is_not_invented_as_stale(tmp_path):
    _champions(tmp_path, **{"k": "2026-08-12"})
    assert stale_targets(["없는:종목"], str(tmp_path),
                         today="2026-08-13") == {}


# ── ③ 배치 요약이 실제로 그렇게 센다 ─────────────────────────


def test_the_retrain_batch_separates_skipped_from_ok(tmp_path, monkeypatch):
    from quant.live import retrain as R

    def fake(market, symbol, **kw):
        key = f"{market}:{symbol}"
        return {"skipped": True, "key": key} if market == "us_stock" else {
            "key": key, "champion": {}}

    monkeypatch.setattr(R, "run_retrain", fake)
    out = R.run_retrain_all([("crypto", "BTC/USDT"), ("us_stock", "SPY")],
                            state_dir=str(tmp_path))
    assert out["ok"] == ["crypto:BTC/USDT"]
    assert out["skipped"] == ["us_stock:SPY"]
    r = json.loads((tmp_path / "run_health.json").read_text("utf-8"))["retrain"]
    assert (r["ok"], r["skipped"], r["failed"]) == (1, 1, 0)


def test_the_retry_cron_skipping_everything_is_not_a_failure(tmp_path,
                                                             monkeypatch):
    """예비 크론은 성공한 날을 다시 돈다 — 전부 건너뛰는 것이 정상 동작이다.

    ⚠️ `not ok`만 보고 예외를 올리면 이 실행이 **매일** 잡을 빨갛게 만든다.
    """
    from quant.live import retrain as R

    monkeypatch.setattr(R, "run_retrain",
                        lambda m, s, **kw: {"skipped": True})
    out = R.run_retrain_all([("crypto", "BTC/USDT")], state_dir=str(tmp_path))
    assert out["ok"] == [] and out["skipped"] == ["crypto:BTC/USDT"]


def test_a_batch_where_everything_actually_failed_still_raises(tmp_path,
                                                              monkeypatch):
    """대조군 — 진짜 전멸은 여전히 예외로 올라와야 한다(조기 경보)."""
    import pytest

    from quant.live import retrain as R

    def boom(market, symbol, **kw):
        raise RuntimeError("데이터 수신 실패")

    monkeypatch.setattr(R, "run_retrain", boom)
    with pytest.raises(RuntimeError, match="전 종목 재학습 실패"):
        R.run_retrain_all([("crypto", "BTC/USDT")], state_dir=str(tmp_path))


def test_the_paper_batch_separates_skipped_from_ok(tmp_path, monkeypatch):
    from quant.live import daily as D

    def fake(market, symbol, **kw):
        return {"skipped": True} if market == "us_stock" else {"equity": 1.0}

    monkeypatch.setattr(D, "run_daily_paper", fake)
    out = D.run_daily_paper_all([("crypto", "BTC/USDT"), ("us_stock", "SPY")],
                                state_dir=str(tmp_path))
    assert out["ok"] == ["crypto:BTC/USDT"]
    assert out["skipped"] == ["us_stock:SPY"]


# ── ④ 정체는 경보로 이어진다 ──────────────────────────────────


def test_stale_targets_reach_the_alert_channel():
    from quant.live.flag_watch import _current_flags as collect_flags

    flags = collect_flags({"run_health": {"retrain": {
        "date": "2026-08-13", "ok": 5, "failed": 0, "skipped": 15,
        "skipped_keys": ["us_stock:SPY"],
        "stale": {"us_stock:SPY": 9}, "max_stale_days": 9}}})
    hit = [v for k, v in flags.items() if k.startswith("run_stale:")]
    assert hit, "며칠째 정체된 종목이 경보로 이어지지 않는다"
    assert "9일" in hit[0] and "us_stock:SPY" in hit[0]


def test_a_quiet_weekend_raises_no_alarm():
    """대조군 — stale이 비어 있으면 건너뜀이 많아도 조용하다."""
    from quant.live.flag_watch import _current_flags as collect_flags

    flags = collect_flags({"run_health": {"retrain": {
        "date": "2026-08-13", "ok": 5, "failed": 0, "skipped": 15,
        "skipped_keys": ["us_stock:SPY"]}}})
    assert not [k for k in flags if k.startswith("run_stale:")]
