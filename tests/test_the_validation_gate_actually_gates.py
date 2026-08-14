"""과최적화 검증이 **말한 대로 막는가** — 선언과 행동의 일치.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
2026-08-14 발견. 제품 문서와 사이트는 이렇게 말하고 있었다:

    "전략 하나가 실제로 쓰이려면 DSR · PBO · CPCV를 전부 통과해야 합니다.
     하나라도 크게 실패하면 그 전략은 쓰지 않습니다."

저장소 전체를 뒤졌더니 PBO·DSR은 세 곳에만 있었다 — 계산(CLI), 경보
(flag_watch), 화면 표시(status). **아무것도 막지 않았다.**

    BTC/USDT  PBO 0.78   (문서: 0.7 초과면 "사실상 확실한 과적합, 버릴 것")
    SPY       DSR 0.014  (문서: 0.95 이상이면 통과)

둘 다 매일 그대로 운용되고 있었다. 이 저장소가 가장 경계하는 실패 —
"선언만 돼 있고 실제로는 안 막는 장치" — 가 하필 제품이 핵심 차별점이라고
부르는 자리에 있었다.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

이 파일이 지키는 계약:
  ① 등급이 문서의 기준선과 일치한다 (숫자가 조용히 바뀌면 실패)
  ② **미측정은 통과가 아니다** — 검증이 죽은 날 가장 공격적으로 굴리는
     실패 모양(감사 105·127)을 막는다
  ③ 감쇠가 **실제 목표 비중까지 도달한다** — 계산만 하고 안 쓰면 무의미
  ④ 감쇠가 스케일러에 되돌려지지 않는다(감사 92·2026-08-11과 같은 결함)
  ⑤ 깎인 사실이 장부에 남는다
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.live.validation_gate import (  # noqa: E402
    DSR_PASS,
    MAX_AGE_DAYS,
    PBO_FAIL,
    PBO_PASS,
    grade,
    validation_damp,
    validation_grades,
)

ROOT = Path(__file__).resolve().parent.parent


def _write(tmp_path, data: dict) -> str:
    (tmp_path / "validation.json").write_text(
        json.dumps(data), encoding="utf-8")
    return str(tmp_path)


# ── ① 등급이 문서의 기준선과 일치한다 ─────────────────────────


def test_the_thresholds_match_the_documented_ones():
    """문서(5-4장)가 약속한 숫자와 코드가 같은가."""
    assert PBO_PASS == 0.2
    assert PBO_FAIL == 0.7
    assert DSR_PASS == 0.95


@pytest.mark.parametrize("rec,want_grade,want_scale", [
    ({"pbo": 0.0, "dsr": 0.99}, "통과", 1.0),
    ({"pbo": 0.2, "dsr": 0.95}, "통과", 1.0),      # 경계는 통과 쪽
    ({"pbo": 0.21, "dsr": 0.99}, "경고", 0.5),
    ({"pbo": 0.0, "dsr": 0.94}, "경고", 0.5),
    ({"pbo": 0.7, "dsr": 0.99}, "경고", 0.5),      # 경계는 아직 실패 아님
    ({"pbo": 0.71}, "실패", 0.0),
    ({"pbo": 0.78}, "실패", 0.0),                  # 발견 당시 BTC 실측값
])
def test_grades_follow_the_documented_lines(rec, want_grade, want_scale):
    g = grade(rec, asof="2026-08-14")
    assert (g["grade"], g["scale"]) == (want_grade, want_scale), g


def test_the_two_symbols_that_started_this_are_actually_gated():
    """발견 당시의 실측값이 실제로 깎이는지 — 회귀 방지용 못."""
    btc = grade({"pbo": 0.7777777777777778, "dsr": None}, "2026-08-14")
    spy = grade({"pbo": 0.0, "dsr": 0.014399869123230824}, "2026-08-14")
    assert btc["scale"] == 0.0, f"PBO 78%인데 그대로 굴린다: {btc}"
    assert spy["scale"] == 0.5, f"DSR 0.01인데 그대로 굴린다: {spy}"


# ── ② 미측정은 통과가 아니다 ──────────────────────────────────


def test_an_unmeasured_symbol_is_not_treated_as_passing():
    """'안 재봤다'와 '재봤더니 괜찮다'를 같게 두면 검증이 죽은 날 가장
    공격적으로 굴린다 — 감사 105·127에서 반복해 겪은 실패 모양이다."""
    g = grade(None, "2026-08-14")
    assert g["grade"] == "미측정"
    assert g["scale"] < 1.0, "측정한 적 없는 종목을 통과로 취급한다"


def test_a_missing_ledger_damps_every_symbol(tmp_path):
    """검증 장부가 통째로 없어도 조용히 전 종목 통과가 되면 안 된다."""
    d = validation_damp(["crypto:BTC/USDT", "us_stock:SPY"], str(tmp_path))
    assert set(d) == {"crypto:BTC/USDT", "us_stock:SPY"}
    assert all(v < 1.0 for v in d.values()), d


def test_a_corrupt_ledger_fails_safe(tmp_path):
    """깨진 파일을 '통과'로 읽으면 파일 손상이 곧 게이트 해제가 된다."""
    (tmp_path / "validation.json").write_text("{not json", encoding="utf-8")
    d = validation_damp(["us_stock:SPY"], str(tmp_path))
    assert d["us_stock:SPY"] < 1.0


def test_an_empty_record_is_not_a_pass(tmp_path):
    """기록은 있는데 PBO·DSR이 비어 있는 경우 — 통과 도장이 아니다."""
    dd = _write(tmp_path, {"us_stock:SPY": {"strategy": "ml", "bars": 800}})
    assert validation_damp(["us_stock:SPY"], dd)["us_stock:SPY"] < 1.0


def test_a_stale_record_expires(tmp_path):
    """며칠 멈춘 검증이 통과 도장을 계속 찍어 주면 안 된다."""
    fresh = grade({"pbo": 0.0, "dsr": 0.99, "asof": "2026-08-14"}, "2026-08-14")
    stale = grade({"pbo": 0.0, "dsr": 0.99, "asof": "2026-07-01"}, "2026-08-14")
    assert fresh["scale"] == 1.0
    assert stale["grade"] == "만료" and stale["scale"] < 1.0
    edge = grade({"pbo": 0.0, "dsr": 0.99, "asof": "2026-08-08"}, "2026-08-14")
    assert edge["age_days"] == 6 <= MAX_AGE_DAYS and edge["scale"] == 1.0


def test_every_requested_symbol_appears_in_the_table(tmp_path):
    """목록에서 빠진 종목은 감쇠 1.0이 되어 조용히 통과한다."""
    dd = _write(tmp_path, {"us_stock:SPY": {"pbo": 0.0, "dsr": 0.99}})
    keys = ["us_stock:SPY", "crypto:BTC/USDT", "kr_stock:005930.KS"]
    g = validation_grades(keys, dd, "2026-08-14")
    assert set(g) == set(keys), f"빠진 종목: {set(keys) - set(g)}"


# ── ③④ 감쇠가 실제 목표 비중까지 도달하는가 ───────────────────


def test_the_damping_reaches_the_final_target_weight():
    """계산만 하고 안 쓰면 무의미하다 — _target_w가 실제로 곱하는지 본다.

    ⚠️ 감쇠는 변동성 타깃(vscale) **뒤에** 걸려야 한다. 앞에 두면 스케일러가
       "위험이 작아졌다"며 되돌려 키워 게이트가 통째로 무효가 된다 —
       2026-08-11에 킬스위치가 정확히 그 이유로 죽어 있었다.
    """
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert "valid_damp.get(key, 1.0)" in src, (
        "검증 게이트가 최종 비중 계산에 곱해지지 않는다 — 계산만 하고 버린다")
    # 설명(docstring)이 아니라 **식 자체**를 본다. 주석에 이름이 있다고
    # 곱해지는 것은 아니다.
    body = src[src.index("def _target_w("):]
    body = body[:body.index("\n    # 예산에 맞춰")]
    expr = next(ln for ln in body.splitlines() if "eff = " in ln and "*" in ln)
    tail = body[body.index(expr):]
    tail = tail[:tail.index("kcap")]
    assert "vscale" in tail and "valid_damp" in tail, tail
    assert tail.index("vscale") < tail.index("valid_damp"), (
        "검증 감쇠가 변동성 타깃보다 앞에 걸렸다 — 스케일러가 되돌려 키운다\n"
        + tail)


def test_the_gate_is_built_for_every_traded_symbol():
    """판단한 종목 전부에 대해 등급을 만드는지 — 배선 확인."""
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert "validation_grades(" in src
    assert 'f"{m}:{s}" for m, s in targets' in src, (
        "운용 대상 전체가 아니라 일부만 게이트에 넣고 있다")


# ── ⑤ 깎인 사실이 장부에 남는가 ───────────────────────────────


def test_the_ledger_records_why_a_symbol_was_damped():
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert '"validation_gate"' in src, (
        "게이트가 비중을 깎고도 장부에 흔적을 안 남긴다 — "
        "'왜 오늘 이 종목을 안 샀나'에 답할 수 없다")


def test_the_gate_explains_itself_in_korean():
    """운영자가 읽을 이유가 비어 있으면 경보가 무의미하다."""
    for rec in ({"pbo": 0.9}, {"pbo": 0.5}, {"dsr": 0.1}, None):
        g = grade(rec, "2026-08-14")
        assert g["why"] and len(g["why"]) > 10, g


# ── ⑥ 검증 범위가 운용 범위를 따라가는가 ──────────────────────

"""2026-08-14까지 야간 검증은 **BTC와 SPY 두 종목만** 돌았다. 종목 목록이
워크플로 YAML에 손으로 박혀 있었기 때문이다. 운용은 8 → 20종목으로 늘었는데
검증은 따라가지 않았고, 나머지 18종목은 PBO·DSR이 한 번도 계산된 적이 없었다.

