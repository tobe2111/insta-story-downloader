"""되살린 기록은 **그날 로그와 같아야 한다** (2026-08-19).

사장님 지시로 2026-08-17·18 두 날을 되살린다. 그 이틀은 시스템이 실제로
판단을 냈고 저장만 못 한 날이다(관문이 서로 다른 이유로 막았다).

⚠️ 되살리기의 유일한 안전장치는 **검산**이다. 그날 깃허브 로그에 찍힌
   자산과 다시 계산한 자산이 같아야만 기록한다. 이 관문이 없으면
   "되살리기"는 그냥 **오늘 계산에 옛 날짜를 붙이는 일**이 된다 —
   이 제품이 절대 하지 않기로 한 바로 그것이다.

   깃허브 로그를 검산값으로 쓰는 이유: 우리가 고칠 수 없는 제3자 기록이다.
   우리 저장소 안의 값으로 우리 계산을 검산하면 아무것도 검산하지 않은 것과
   같다.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SCRIPT = ROOT / "scripts" / "recover_missing_bars.py"


def _load():
    spec = importlib.util.spec_from_file_location("_recover", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def _never_touch_the_real_site(monkeypatch):
    """⚠️ 이 검사는 **저장소의 진짜 파일을 건드리면 안 된다.**

    처음 썼을 때 이 자물쇠가 한 검사에만 있었다. 변이 시험이 검산 관문을
    망가뜨리자 나머지 검사들이 그대로 통과해 `write_docs_status()`까지
    갔고, 임시 폴더의 장부로 **저장소의 docs/status.json을 덮어썼다**
    (기록 3개 → 1개). 화면 검사 여섯 개가 그때부터 무너졌고, 원인을
    찾는 데 시간이 걸렸다.

    검사가 자기 상자 밖에 손을 대면, 깨지는 것은 그 검사가 아니라
    **다른 검사**다. 그래서 자물쇠는 한 곳이 아니라 전부에 건다.
    """
    import quant.live.daily as daily
    monkeypatch.setattr(daily, "write_docs_status", lambda *a, **k: None)


@pytest.fixture
def ledger(tmp_path):
    """08-15에서 멈춘 장부 한 벌."""
    d = tmp_path / "paper"
    d.mkdir(parents=True)
    st = {"market": "portfolio", "symbol": "ALL", "currency": "KRW",
          "cash": 1000.0, "positions": {}, "last_bar": "2026-08-15",
          "history": [{"date": "2026-08-15", "equity": 997197.56}]}
    (d / "portfolio_ALL.json").write_text(json.dumps(st), "utf-8")
    return tmp_path


def _fake_run(tmp, date, equity):
    """장부에 한 줄을 붙이는 가짜 배치."""
    def _run(*a, **kw):
        p = tmp / "paper" / "portfolio_ALL.json"
        st = json.loads(p.read_text("utf-8"))
        st["history"].append({"date": date, "equity": equity})
        st["last_bar"] = date
        p.write_text(json.dumps(st), "utf-8")
        return {"date": date}
    return _run


def _run_cli(mod, ledger, monkeypatch, *argv):
    # 화면 파일도 임시 폴더로 돌린다 — 검사는 자기 상자 밖에 손대지 않는다.
    monkeypatch.setattr(sys, "argv",
                        ["recover", "--state-dir", str(ledger),
                         "--docs-status", str(ledger / "status.json"), *argv])
    return mod.main()


def _hist(ledger):
    p = ledger / "paper" / "portfolio_ALL.json"
    return json.loads(p.read_text("utf-8"))["history"]


# ── 검산이 실제로 막는가 ────────────────────────────────────────

def test_a_number_that_differs_from_the_log_is_not_recorded(
        ledger, monkeypatch):
    """1원만 달라도 기록하지 않는다 — '거의 같다'는 같은 게 아니다."""
    mod = _load()
    import quant.live.daily as daily
    monkeypatch.setattr(daily, "run_daily_portfolio",
                        _fake_run(ledger, "2026-08-17", 999_268.50))
    rc = _run_cli(mod, ledger, monkeypatch,
                  "--bar", "2026-08-17", "--expect", "999267.50", "--write")
    assert rc == 1, "로그와 다른데 통과시켰다"
    assert [r["date"] for r in _hist(ledger)] == ["2026-08-15"], (
        "검산에 실패했는데 장부에 남았다")


def test_a_wrong_date_is_not_recorded(ledger, monkeypatch):
    """자산이 맞아도 **다른 날**로 적히면 되살린 게 아니다.

    2026-08-16 밤에 실제로 이 일이 났다 — 판정일이 08-14로 뒷걸음쳤다.
    """
    mod = _load()
    import quant.live.daily as daily
    monkeypatch.setattr(daily, "run_daily_portfolio",
                        _fake_run(ledger, "2026-08-14", 999_267.50))
    rc = _run_cli(mod, ledger, monkeypatch,
                  "--bar", "2026-08-17", "--expect", "999267.50", "--write")
    assert rc == 1, "다른 날짜로 적혔는데 통과시켰다"
    assert [r["date"] for r in _hist(ledger)] == ["2026-08-15"]


def test_the_ledger_is_restored_after_a_failed_recovery(ledger, monkeypatch):
    """실패한 되살리기는 **흔적을 남기지 않는다** — 반쯤 고친 장부가 제일 나쁘다."""
    mod = _load()
    before = (ledger / "paper" / "portfolio_ALL.json").read_text("utf-8")
    import quant.live.daily as daily
    monkeypatch.setattr(daily, "run_daily_portfolio",
                        _fake_run(ledger, "2026-08-17", 1.0))
    _run_cli(mod, ledger, monkeypatch,
             "--bar", "2026-08-17", "--expect", "999267.50", "--write")
    assert (ledger / "paper" / "portfolio_ALL.json").read_text("utf-8") == before


def test_recovering_without_a_checksum_is_refused(ledger, monkeypatch):
    """검산값 없이 되살리는 길을 열어 두면 그게 지어내는 길이다."""
    mod = _load()
    rc = _run_cli(mod, ledger, monkeypatch, "--bar", "2026-08-17", "--write")
    assert rc == 2, "검산값 없이 되살리기를 허용했다"
    assert [r["date"] for r in _hist(ledger)] == ["2026-08-15"]


# ── 대조군 — 맞으면 실제로 남는다 ───────────────────────────────
#
# 이게 없으면 "언제나 거부"도 통과하고, 그러면 도구가 아무 일도 못 한다.

def test_a_matching_number_is_recorded(ledger, monkeypatch):
    mod = _load()
    import quant.live.daily as daily
    monkeypatch.setattr(daily, "run_daily_portfolio",
                        _fake_run(ledger, "2026-08-17", 999_267.50))
    rc = _run_cli(mod, ledger, monkeypatch,
                  "--bar", "2026-08-17", "--expect", "999267.50", "--write")
    assert rc == 0, "그날 로그와 같은데 거부했다"
    assert [r["date"] for r in _hist(ledger)] == ["2026-08-15", "2026-08-17"]


def test_a_dry_run_never_touches_the_ledger(ledger, monkeypatch):
    """--write 없이는 맞아도 남기지 않는다 — 먼저 보고 나서 결정한다."""
    mod = _load()
    import quant.live.daily as daily
    monkeypatch.setattr(daily, "run_daily_portfolio",
                        _fake_run(ledger, "2026-08-17", 999_267.50))
    rc = _run_cli(mod, ledger, monkeypatch,
                  "--bar", "2026-08-17", "--expect", "999267.50")
    assert rc == 0
    assert [r["date"] for r in _hist(ledger)] == ["2026-08-15"]


# ── 그날 시스템이 본 것과 같은 것을 보여 주는가 ────────────────

def test_the_feed_is_cut_at_that_day(monkeypatch):
    """오늘의 더 좋은 데이터를 넣으면 그건 재현이 아니라 새 계산이다."""
    pd = pytest.importorskip("pandas")
    mod = _load()
    idx = pd.to_datetime(["2026-08-14", "2026-08-15", "2026-08-16",
                          "2026-08-17", "2026-08-18", "2026-08-19"])
    df = pd.DataFrame({"close": [1.0, 2, 3, 4, 5, 6]}, index=idx)

    class _Inner:
        def get_ohlcv(self, *a, **kw):
            return df.copy()

    cut = mod._Truncated(_Inner(), "2026-08-17", "us_stock", None)
    assert [str(i)[:10] for i in cut.get_ohlcv("SPY").index] == [
        "2026-08-14", "2026-08-15", "2026-08-16", "2026-08-17"]


def test_crypto_can_be_cut_on_its_own_day():
    """2026-08-17 밤 실제 배치는 코인이 2026-03-04에 멈춘 채 판단했다(감사 261).

    오늘은 그 경로가 고쳐져 최신 봉이 온다. 그날을 재현하려면 코인만 따로
    잘라야 한다 — 안 그러면 그날 시스템이 **못 봤던** 시세로 계산하게 된다.
    """
    pd = pytest.importorskip("pandas")
    mod = _load()
    idx = pd.to_datetime(["2026-03-03", "2026-03-04", "2026-08-17"])
    df = pd.DataFrame({"close": [1.0, 2, 3]}, index=idx)

    class _Inner:
        def get_ohlcv(self, *a, **kw):
            return df.copy()

    cut = mod._Truncated(_Inner(), "2026-08-17", "crypto", "2026-03-04")
    assert [str(i)[:10] for i in cut.get_ohlcv("BTC/USDT").index] == [
        "2026-03-03", "2026-03-04"]
    # 같은 설정이어도 주식은 그날까지 본다 — 시장마다 사정이 다르다.
    keep = mod._Truncated(_Inner(), "2026-08-17", "us_stock", "2026-03-04")
    assert len(keep.get_ohlcv("SPY").index) == 3
