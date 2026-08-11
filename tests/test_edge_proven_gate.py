"""엣지 입증 게이트 — 노출을 키워도 되는지 판정하는 자리 (감사 78).

`edge_proven()`은 목표 변동성을 검증치(연 12%)에서 입증치(연 20%)로 푸는
**단 하나의 관문**이다. 잘못 True를 내면 통계로 입증되지 않은 전략에
노출을 키운다 — 8만원 계좌에서 가장 비싼 실수다.

그런데 커버리지에서 **25줄 중 22줄이 미실행**이었다. 기존 검사
(test_settings_contract)는 "미입증인데 잠금을 푸는가"만 봤고, 그건
`edge_proven`이 항상 False를 내는 지금 상태에서는 **입력이 무엇이든
초록**이다. 즉 **판정 로직 자체는 한 번도 검사된 적이 없었다.**

여기서는 가짜 장부를 만들어 두 관문을 각각 통과·차단시켜 본다. 핵심은
**"운 좋은 승자"를 거절하는가**다 — 점추정이 50%를 넘었다는 이유로 노출을
키우면, 우리가 그토록 걸러낸 그 실수를 우리가 저지르는 것이다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.risk import portfolio_vol as PV          # noqa: E402


def _history(n_pairs: int, hit_rate: float) -> list[dict]:
    """(prob_up, 다음날 방향) 짝이 n개 나오도록 장부를 만든다.

    맞힌 짝은 prob_up>0.5 & 상승, 틀린 짝은 prob_up>0.5 & 하락으로 만든다.
    """
    hits = round(n_pairs * hit_rate)
    price = 100.0
    hist = []
    for i in range(n_pairs):
        up = i < hits                       # 앞쪽 hits개를 적중으로
        hist.append({"prob_up": 0.6, "price": price})
        price = price * 1.01 if up else price * 0.99
    hist.append({"prob_up": 0.6, "price": price})    # 마지막 짝을 닫는다
    return hist


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    """가짜 장부 + 판정 시계를 세팅하고 edge_proven을 돌린다."""

    def _run(days=999, target_days=90, n_pairs=0, hit_rate=0.6,
             gen=True, extra_files=()):
        paper = tmp_path / "paper"
        paper.mkdir(exist_ok=True)
        if n_pairs:
            (paper / "crypto_BTC.json").write_text(
                json.dumps({"market": "crypto",
                            "history": _history(n_pairs, hit_rate)}),
                encoding="utf-8")
        for name, payload in extra_files:
            (paper / name).write_text(json.dumps(payload), encoding="utf-8")

        import quant.live.daily as dl
        info = ({"days": days, "target_days": target_days,
                 "feature_set": "fs8"} if gen else None)
        monkeypatch.setattr(dl, "_generation_info", lambda *_a, **_k: info)
        return PV.edge_proven(str(tmp_path))

    return _run


# ── 관문 ① 판정 시계 ────────────────────────────────────────────

def test_clock_not_finished_blocks_everything(ledger):
    """시계가 안 끝났으면 적중률이 아무리 좋아도 미입증이다."""
    ok, why = ledger(days=89, target_days=90, n_pairs=400, hit_rate=0.9)
    assert ok is False
    assert "판정 시계" in why and "89일차/90일" in why


def test_missing_generation_info_is_not_proven(ledger):
    """세대 정보가 없으면 '모른다'이지 '입증'이 아니다."""
    ok, why = ledger(gen=False)
    assert ok is False and "정보 없음" in why


# ── 관문 ② 통계 ────────────────────────────────────────────────

def test_thin_sample_blocks_even_with_perfect_hits(ledger):
    ok, why = ledger(n_pairs=PV.MIN_EDGE_SAMPLES - 1, hit_rate=1.0)
    assert ok is False
    assert f"{PV.MIN_EDGE_SAMPLES}" in why and "표본 부족" in why


def test_a_lucky_winner_is_refused(ledger):
    """점추정 55%는 50%를 넘지만 **동전과 구별되지 않는다.**

    이게 이 게이트의 존재 이유다. 여기서 True가 나오면 우리가 그토록
    걸러낸 '운 좋은 승자'가 되어 노출을 키운다.
    """
    n = PV.MIN_EDGE_SAMPLES
    ok, why = ledger(n_pairs=n, hit_rate=0.55)
    assert ok is False, f"소표본 55%를 입증으로 판정했다 — {why}"
    assert "동전과 구별 불가" in why


def test_a_real_edge_is_recognized(ledger):
    """반대로 진짜 엣지를 영원히 막으면 그것도 결함이다."""
    ok, why = ledger(n_pairs=400, hit_rate=0.62)
    assert ok is True, f"뚜렷한 엣지를 입증으로 인정하지 않았다 — {why}"
    assert "50%" in why


def test_exactly_at_the_boundary_stays_closed(ledger):
    """하한이 정확히 50%면 열지 않는다(부등호가 뒤집히는 것을 막는다)."""
    ok, why = ledger(n_pairs=PV.MIN_EDGE_SAMPLES, hit_rate=0.50)
    assert ok is False and "동전과 구별 불가" in why


# ── 안전 기본값 ────────────────────────────────────────────────

def test_a_broken_ledger_fails_closed(ledger, tmp_path, monkeypatch):
    """장부가 깨져도 '입증'으로 넘어가면 안 된다 — 모를 때는 잠근다."""
    import quant.live.daily as dl
    monkeypatch.setattr(dl, "_generation_info",
                        lambda *_a, **_k: (_ for _ in ()).throw(
                            RuntimeError("장부 손상")))
    ok, why = PV.edge_proven(str(tmp_path))
    assert ok is False and "판정 불가" in why


def test_unreadable_paper_file_is_skipped_not_fatal(ledger, tmp_path):
    """읽을 수 없는 장부 하나가 판정 전체를 죽이면 안 된다."""
    ok, _ = ledger(n_pairs=400, hit_rate=0.62)
    (tmp_path / "paper" / "broken.json").write_text("{{{", encoding="utf-8")
    ok2, why2 = ledger(n_pairs=400, hit_rate=0.62)
    assert ok2 == ok, f"깨진 파일 하나가 판정을 바꿨다 — {why2}"


def test_portfolio_ledger_is_not_double_counted(ledger):
    """통합 계좌 장부는 종목 장부의 합이라 같이 세면 표본이 부풀려진다."""
    n = PV.MIN_EDGE_SAMPLES - 1
    plain, _ = ledger(n_pairs=n, hit_rate=1.0)
    assert plain is False                       # 기준선: 표본 부족

    withport, why = ledger(
        n_pairs=n, hit_rate=1.0,
        extra_files=[("portfolio_ALL.json",
                      {"market": "portfolio", "history": _history(n, 1.0)})])
    assert withport is False, (
        "통합 계좌 장부까지 세어 표본이 부풀려졌다 — 같은 매매를 두 번 "
        f"센 것이다 ({why})")


# ── 게이트가 실제로 목표 변동성을 묶는가 ────────────────────────

def test_unproven_edge_actually_caps_the_target(ledger, tmp_path, monkeypatch):
    """판정이 행동으로 이어지는가 — 미입증이면 검증 목표를 넘지 못한다."""
    import quant.live.daily as dl
    monkeypatch.setattr(dl, "_generation_info",
                        lambda *_a, **_k: {"days": 1, "target_days": 90,
                                           "feature_set": "fs8"})
    monkeypatch.setattr("quant.utils.settings.load_settings",
                        lambda *_a, **_k: {"portfolio_target_vol": 0.50})
    target, proven, _why = PV.target_vol_now(str(tmp_path))
    assert proven is False
    assert target <= PV.VERIFY_TARGET_VOL, (
        f"미입증인데 목표 변동성이 {target:.0%} — 설정 실수가 그대로 "
        "노출이 된다")
