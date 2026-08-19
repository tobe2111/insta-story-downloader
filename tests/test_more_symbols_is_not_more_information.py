"""종목을 늘렸는데 정보가 늘었는가 (2026-08-19, 사장님 지시).

사장님: "자산군 최대한 많이 넣어, 종목들도 최대한 많이"

맞는 방향이지만 **비슷한 종목을 늘리는 것은 정보가 아니다.** 같이 움직이는
종목이 스물이면 장부는 스무 줄이 쌓여도 통계가 받는 정보는 한두 개 몫이다.
그래서 이 저장소는 종목 수 대신 **실효 표본 수**를 재서 공개한다.

지켜야 할 약속:
- 완전히 같이 움직이는 종목들은 실효 표본이 1에 가깝다.
- 서로 무관한 종목들은 실효 표본이 종목 수에 가깝다.
- 기록이 얇으면 재지 않고 "못 잰다"고 말한다(빈칸은 '문제 없음'으로 읽힌다).
- 유니버스 코어에 **다르게 움직이는 자산군**이 실제로 들어 있다.
- 새로 넣는 것이 ETF·코인 위주다 — 개별주는 한 주 값 때문에 못 담는다.
- 배선: 배치가 status에 싣고, 첫 화면이 장부에서 읽는다.
"""
from __future__ import annotations

import json
import math
import random
import time
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live import breadth as B                        # noqa: E402


def _rets(seq):
    return {f"2026-01-{i + 1:02d}": v for i, v in enumerate(seq)}


def test_identical_movers_count_as_one():
    """같은 것을 스무 번 사도 정보는 한 개다."""
    # ⚠️ 시드를 **한 번만** 만든다. 매번 Random(3)을 새로 만들면 40개 값이
    #    전부 같아져(변동 0) 상관을 아예 못 재고, 그러면 이 검사는 "같이
    #    움직이면 한 개 몫"을 확인하는 게 아니라 계측기가 못 재는 상황을
    #    확인하게 된다 — 통과해도 아무것도 지키지 않는 검사가 된다.
    rng = random.Random(3)
    base = [rng.gauss(0, 0.01) for _ in range(40)]
    got = B.effective_n({f"s{i}": _rets(base) for i in range(20)})
    assert got["effective_n"] is not None, (
        f"상관을 재지 못했다 — 검사 자료가 잘못됐다: {got}")
    assert got["effective_n"] <= 1.2, (
        f"완전히 같이 움직이는 20종목의 실효 표본이 {got['effective_n']} — "
        "종목 수를 정보로 착각하고 있다")


def test_unrelated_movers_count_separately():
    """대조군 — 서로 무관하면 종목 수에 가까워야 한다."""
    rng = random.Random(11)
    got = B.effective_n({f"s{i}": _rets([rng.gauss(0, 0.01) for _ in range(60)])
                         for i in range(8)})
    assert got["effective_n"] >= 5.0, (
        f"무관한 8종목인데 실효 표본이 {got['effective_n']} — 계측기가 고장났다")


def test_a_thin_record_says_so_instead_of_guessing():
    got = B.effective_n({"a": _rets([0.01] * 3), "b": _rets([0.02] * 3)})
    assert got["effective_n"] is None and "못 잽" in got.get("reason", ""), got


def test_the_universe_actually_holds_different_kinds_of_assets():
    """'자산군을 늘렸다'가 선언이 아니라 목록에 있는가."""
    from quant.universe import KR_ASSET_CORE, US_ASSET_CORE
    for want in ("GLD", "TLT", "DBC", "UUP", "VNQ", "EEM"):
        assert want in US_ASSET_CORE, f"{want}(주식과 다르게 움직이는 자산)가 없다"
    assert len(US_ASSET_CORE) >= 12 and len(KR_ASSET_CORE) >= 3
    # 구조적 장기 손실 상품은 '자산군 확대'라는 이름으로도 담지 않는다.
    for banned in ("VXX", "UVXY", "SVXY", "SQQQ", "TQQQ"):
        assert banned not in US_ASSET_CORE, f"{banned}는 담으면 안 되는 상품이다"


def test_new_names_are_affordable_in_a_million_won_account():
    """1주 값이 비싼 개별주를 더 넣으면 '못 사는 종목'만 늘어난다."""
    src = (ROOT / "quant" / "universe.py").read_text("utf-8")
    assert "lot_infeasible" in src, (
        "왜 ETF 위주인지(1주도 못 사는 문제) 근거가 코드에 없다")
    from quant.universe import KR_ASSET_CORE
    # 한국 자산군 코어는 전부 ETF 코드(6자리 + .KS)여야 한다.
    for s in KR_ASSET_CORE:
        assert s.endswith(".KS") and s[:6].isdigit(), s


