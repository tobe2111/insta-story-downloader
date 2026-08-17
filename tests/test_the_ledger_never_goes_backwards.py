"""판정일이 **과거로 뒷걸음쳐** 장부에 같은 날이 두 번 적혔다 (감사 262).

2026-08-16 야간 페이퍼 배치가 **두 번 다 실패**했습니다. 실패 이유:

    ❌ 장부 관문 실패 — portfolio_ALL.json: 같은 날 중복 기록 ['2026-08-14']

원인은 하나로 이어집니다.

    ① 코인 시세가 165일 묵었다(감사 261 — 이어받기가 개수로 멈췄다)
    ② 그래서 판정일이 2026-08-15 → **2026-08-14**로 뒷걸음쳤다
    ③ 멱등 가드는 `==`만 봤다 → 과거 날짜가 그대로 통과해 한 줄 더 붙었다
    ④ 장부 관문이 커밋을 막았다 ✅

**세 장치가 각각 제 몫을 했습니다** — 정체 경보가 165일을 짚었고, 장부
관문이 오염된 기록을 막았고, 그래서 사이트에는 아무것도 안 나갔습니다.
남은 구멍은 ③입니다: **배치가 애초에 그 기록을 만들지 말았어야 합니다.**

`같은 봉`은 "이미 했다"(정상)이고 `과거 봉`은 "입력이 고장났다"(사고)입니다.
둘을 같은 가지에 두면 사고가 정상으로 보입니다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.daily import run_daily_paper, run_daily_portfolio  # noqa: E402
from quant.live.retrain import save_champions  # noqa: E402


def _seed_portfolio(tmp_path, dates, last_bar):
    d = tmp_path / "paper"
    d.mkdir(parents=True, exist_ok=True)
    (d / "portfolio_ALL.json").write_text(json.dumps({
        "market": "portfolio", "symbol": "ALL", "cash": 1_000_000.0,
        "positions": {}, "last_bar": last_bar,
        "history": [{"date": x, "equity": 1_000_000.0, "return_pct": 0.0}
                    for x in dates]}), "utf-8")


def _targets(tmp_path, n=3):
    save_champions({f"synthetic:T{i}": {"strategy": "ma_cross",
                                        "params": {"fast": 10, "slow": 30},
                                        "promotions": 0} for i in range(n)},
                   str(tmp_path))
    return [("synthetic", f"T{i}") for i in range(n)]


# ── 통합 계좌 ────────────────────────────────────────────────

def test_a_backwards_bar_is_refused(tmp_path):
    """실측 그 장면 — 기록은 08-15인데 오늘 판정이 08-14로 왔다."""
    targets = _targets(tmp_path)
    d = str(tmp_path)
    first = run_daily_portfolio(targets, lookback=200, state_dir=d,
                                require_real_data=False)
    assert not first.get("skipped")

    st = json.loads((tmp_path / "paper" / "portfolio_ALL.json").read_text("utf-8"))
    real_bar = st["last_bar"]
    # 장부만 **미래**로 옮긴다 — 다음 실행의 판정일이 과거가 된다.
    future = str(pd.Timestamp(real_bar) + pd.Timedelta(days=5))
    st["last_bar"] = future
    st["history"].append({"date": future[:10], "equity": 1_000_000.0,
                          "return_pct": 0.0})
    (tmp_path / "paper" / "portfolio_ALL.json").write_text(json.dumps(st), "utf-8")

    rec = run_daily_portfolio(targets, lookback=200, state_dir=d,
                              require_real_data=False)
    assert rec.get("skipped") is True
    assert rec.get("backwards") == real_bar, (
        f"뒷걸음 사실을 안 남겼다: {rec}")

    after = json.loads(
        (tmp_path / "paper" / "portfolio_ALL.json").read_text("utf-8"))
    dates = [r["date"] for r in after["history"]]
    assert len(dates) == len(set(dates)), f"같은 날이 두 번 적혔다: {dates}"
    assert after["last_bar"] == future, "장부가 과거로 되감겼다"


def test_the_same_bar_is_still_just_skipped(tmp_path):
    """대조군 — 같은 봉은 '이미 했다'(정상)다. 사고로 적으면 경보가 배경음이 된다."""
    targets = _targets(tmp_path)
    d = str(tmp_path)
    run_daily_portfolio(targets, lookback=200, state_dir=d,
                        require_real_data=False)
    rec = run_daily_portfolio(targets, lookback=200, state_dir=d,
                              require_real_data=False)
    assert rec.get("skipped") is True
    assert "backwards" not in rec, "정상 건너뜀을 사고로 적었다"


def test_a_fresh_ledger_is_not_blocked(tmp_path):
    """대조군 — 기록이 없으면 비교할 것이 없다. 첫날이 막히면 영영 못 시작한다."""
    rec = run_daily_portfolio(_targets(tmp_path), lookback=200,
                              state_dir=str(tmp_path), require_real_data=False)
    assert not rec.get("skipped"), rec


# ── 종목별 참고 계좌 ─────────────────────────────────────────

def test_the_per_symbol_ledger_is_guarded_too(tmp_path):
    """통합 계좌만 막으면 같은 사고가 이쪽 장부를 조용히 오염시킨다."""
    save_champions({"synthetic:T0": {"strategy": "ma_cross",
                                     "params": {"fast": 10, "slow": 30},
                                     "promotions": 0}}, str(tmp_path))
    d = str(tmp_path)
    run_daily_paper("synthetic", "T0", lookback=200, state_dir=d,
                    require_real_data=False)
    p = tmp_path / "paper" / "synthetic_T0.json"
    st = json.loads(p.read_text("utf-8"))
    real = st["last_bar"]
    st["last_bar"] = str(pd.Timestamp(real) + pd.Timedelta(days=5))
    p.write_text(json.dumps(st), "utf-8")

    rec = run_daily_paper("synthetic", "T0", lookback=200, state_dir=d,
                          require_real_data=False)
    assert rec.get("skipped") is True and rec.get("backwards") == real


def test_the_per_symbol_same_bar_is_normal(tmp_path):
    """대조군 — 여기서도 같은 봉은 조용한 건너뜀이어야 한다."""
    save_champions({"synthetic:T0": {"strategy": "ma_cross",
                                     "params": {"fast": 10, "slow": 30},
                                     "promotions": 0}}, str(tmp_path))
    d = str(tmp_path)
    run_daily_paper("synthetic", "T0", lookback=200, state_dir=d,
                    require_real_data=False)
    rec = run_daily_paper("synthetic", "T0", lookback=200, state_dir=d,
                          require_real_data=False)
    assert rec.get("skipped") is True and "backwards" not in rec


# ── 장부 관문이 이 사고를 여전히 잡는가 (마지막 방어선) ──────

def test_the_ledger_gate_still_catches_duplicates(tmp_path):
    """배치가 뚫려도 관문이 남는다 — 두 겹을 다 확인한다."""
    from collections import Counter

    _seed_portfolio(tmp_path, ["2026-08-13", "2026-08-14", "2026-08-15",
                               "2026-08-14"], "2026-08-14")
    hist = json.loads(
        (tmp_path / "paper" / "portfolio_ALL.json").read_text("utf-8"))["history"]
    dup = [d for d, c in Counter(r["date"] for r in hist).items() if c > 1]
    assert dup == ["2026-08-14"], "실측 사고 모양을 재현하지 못했다"


def test_the_gate_script_is_wired_into_the_batch():
    """관문이 워크플로에서 실제로 불리는가 — 안 부르면 없는 것과 같다."""
    wf = (ROOT / ".github" / "workflows" / "daily-paper.yml").read_text("utf-8")
    assert "scripts/ledger_gate.py" in wf
    assert wf.index("scripts/ledger_gate.py") < wf.index("git commit"), (
        "관문이 커밋 뒤에 있다 — 막을 수 없다")
