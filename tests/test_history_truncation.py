"""저장 상한(HISTORY_CAP)에 걸린 뒤에도 화면의 숫자가 뜻을 유지하는가.

2026-08-11 감사 ㊿. 감시 대시보드는 총손익을 `equity[-1]/equity[0]-1`로,
최대낙폭을 남아 있는 equity 배열만 훑어 계산했다. 라이브 러너는 무한
성장을 막으려 history를 최근 5000개로 자르는데, 자르는 순간 이 두 숫자의
뜻이 조용히 바뀐다:

  · 총손익 → '잘린 시점 이후 손익'이 되는데 라벨은 그대로 "손익(PnL)"
  · 최대낙폭 → 가장 아팠던 구간이 밀려나면 **저절로 좋아진다**

시간이 지나면 스스로 개선되는 위험 지표는 지표가 아니라 위안이다.
게다가 /monitor의 5초 폴링 JS가 같은 계산을 다시 하므로, 서버를 고쳐도
JS를 고치지 않으면 5초 뒤 잘못된 값으로 덮어써진다(같은 결함의 재발
경로 — 예전에 한 번 당했다).

계약:
  ① fold_history는 자른 구간의 손익·낙폭을 요약에 접어 넣는다(등가 계산)
  ② 대시보드는 요약을 seed로 써서 전 기간 총손익·최대낙폭을 보여준다
  ③ /monitor의 JS도 같은 seed를 쓴다(서버만 고치면 5초 뒤 덮어써진다)
  ④ 세 러너(engine·multi·autolearn) 모두 요약을 상태에 싣는다
  ⑤ '거래횟수'는 스냅샷에 실린 최근 20건이 아니라 누적 건수를 쓴다
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.reporting.dashboard import build_dashboard_html  # noqa: E402
from quant.utils.jsonio import fold_history  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _curve() -> list[dict]:
    """100 → 200 → 50(-75% 낙폭) → 120 으로 끝나는 자본 곡선."""
    eq = ([100.0 + i for i in range(100)]          # 100 → 199
          + [200.0]
          + [200.0 - 1.5 * i for i in range(100)]  # 200 → 51.5 (최악 구간)
          + [50.0 + 0.7 * i for i in range(100)])  # 회복
    return [{"time": f"t{i}", "equity": e, "weight": 0.0} for i, e in enumerate(eq)]


def _walk(equity: list[float]) -> tuple[float, float]:
    """전 구간을 그대로 훑은 (총손익, 최대낙폭) — 정답."""
    peak, dd = equity[0], 0.0
    for e in equity:
        peak = max(peak, e)
        dd = min(dd, e / peak - 1.0)
    return equity[-1] / equity[0] - 1.0, dd


# ── ① 요약이 잘린 구간을 정확히 대신한다 ──────────────────────


def test_fold_history_is_equivalent_to_full_walk():
    hist = _curve()
    truth_pnl, truth_dd = _walk([h["equity"] for h in hist])

    # 한 번에 자르든, 조금씩 여러 번 자르든 결과가 같아야 한다.
    for cap in (10, 50, 137, 299):
        kept, summ = fold_history(list(hist), cap=cap)
        assert len(kept) == cap
        assert summ["dropped"] == len(hist) - cap
        peak, dd = summ["peak"], summ["max_drawdown"]
        for h in kept:
            peak = max(peak, h["equity"])
            dd = min(dd, h["equity"] / peak - 1.0)
        pnl = kept[-1]["equity"] / summ["start"] - 1.0
        assert abs(pnl - truth_pnl) < 1e-12
        assert abs(dd - truth_dd) < 1e-12


def test_fold_history_accumulates_across_repeated_calls():
    """매 사이클 호출되므로 여러 번 접어도 최초값·최고점이 살아 있어야 한다."""
    hist = _curve()
    truth_pnl, truth_dd = _walk([h["equity"] for h in hist])
    kept: list[dict] = []
    summ: dict = {}
    for rec in hist:                      # 러너가 한 건씩 append 하는 흐름
        kept.append(rec)
        kept, summ = fold_history(kept, summ, cap=20)
    peak, dd = summ["peak"], summ["max_drawdown"]
    for h in kept:
        peak = max(peak, h["equity"])
        dd = min(dd, h["equity"] / peak - 1.0)
    assert abs(kept[-1]["equity"] / summ["start"] - 1.0 - truth_pnl) < 1e-12
    assert abs(dd - truth_dd) < 1e-12


def test_fold_history_is_noop_below_cap():
    hist = _curve()[:5]
    kept, summ = fold_history(list(hist), cap=100)
    assert kept == hist and summ == {}


# ── ② 대시보드가 요약을 실제로 쓴다 ───────────────────────────


def test_dashboard_reports_full_period_drawdown_after_truncation():
    hist = _curve()
    truth_pnl, truth_dd = _walk([h["equity"] for h in hist])
    kept, summ = fold_history(list(hist), cap=30)

    # 요약 없이(=예전 동작) 그리면 낙폭이 '좋아져' 있어야 한다 — 결함의 재현
    naive = build_dashboard_html({"history": kept, "orders": []})
    assert f"{truth_dd:.2%}" not in naive

    fixed = build_dashboard_html(
        {"history": kept, "history_summary": summ, "orders": []})
    assert f"{truth_dd:.2%}" in fixed          # 전 기간 최대낙폭
    assert f"{truth_pnl:+.2%}" in fixed        # 전 기간 총손익
    # 그래프가 잘려 있다는 사실을 화면에 적는다(조용한 표본 축소 금지)
    assert "저장 상한으로 생략" in fixed


def test_dashboard_without_summary_still_works():
    """옛 상태 파일(요약 없음)도 예전처럼 동작해야 한다(하위 호환)."""
    html = build_dashboard_html(
        {"history": [{"equity": 100.0}, {"equity": 110.0}], "orders": []})
    assert "+10.00%" in html


# ── ③ /monitor JS도 같은 seed를 쓴다 ──────────────────────────


def test_monitor_js_seeds_from_summary():
    src = (ROOT / "quant" / "web" / "app.py").read_text(encoding="utf-8")
    assert "s.history_summary" in src, "JS가 요약을 안 쓰면 5초 뒤 덮어쓴다"
    assert "sm.max_drawdown" in src and "sm.peak" in src and "sm.start" in src
    # 예전의 '배열 첫 값에서 시작' 계산이 남아 있으면 안 된다
    assert "st=eq[0], pnl=st? cur/st-1:0" not in src
    assert "let peak=st, dd=0;" not in src


# ── ④ 세 러너 모두 요약을 싣는다 ──────────────────────────────


def test_all_runners_persist_history_summary():
    for name in ("engine", "multi", "autolearn"):
        src = (ROOT / "quant" / "live" / f"{name}.py").read_text(encoding="utf-8")
        assert "fold_history(" in src, f"{name}: 요약 없이 자르고 있다"
        assert '"history_summary": self.history_summary' in src, name
        assert "cap_history(self.history)" not in src, f"{name}: 옛 방식 잔존"


# ── ⑤ 거래횟수는 누적 건수 ────────────────────────────────────


def test_trade_count_is_cumulative_not_snapshot_slice():
    html = build_dashboard_html(
        {"history": [{"equity": 100.0}, {"equity": 101.0}],
         "orders": [{"side": "buy"}] * 20, "order_count": 4137})
    assert "4,137" in html or "4137" in html
    for name in ("engine", "multi", "autolearn"):
        src = (ROOT / "quant" / "live" / f"{name}.py").read_text(encoding="utf-8")
        assert '"order_count"' in src, f"{name}: 누적 주문 건수 미기록"
    src = (ROOT / "quant" / "web" / "app.py").read_text(encoding="utf-8")
    assert "s.order_count" in src