def test_it_is_wired_and_the_screen_reads_the_ledger():
    daily = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert 'status["breadth"]' in daily, "status.json에 실효 표본이 안 실린다"
    i = daily.find('status["breadth"] = breadth')
    assert "try:" in daily[max(0, i - 200):i], "계측기가 예외 방벽 없이 배치에 있다"
    page = (ROOT / "docs" / "index.html").read_text("utf-8")
    assert "st.breadth" in page, "첫 화면이 장부에서 읽지 않는다"
    assert "개 몫" in page, "종목 수와 정보량의 구별이 화면 말에 없다"


def test_the_live_meter_runs_on_the_real_ledger():
    out = B.breadth("state")
    if out is None:
        return
    a = out["all"]
    assert a["n"] >= 1
    if a.get("effective_n") is not None:
        assert 0 < a["effective_n"] <= a["n"] + 1e-9, (
            f"실효 표본({a['effective_n']})이 종목 수({a['n']})보다 크다 — 불가능")
        assert not math.isnan(a["effective_n"])


# ── 종목이 늘어도 밤 배치가 잘리지 않는가 (2026-08-19) ──────────────
#
# 실측: 20종목 재학습에 34.5분. 45종목이면 78분쯤인데 잡 한도는 45분이다.
# 한도를 올리면 "재학습이 끝난 뒤 배치가 시작한다"는 파이프라인 계약이
# 깨진다 — 배치가 그날 승격된 챔피언을 놓친다. 그래서 한도를 올리는 대신
# 시간 예산 안에서 돌고 **못 돈 종목을 다음 밤에 먼저 돈다.**

def test_the_retrain_yields_before_the_job_is_killed(tmp_path, monkeypatch):
    """예산을 넘기면 남은 종목을 남기고 멈춘다 — 잡이 통째로 죽는 것보다 낫다."""
    import quant.live.retrain as R

    monkeypatch.setenv("QUANT_RETRAIN_BUDGET_SEC", "0.05")
    calls = []

    def _fake(market, symbol, **kw):
        # 종목마다 실제로 시간을 쓴다 — 즉시 반환하는 가짜로는 예산이
        # 넘는 상황 자체가 재현되지 않는다(검사가 아무것도 안 지킨다).
        time.sleep(0.03)
        calls.append(f"{market}:{symbol}")
        return {"skipped": False, "promoted": False}

    monkeypatch.setattr(R, "run_retrain", _fake)
    tgt = [("crypto", f"C{i}/USDT") for i in range(6)]
    out = R.run_retrain_all(targets=tgt, state_dir=str(tmp_path))
    assert len(calls) < len(tgt), (
        f"예산이 0인데 {len(calls)}종목을 다 돌았다 — 잡이 시간 초과로 죽는다")
    cur = json.loads((tmp_path / "retrain_cursor.json").read_text("utf-8"))
    assert cur["next_key"], "다음 밤이 어디서 이어받을지 기록이 없다"
    assert cur["not_reached"], "못 돈 종목을 기록하지 않았다 — 조용히 줄어든다"
    assert isinstance(out, dict)


def test_tomorrow_starts_where_tonight_stopped(tmp_path, monkeypatch):
    """이어달리기 — 어제 못 돈 종목이 오늘 맨 앞에 온다(영영 안 도는 종목 방지)."""
    import quant.live.retrain as R

    (tmp_path / "retrain_cursor.json").write_text(
        json.dumps({"next_key": "crypto:C3/USDT"}), "utf-8")
    monkeypatch.setenv("QUANT_RETRAIN_BUDGET_SEC", "300")
    seen = []
    monkeypatch.setattr(R, "run_retrain",
                        lambda m, s, **kw: (seen.append(f"{m}:{s}"),
                                            {"skipped": False})[1])
    tgt = [("crypto", f"C{i}/USDT") for i in range(6)]
    R.run_retrain_all(targets=tgt, state_dir=str(tmp_path))
    assert seen[0] == "crypto:C3/USDT", (
        f"어제 멈춘 지점에서 이어받지 않는다: {seen[:2]}")
    assert len(seen) == len(tgt), "예산이 충분한데 다 안 돌았다"


def test_the_pipeline_contract_is_still_intact():
    """한도를 올려서 계약을 깨는 방식으로 도망치지 않았는가."""
    import yaml
    d = yaml.safe_load((ROOT / ".github" / "workflows"
                        / "nightly-retrain.yml").read_text("utf-8"))
    assert d["jobs"]["retrain"]["timeout-minutes"] <= 60, (
        "재학습 한도를 늘려 파이프라인 여유를 잡아먹었다")
    step = [s for s in d["jobs"]["retrain"]["steps"]
            if "retrain --all" in str(s.get("run", ""))][0]
    assert step["env"].get("QUANT_RETRAIN_BUDGET_SEC"), (
        "시간 예산이 주입되지 않는다 — 45종목이면 한도에 잘린다")
