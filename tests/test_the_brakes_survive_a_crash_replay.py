"""위기 재생이 **실전 브레이크 그대로**를 과거 위기에 통과시키는가.

이 검사가 지키는 것:
  ① 재생은 브레이크를 **다시 적지 않는다** — 실전 함수를 import 한다.
     복사본을 검증하면 복사본만 안전해진다(FROZEN_IDEAS ①).
  ② 합성 폭락에서 킬스위치가 **실제로 발동해 기록에 남고**, 낙폭이
     브레이크 없는 쪽보다 얕아진다 — 값으로 확인한다.
  ③ 조용한 시장에서는 브레이크가 울리지 않는다(매일 울리는 경보는 꺼진
     경보다).
  ④ 산출물은 반드시 kind="simulation" 표식과 정직한 한계를 단다 —
     시뮬레이션이 실측처럼 읽히는 순간 이 제품의 정체성이 무너진다.
  ⑤ 이 장치가 실제 배치에 **배선**돼 있다 — 만들어 두고 아무도 안 돌리는
     계측기는 이 저장소가 반복해서 잡아 온 병이다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.risk import replay as R  # noqa: E402

SRC = (ROOT / "quant" / "risk" / "replay.py").read_text("utf-8")


def _closes(phase_rets: list[tuple[int, float]], n_sym: int = 3,
            seed: int = 7) -> dict[str, pd.Series]:
    """구간별 (일수, 평균 수익률)로 합성 가격을 만든다 — 약간의 잡음 포함."""
    rng = np.random.default_rng(seed)
    rets = np.concatenate([
        rng.normal(mu, 0.004, size=days) for days, mu in phase_rets])
    idx = pd.date_range("2024-01-01", periods=len(rets), freq="D")
    out = {}
    for j in range(n_sym):
        noise = rng.normal(0.0, 0.002, size=len(rets))
        out[f"crypto:S{j}/USDT"] = pd.Series(
            100.0 * np.cumprod(1.0 + rets + noise), index=idx)
    return out


CRASH = [(80, 0.001), (12, -0.03), (120, 0.004)]     # 평온 → 폭락 → 회복
QUIET = [(200, 0.0004)]                              # 내내 평온


# ── ① 브레이크를 다시 적지 않는다 ──────────────────────────────

def test_the_replay_borrows_the_real_brakes():
    assert "from quant.live.daily import _kill_switch_scale" in SRC, (
        "재생이 실전 킬스위치를 안 쓴다 — 복사본을 검증하면 복사본만 안전하다")
    assert "from quant.risk.portfolio_vol import" in SRC and "vol_scale" in SRC


def test_no_kill_switch_thresholds_are_restated():
    """-25%·-15% 문턱이 여기 다시 적히면 실전과 갈라지는 날이 온다."""
    body = SRC.split('"""', 2)[-1]
    for banned in ("-0.25", "-0.15"):
        assert banned not in body, (
            f"킬스위치 문턱({banned})이 재생에 다시 적혀 있다")


# ── ② 폭락에서 실제로 작동하는가 ───────────────────────────────

def test_a_crash_triggers_the_kill_switch_and_it_is_recorded():
    rep = R.replay_risk_layer(_closes(CRASH))
    assert rep is not None
    assert rep["kill_switch_episodes"], (
        "12일간 -3%/일 폭락에도 킬스위치 발동 기록이 없다 — 브레이크가 "
        "장식이거나 기록이 장식이다")
    ep = rep["kill_switch_episodes"][0]
    assert ep["dd_at_trigger"] <= -0.15, ep
    assert ep["min_scale"] <= 0.5, ep


def test_the_brakes_actually_cut_the_drawdown():
    """브레이크 있는 쪽 낙폭이 없는 쪽보다 **실제로** 얕아야 한다."""
    rep = R.replay_risk_layer(_closes(CRASH))
    assert rep["braked"]["mdd"] > rep["raw"]["mdd"], (
        f"브레이크를 밟았는데 낙폭이 같거나 깊다: "
        f"braked {rep['braked']['mdd']} vs raw {rep['raw']['mdd']} — "
        "브레이크가 자산 곡선에 반영되지 않고 있다")


def test_exposure_never_exceeds_the_no_leverage_line():
    rep = R.replay_risk_layer(_closes(CRASH))
    assert rep["mean_exposure"] <= 1.0 + 1e-9, (
        f"평균 노출 {rep['mean_exposure']} — 레버리지 금지선(100%)을 넘었다")


# ── ③ 조용한 시장에서는 조용하다 ───────────────────────────────

