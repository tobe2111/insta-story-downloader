"""장부 무결성 계약 검사 — 저장된 기록 자체를 검사한다.

배경(2026-08-11 감사): 한국주식 6종목의 기록 배열이 08-05 → **08-07 →
08-06** → 08-10 순으로 어긋나 있었다. 원인은 데이터 소스가 한때 아직 닫히지도
않은 08-07 봉을 먼저 내보낸 것(그래서 _drop_unclosed를 추가했다). 값 자체는
그날의 진짜 기록이지만 배열 순서가 뒤집혀, '직전 날'을 참조하는 계산
(하루치 수익률·낙폭·최고/최악일)이 엉뚱한 날을 전날로 잡는다.

저장된 값은 건드리지 않는다 — "과거를 고치지 않는다"가 먼저다. 대신
읽는 쪽이 시간순으로 정렬해 계산하고(chrono), 새 기록은 시간순 자리에
삽입한다. 이 테스트는 그 계약과 장부 자체의 정합을 함께 지킨다.
"""
from __future__ import annotations

import glob
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.live.daily import (  # noqa: E402
    chrono,
    day_return_pct,
    twr_index,
)

ROOT = Path(__file__).resolve().parent.parent
STATES = sorted(glob.glob(str(ROOT / "state" / "paper" / "*.json")))


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── ① 계약: 읽는 쪽이 순서를 바로잡는다 ───────────────────────


def test_chrono_sorts_without_changing_values():
    h = [{"date": "2026-08-07", "equity": 2.0},
         {"date": "2026-08-06", "equity": 1.0}]
    out = chrono(h)
    assert [r["date"] for r in out] == ["2026-08-06", "2026-08-07"]
    assert sorted(r["equity"] for r in out) == [1.0, 2.0]   # 값은 그대로
    assert h[0]["date"] == "2026-08-07"                     # 원본 불변


def test_day_return_uses_the_date_previous_day():
    """배열의 앞 원소가 아니라 '날짜상 전날'을 기준으로 삼아야 한다."""
    scrambled = [{"date": "2026-08-05", "equity": 100.0},
                 {"date": "2026-08-07", "equity": 110.0},
                 {"date": "2026-08-06", "equity": 100.0}]
    # 날짜순이면 마지막은 08-07(110), 전날은 08-06(100) → +10%
    assert day_return_pct(scrambled, [], start_cash=100.0) == 10.0


def test_index_series_follows_date_order():
    scrambled = [{"date": "2026-08-07", "equity": 120.0},
                 {"date": "2026-08-06", "equity": 100.0}]
    idx = twr_index(scrambled, [], start_cash=100.0)
    assert idx[0] < idx[1]                     # 08-06 → 08-07 순서


def test_new_records_are_inserted_in_order():
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert src.count('cap_history(chrono(st["history"] + [record]))') >= 2


# ── ② 실제 장부의 정합 ────────────────────────────────────────


def test_no_duplicate_dates_in_any_ledger():
    for path in STATES:
        hist = _load(path).get("history") or []
        dates = [r["date"] for r in hist]
        dup = [d for d, c in Counter(dates).items() if c > 1]
        assert not dup, f"{Path(path).name}: 같은 날 중복 기록 {dup}"


def test_principal_and_pnl_agree():
    for path in STATES:
        for r in _load(path).get("history") or []:
            if r.get("principal") and r.get("pnl") is not None:
                assert abs((r["equity"] - r["principal"]) - r["pnl"]) < 0.02, (
                    f"{Path(path).name} {r['date']}: 원금+손익 ≠ 자산")


def test_return_pct_matches_principal():
    for path in STATES:
        for r in _load(path).get("history") or []:
            if r.get("principal") and r.get("return_pct") is not None:
                calc = (r["equity"] / r["principal"] - 1) * 100
                assert abs(calc - r["return_pct"]) < 0.011, (
                    f"{Path(path).name} {r['date']}: 표시 {r['return_pct']} "
                    f"vs 계산 {calc:.4f}")


def test_no_implausible_equity_jumps():
    """하루 ±50% 초과 변동은 데이터 사고를 의심해야 한다(입금은 제외)."""
    for path in STATES:
        st = _load(path)
        flows = {d["date"] for d in (st.get("deposits") or [])}
        hist = chrono(st.get("history") or [])
        for a, b in zip(hist, hist[1:]):
            if b["date"] in flows or not a.get("equity"):
                continue
            ch = b["equity"] / a["equity"] - 1
            assert abs(ch) < 0.5, (
                f"{Path(path).name} {b['date']}: 자산 {ch * 100:+.0f}% 급변")


def test_every_record_carries_an_accounting_tag():
    """어느 회계 기준의 숫자인지 영구히 구분된다 — 사이트의 약속."""
    for path in STATES:
        hist = _load(path).get("history") or []
        recent = [r for r in hist if r.get("date", "") >= "2026-08-05"]
        for r in recent:
            assert r.get("accounting"), (
                f"{Path(path).name} {r['date']}: 회계 기준 태그 없음")
