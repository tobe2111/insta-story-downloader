"""재시작 카오스 테스트 — 크래시·손상·중단 후에도 안전하게 복구되는지.

라이브 러너는 언제든 죽을 수 있다(정전·OOM·강제종료). 이 테스트는:
  1) state.json이 중간에 잘려(손상) 있어도 로더가 예외 없이 기본값으로 폴백
  2) atomic_write_json이 중단돼도 손상 파일을 절대 남기지 않음(원본 보존 + tmp 정리)
  3) 재시작 시 reconcile()이 state 누락/손상 상황에서도 실제 포지션을 보고

앞 두 묶음은 순수 stdlib(로컬 실행 가능), reconcile 묶음은 pandas 필요(CI 실행).
"""
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_ROOT = Path(__file__).resolve().parent.parent


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, str(_ROOT / rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


jio = _load("chaos_jsonio", "quant/utils/jsonio.py")
summ = _load("chaos_summary", "quant/live/summary.py")


def _write_state(path: Path) -> dict:
    snap = {"symbol": "BTC/USDT", "last_summary_date": "2026-07-03",
            "history": [{"time": "2026-07-03 01:00:00", "weight": 0.5,
                         "equity": 10_000.0}]}
    jio.atomic_write_json(path, snap)
    return snap


# ── 1) 손상된 state 파일 → 로더 폴백 ─────────────────────────────────────


def test_truncated_state_file_loader_falls_back(tmp_path):
    p = tmp_path / "state.json"
    _write_state(p)
    text = p.read_text(encoding="utf-8")
    p.write_text(text[: len(text) // 2], encoding="utf-8")   # 파일 중간에서 잘림(크래시 흉내)

    # json.loads는 실패하지만, 요약 날짜 로더는 예외 없이 None(기본값)으로 폴백
    try:
        json.loads(p.read_text(encoding="utf-8"))
        assert False, "잘린 파일은 유효 JSON이 아니어야 함"
    except ValueError:
        pass
    assert summ.load_last_summary_date(str(p)) is None


def test_missing_state_file_loader_falls_back(tmp_path):
    assert summ.load_last_summary_date(str(tmp_path / "없음.json")) is None


# ── 2) atomic_write_json — 중단돼도 손상 파일을 남기지 않는다 ─────────────


def test_interrupted_replace_keeps_original_and_cleans_tmp(tmp_path):
    p = tmp_path / "state.json"
    original = _write_state(p)

    def _boom(src, dst):                              # 교체 순간의 크래시 흉내
        raise OSError("디스크 오류 흉내")

    orig_replace = jio.os.replace
    jio.os.replace = _boom
    try:
        try:
            jio.atomic_write_json(p, {"history": ["새", "데이터"]})
            assert False, "os.replace 실패는 예외로 올라와야 함"
        except OSError:
            pass
    finally:
        jio.os.replace = orig_replace

    # 원본은 그대로(유효 JSON, 이전 내용), 부분 임시파일은 정리됨
    assert json.loads(p.read_text(encoding="utf-8")) == original
    assert not list(tmp_path.glob("*.tmp"))


def test_unserializable_object_leaves_no_partial_file(tmp_path):
    p = tmp_path / "state.json"
    original = _write_state(p)
    try:
        jio.atomic_write_json(p, {"bad": object()})   # 직렬화 불가 → dumps에서 실패
        assert False, "직렬화 불가면 예외여야 함"
    except TypeError:
        pass
    assert json.loads(p.read_text(encoding="utf-8")) == original
    assert not list(tmp_path.glob("*.tmp"))


def test_rewrite_after_corruption_recovers(tmp_path):
    """손상 후 다음 사이클의 정상 저장이 파일을 복구한다(러너 재기동 시나리오)."""
    p = tmp_path / "state.json"
    _write_state(p)
    p.write_text('{"half":', encoding="utf-8")        # 손상
    jio.atomic_write_json(p, {"history": [], "last_summary_date": "2026-07-04"})
    assert json.loads(p.read_text(encoding="utf-8"))["last_summary_date"] == "2026-07-04"


# ── 3) 재시작 reconcile — state 누락/손상에도 실제 포지션을 보고 ──────────
#    (pandas 필요 — 로컬에 없으면 건너뛰고 CI에서 실행된다)


def _require_pandas():
    try:
        import pandas  # noqa: F401
    except ImportError:
        raise unittest.SkipTest("pandas 미설치 — CI에서 실행")


def _make_trader(state_path, sent):
    from quant.broker import PaperBroker
    from quant.data import SyntheticDataProvider
    from quant.live import LiveTrader
    from quant.risk import RiskManager

    class N:
        def send(self, msg, level="info"):
            sent.append(msg)

    broker = PaperBroker(cash=10_000)
    broker.market_order("BTC/USDT", "buy", 0.1, 60_000)   # 실제 포지션 생성
    return LiveTrader(SyntheticDataProvider(), None, broker, RiskManager(),
                      "BTC/USDT", state_path=state_path, notifier=N())


def test_reconcile_reports_position_when_state_missing(tmp_path):
    _require_pandas()
    sent: list[str] = []
    trader = _make_trader(str(tmp_path / "없는_state.json"), sent)
    trader.reconcile()                                # state 없어도 크래시 없이 보고
    assert sent and "재시작 정합성" in sent[0] and "BTC/USDT" in sent[0]


def test_reconcile_reports_position_when_state_corrupt(tmp_path):
    _require_pandas()
    p = tmp_path / "state.json"
    _write_state(p)
    text = p.read_text(encoding="utf-8")
    p.write_text(text[: len(text) // 2], encoding="utf-8")   # 손상

    sent: list[str] = []
    trader = _make_trader(str(p), sent)               # __init__의 요약날짜 로드도 폴백
    assert trader._last_summary_date is None
    trader.reconcile()                                # 손상 state → prev=None 폴백, 보고는 수행
    assert sent and "재시작 정합성" in sent[0]
    # 손상 파일이라 직전 목표비중은 표시되지 않는다(모르는 값은 침묵)
    assert "직전 목표비중" not in sent[0]
