"""'이긴 후보 없음'과 '대결이 안 열림'은 다르다 — 보고서가 그 차이를 말한다.

야간 오디션이 아무것도 비교하지 못한 날이 있습니다(후보 대부분이 챔피언과
같은 신호를 내서 대결이 성립하지 않는 경우 — 장부의 `vacuous`). 그 표식은
**사이트에는 실려 있었지만 주간 보고서에는 없었습니다.**

사장님에게 실제로 도착하는 문서는 주간 보고서입니다. 거기서 두 상태가 같아
보이면, "이번 주 승격 0회 — 확실히 나은 후보가 없었다는 뜻(정상)"이라는
문장이 **아무것도 심사하지 못한 주에도 똑같이** 나갑니다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.daily import format_weekly, weekly_summary  # noqa: E402


def _summary(**auditions):
    base = {"runs": 0, "candidates": 0, "promoted": 0, "vacuous": 0}
    base.update(auditions)
    return {"period": ["2026-08-08", "2026-08-14"],
            "markets": {"crypto:BTC/USDT": {
                "week_return_pct": 0.0, "equity": 1_000_000,
                "total_return_pct": 0.0, "n_days": 5,
                "best_day": None, "worst_day": None}},
            "swaps": [], "health": {"auditions": base}}


def test_the_weekly_report_says_the_audition_never_opened():
    text = format_weekly(_summary(runs=35, candidates=700, vacuous=35))
    assert "35회는" in text and "열리지 않았습니다" in text


def test_a_healthy_week_says_nothing_extra():
    """대조군 — 정상인 주에 경고가 붙으면 경고가 배경음이 된다."""
    text = format_weekly(_summary(runs=35, candidates=700, vacuous=0))
    assert "열리지 않았습니다" not in text
    assert "오디션" in text, "정상인 주에도 오디션 줄 자체는 있어야 한다"


def test_the_summary_counts_them_from_the_ledger(tmp_path):
    """장부에 적힌 것을 요약이 실제로 세는가 — 손으로 만든 dict 말고."""
    (tmp_path / "paper").mkdir()
    (tmp_path / "paper" / "crypto_BTC_USDT.json").write_text(json.dumps({
        "market": "crypto", "symbol": "BTC/USDT",
        "history": [{"date": "2026-08-09", "equity": 1_000_000,
                     "return_pct": 0.0},
                    {"date": "2026-08-10", "equity": 1_000_000,
                     "return_pct": 0.0}]}), "utf-8")
    (tmp_path / "retrain_history.jsonl").write_text("\n".join([
        json.dumps({"asof": "2026-08-09", "market": "crypto",
                    "symbol": "BTC/USDT", "promoted": False,
                    "n_candidates": 23, "vacuous": True}),
        json.dumps({"asof": "2026-08-10", "market": "us_stock",
                    "symbol": "SPY", "promoted": False,
                    "n_candidates": 23, "vacuous": False}),
    ]) + "\n", "utf-8")
    a = weekly_summary(str(tmp_path))["health"]["auditions"]
    assert a["runs"] == 2 and a["vacuous"] == 1, a


def test_the_name_is_the_one_the_ledger_writes():
    """판정 이름이 두 개면 언젠가 갈라진다 — 장부가 쓰는 이름 하나만 쓴다."""
    retrain = (ROOT / "quant" / "live" / "retrain.py").read_text("utf-8")
    daily = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert '"vacuous": True' in retrain, "장부가 이 표식을 안 쓴다"
    assert 'rec.get("vacuous")' in daily, "요약이 장부의 이름을 안 읽는다"
