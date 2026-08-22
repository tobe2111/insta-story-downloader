"""먼저 기록한 쪽이 이기면 안 된다 (2026-08-19 실측 사고).

무슨 일이 있었나: 사흘 멈춘 배치를 살리려고 04:18 UTC에 수동으로 한 번
돌렸다. 그날의 정규 밤 배치는 22:15/22:30이고, 과최적화 검증 결과는 그
사이인 20:59에 도착했다. 밤 배치 두 번은 **정상 성공했는데도 아무것도
바꾸지 못했다** — 멱등 가드가 "오늘 봉은 이미 기록됨"이라며 건너뛴 것이다.
그래서 계좌는 오후 1시의 낡은 검증(20종목 중 18종목 '미측정')으로 하루를
굴렀고, 같은 날 머지된 유니버스 확대도 반영되지 않았다.

멱등 가드 자체는 옳다 — 그냥 다시 돌리면 그날 매매가 두 번 일어나 비용이
두 배가 된다. 그래서 답은 "다시 돌리자"가 아니라 **되돌림 지점**이다.

지켜야 할 약속:
- 재료가 그대로면 예전처럼 건너뛴다(이게 기본값이다).
- 검증 장부가 새로 왔을 때만 다시 돌린다.
- 되돌림 지점이 없거나 **다른 봉의 것**이면 다시 돌리지 않는다 — 추측하지
  않고 안전한 쪽(건너뜀)으로 실패한다.
- 되돌리면 계좌가 **계산 전 상태 그대로**여야 한다. 반쯤 되돌린 채로
  계산을 시작하는 것이 가장 나쁘다.
- 되돌림은 오늘 한 줄만 걷어낸다 — 지난 날짜 기록은 손대지 않는다.
- 같은 날짜라도 종목 수가 늘면 '새 재료'다(2026-08-19이 정확히 그랬다:
  아침 2종목 → 밤 20종목, 날짜는 같음).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live import redo as R                            # noqa: E402


def _state():
    return {"cash": 1000.0,
            "positions": {"A": {"quantity": 1.0, "avg_price": 10.0}},
            "prev_weights": {"A": 0.5},
            "last_bar": "2026-08-18",
            "history": [{"date": "2026-08-18", "equity": 990.0}]}


def _run_a_bar(st, bar, stamp, cash, positions):
    """하루치 계산을 흉내낸다 — 되돌림 지점을 찍고 상태를 바꾼 뒤 한 줄 적는다."""
    R.mark_restore_point(st, bar)
    st["cash"] = cash
    st["positions"] = positions
    st["last_bar"] = bar
    st["history"].append({"date": bar, "equity": cash, "validation_stamp": stamp})


def _ledger(tmp_path, symbols, asof="2026-08-19"):
    d = tmp_path
    d.mkdir(exist_ok=True)
    (d / "validation.json").write_text(json.dumps(
        {f"crypto:S{i}": {"asof": asof, "pbo": 0.1} for i in range(symbols)}),
        "utf-8")
    return str(d)


def test_the_same_ingredients_still_mean_skip(tmp_path):
    """기본값은 예전 그대로 — 재료가 안 바뀌면 다시 돌리지 않는다."""
    sd = _ledger(tmp_path / "a", 2)
    st = _state()
    _run_a_bar(st, "2026-08-19", R.validation_stamp(sd), 1010.0, {"B": {}})
    redo, why = R.should_redo(st, "2026-08-19", sd)
    assert redo is False, f"재료가 그대로인데 다시 돌린다: {why}"
    assert "그대로" in why


def test_new_validation_on_the_same_day_counts_as_new_ingredients(tmp_path):
    """날짜가 같아도 종목이 늘면 새 재료다 — 실제 사고가 정확히 이 모양이었다."""
    morning = _ledger(tmp_path / "m", 2)
    st = _state()
    _run_a_bar(st, "2026-08-19", R.validation_stamp(morning), 1010.0, {"B": {}})
    night = _ledger(tmp_path / "n", 20)          # 같은 날짜, 종목 20개
    redo, why = R.should_redo(st, "2026-08-19", night)
    assert redo is True, f"밤에 20종목이 들어왔는데 안 돌린다: {why}"
    assert "바뀌었다" in why


def test_rewinding_puts_the_account_back_exactly(tmp_path):
    sd = _ledger(tmp_path / "a", 2)
    st = _state()
    before = json.dumps({k: v for k, v in st.items() if k != "history"},
                        sort_keys=True)
    _run_a_bar(st, "2026-08-19", R.validation_stamp(sd), 1.0, {"Z": {}})
    assert R.rewind(st, "2026-08-19") is True
    after = json.dumps({k: v for k, v in st.items()
                        if k not in ("history", R.RESTORE_KEY)}, sort_keys=True)
    assert after == before, (
        f"되돌렸는데 계좌가 계산 전과 다르다\n전: {before}\n후: {after}")
    assert [h["date"] for h in st["history"]] == ["2026-08-18"], (
        "오늘 한 줄만 걷어내야 하는데 다른 날까지 건드렸다")


def test_a_missing_or_mismatched_point_never_rewinds(tmp_path):
    sd = _ledger(tmp_path / "a", 20)
    st = _state()                                 # 되돌림 지점이 아예 없다
    st["history"].append({"date": "2026-08-19", "equity": 1.0,
                          "validation_stamp": "2026-08-19/2"})
    assert R.should_redo(st, "2026-08-19", sd)[0] is False
    assert R.rewind(st, "2026-08-19") is False
    # 다른 봉의 지점이 남아 있는 경우 — 이걸 쓰면 어제 상태로 되감긴다
    R.mark_restore_point(st, "2026-08-18")
    assert R.should_redo(st, "2026-08-19", sd)[0] is False, (
        "다른 봉의 되돌림 지점으로 오늘을 되감으려 한다")
    assert R.rewind(st, "2026-08-19") is False
    assert len(st["history"]) == 2, "되돌리지 않기로 해 놓고 기록을 건드렸다"


def test_a_record_without_a_stamp_is_never_redone(tmp_path):
    """어떤 재료를 썼는지 모르는 기록은 다시 돌리지 않는다(옛 기록 보호)."""
    sd = _ledger(tmp_path / "a", 20)
    st = _state()
    R.mark_restore_point(st, "2026-08-19")
    st["history"].append({"date": "2026-08-19", "equity": 1.0})   # stamp 없음
    redo, why = R.should_redo(st, "2026-08-19", sd)
    assert redo is False and "남아 있지 않" in why


def test_an_unreadable_ledger_is_not_new_ingredients(tmp_path):
    d = tmp_path / "broken"
    d.mkdir()
    (d / "validation.json").write_text("{{{", "utf-8")
    assert R.validation_stamp(str(d)) == "", "깨진 장부를 지문으로 만든다"
    st = _state()
    R.mark_restore_point(st, "2026-08-19")
    st["history"].append({"date": "2026-08-19", "validation_stamp": "x/2"})
    assert R.should_redo(st, "2026-08-19", str(d))[0] is False, (
        "장부를 못 읽는 것을 '새 재료'로 읽어 매일 다시 돌린다")


def test_the_snapshot_is_everything_not_a_chosen_few():
    """복사 목록을 손으로 고르면 언젠가 새 필드가 빠지고, 돈이 틀린다."""
    st = {"cash": 1.0, "positions": {}, "새필드": {"깊은": [1, 2]},
          "history": [{"date": "d"}]}
    R.mark_restore_point(st, "b")
    snap = st[R.RESTORE_KEY]["state"]
    assert "새필드" in snap, "화이트리스트로 고르고 있다 — 새 필드가 빠진다"
    assert "history" not in snap, "기록까지 복사하면 되돌림이 기록을 되살린다"
    st["새필드"]["깊은"].append(3)
    assert snap["새필드"]["깊은"] == [1, 2], "얕은 복사라 원본과 같이 변한다"


def test_the_pipeline_actually_uses_it():
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert "mark_restore_point(st, bar)" in src, "되돌림 지점을 안 찍는다"
    assert "should_redo(st, bar, state_dir)" in src, "다시 돌릴지 안 묻는다"
    assert '"validation_stamp": val_stamp' in src, (
        "어떤 검증 장부를 썼는지 기록에 안 남는다 — 그러면 다음 실행이 "
        "판단할 근거가 없다")
