"""무제약 그림자 — "제약을 다 풀면?"의 실측 답 (2026-08-19, 사장님 지시).

지켜야 할 약속:
- 목표 비중은 신호 × 배분 그대로다 — 감쇠·게이트·타깃이 하나라도 끼면
  이 실험은 '제약 없는 계좌'가 아니게 된다.
- 무레버리지 상한(총노출 100%)만은 남는다 — 가상이라도 빚은 못 낸다.
- 같은 봉 멱등 · 시세 없는 날 무기록(사다리 규약).
- 최대낙폭을 함께 기록한다 — 이 계좌가 앞서는 구간은 위험을 더 진
  대가일 수 있고, 그 경고 없이 수익만 보여주면 이 실험은 유혹이 된다.
- 본 계좌 배치에 배선돼 있고, 실험 실패가 본 계좌를 못 죽인다.
- 화면이 주의 문구를 장부에서 읽는다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import quant.live.unshackled as U                        # noqa: E402

_MARKS = {"m:A": 100.0, "m:B": 200.0}


def _run(tmp_path, bar, marks=_MARKS,
         weights=None, slices=None):
    return U.run_unshackled(bar=bar,
                            weights=weights or {"m:A": 1.0, "m:B": 1.0},
                            slices=slices or {"m:A": 0.3, "m:B": 0.3},
                            marks=marks, n_total=2, state_dir=str(tmp_path))


def test_the_target_is_signal_times_slice_and_nothing_else(tmp_path):
    _run(tmp_path, "2026-08-19")
    st = json.loads((tmp_path / "unshackled.json").read_text("utf-8"))
    assert st["prev_weights"] == {"m:A": 0.3, "m:B": 0.3}, (
        f"신호×배분 그대로가 아니다: {st['prev_weights']} — 어떤 감쇠가 "
        "끼는 순간 이 실험은 '무제약'이 아니다")


def test_no_leverage_even_here(tmp_path):
    _run(tmp_path, "2026-08-19",
         weights={"m:A": 1.0, "m:B": 1.0}, slices={"m:A": 0.8, "m:B": 0.8})
    st = json.loads((tmp_path / "unshackled.json").read_text("utf-8"))
    gross = sum(abs(v) for v in st["prev_weights"].values())
    assert abs(gross - 1.0) < 1e-6, f"총노출 {gross} — 가상이라도 빚은 못 낸다"


def test_same_bar_is_idempotent(tmp_path):
    _run(tmp_path, "2026-08-19")
    a = json.loads((tmp_path / "unshackled.json").read_text("utf-8"))
    _run(tmp_path, "2026-08-19")
    b = json.loads((tmp_path / "unshackled.json").read_text("utf-8"))
    assert a == b and len(b["history"]) == 1, "같은 봉에 두 번 움직였다"


def test_no_marks_writes_nothing(tmp_path):
    assert _run(tmp_path, "2026-08-19", marks={}) is None
    assert not (tmp_path / "unshackled.json").exists(), (
        "시세 없는 날 기록을 만들었다 — 가짜 평평함")


def test_drawdown_is_tracked_not_hidden(tmp_path):
    _run(tmp_path, "2026-08-19", marks={"m:A": 100.0, "m:B": 200.0})
    _run(tmp_path, "2026-08-20", marks={"m:A": 90.0, "m:B": 180.0})   # -10%
    rec = _run(tmp_path, "2026-08-21", marks={"m:A": 80.0, "m:B": 160.0})
    assert rec["mdd_pct"] < -5.0, (
        f"연속 하락인데 낙폭이 {rec['mdd_pct']}% — 위험이 안 보이는 무제약 "
        "실험은 유혹이지 측정이 아니다")
    pub = U.unshackled_public(str(tmp_path))
    assert pub["worst_mdd_pct"] <= rec["mdd_pct"]
    assert "위험" in pub["note"] and "최대낙폭" in pub["note"]


def test_the_daily_batch_is_wired_and_cannot_be_killed_by_it():
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert "run_unshackled(bar=bar" in src, "일일 배치에 배선이 없다"
    i = src.find("run_unshackled(bar=bar")
    assert "try:" in src[max(0, i - 400):i], (
        "실험이 예외 방벽 없이 본 계좌 경로에 있다")
    assert 'status["unshackled"]' in src, "status.json에 실리지 않는다"


def test_the_screen_reads_the_warning_from_the_ledger():
    index = (ROOT / "docs" / "index.html").read_text("utf-8")
    assert "st.unshackled" in index and "unshackled-card" in index, (
        "화면 카드가 없다 — 실험은 공개돼야 실험이다")
    assert "u.note" in index or "esc(u.note" in index, (
        "주의 문구를 장부에서 읽지 않는다 — 산문에 다시 쓰면 어긋난다")