def test_a_quiet_market_fires_no_episodes():
    rep = R.replay_risk_layer(_closes(QUIET))
    assert rep["kill_switch_episodes"] == [], (
        f"평온한 시장에서 킬스위치가 울렸다: {rep['kill_switch_episodes']} — "
        "매일 울리는 경보는 꺼진 경보다")


# ── ④ 시뮬레이션 표식과 정직한 한계 ────────────────────────────

def test_the_output_is_labeled_simulation():
    rep = R.replay_risk_layer(_closes(QUIET))
    assert rep["kind"] == "simulation", (
        "시뮬레이션 표식이 없다 — 이 숫자가 실측처럼 읽히면 선택 편향 없는 "
        "공개 실험이라는 정체성이 무너진다")


def test_the_honest_limits_travel_with_the_numbers():
    rep = R.replay_risk_layer(_closes(QUIET))
    text = " ".join(rep["honest_limits"])
    for word in ("비용", "생존", "환율"):
        assert word in text, f"정직한 한계에 '{word}'가 빠졌다: {text}"


# ── ⑤ 배선 — 만들어 두고 안 돌리면 없는 장치다 ─────────────────

def test_the_nightly_batch_actually_runs_it_and_commits_the_result():
    wf = (ROOT / ".github" / "workflows" / "nightly-validate.yml"
          ).read_text("utf-8")
    assert "scripts/risk_report.py" in wf, (
        "위험 리포트가 어느 배치에도 배선돼 있지 않다 — 만들어 두고 아무도 "
        "안 돌리는 계측기는 이 저장소가 반복해서 잡아 온 병이다")
    assert "docs/risk.json" in wf, (
        "리포트를 만들고 커밋하지 않는다 — 아티팩트는 만료되고, 만료되는 "
        "증거는 감시가 아니다")


def test_the_site_no_longer_shows_the_card_by_owner_decision():
    """공개 화면의 위기 재생 카드는 **사장님 지시(2026-08-18)로 내렸다**.

    내린 것은 표시뿐이다 — 데이터(docs/risk.json)와 야간 갱신 배선은
    그대로 돈다(위의 배선 검사와 아래 데이터 검사가 계속 지킨다).
    카드를 다시 올리려면 이 검사를 **의도적으로** 되돌려야 한다 —
    화면 구성이 소리 없이 바뀌는 것을 막는 자물쇠다.
    """
    index = (ROOT / "docs" / "index.html").read_text("utf-8")
    assert "risk.json" not in index, (
        "내리기로 한 위기 재생 카드가 첫 화면에 다시 나타났다 — 의도한 "
        "복원이면 이 검사를 함께 고치라")


def test_the_committed_report_is_a_simulation_and_parses():
    """저장소에 실제로 커밋된 첫 리포트 — 사실 고정."""
    import json
    p = ROOT / "docs" / "risk.json"
    assert p.exists(), "docs/risk.json이 없다 — 사이트 카드가 영원히 '불러오는 중'이다"
    data = json.loads(p.read_text("utf-8"))
    assert data["kind"] == "simulation"
    if data.get("replay"):
        assert data["replay"]["braked"]["mdd"] >= data["replay"]["raw"]["mdd"]


# ── 스냅샷 로더 — 재생의 입력이 진짜인가 ───────────────────────

def test_the_loader_stitches_snapshots_into_deeper_history(tmp_path):
    """같은 종목의 여러 스냅샷을 이어 **가장 깊은 역사**를 만든다.

    2026-03 스냅샷(800봉)과 최근 스냅샷(300봉)을 이으면 코인이 2023년까지
    닿는다 — 이 이어붙이기가 없으면 재생은 최근 300일만 보고 '위기 없음'을
    보고한다.
    """
    import gzip
    for day, start in (("2026-03-04", "2023-01-01"),
                       ("2026-08-15", "2025-06-01")):
        d = tmp_path / day
        d.mkdir()
        idx = pd.date_range(start, periods=100, freq="D")
        csv = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0,
                            "close": np.linspace(100, 110, 100),
                            "volume": 1.0}, index=idx).to_csv()
        with gzip.open(d / "crypto_BTC_USDT.csv.gz", "wt") as fh:
            fh.write(csv)
    closes = R.load_snapshot_closes(str(tmp_path))
    assert "crypto:BTC/USDT" in closes
    s = closes["crypto:BTC/USDT"]
    assert str(s.index[0].date()) == "2023-01-01"
    assert str(s.index[-1].date()) == "2025-09-08"
    assert len(s) == 200, f"이어붙이기가 안 됐다: {len(s)}봉"
