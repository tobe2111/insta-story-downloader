"""매매하는 목록과 심사하는 목록은 같아야 한다 (2026-08-23 실측 사고).

무슨 일이 있었나. 유니버스를 20 → 40종목으로 늘렸는데, 늘어난 것은
**매매 목록**뿐이었다:

    페이퍼 배치  → quant.universe.active_targets   40종목  "이 40개를 산다"
    재학습·검증  → quant.markets.AUTO_TARGETS      20종목  "이 20개를 심사한다"

결과: **22종목이 오디션 한 번 없이 기본 전략으로 돈을 받고 있었다.** 그
전략이 그 종목에서 통하는지 아무도 확인한 적이 없는데, 검증 기록만 없다는
이유로 '미측정'(×0.5)을 받아 절반씩 실려 있었다. 그때 계좌 노출 45.5%의
절반 넘는 돈이 그 위에 앉아 있었다.

이 저장소가 반복해서 잡아 온 병(선언과 행동의 불일치)이고, 하필 유니버스를
늘린 그 작업이 만든 것이다.

지켜야 할 약속:
- 심사(재학습·검증) 대상은 **지금 매매하는 목록**에서 나온다. 손으로 적은
  상수를 기본값으로 쓰지 않는다.
- 시간이 모자라면 **잘렸다는 사실을 남기고** 다음 밤에 이어 돈다. 조용히
  줄면 "전 종목 심사 완료"로 읽힌다.
- '심사받은 적 없음'은 '검증이 늦었다'와 다르게 취급한다 — 더 세게 깎는다.
- 챔피언 장부를 못 읽는 날은 **전 종목을 '심사받음'으로** 본다. 파일 하나
  깨졌다고 계좌를 통째로 멈추는 것은 안전이 아니라 고장이다.
- 그 사실이 공개 페이지에 나온다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live import validation_gate as VG                # noqa: E402


# ── ① 진실의 출처가 하나인가 ────────────────────────────────────

def test_retraining_walks_what_we_actually_trade():
    src = (ROOT / "quant" / "live" / "retrain.py").read_text("utf-8")
    i = src.find("def run_retrain_all")
    body = src[i:i + 2500]
    assert "active_targets" in body, (
        "재학습이 매매 목록이 아니라 손으로 적은 상수를 순회한다")
    assert "targets or active_targets" in body


def test_validation_walks_what_we_actually_trade():
    src = (ROOT / "quant" / "cli.py").read_text("utf-8")
    i = src.find('if getattr(args, "all_targets", False):')
    body = src[i:i + 2500]
    assert "active_targets" in body, (
        "검증이 매매 목록이 아니라 손으로 적은 상수를 순회한다")


def test_both_jobs_can_run_out_of_time_without_lying():
    """시간이 모자라 잘린 사실은 반드시 기록에 남는다."""
    retrain = (ROOT / "quant" / "live" / "retrain.py").read_text("utf-8")
    cli = (ROOT / "quant" / "cli.py").read_text("utf-8")
    assert "QUANT_RETRAIN_BUDGET_SEC" in retrain
    assert "QUANT_VALIDATE_BUDGET_SEC" in cli, "검증에는 시간 예산이 없다"
    for name, src in (("재학습", retrain), ("검증", cli)):
        assert "not_reached" in src, f"{name}: 못 돈 종목을 안 남긴다"
        assert "cursor" in src.lower(), f"{name}: 이어달리기 커서가 없다"


# ── ② '심사 전'과 '미측정'을 구별하는가 ─────────────────────────

def test_never_auditioned_is_damped_harder_than_merely_unmeasured():
    untried = VG.grade(None, "2026-08-23", tried=False)
    late = VG.grade(None, "2026-08-23", tried=True)
    assert untried["grade"] == "심사 전" and late["grade"] == "미측정"
    assert untried["scale"] < late["scale"], (
        f"심사 전 {untried['scale']} 이 미측정 {late['scale']} 보다 안 낮다 — "
        "'한 번도 안 재봤다'와 '오늘 못 쟀다'를 같게 본다")
    assert VG.SCALE_UNTRIED == 0.25


def test_a_symbol_with_a_measurement_is_judged_on_the_measurement():
    """심사 전이라도 검증 기록이 있으면 그 기록으로 판단한다(더 많이 아는 쪽)."""
    rec = {"asof": "2026-08-23", "pbo": 0.9, "dsr": 0.5,
           "cpcv_worst_return": 0.1}
    g = VG.grade(rec, "2026-08-23", tried=False)
    assert g["grade"] == "실패", g          # PBO 0.9 → 관망이 맞다
    assert g["scale"] == 0.0


def test_the_grade_table_asks_the_champion_ledger(tmp_path):
    (tmp_path / "validation.json").write_text("{}", "utf-8")
    (tmp_path / "champions.json").write_text(json.dumps({
        "crypto:BTC/USDT": {"strategy": "ml", "params": {}}}), "utf-8")
    g = VG.validation_grades(["crypto:BTC/USDT", "us_stock:DBC"],
                             str(tmp_path), "2026-08-23")
    assert g["crypto:BTC/USDT"]["grade"] == "미측정"      # 심사는 받았다
    assert g["us_stock:DBC"]["grade"] == "심사 전"        # 챔피언조차 없다
    assert g["us_stock:DBC"]["scale"] < g["crypto:BTC/USDT"]["scale"]


def test_an_unreadable_champion_ledger_does_not_halt_the_account(tmp_path):
    """파일 하나 깨졌다고 전 종목을 4분의 1로 깎으면 그건 안전이 아니라 고장이다."""
    (tmp_path / "validation.json").write_text("{}", "utf-8")
    (tmp_path / "champions.json").write_text("{{{ 깨진 파일", "utf-8")
    g = VG.validation_grades(["crypto:BTC/USDT", "us_stock:DBC"],
                             str(tmp_path), "2026-08-23")
    assert all(v["grade"] == "미측정" for v in g.values()), (
        f"장부를 못 읽었다고 전 종목을 '심사 전'으로 떨어뜨린다: "
        f"{ {k: v['grade'] for k, v in g.items()} }")


def test_the_summary_names_the_new_grade():
    s = VG.gate_summary({"a": {"grade": "심사 전"}, "b": {"grade": "통과"}})
    assert "심사 전" in s, s


# ── ③ 화면이 그 사실을 말하는가 ─────────────────────────────────

def test_the_public_page_says_how_many_are_unjudged():
    page = (ROOT / "docs" / "trust.html").read_text("utf-8")
    assert 'id="untried"' in page, "심사 전 종목 카드가 없다"
    assert "\"심사 전\"" in page, "화면이 그 등급을 읽지 않는다"
    assert "4분의 1" in page, "얼마나 줄이는지 안 말한다"
    # 게이트는 최상위가 아니라 **본 계좌의 마지막 기록 안**에 있다.
    # 최상위에서 읽으면 카드가 영원히 빈 채로 초록이 된다 — 이 저장소가
    # 반복해 잡아 온 "없는 필드를 읽는 화면" 계열이다.
    assert "_lastRec.validation_gate" in page, (
        "게이트를 본 계좌 기록에서 읽지 않는다 — 카드가 영원히 빈다")
    assert "_pfALL.history" in page
