"""감사 로그가 매매를 죽일 수 있었다 (감사 174).

`record_order`는 주문을 **보낸 뒤에** 불린다. 실행된 주문 한 건을 JSONL로
덧붙이는 곁가지 기록이다. 독스트링에도 이렇게 적혀 있다 —
"실패해도 예외를 삼킨다".

그런데 실제로는 한 종류만 삼켰다.

    except OSError:
        pass

직렬화가 실패하는 두 경우가 그대로 새어 나갔다.

    datetime 키 등 직렬화 불가 키 → TypeError
    순환 참조                     → ValueError

여기서 죽으면 **돈은 이미 움직였는데 배치가 그 자리에서 멈춘다.** 남은
종목은 처리되지 않고, 방금 낸 주문은 장부에도 안 남는다. 가장 나쁜 순간의
실패다. 그리고 약속(독스트링)과 코드가 어긋나 있었다 — 읽는 사람은 안전한
줄 안다(FROZEN_IDEAS ㊾).

──────────────────────────────────────────────────────────────
같은 파일의 죽은 손잡이

`build_review(history, periods_per_year=365)`가 그 인자를 **본문에서 한 번도
쓰지 않았다.** 그런데 CLI는 시장에 맞춰(코인 365 / 주식 252) 값을 성실히
계산해 넘기고 있었다. 고르면 뭔가 달라질 것처럼 보이지만 아무 일도 안 난다.
`trade_stats`에 연율화 지표가 없어 쓸 자리 자체가 없다 — 지웠다.
"""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.journal import (  # noqa: E402
    build_review,
    load_orders,
    record_order,
    review_state_file,
)

ORDER = {"symbol": "BTC/USDT", "side": "buy", "quantity": 0.1, "price": 60000.0}


def _circular() -> dict:
    d: dict = {}
    d["self"] = d
    return d


# ── 어떤 실패도 매매를 멈추면 안 된다 ─────────────────────────


@pytest.mark.parametrize("label,context", [
    ("직렬화 불가 키", {datetime.date(2024, 1, 1): 1}),
    ("순환 참조", {"x": _circular()}),
    ("직렬화 불가 값", {"obj": object()}),
])
def test_a_broken_context_does_not_raise(tmp_path, label, context):
    """주문은 이미 나갔다 — 기록이 실패해도 배치는 계속 가야 한다."""
    record_order(tmp_path / "orders.jsonl", ORDER, context)   # 예외가 없으면 통과


def test_an_unwritable_path_does_not_raise(tmp_path):
    """디스크·권한 문제도 마찬가지다."""
    blocked = tmp_path / "afile"
    blocked.write_text("not a dir")
    record_order(blocked / "orders.jsonl", ORDER, {"time": "t"})


def test_the_failure_is_logged_not_silent(tmp_path, caplog):
    """삼키되 숨기지는 않는다 — 기록이 빈 이유를 나중에 알 수 있어야 한다."""
    import logging

    with caplog.at_level(logging.WARNING):
        record_order(tmp_path / "o.jsonl", ORDER, {"x": _circular()})
    assert any("감사 로그" in r.message for r in caplog.records), caplog.text


# ── 대조군: 정상 기록은 온전해야 한다 ─────────────────────────


def test_a_normal_order_is_recorded_completely(tmp_path):
    p = tmp_path / "orders.jsonl"
    record_order(p, ORDER, {"time": "2024-01-01T00:00:00", "mode": "live"})
    got = load_orders(p)
    assert len(got) == 1
    assert got[0]["symbol"] == "BTC/USDT" and got[0]["mode"] == "live"
    assert got[0]["quantity"] == pytest.approx(0.1)


def test_records_append_and_survive_a_broken_one_in_between(tmp_path):
    """망가진 한 건이 앞뒤 기록을 날리면 안 된다."""
    p = tmp_path / "orders.jsonl"
    record_order(p, {**ORDER, "order_id": "A"}, {"time": "t1"})
    record_order(p, {**ORDER, "order_id": "B"}, {"x": _circular()})   # 실패
    record_order(p, {**ORDER, "order_id": "C"}, {"time": "t3"})
    ids = [r.get("order_id") for r in load_orders(p)]
    assert ids == ["A", "C"], ids


def test_a_corrupt_line_is_skipped_not_fatal(tmp_path):
    """append-only 파일은 중간이 잘릴 수 있다 — 읽기가 통째로 죽으면 안 된다."""
    p = tmp_path / "orders.jsonl"
    record_order(p, {**ORDER, "order_id": "A"}, {})
    with p.open("a", encoding="utf-8") as f:
        f.write('{"order_id": "B", broken\n')
    record_order(p, {**ORDER, "order_id": "C"}, {})
    assert [r.get("order_id") for r in load_orders(p)] == ["A", "C"]


def test_a_missing_file_reads_as_empty(tmp_path):
    assert load_orders(tmp_path / "nope.jsonl") == []


# ── 죽은 손잡이가 사라졌는가 ──────────────────────────────────


def test_the_review_no_longer_takes_a_parameter_it_ignores():
    """쓰지 않는 인자를 받으면 '고르면 달라진다'는 오해가 생긴다."""
    import inspect

    assert "periods_per_year" not in inspect.signature(build_review).parameters
    assert "periods_per_year" not in inspect.signature(
        review_state_file).parameters
    cli = (ROOT / "quant" / "cli.py").read_text("utf-8")
    assert "review_state_file(args.state, periods_per_year" not in cli, (
        "CLI가 아직 쓰이지 않는 값을 넘긴다")


# ── 복기 통계 자체의 계약 ─────────────────────────────────────


def test_a_round_trip_is_counted_once():
    """정답을 손으로 아는 자료 — 진입 후 청산 한 번 = 거래 1건."""
    hist = [{"equity": 100.0, "weight": 0.0},
            {"equity": 100.0, "weight": 1.0},
            {"equity": 110.0, "weight": 1.0},
            {"equity": 120.0, "weight": 0.0}]
    rev = build_review(hist)
    assert rev["num_trades"] == 1, rev
    assert rev["total_return"] == pytest.approx(0.2), rev


def test_too_few_points_is_reported_as_no_trades():
    """대조군 — 자료가 없으면 없다고 해야지 억지 통계를 내면 안 된다."""
    rev = build_review([{"equity": 100.0, "weight": 1.0}])
    assert rev["num_trades"] == 0 and rev["n_points"] == 1


def test_a_missing_state_file_is_not_an_error(tmp_path):
    rev = review_state_file(tmp_path / "none.json")
    assert rev["num_trades"] == 0


def test_a_corrupt_state_file_is_not_an_error(tmp_path):
    p = tmp_path / "state.json"
    p.write_text("{broken", encoding="utf-8")
    assert review_state_file(p)["num_trades"] == 0


def test_the_review_reads_a_real_ledger_shape(tmp_path):
    """장부 형태(추가 칸이 많은 dict)를 그대로 넣어도 읽혀야 한다."""
    hist = [{"date": "2024-01-0%d" % (i + 1), "equity": 100.0 + 10 * i,
             "weight": 1.0 if i % 2 else 0.0, "price": 1.0, "hit_rate": None}
            for i in range(6)]
    p = tmp_path / "state.json"
    p.write_text(json.dumps({"history": hist}), encoding="utf-8")
    assert review_state_file(p)["n_points"] == 6