목록이 두 곳에 있으면 반드시 갈라진다. 검증 대상은 코드(AUTO_TARGETS)가
갖고, 워크플로는 그것을 부르기만 해야 한다."""

_WF = ROOT / ".github" / "workflows" / "nightly-validate.yml"


def test_the_workflow_does_not_carry_its_own_symbol_list():
    wf = _WF.read_text("utf-8")
    assert "--all" in wf, "야간 검증이 전 종목 모드를 쓰지 않는다"
    assert "AUTO_TARGETS" in wf, (
        "워크플로가 운용 대상 목록을 코드에서 가져오지 않는다")
    # 하드코딩된 종목 쌍이 실행 명령에 남아 있으면 다시 갈라진다
    for line in wf.splitlines():
        if line.strip().startswith("python -m quant validate"):
            assert "--symbol" not in line, (
                f"검증 명령에 종목이 손으로 박혀 있다: {line.strip()}")


def test_validate_all_covers_every_traded_symbol():
    """--all이 도는 목록 = 실제 운용 목록."""
    from quant.markets import AUTO_TARGETS

    import quant.cli as cli
    src = Path(cli.__file__).read_text("utf-8")
    assert "all_targets" in src and "AUTO_TARGETS" in src
    assert len(AUTO_TARGETS) >= 20, (
        f"운용 대상이 {len(AUTO_TARGETS)}종목 — 목록이 줄었다면 확인 필요")


def test_validate_records_the_date_it_measured():
    """날짜가 없으면 게이트가 '만료'를 판정할 수 없어 옛 기록이 영원히 통과한다."""
    import quant.cli as cli
    src = Path(cli.__file__).read_text("utf-8")
    block = src[src.index('prev[f"{args.market}:{args.symbol}"]'):]
    block = block[:block.index("atomic_write_json")]
    assert '"asof"' in block, (
        "검증 결과에 날짜를 안 남긴다 — 며칠 멈춘 검증이 통과 도장을 계속 찍는다")


def test_one_symbols_failure_does_not_lose_the_rest(monkeypatch, tmp_path):
    """20종목 중 하나가 실패해도 나머지 19종목의 검증을 잃지 않는다.

    다만 실패를 **삼키지도 않는다** — 종료코드로 드러나야 한다.
    """
    import quant.cli as cli

    seen, boom = [], {"crypto:ETH/USDT"}

    def fake(args):
        if getattr(args, "all_targets", False):
            return real(args)
        key = f"{args.market}:{args.symbol}"
        seen.append(key)
        if key in boom:
            raise RuntimeError("데이터 수신 실패")

    real = cli._cmd_validate
    monkeypatch.setattr(cli, "_cmd_validate", fake)

    from quant.markets import AUTO_TARGETS
    args = type("A", (), {})()
    args.all_targets = True
    with pytest.raises(SystemExit) as ei:
        fake(args)
    assert len(seen) == len(AUTO_TARGETS), (
        f"{len(seen)}종목에서 멈췄다 — 한 종목 실패가 나머지를 죽인다")
    assert "ETH" in str(ei.value) or "1종목" in str(ei.value), str(ei.value)
