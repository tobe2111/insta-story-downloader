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


# 날짜(asof)를 붙여 둔다 — 안 붙이면 '신선도 미상'으로 자동 감점되어
# 이 표가 검사하려는 PBO·DSR 판정을 못 본다(그 규칙은 아래에서 따로 본다).
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
    g = grade({"cpcv_worst_return": 0.05, **rec, "asof": "2026-08-14"},
              asof="2026-08-14")
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


def test_a_half_measured_record_is_not_a_pass():
    """PBO만 재고 DSR을 못 잰 기록(실제로 흔함)이 만점을 받으면 안 된다.

    ⚠️ 2026-08-14 자체 점검에서 발견. 이 모듈은 "'안 재봤다'는 '괜찮다'가
    아니다"를 원칙으로 세워 놓고, **필드 단위에서는 그걸 안 지키고 있었다** —
    'PBO 통과 + DSR 없음'은 아무 이유도 안 쌓여 ×1.0을 받았다.
    워크포워드가 DSR을 못 내면 null로 남으므로 드문 경우도 아니다.
    """
    only_pbo = grade({"pbo": 0.05, "dsr": None, "cpcv_worst_return": 0.05,
                      "asof": "2026-08-14"}, "2026-08-14")
    assert only_pbo["scale"] == 0.5, f"반쪽 측정이 만점을 받는다: {only_pbo}"
    assert "DSR" in only_pbo["why"]

    only_dsr = grade({"pbo": None, "dsr": 0.99, "cpcv_worst_return": 0.05,
                      "asof": "2026-08-14"}, "2026-08-14")
    assert only_dsr["scale"] == 0.5, only_dsr
    assert "PBO" in only_dsr["why"]


def test_a_record_without_a_date_cannot_be_called_fresh():
    """날짜가 없으면 만료를 판정할 수 없다 — '통과' 도장을 줄 근거도 없다.

    ⚠️ 2026-08-14 자체 점검에서 발견. 만료 장치를 만들어 놓고, 정작 **그때
    장부에 있던 기록 두 건이 전부 날짜가 없어** 만료 판정이 통째로
    건너뛰어졌다. 검증이 멈춰도 옛 도장이 영원히 유효한 셈이었다.
    """
    aged = grade({"pbo": 0.0, "dsr": 0.99,                  # asof 없음
                  "cpcv_worst_return": 0.05}, "2026-08-14")
    assert aged["scale"] < 1.0, f"날짜 없는 기록이 만점을 받는다: {aged}"
    assert "날짜" in aged["why"]


def test_a_failure_is_a_failure_regardless_of_age():
    """오래된 '버릴 것'도 여전히 '버릴 것'이다 — 나이가 형을 감면하지 않는다."""
    for rec in ({"pbo": 0.9}, {"pbo": 0.9, "asof": "2020-01-01"}):
        g = grade(rec, "2026-08-14")
        assert g["scale"] == 0.0, g


def test_a_stale_record_expires(tmp_path):
    """며칠 멈춘 검증이 통과 도장을 계속 찍어 주면 안 된다."""
    ok = {"pbo": 0.0, "dsr": 0.99, "cpcv_worst_return": 0.05}
    fresh = grade({**ok, "asof": "2026-08-14"}, "2026-08-14")
    stale = grade({**ok, "asof": "2026-07-01"}, "2026-08-14")
    assert fresh["scale"] == 1.0
    assert stale["grade"] == "만료" and stale["scale"] < 1.0
    edge = grade({**ok, "asof": "2026-08-08"}, "2026-08-14")
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


# ── ⑦ 게이트가 어느 계좌에 걸리는지 — 경계가 문서와 코드에 다 있는가 ──

"""배치는 계좌 두 종류를 돈다:
  · 통합 분산 계좌(run_daily_portfolio) — 실제로 돈이 도는 쪽. 게이트가 걸린다.
  · 종목별 참고 계좌(run_daily_paper) — 전략의 원래 행동을 재는 **계기**.
    게이트를 **일부러 안 건다.**

계기에도 걸면 순환이 된다: 깎인 수익이 장부에 쌓이고, 그 장부에서 뽑은 켈리
상한이 다시 통합 계좌의 비중을 정한다. 의도된 경계지만, **문서가 그 구분을
안 하면** 종목별 화면을 본 사람은 게이트가 안 걸린 줄 안다."""


def test_the_boundary_is_written_where_someone_would_look():
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    body = src[src.index("def run_daily_paper("):]
    body = body[:body.index("def run_daily_portfolio(")]
    assert "검증 게이트를 여기 걸지" in body, (
        "종목별 경로에 게이트가 없는 이유가 적혀 있지 않다 — 다음 사람이 "
        "'빠뜨렸다'고 보고 넣으면 켈리 상한이 순환한다")
    assert "순환" in body

    readme = (ROOT / "README.md").read_text("utf-8")
    assert "종목별 참고 계좌" in readme and "통합 분산 계좌" in readme, (
        "README가 게이트의 적용 범위를 밝히지 않는다")


