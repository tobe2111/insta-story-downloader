"""내림에 거는 것이 도움이 되는지를 **기계가 판정**한다.

사장님 (2026-09-03): *"하락장에선 대응 여력없이 수익을 못내네..?
특히 선물은 롱숏 포지션 다 가능한데 더 손해가 커."*

선물 트랙 문서는 "나란히 돌려서 잰다"고 적혀 있었는데 **나란히 도는 반대쪽이
없었다.** 같은 챔피언이 롱 전용이었으면 얼마였을지를 아무도 계산하지 않았다.

여기서 지키는 약속:

  ① 방향을 쓸지 말지를 **사람이 정하지 않는다** — 장부의 판정이 정한다.
  ② **판정이 없으면 막지 않는다.** 못 잰 것과 나쁜 것은 다른 사건이다.
  ③ **유의하지 않은 것도 막지 않는다.** "아직 모른다"는 "끄라"가 아니다.
  ④ 관측 단위는 종목이 아니라 **날짜**다(패널 관문과 같은 자).
  ⑤ 숏을 못 내는 챔피언은 **'차이 0'으로 담지 않는다** — 없는 것을 관측으로
     세면 패널 평균이 인위적으로 0쪽으로 끌린다.
  ⑥ 밤의 열쇠는 **한국 달력일**이다(마지막 봉 날짜도 UTC 날짜도 아니다).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live import direction_gate as dg  # noqa: E402


def _series(vals, start="2026-01-01"):
    idx = pd.date_range(start, periods=len(vals), freq="D")
    return pd.Series(vals, index=idx, dtype=float)


def _panel(n_symbols=6, n_dates=60, value=0.0):
    return {f"m:S{i}": _series([value] * n_dates) for i in range(n_symbols)}


# ── ① 손잡이는 스펙 하나만 바꾼다 ──────────────────────────────────────
def test_the_twin_differs_only_by_direction():
    spec = {"strategy": "ml", "params": {"model": "gb", "threshold": 0.6}}
    two = dg.two_sided_spec(spec)
    assert two["params"]["allow_short"] is True
    assert {k: v for k, v in two["params"].items() if k != "allow_short"} \
        == spec["params"], "방향 말고 다른 것이 같이 바뀌었다"
    assert spec["params"].get("allow_short") is None, "원본이 오염됐다"


def test_a_rule_champion_is_not_probed():
    """규칙 전략은 음수 신호를 아예 안 낸다 — 잴 것이 없다."""
    assert dg.can_probe({"strategy": "ml", "params": {}}) is True
    assert dg.can_probe({"strategy": "ma_cross", "params": {}}) is False
    assert dg.can_probe(None) is False


# ── ② 판정이 없으면 막지 않는다 ────────────────────────────────────────
def test_no_verdict_does_not_block(tmp_path):
    ok, why = dg.two_sided_allowed(str(tmp_path))
    assert ok is True and why is None, (ok, why)


def test_a_skipped_night_does_not_block(tmp_path):
    """재료가 모자라 못 잰 밤은 **위반이 아니다.**"""
    from quant.live.retrain import night_key
    dg.record({"night": night_key(), "skipped": True, "n_symbols": 2,
               "reason": "종목이 모자랍니다"}, str(tmp_path))
    assert dg.two_sided_allowed(str(tmp_path))[0] is True


def test_an_insignificant_verdict_does_not_block(tmp_path):
    """'아직 모른다'는 '끄라'가 아니다 — 그러면 실험이 첫날에 죽는다."""
    rec = dg.judge(_panel(value=-1e-6), night="2026-09-03",
                   n_symbols_seen=6, state_dir=str(tmp_path))
    assert not rec.get("skipped"), rec
    assert abs(float(rec["t_stat"])) < rec["t_threshold"]
    dg.record({**rec, "night": _today()}, str(tmp_path))
    assert dg.two_sided_allowed(str(tmp_path))[0] is True


def _today():
    from quant.live.retrain import night_key
    return night_key()


# ── ③ 유의하게 나쁠 때만 끈다 ──────────────────────────────────────────
def _skewed(sign):
    """부호가 뚜렷한 패널 — 잡음 위에 한쪽으로 치우친 평균.

    ⚠️ 값이 **거의 상수**면 t가 0으로 나온다(``degenerate_spread``가 퇴화한
       분산을 막는다). 그러니 잡음을 실제로 넣어야 이 검사가 관문을 잰다 —
       처음에 상수로 썼다가 "뚜렷하게 나쁜데 안 껐다"는 거짓 실패를 봤다.
    """
    import random

    rng = random.Random(7)
    out = {}
    for i in range(6):
        vals = [sign * 0.01 + rng.gauss(0.0, 0.004) for _ in range(60)]
        out[f"m:S{i}"] = _series(vals)
    return out


def test_a_clearly_bad_direction_turns_two_sided_off(tmp_path):
    rec = dg.judge(_skewed(-1), night=_today(), n_symbols_seen=6,
                   state_dir=str(tmp_path))
    assert float(rec["t_stat"]) < -rec["t_threshold"], rec
    dg.record(rec, str(tmp_path))
    ok, why = dg.two_sided_allowed(str(tmp_path))
    assert ok is False, (ok, why)


def test_a_clearly_good_direction_keeps_two_sided_on(tmp_path):
    rec = dg.judge(_skewed(+1), night=_today(), n_symbols_seen=6,
                   state_dir=str(tmp_path))
    dg.record(rec, str(tmp_path))
    assert dg.two_sided_allowed(str(tmp_path))[0] is True


def test_a_stale_verdict_is_not_used(tmp_path):
    """낡은 판정으로 오늘을 막지 않는다 — 그 사이 챔피언이 바뀐다."""
    import datetime as _dt
    old = (_dt.date.fromisoformat(_today())
           - _dt.timedelta(days=dg.MAX_AGE_NIGHTS + 1)).isoformat()
    rec = dg.judge(_skewed(-1), night=old, n_symbols_seen=6,
                   state_dir=str(tmp_path))
    dg.record(rec, str(tmp_path))
    assert dg.two_sided_allowed(str(tmp_path))[0] is True, "낡은 판정이 막았다"


# ── ④ 관측 단위는 날짜다 ───────────────────────────────────────────────
def test_symbols_cannot_stand_in_for_dates(tmp_path):
    """종목을 아무리 늘려도 **날짜가 짧으면** 판정하지 않는다.

    "40종목 × 60봉 = 2,400표본"으로 세면 관문이 거짓으로 열린다.
    """
    thin = {f"m:S{i}": _series([0.01] * 5) for i in range(40)}
    rec = dg.judge(thin, night=_today(), n_symbols_seen=40,
                   state_dir=str(tmp_path))
    assert rec["skipped"] is True and rec["n_dates"] < 40, rec


def test_one_symbol_is_not_a_panel(tmp_path):
    rec = dg.judge({"m:S0": _series([0.01] * 200)}, night=_today(),
                   n_symbols_seen=1, state_dir=str(tmp_path))
    assert rec["skipped"] is True, rec


# ── ⑤ 못 잰 종목은 이유와 함께 남는다 ─────────────────────────────────
def test_the_ledger_says_why_a_symbol_was_not_measured(tmp_path):
    rec = dg.judge({}, night=_today(), n_symbols_seen=8,
                   state_dir=str(tmp_path),
                   long_only=["crypto:BTC/USDT"],
                   unmeasured={"us_stock:AAPL": "봉이 짧습니다"})
    assert rec["long_only_symbols"] == ["crypto:BTC/USDT"]
    assert rec["unmeasured"] == {"us_stock:AAPL": "봉이 짧습니다"}
    # 재료가 0인 밤에도 **줄을 남긴다** — 안 남기면 "못 쟀다"(고장)와
    # "밤 배치가 안 돌았다"가 장부에서 똑같이 보인다.
    assert rec["n_symbols_seen"] == 8
    dg.record(rec, str(tmp_path))
    assert (tmp_path / dg.DIRECTION_FILE).exists()


def test_a_long_only_champion_is_not_counted_as_a_zero():
    """규칙 전략을 '차이 0'으로 담으면 패널 평균이 0쪽으로 끌린다."""
    src = (ROOT / "quant" / "live" / "retrain.py").read_text("utf-8")
    assert "direction_probe_skipped" in src, (
        "숏을 못 내는 챔피언이 왜 빠졌는지 장부에 안 남는다")
    assert "if dseries is not None and len(dseries):" in src, (
        "빈 계열을 그대로 담으면 없는 관측이 패널에 들어간다")


# ── ⑥ 밤의 열쇠는 한국 달력일 ──────────────────────────────────────────
def test_the_night_key_is_the_korean_calendar_day():
    src = (ROOT / "quant" / "live" / "direction_gate.py").read_text("utf-8")
    assert "night_key" in src, "밤을 세는데 night_key를 안 쓴다"
    assert "date.today()" not in src, (
        "UTC 달력일로 밤을 세면 자정을 넘긴 2회차가 새 밤이 된다")


def test_two_rounds_of_one_night_merge_by_dates(tmp_path):
    """같은 밤의 두 회차는 **날짜별 합·개수로** 합친다.

    서로 다른 종목 집합에서 나온 두 t로 union 의 t 를 만들 수는 없다.
    """
    a = dg.judge({f"a{i}": _series([0.001] * 60) for i in range(3)},
                 night=_today(), n_symbols_seen=3, state_dir=str(tmp_path))
    b = dg.judge({f"b{i}": _series([0.001] * 60) for i in range(3)},
                 night=_today(), n_symbols_seen=3, state_dir=str(tmp_path))
    # 각각은 종목이 3개라 판정이 안 된다.
    assert a["skipped"] and b["skipped"], (a["reason"], b["reason"])
    dg.record(a, str(tmp_path))
    dg.record(b, str(tmp_path))
    merged = dg.nights(str(tmp_path))[_today()]
    # 합치면 6종목이 되어 판정이 선다 — 거르기는 **합친 뒤 한 번만** 한다.
    assert merged["merged"] is True
    assert not merged.get("skipped"), merged
    assert merged["n_symbols"] == 6, merged


def test_overlapping_rounds_are_not_merged(tmp_path):
    """두 회차가 같은 종목을 보면 합치지 않는다 — 두 표를 행사하면 t가 부푼다."""
    same = {f"a{i}": _series([0.001] * 60) for i in range(6)}
    for _ in range(2):
        dg.record(dg.judge(same, night=_today(), n_symbols_seen=6,
                           state_dir=str(tmp_path)), str(tmp_path))
    merged = dg.nights(str(tmp_path))[_today()]
    assert merged.get("skipped") is True, merged
    assert "겹" in str(merged.get("reason")), merged


# ── ⑦ 문턱은 패널 관문과 같은 값이다 ───────────────────────────────────
def test_the_threshold_is_borrowed_not_invented():
    from quant.live.retrain import PANEL_T_REF
    assert dg.t_threshold() == float(PANEL_T_REF), (
        "방향만 문턱이 다르면 그건 관문이 아니라 편의다")


# ── ⑧ 선물 트랙이 그 판정을 **실제로** 따른다 ─────────────────────────
def test_the_futures_track_asks_before_going_two_sided():
    from quant.live import futures_challenger as fc
    src = __import__("inspect").getsource(fc.run_futures_round)
    assert "direction_gate.two_sided_allowed(state_dir)" in src, (
        "판정을 조회하지 않으면 관문이 아니라 장식이다")
    assert "allow_two_sided=two_sided_ok" in src, (
        "조회해 놓고 안 쓰면 화면만 바뀌고 매매는 그대로다")


def test_a_blocked_direction_actually_makes_the_signal_long_only(monkeypatch):
    from quant.live import futures_challenger as fc
    monkeypatch.setattr(fc, "_spec",
                        lambda sym, sd: {"strategy": "ml",
                                         "params": {"model": "logreg"}})
    _, two = fc.build_two_sided("BTC/USDT", "state", allow_two_sided=True)
    assert two is True
    _, two = fc.build_two_sided("BTC/USDT", "state", allow_two_sided=False)
    assert two is False, "관문이 닫혔는데 양방향으로 세웠다"


def test_the_round_records_the_direction_verdict():
    from quant.live import futures_challenger as fc
    src = __import__("inspect").getsource(fc.run_futures_round)
    assert 'rec["direction_gate"]' in src, (
        "판정을 안 남기면 '아직 못 쟀다'와 '재 보니 괜찮더라'가 같아진다")
    rep_src = __import__("inspect").getsource(fc.public_report)
    assert '"direction_gate"' in rep_src, "화면 재료에 판정이 없다"


# ── ⑨ 오디션이 재료를 실제로 줍는다 ───────────────────────────────────
def test_the_audition_collects_the_material_in_the_same_replay():
    """챔피언 재생은 한 번이므로 추가 비용은 **백테스트 1회**다."""
    src = (ROOT / "quant" / "live" / "retrain.py").read_text("utf-8")
    assert "direction_probe: bool = False" in src
    assert "direction_probe=True)" in src, "밤 배치가 재료를 안 줍는다"
    assert 'result["direction_diff"]' in src
    # ⚠️ 재현 검증(verify)은 이 비용을 낼 이유가 없다 — 기본값이 꺼짐이어야 한다.
    assert "direction_probe: bool = True" not in src


def test_the_nightly_batch_writes_a_row_even_when_nothing_was_measured():
    src = (ROOT / "quant" / "live" / "retrain.py").read_text("utf-8")
    i = src.index("direction_gate.record(")
    assert "if direction_diffs" not in src[max(0, i - 400):i], (
        "재료가 0인 밤에 줄을 안 남기면 '고장'과 '배치 미실행'이 같아 보인다")


# ── ⑩ 화면이 그 말을 영어로도 할 수 있어야 한다 ───────────────────────
#
# ⚠️ **판정이 뒤집힌 날의 문구는 평소 화면에 안 나온다.** 그래서 영어 화면
#    검사가 그 문구를 영영 못 보고, 실제로 뒤집히는 날 공개 페이지에서
#    처음 한국어가 뜬다. 사전을 직접 읽어 미리 못 박는다.
_DICT = ROOT / "docs" / "assets" / "i18n-en.js"


@pytest.mark.parametrize("phrase", [
    "지금은 오를 때만 삽니다.",
    "지금은 오를 때와 내릴 때 모두 겁니다.",
    "내림에 거는 쪽이 뚜렷하게 나빠서 잠시 껐습니다.",
    "아직 좋다고도 나쁘다고도 말할 수 없는 자리라 실험을 계속합니다.",
    "밤 심사가 여러 종목을 가로질러 잰 점수(문턱을 넘으면 판정이 바뀝니다):",
    "잰 범위(종목 수 · 날짜 수):",
])
def test_the_direction_wording_is_already_translated(phrase):
    d = _DICT.read_text("utf-8")
    assert f'"{phrase}"' in d, f"방향 관문 문구가 사전에 없다: {phrase}"


def test_the_page_and_the_dictionary_use_the_same_sentences():
    """화면이 쓰는 문장과 사전 열쇠가 갈리지 않는다.

    한국어 화면은 멀쩡해서, 갈려도 **영어에서만** 조용히 끊긴다.
    """
    page = (ROOT / "docs" / "futures.html").read_text("utf-8")
    d = _DICT.read_text("utf-8")
    for phrase in ("지금은 오를 때만 삽니다.",
                   "잰 범위(종목 수 · 날짜 수):"):
        assert phrase in page, f"화면에 없는 문장을 사전이 들고 있다: {phrase}"
        assert f'"{phrase}"' in d


# ── ⑪ 장부는 자기 비용 기준을 함께 적는다 ─────────────────────────────
def test_the_verdict_carries_its_cost_basis(tmp_path):
    rec = dg.judge(_panel(), night=_today(), n_symbols_seen=6,
                   state_dir=str(tmp_path))
    assert rec["cost_basis_bp"], "비용 기준 없이 수익 차를 판정했다"
    # 펀딩비가 빠졌다는 사실을 **칸으로** 남긴다 — 안 남기면 나중에
    # "왜 선물 실적과 안 맞나"에 장부가 답할 수 없다.
    assert rec["funding_excluded"] is True
    json.dumps(rec, ensure_ascii=False)      # 장부에 그대로 적힐 수 있는가
