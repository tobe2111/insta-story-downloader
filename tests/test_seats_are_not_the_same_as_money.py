"""의석 수와 **돈의 분산**은 다른 이야기다 (2026-08-19, 실측에서 나옴).

사장님 질문("상위 프로그램 수준에 도달했나")에 답하려고 의회를 실측하다
나온 것이다. 장부는 이렇게 말하고 있었다:

    39석 · 서로 다른 전략 11종 · 그런데 **자금의 72.9%가 한 스펙**

원인은 코드에서 두 갈래로 갈린다:
  · 의석을 **여는 문**은 상관을 본다(다양성 의석: 상관 0.5 미만만 통과)
  · 의석 **크기를 정하는 규칙**은 수익만 본다(softmax(홀드아웃 수익))

그래서 다르게 들어온 의원이 시간이 지나면 얇아진다. 포트폴리오 이론은
반대로 말한다 — 기대수익이 비슷하고 상관이 낮으면 비중을 더 줘야 위험이
준다.

⚠️ 그런데 이걸 지금 본 계좌에 적용하면 **판정 시계가 리셋된다**('얼마를
   사는가'는 세대 축이다). 사장님 지시가 "무슨 수정을 해도 판정 시간은
   리셋되면 안 된다"이므로, 이 단계에서는 **재기만 한다.**

지켜야 할 약속:
- 상관까지 본 비중을 계산할 수 있고, 못 재면 None이라고 말한다(0 아님).
- 그 비중은 **기록일 뿐** 매매 비중(weight)을 바꾸지 않는다.
- 의석 현황에 '가장 큰 전략의 자금 점유'가 함께 실린다 — 의석 수만
  말하면 절반만 말하는 것이다.
- 공개 페이지가 그 숫자를 장부에서 읽는다.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live import parliament as P                     # noqa: E402


def _series(vals):
    return pd.Series(vals, index=pd.date_range("2026-01-01", periods=len(vals),
                                               freq="D"))


def test_the_grid_only_walks_the_simplex():
    combos = list(P._simplex_grid(3, P.DIVERSITY_STEP))
    assert combos, "격자가 비어 있다"
    for w in combos:
        assert abs(sum(w) - 1.0) < 1e-9, f"합이 1이 아니다: {w}"
        assert all(x >= -1e-12 for x in w), f"음수 비중이 있다: {w}"


def test_a_low_correlation_partner_gets_more_than_returns_alone_would_give():
    """같은 수익인데 **반대로 움직이는** 짝이면 비중을 더 받아야 한다."""
    rng = random.Random(7)
    a = [rng.gauss(0.001, 0.01) for _ in range(80)]
    mirror = [0.002 - x for x in a]          # 평균은 같고 상관은 −1에 가깝다
    twin = [x + rng.gauss(0, 1e-5) for x in a]   # 평균도 같고 상관도 ≈ +1
    rets = {0: _series(a), 1: _series(mirror), 2: _series(twin)}

    far = P.diversity_weights(rets, [0, 1])
    near = P.diversity_weights(rets, [0, 2])
    assert far and near
    # 반대로 움직이는 짝은 균등에 가깝게(둘 다 실어야 위험이 준다),
    # 똑같이 움직이는 짝은 굳이 나눌 이유가 없다.
    assert abs(far[0] - far[1]) < abs(near[0] - near[2]) + 1e-9, (
        f"상관을 안 보고 있다: 무상관 {far} vs 중복 {near}")
    # ⚠️ 위 한 줄만으로는 부족했다(변이 시험). 수익만 보면 두 경우 모두
    #    한쪽 끝(코너)을 고르고, 그러면 두 격차가 **같아서** 위 비교가
    #    통과한다. 반대로 움직이는 짝은 섞을수록 흔들림이 줄어드니
    #    **반반에 가까워야** 한다 — 그 숫자를 직접 못 박는다.
    assert abs(far[0] - 0.5) < 0.1, (
        f"평균이 같고 반대로 움직이는 짝인데 반반이 아니다: {far} — "
        "위험(흔들림)을 안 보고 수익만 보고 있다")


def test_a_thin_record_says_it_cannot_measure():
    rng = random.Random(3)
    short = {i: _series([rng.gauss(0, 0.01) for _ in range(5)])
             for i in (0, 1)}
    assert P.diversity_weights(short, [0, 1]) is None, (
        "닷새치로 최적 비중을 말하면 그건 잡음이다")
    assert P.diversity_weights({0: _series([0.01] * 40)}, [0]) is None, (
        "의석이 하나뿐이면 나눌 것이 없다")


def test_the_alternative_never_moves_the_real_weight():
    """기록용 값이 매매 비중을 건드리면 판정 시계가 조용히 리셋된다."""
    src = (ROOT / "quant" / "live" / "parliament.py").read_text("utf-8")
    i = src.find("alt = diversity_weights(")
    assert i > 0, "대안 비중을 계산하는 자리가 없다"
    tail = src[i:i + 600]
    assert 'm["alt_weight"] = alt[i]' in tail, "대안 비중을 안 적는다"
    assert 'm["weight"] =' not in tail, (
        "대안 비중이 실제 매매 비중을 덮어쓴다 — 이 값은 기록용이다")


def test_the_gap_is_none_until_it_is_measured():
    ms = [{"strategy": "ml", "params": {}, "weight": 0.7},
          {"strategy": "psar", "params": {}, "weight": 0.3}]
    assert P.weight_gap(ms) is None, "못 잰 격차를 숫자로 말한다"
    ms[0]["alt_weight"] = 0.5
    ms[1]["alt_weight"] = 0.5
    assert P.weight_gap(ms) == 0.2, P.weight_gap(ms)


def test_the_census_says_who_holds_the_money_not_only_who_holds_a_seat():
    champs = {
        "crypto:BTC/USDT": {
            "strategy": "ml", "params": {"model": "logreg"},
            "parliament": [{"strategy": "ml", "params": {"model": "logreg"},
                            "weight": 0.9},
                           {"strategy": "psar", "params": {}, "weight": 0.1}]},
        "crypto:ETH/USDT": {
            "strategy": "ml", "params": {"model": "logreg"},
            "parliament": [{"strategy": "ml", "params": {"model": "logreg"},
                            "weight": 0.9},
                           {"strategy": "psar", "params": {}, "weight": 0.1}]},
    }
    c = P.seat_census(champs)
    assert c["multi_seat"] == 2 and c["diversified"] is True
    assert c["distinct_specs"] == 2
    # 두 계좌 모두 90%가 같은 스펙 — 의석은 둘인데 돈은 하나다.
    assert abs(c["top_spec_share"] - 0.9) < 1e-6, c["top_spec_share"]
    assert c["weight_gap"] is None and c["weight_gap_measured"] == 0


def test_the_public_page_reads_the_money_share_from_the_ledger():
    page = (ROOT / "docs" / "trust.html").read_text("utf-8")
    assert "p.top_spec_share" in page, (
        "공개 페이지가 자금 점유를 장부에서 읽지 않는다 — 의석 수만 "
        "말하면 절반만 말하는 것이다")
    assert "p.weight_gap" in page, "상관까지 본 비중과의 거리가 화면에 없다"
    assert "판정 시계가 리셋" in page, (
        "왜 재기만 하고 적용은 안 하는지가 화면에 없다")