def test_the_money_account_is_the_one_that_is_gated():
    """배선 확인 — 게이트는 통합 계좌 경로에만 있다."""
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    per_symbol = src[src.index("def run_daily_paper("):
                     src.index("def run_daily_portfolio(")]
    portfolio = src[src.index("def run_daily_portfolio("):]
    assert "valid_damp.get(" not in per_symbol
    assert "valid_damp.get(" in portfolio


# ── ⑧ 3중 관문의 세 번째(CPCV)가 어디에도 안 닿고 있었다 ──────────

"""2026-08-14 자체 점검에서 발견. 문서는 "3중 관문(DSR·PBO·CPCV)"이라 말하고
통과 기준까지 적어 뒀다 — "가장 나쁜 경로에서도 플러스". 그런데 CPCV는
**계산되고 화면에 찍힌 뒤 버려졌다.** validate가 `cv`를 만들어 출력만 하고
장부에 저장하지 않아, 어떤 판단에도 닿은 적이 없다.

DSR·PBO를 게이트에 붙이면서 "그럼 셋째는?"을 물어보다 나왔다."""


def test_cpcv_reaches_the_gate():
    from quant.live.validation_gate import CPCV_WORST_PASS

    ok = {"pbo": 0.0, "dsr": 0.99, "asof": "2026-08-14"}
    good = grade({**ok, "cpcv_worst_return": 0.05}, "2026-08-14")
    bad = grade({**ok, "cpcv_worst_return": -0.03}, "2026-08-14")
    assert good["scale"] == 1.0, good
    assert bad["scale"] == 0.5, f"최악 경로가 마이너스인데 그대로 굴린다: {bad}"
    assert "CPCV" in bad["why"]
    assert CPCV_WORST_PASS == 0.0        # 문서가 적은 기준선


def test_an_unmeasured_cpcv_is_not_a_pass():
    """DSR·PBO만 재고 CPCV를 안 잰 기록도 만점이 아니다."""
    g = grade({"pbo": 0.0, "dsr": 0.99, "asof": "2026-08-14"}, "2026-08-14")
    assert g["scale"] == 0.5 and "CPCV" in g["why"], g


def test_validate_actually_saves_the_cpcv_result():
    """계산해 놓고 안 저장하면 게이트가 볼 수가 없다 — 원래의 결함."""
    import quant.cli as cli

    src = Path(cli.__file__).read_text("utf-8")
    block = src[src.index('prev[f"{args.market}:{args.symbol}"]'):]
    block = block[:block.index("atomic_write_json")]
    assert '"cpcv_worst_return"' in block, (
        "CPCV 결과가 장부에 저장되지 않는다 — 3중 관문의 셋째가 "
        "화면에만 찍히고 사라진다")


def test_all_symbols_do_not_overwrite_one_report_file(tmp_path, monkeypatch):
    """`--all --report`이 **20종목을 같은 파일에 덮어쓰면** 안 된다.

    ⚠️ 파일은 있고 이름도 맞으니 아무도 눈치채지 못한다. 그 리포트를 열어 본
       사람은 마지막 종목의 그래프를 **다른 19종목의 것으로 읽는다.**
       조용히 틀린 자료를 주는 쪽이 아예 없는 것보다 나쁘다.

    ⚠️ 검사가 **진짜 코드**를 돌게 한다. 여기서 같은 경로 규칙을 다시 적으면
       그건 자기 사본을 검사하는 것이고(오늘 반복해서 잡은 함정), 코드가
       바뀌어도 영원히 초록이다. `_cmd_validate`는 자기 자신을 다시 부르므로,
       모듈 속성만 바꿔치기하면 그 재귀 호출이 잡힌다 — 바깥 호출은 원본이라
       `--all` 분기는 실제 코드가 돈다.
    """
    import types

    from quant import cli
    from quant.markets import AUTO_TARGETS

    original = cli._cmd_validate
    seen: list[str] = []
    monkeypatch.setattr(cli, "_cmd_validate",
                        lambda one: seen.append(one.report))

    original(types.SimpleNamespace(all_targets=True, market="", symbol="",
                                   report=str(tmp_path / "리포트.html")))

    assert len(seen) == len(AUTO_TARGETS), f"{len(seen)}종목만 돌았다"
    assert len(set(seen)) == len(seen), (
        f"리포트 경로가 겹친다 — 덮어쓰기: {sorted(seen)[:3]}")
    for path in seen:
        assert path.endswith(".html"), f"확장자가 사라졌다: {path}"


def test_all_without_report_asks_for_no_path(tmp_path, monkeypatch):
    """리포트를 안 쓰겠다고 했으면 경로를 만들어 내지 않는다."""
    import types

    from quant import cli

    original = cli._cmd_validate
    seen: list = []
    monkeypatch.setattr(cli, "_cmd_validate",
                        lambda one: seen.append(getattr(one, "report", None)))
    original(types.SimpleNamespace(all_targets=True, market="", symbol="",
                                   report=None))
    assert seen and all(x is None for x in seen), f"경로를 지어냈다: {seen[:3]}"
