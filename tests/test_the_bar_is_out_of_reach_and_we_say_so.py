"""통과가 0종목인 날, 왜 그런지까지 같은 자리에서 말한다 (2026-08-19).

이날 20종목 과최적화 검증이 처음으로 완주했고 결과는 이랬다:

    실패 6 · 경고 13 · 미측정 1 · **통과 0** · DSR 최고 0.16(통과선 0.95)

여기서 "전략이 나쁘다"와 "지금 표본으로는 넘을 수 없는 관문이다"는 대응이
정반대다. 그래서 추측하지 않고 역산했다 — DSR은 (표본 길이, 누적 시행 횟수,
실현 샤프)로 정해지니, 앞의 둘을 장부에서 읽으면 셋째를 풀 수 있다.
실측 T=800봉 · N=238회에서 필요 연환산 샤프는 약 2.5다.

지켜야 할 약속:
- 필요 샤프는 **장부 값으로** 계산한다(상수를 박아 두지 않는다).
- 표본이 길수록 필요 샤프가 낮아진다 — 방향이 뒤집히면 계산이 틀린 것이다.
- 못 재면 None. 모르는 것을 숫자로 만들지 않는다.
- 통과선(0.95)은 검증 게이트와 **같은 값**이어야 한다. 여기서 몰래 낮추면
  화면과 실제 판정이 갈린다.
- 공개 페이지가 이 숫자를 장부에서 읽고, **관문을 낮추지 않는다는 사실**도
  함께 말한다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live import provable as PV                      # noqa: E402
from quant.live.validation_gate import DSR_PASS            # noqa: E402


def _write(tmp_path, val: dict, champs: dict) -> str:
    (tmp_path / "validation.json").write_text(
        json.dumps(val, ensure_ascii=False), "utf-8")
    (tmp_path / "champions.json").write_text(
        json.dumps(champs, ensure_ascii=False), "utf-8")
    return str(tmp_path)


def test_the_public_bar_is_the_same_bar_the_gate_uses():
    assert PV.DSR_PASS == DSR_PASS, (
        "화면이 말하는 통과선과 실제 판정선이 다르다 — 둘 중 하나는 거짓말이다")


def test_a_longer_record_needs_a_smaller_edge():
    """표본이 길수록 증명이 쉬워진다 — 이 방향이 뒤집히면 역산이 틀린 것이다."""
    prev = None
    for bars in (800, 1600, 3200, 20800):
        need = PV.required_sharpe(bars, 238)
        assert need is not None
        if prev is not None:
            assert need < prev, (
                f"표본을 {bars}봉으로 늘렸는데 필요 샤프가 안 줄었다: "
                f"{prev} → {need}")
        prev = need


def test_the_edge_needed_shrinks_like_one_over_root_n():
    """표본이 4배면 필요 엣지는 대략 절반이다 — 통계의 기본 축척.

    ⚠️ 방향만 보는 검사로는 부족했다(변이 시험). 표본 길이를 한 자리에서만
       쓰고 다른 자리에 800을 박아 두면 방향은 그대로 맞는데 **값이 통째로
       틀린다** — 그러면 "1시간봉이면 샤프 1.02면 된다" 같은 화면 숫자가
       거짓이 된다. 축척 자체를 못 박는다.
    """
    import math

    base = PV.required_sharpe(800, 238)
    for mult in (4, 26):
        got = PV.required_sharpe(800 * mult, 238) / base
        want = 1.0 / math.sqrt(mult)
        assert abs(got - want) < 0.1 * want + 0.02, (
            f"표본 {mult}배에서 필요 엣지 비율이 {got:.3f} — "
            f"1/√{mult}={want:.3f}에서 너무 멀다. 표본 길이가 계산의 "
            "일부에만 반영되고 있을 수 있다")


def test_more_tries_needs_a_bigger_edge():
    """많이 시도할수록 증명이 어려워진다(다중검정) — 그게 DSR의 존재 이유다."""
    few = PV.required_sharpe(800, 10)
    many = PV.required_sharpe(800, 2000)
    assert few is not None and many is not None
    assert many > few, f"시행을 200배 늘렸는데 문턱이 안 올랐다: {few} → {many}"


def test_a_record_too_short_to_judge_says_so():
    assert PV.required_sharpe(3, 100) is None, "봉 3개로 필요 샤프를 말한다"
    assert PV.annualized(None) is None


def test_the_measurement_reads_the_ledger_not_a_hardcoded_number(tmp_path):
    """표본 길이·시행 횟수를 장부에서 읽는가 — 두 장부로 두 답이 나와야 한다."""
    val_short = {"crypto:BTC/USDT": {"bars": 800, "dsr": 0.1,
                                     "asof": "2026-08-19"}}
    val_long = {"crypto:BTC/USDT": {"bars": 20800, "dsr": 0.1,
                                    "asof": "2026-08-19"}}
    champs = {"crypto:BTC/USDT": {"strategy": "ml", "params": {},
                                  "trials_total": 238}}
    da, db = tmp_path / "a", tmp_path / "b"
    da.mkdir()
    db.mkdir()
    a = PV.provability(_write(da, val_short, champs))
    b = PV.provability(_write(db, val_long, champs))
    assert a and b
    assert a["bars_median"] == 800 and b["bars_median"] == 20800
    assert b["required_ann_sharpe"] < a["required_ann_sharpe"], (
        f"장부를 안 읽고 상수를 쓰고 있다: {a['required_ann_sharpe']} vs "
        f"{b['required_ann_sharpe']}")
    assert a["passing"] == 0 and a["trials_median"] == 238


def test_an_empty_ledger_measures_nothing(tmp_path):
    d = tmp_path / "empty"
    d.mkdir()
    assert PV.provability(str(d)) is None, "장부가 없는데 숫자를 지어낸다"
    (d / "validation.json").write_text("{}", "utf-8")
    assert PV.provability(str(d)) is None
    # ⚠️ 기록은 있는데 **재본 값이 없는** 경우가 더 흔하다(검증이 중간에
    #    죽으면 이렇게 남는다). 이때 숫자를 지어내면 빈칸이 '측정됨'으로
    #    읽힌다 — 이 제품이 반복해서 잡아 온 결함 계열이다.
    (d / "validation.json").write_text(
        json.dumps({"crypto:BTC/USDT": {"asof": "2026-08-19"}}), "utf-8")
    assert PV.provability(str(d)) is None, (
        "PBO·DSR·봉 수가 하나도 없는 기록으로 '필요 샤프'를 발표한다")


def test_not_measurable_is_not_an_error(tmp_path, caplog):
    """'못 쟀다'와 '고장났다'를 구분한다.

    ⚠️ 왜 경보까지 보나(변이 시험 2026-08-19). 이 함수는 실패를 통째로
       삼키는 except가 있어서, 정상 판단(못 잼)을 지워도 결과는 똑같이
       None이 된다 — 대신 **경고 로그가 남는다.** 그러면 '오늘은 잴 게
       없었다'가 매일 경보로 올라오고, 진짜 고장이 그 잡음에 묻힌다.
       그래서 결과만이 아니라 **조용했는지**까지 본다.
    """
    import logging

    d = tmp_path / "thin"
    d.mkdir()
    (d / "validation.json").write_text(
        json.dumps({"crypto:BTC/USDT": {"asof": "2026-08-19"}}), "utf-8")
    with caplog.at_level(logging.WARNING):
        assert PV.provability(str(d)) is None
    noisy = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert not noisy, (
        "잴 것이 없을 뿐인데 경고를 울린다 — 매일 울리는 경보는 곧 "
        f"아무도 안 보는 경보가 된다: {[r.getMessage() for r in noisy]}")


def test_the_paths_out_are_all_about_more_sample_not_a_lower_bar():
    labels = [lbl for lbl, _m in PV.PATHS]
    assert len(labels) >= 3
    assert all(m >= 1.0 for _lbl, m in PV.PATHS), (
        "표본을 줄이는 길이 선택지에 들어 있다")
    joined = " ".join(labels)
    for banned in ("기준", "관문", "0.95", "낮"):
        assert banned not in joined, (
            f"탈출구 목록이 관문을 건드리는 쪽을 말한다: {joined!r}")


def test_the_ledger_and_the_page_carry_it():
    daily = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert 'status["provable"]' in daily, "증명 가능성이 장부에 안 실린다"
    page = (ROOT / "docs" / "trust.html").read_text("utf-8")
    assert "st.provable" in page, "공개 페이지가 장부에서 안 읽는다"
    assert "required_ann_sharpe" in page, "필요 샤프가 화면에 없다"
    assert "골대 이동" in page, (
        "관문을 낮추지 않는다는 사실이 같은 자리에 없다 — 나쁜 숫자만 "
        "적고 원칙을 안 적으면 읽는 사람은 곧 기준이 바뀔 것으로 읽는다")
