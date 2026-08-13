"""장부를 쓰는 마지막 관문 — 무엇이 들어와도 그날 기록을 잃지 않는가 (감사 200).

훑은 파일: `quant/utils/jsonio.py`. 36곳이 이 함수를 통해 상태·장부를 쓴다.

**결함은 없었다. 구멍이 하나 있었다.**

이 모듈은 첫 줄부터 "NaN이 저장을 멈추는 것을 막는다"고 적어 두고, 그 이유까지
남겨 놓았다 — *"allow_nan=False로 raise시키면 cycle의 except가 삼켜 저장이
아예 멈춘다."* 즉 **"예외가 나면 그날 장부가 사라진다"**는 것을 알고 만들어졌다.

그런데 **같은 except가 삼키는 다른 예외**는 막지 않고 있었다. 실측(고치기 전):

    float('nan')      → None       (설계대로 막힌다)
    np.float64('nan') → None       (float의 하위 클래스라 막힌다)
    np.float32(1.5)   → TypeError   ← 저장이 통째로 죽는다
    np.int64(7)       → TypeError
    np.bool_(True)    → TypeError
    pandas Timestamp  → TypeError
    datetime · Path   → TypeError

`np.float64`가 통과하는 것이 특히 고약하다 — numpy 값이 들어와도 대개
괜찮으니 안심하게 되는데, `float32`·`int64`·`bool_` 하나가 섞이는 날 그날
기록이 통째로 사라진다. `np.bool_`은 pandas 비교식(`a > b`)이 그냥 내놓는 값이라
필드 하나 추가하다 닿기 쉽다.

⚠️ **지금 새는 곳은 아니다.** 실제 하루치 실행으로 확인했다 — `daily.py`가
   필드마다 `float(...)`로 감싸 두어 비-내장 타입이 장부에 닿지 않는다.
   감사 196에서 "실험이 실제 경로를 지나는지부터 확인할 것"을 배웠으므로
   여기서도 확인했고, **live 결함이 아니라 잠재 구멍이라고 적는다.**
   다만 그 방어는 필드를 추가하는 사람이 매번 기억해야 하는 종류라,
   원천에 최후 수단을 둔다(감사 196에서 ML 피처에 한 것과 같은 판단).

막는 방향은 '거절'이 아니라 '보존'이다 — 하루치 장부를 잃는 것보다 값이
문자열로 남는 편이 낫다. 다만 **조용히** 바뀌면 안 되므로 경고를 남긴다.

그리고 `fold_history`의 "근사가 아니라 등가" 주장은 **사실이었다.**
무작위 200회로 전 구간 계산과 대조해 오차 0을 확인했고, 이 파일이 그
주장을 계약으로 고정한다.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import pathlib
import random
import sys
from contextlib import contextmanager

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.utils.jsonio import atomic_write_json, fold_history  # noqa: E402


@contextmanager
def _quant_logs():
    """`quant` 로거는 propagate=False라 caplog가 아무것도 못 본다(감사 195)."""
    got: list[str] = []

    class _Collect(logging.Handler):
        def emit(self, record):
            got.append(record.getMessage())

    logger = logging.getLogger("quant")
    h = _Collect()
    logger.addHandler(h)
    try:
        yield got
    finally:
        logger.removeHandler(h)


def _roundtrip(tmp_path, value):
    fp = tmp_path / "s.json"
    atomic_write_json(fp, {"v": value})
    return json.loads(fp.read_text(encoding="utf-8"))["v"]


# ── ① 어떤 값도 그날 기록을 죽이지 못한다 ─────────────────────


def test_numpy_scalars_do_not_kill_the_save(tmp_path):
    """numpy 스칼라가 섞여도 저장이 죽지 않고, **값이 보존된다**.

    문자열로 뭉개면 사이트가 숫자로 못 읽는다 — 살리는 것과 뜻을 지키는
    것은 다른 문제다.
    """
    np = pytest.importorskip("numpy")
    assert _roundtrip(tmp_path, np.float32(1.5)) == 1.5
    assert _roundtrip(tmp_path, np.int64(7)) == 7
    assert _roundtrip(tmp_path, np.bool_(True)) is True
    # 비유한값은 numpy에서 와도 None이어야 한다(브라우저 JSON.parse 보호)
    assert _roundtrip(tmp_path, np.float32("nan")) is None
    assert _roundtrip(tmp_path, np.float64("inf")) is None


def test_the_original_nan_contract_still_holds(tmp_path):
    """대조군 — 이 모듈이 원래 막던 것(파이썬 float NaN/inf)은 그대로 막는가.

    새 최후 수단이 옛 방어를 밀어내지 않았는지 본다. `NaN` 토큰이 파일에
    들어가면 브라우저의 JSON.parse가 SyntaxError를 내고 화면이 멈춘다.
    """
    assert _roundtrip(tmp_path, float("nan")) is None
    assert _roundtrip(tmp_path, float("inf")) is None
    assert _roundtrip(tmp_path, -float("inf")) is None
    fp = tmp_path / "s.json"
    atomic_write_json(fp, {"a": float("nan"), "b": [float("inf"), 1.0]})
    raw = fp.read_text(encoding="utf-8")
    assert "NaN" not in raw and "Infinity" not in raw, raw


def test_times_and_paths_keep_their_meaning(tmp_path):
    """시각은 ISO 문자열로 — 뜻이 남아야 나중에 다시 읽을 수 있다."""
    assert _roundtrip(tmp_path, dt.datetime(2026, 8, 13)).startswith("2026-08-13")
    assert _roundtrip(tmp_path, dt.date(2026, 8, 13)) == "2026-08-13"
    assert _roundtrip(tmp_path, pathlib.Path("/tmp/x")) == "/tmp/x"
    assert _roundtrip(tmp_path, {3, 1, 2}) == [1, 2, 3]


def test_a_truly_unknown_value_is_saved_but_says_so(tmp_path):
    """정말 모르는 값도 기록을 죽이지 않되, **조용히** 바뀌지는 않는다.

    조용히 문자열이 되면 다음 사람이 "왜 이 필드가 문자열이지?"에서
    막힌다. 살리는 것과 숨기는 것은 다르다.
    """
    class _Odd:
        def __repr__(self):
            return "<이상한 값>"

    with _quant_logs() as logs:
        got = _roundtrip(tmp_path, _Odd())
    assert got == "<이상한 값>"
    assert [m for m in logs if "JSON으로 바꿀 수 없는" in m], logs

    # 대조군 — 평범한 값에는 경고가 나오면 안 된다(늑대 소년 방지).
    with _quant_logs() as quiet:
        assert _roundtrip(tmp_path, {"a": [1, 2.5, "x", None, True]}) == \
            {"a": [1, 2.5, "x", None, True]}
    assert not [m for m in quiet if "JSON으로 바꿀 수 없는" in m]


def test_the_file_is_still_replaced_atomically(tmp_path):
    """최후 수단이 원자성을 깨지 않았는가 — 실패해도 원본이 남아야 한다."""
    fp = tmp_path / "s.json"
    atomic_write_json(fp, {"good": 1})

    class _Boom:
        def __repr__(self):
            raise RuntimeError("repr조차 실패")

    with pytest.raises(Exception):
        atomic_write_json(fp, {"v": _Boom()})
    assert json.loads(fp.read_text(encoding="utf-8")) == {"good": 1}, (
        "쓰기가 실패했는데 원본이 손상됐다")
    assert not list(tmp_path.glob("*.tmp")), "부분 임시파일이 남았다"


# ── ② 잘라도 값이 같다 — "근사가 아니라 등가" ─────────────────


def _full(hist):
    eq = [h["equity"] for h in hist]
    peak, dd = eq[0], 0.0
    for e in eq:
        peak = max(peak, e)
        dd = min(dd, e / peak - 1.0)
    return eq[-1] / eq[0] - 1.0, dd


def _via_fold(hist, cap, chunk):
    """실제 러너처럼 조금씩 쌓으며 **반복해서** 접는다."""
    kept, summ = [], {}
    for i in range(0, len(hist), chunk):
        kept.extend(hist[i:i + chunk])
        kept, summ = fold_history(kept, summ, cap=cap)
    eq = [h["equity"] for h in kept]
    start = summ.get("start") or eq[0]
    peak = summ.get("peak") or start
    dd = float(summ.get("max_drawdown") or 0.0)
    for e in eq:
        peak = max(peak, e)
        dd = min(dd, e / peak - 1.0)
    return eq[-1] / start - 1.0, dd


def test_folding_is_exactly_equivalent_to_never_truncating():
    """독스트링의 "근사가 아니라 등가"를 실제로 검증한다.

    이 주장이 틀리면 최대낙폭이 저장 상한에 걸린 날부터 저절로 좋아진다 —
    시간이 지나면 스스로 개선되는 위험 지표는 지표가 아니라 위안이다(㊿).
    """
    rng = random.Random(7)
    worst_pnl = worst_dd = 0.0
    for _ in range(200):
        v, hist = 100.0, []
        for _ in range(rng.randint(30, 120)):
            v = max(v * (1 + rng.gauss(0, 0.05)), 1e-6)
            hist.append({"equity": v})
        a = _full(hist)
        b = _via_fold(hist, rng.randint(5, 25), rng.randint(1, 9))
        worst_pnl = max(worst_pnl, abs(a[0] - b[0]))
        worst_dd = max(worst_dd, abs(a[1] - b[1]))
    assert worst_pnl < 1e-9, f"총손익이 어긋난다(최대 {worst_pnl:.2e})"
    assert worst_dd < 1e-9, f"최대낙폭이 어긋난다(최대 {worst_dd:.2e})"


def test_the_truncation_actually_happened():
    """대조군 — 위 검사가 '자르지 않아서' 통과한 것이 아님을 못 박는다."""
    hist = [{"equity": 100.0 + i} for i in range(50)]
    kept, summ = fold_history(list(hist), {}, cap=10)
    assert len(kept) == 10 and summ["dropped"] == 40, summ
    assert summ["start"] == 100.0, "잘린 구간의 최초 자산을 잃었다"


def test_a_record_without_equity_does_not_poison_the_summary():
    """자산 값이 없거나 비유한값인 기록이 섞여도 요약이 망가지지 않는다."""
    hist = ([{"equity": 100.0}, {"nope": 1}, {"equity": float("nan")},
             {"equity": 50.0}] + [{"equity": 60.0}] * 3)
    kept, summ = fold_history(hist, {}, cap=2)
    assert summ["start"] == 100.0 and summ["peak"] == 100.0
    assert abs(summ["max_drawdown"] - (-0.5)) < 1e-12, summ
