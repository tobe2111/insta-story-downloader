"""90일 시계가 **실제로 본 것**을 기준으로 도는가 (감사 271).

무슨 일이 있었나
    이 시스템은 "구조가 바뀌면 성과 통계의 시계를 0일부터 다시 센다"는
    원칙을 갖고 있고, 그 판정 재료가 `FEATURE_SET`이라는 태그다. 그런데
    그 태그는 **사람이 손으로 적는 이름표**다. 무엇을 보겠다는 선언일 뿐,
    그날 밤 실제로 붙은 것과 같다는 보장이 없다.

    실제로 코인 펀딩·미결제약정 관련 피처 3개가 몇 주 동안 하나도 붙지
    않았다(감사 270). 그동안 태그는 내내 같았다. 그리고 그 3개를 되살리는
    순간, **모델이 보는 것은 달라지는데 시계는 안 멈춘다.**

    그러면 "한 세대의 90일"이라며 발표하는 표본이, 앞부분(3개 없음)과
    뒷부분(3개 있음)이 섞인 것이 된다. 90일 뒤에야 "그 표본은 섞여
    있었다"를 알게 된다 — 그때는 되돌릴 방법이 없다.

    이 저장소가 반복해서 잡아 온 계열 그대로다: **선언만 돼 있고 실제와
    맞는지는 아무도 안 보는 장치.**

여기서 지키는 것
  ① 밤마다 **실제로 붙은** 선택 피처가 기록에 남는다.
  ② 그 구성이 달라지면 판정 시계가 그날부터 다시 센다.
  ③ 하루이틀짜리 소스 장애로는 리셋되지 않는다(안 그러면 영원히 90일에
     못 닿는다 — 매일 리셋되는 시계는 없는 시계다).
  ④ 시장을 섞어 날짜로만 묶지 않는다(코인과 주식은 기준 봉 날짜가 다르다).
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live import daily as D  # noqa: E402

F = frozenset


def _write(tmp_path, rows) -> str:
    p = tmp_path / "retrain_history.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows),
                 "utf-8")
    return str(tmp_path)


def _day(back: int) -> str:
    return (dt.date.today() - dt.timedelta(days=back)).isoformat()


def _rec(asof, market, used, feature_set=None):
    from quant.strategies.ml import FEATURE_SET
    return {"asof": asof, "market": market, "symbol": "X",
            "feature_set": feature_set or FEATURE_SET,
            "features_used": list(used)}


# ── ① 실제로 붙은 것이 기록에 남는가 ───────────────────────────

def test_the_retrain_record_carries_what_actually_attached():
    src = (ROOT / "quant" / "live" / "retrain.py").read_text("utf-8")
    assert '"features_used": _features_used(df),' in src, (
        "밤마다 무엇이 실제로 붙었는지 기록에 안 남는다 — 남기지 않으면 "
        "구성이 바뀐 날을 영원히 알 수 없다")


def test_it_reads_the_frame_not_the_declared_tag():
    """선언 태그를 그대로 베끼면 이 장치는 아무것도 안 하는 것이다."""
    import inspect

    from quant.live.retrain import _features_used
    src = inspect.getsource(_features_used)
    assert "optional_features_from_df" in src, (
        "실측이 아니라 선언을 다시 적고 있다")
    assert "FEATURE_SET" not in src


def test_features_used_reflects_the_frame():
    """값으로 확인한다 — 컬럼이 있고 없고에 따라 결과가 달라져야 한다."""
    import numpy as np
    import pandas as pd

    from quant.live.retrain import _features_used
    idx = pd.date_range("2026-01-01", periods=30, freq="D")
    base = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0,
                         "close": np.linspace(1, 2, 30), "volume": 1.0},
                        index=idx)
    bare = _features_used(base)
    withf = _features_used(base.assign(funding=0.0001))
    assert set(bare) < set(withf), (
        f"펀딩 컬럼을 붙였는데 실측 목록이 그대로다: {bare} vs {withf}")


# ── ② 구성이 바뀌면 시계가 다시 센다 ──────────────────────────

def test_a_new_feature_appearing_restarts_the_clock(tmp_path):
    """죽었던 피처가 되살아나면 그날부터 새 세대다.

    이것이 감사 271의 핵심이다 — 안 막으면 90일 표본이 섞인다.
    """
    rows = [_rec(_day(i), "crypto", ["x_btc"]) for i in range(20, 3, -1)]
    rows += [_rec(_day(i), "crypto", ["x_btc", "x_funding", "x_oi_chg5"])
             for i in range(3, -1, -1)]
    gen = D._generation_info(_write(tmp_path, rows))
    assert gen["realized"]["since"] == _day(3), (
        f"펀딩이 되살아난 날을 경계로 안 잡는다: {gen['realized']}")
    assert gen["since"] == _day(3) and gen["days"] == 3, (
        f"경계는 찾았는데 최종 시계에 반영되지 않았다: {gen['since']}")


def test_a_steady_setup_keeps_counting(tmp_path):
    """아무것도 안 바뀌면 시계는 그대로 흘러야 한다 — 매일 리셋은 고장이다."""
    rows = [_rec(_day(i), "crypto", ["x_btc", "x_funding"])
            for i in range(30, -1, -1)]
    gen = D._generation_info(_write(tmp_path, rows))
    # 실행 구조(STRUCTURE_EPOCH)가 최근이면 최종 시계는 그쪽에 눌린다.
    # 여기서 보는 것은 **실측 축이 경계를 만들지 않는다**는 것이다.
    assert gen["realized"]["since"] == _day(30), (
        f"구성이 그대로인데 실측 축이 경계를 만든다: {gen['realized']}")


def test_the_tag_changes_when_the_realized_set_changes(tmp_path):
    """개수가 같아도 **구성**이 다르면 다른 세대다."""
    a = D._generation_info(_write(
        tmp_path, [_rec(_day(i), "crypto", ["x_btc", "x_funding"])
                   for i in range(5, -1, -1)]))["feature_set"]
    b = D._generation_info(_write(
        tmp_path, [_rec(_day(i), "crypto", ["x_btc", "x_spy"])
                   for i in range(5, -1, -1)]))["feature_set"]
    assert a != b, f"피처 2개끼리 구성이 달라도 같은 이름표다: {a}"


def test_an_old_history_without_the_field_changes_nothing(tmp_path):
    """`features_used`가 없던 옛 기록을 '아무것도 안 붙었다'로 읽으면 안 된다.

    그렇게 읽으면 기록을 시작한 날에 없던 변화가 있었던 것처럼 보인다.
    """
    from quant.strategies.ml import FEATURE_SET
    rows = [{"asof": _day(i), "market": "crypto", "symbol": "X",
             "feature_set": FEATURE_SET} for i in range(40, -1, -1)]
    gen = D._generation_info(_write(tmp_path, rows))
    assert "realized" not in gen, "기록에 없는 것을 지어내고 있다"
    assert gen["days"] >= 4, (
        "옛 기록만 있는데 시계가 리셋됐다 — 배포하는 날 통계가 사라진다")


# ── ③ 하루이틀 장애로는 리셋되지 않는다 ───────────────────────

def test_a_one_night_outage_does_not_reset_the_clock(tmp_path):
    """FRED·KRX는 가끔 하룻밤 죽는다. 그때마다 리셋되면 90일은 영영 안 온다."""
    full = ["x_btc", "x_funding"]
    rows = []
    for i in range(20, -1, -1):
        used = ["x_btc"] if i == 7 else full          # 딱 하룻밤 결손
        rows.append(_rec(_day(i), "crypto", used))
    gen = D._generation_info(_write(tmp_path, rows))
    assert gen["realized"]["since"] == _day(20), (
        f"하룻밤 소스 장애가 세대 경계가 됐다: {gen['realized']}")


def test_a_lasting_change_does_reset_it(tmp_path):
    """반대 방향 — 오래 지속되는 변화는 반드시 경계가 돼야 한다.

    ③이 ②를 삼키면 이 장치는 아무것도 안 막는 장식이 된다.
    """
    full = ["x_btc", "x_funding"]
    rows = []
    for i in range(20, -1, -1):
        used = ["x_btc"] if 5 <= i <= 9 else full     # 닷새 연속 결손
        rows.append(_rec(_day(i), "crypto", used))
    gen = D._generation_info(_write(tmp_path, rows))
    assert gen["realized"]["since"] == _day(4), (
        f"닷새짜리 구성 변화를 딸꾹질로 넘겼다: {gen['realized']}")


def test_the_clock_does_not_dip_to_zero_and_come_back(tmp_path):
    """장애가 **끝나기 전에도** 시계가 흔들리면 안 된다.

    허용치를 '나중에 되돌린다'로만 구현하면, 장애 당일에는 시계가 0일차로
    떨어졌다가 다음 날 45일차로 되돌아온다. 숫자가 되돌아오는 것 자체가
    보는 사람에게는 사고로 읽히고, 실제로는 아무 일도 없었던 것이다.
    """
    full = ["x_btc", "x_funding"]
    rows = [_rec(_day(i), "crypto", full) for i in range(20, 0, -1)]
    rows.append(_rec(_day(0), "crypto", ["x_btc"]))     # 오늘 밤 결손
    gen = D._generation_info(_write(tmp_path, rows))
    assert gen["realized"]["since"] == _day(20), (
        f"확정되지 않은 변화로 시계가 이미 리셋됐다: {gen['realized']}")


def test_a_confirmed_change_is_dated_back_to_when_it_started(tmp_path):
    """확정되면 **시작한 날**로 소급해야 한다 — 확정된 날이 아니라.

    사흘째에야 리셋하면서 그날을 시작으로 적으면, 이미 달라진 입력으로
    돌아간 이틀이 이전 세대에 섞인다.
    """
    old = ["x_btc"]
    new = ["x_btc", "x_funding"]
    rows = [_rec(_day(i), "crypto", old) for i in range(20, 2, -1)]
    rows += [_rec(_day(i), "crypto", new) for i in range(2, -1, -1)]
    gen = D._generation_info(_write(tmp_path, rows))
    assert gen["realized"]["since"] == _day(2), (
        f"확정한 날을 시작으로 적었다 — 앞의 이틀이 이전 세대에 섞인다: "
        f"{gen['realized']}")


def test_the_tolerance_is_bounded_on_both_sides():
    """문턱이 실제 상황을 가르는가 — 상수를 자기 자신과 비교하면 무의미하다.

    바깥에서 온 사실 둘로 가둔다: 이 저장소에서 관측된 소스 장애는 대개
    하루, 길어야 이틀이었다. 그리고 90일 시계가 의미를 가지려면 허용치가
    그 시계보다 훨씬 짧아야 한다.
    """
    assert D.GEN_CONFIRM_NIGHTS > 2, (
        "이틀짜리 장애가 세대 교체로 읽힌다 — 시계가 90일에 닿지 못한다")
    assert D.GEN_CONFIRM_NIGHTS < 10, (
        "허용치가 길어 진짜 구성 변화가 열흘 가까이 묻힌다")


# ── ④ 시장을 섞지 않는다 ───────────────────────────────────────

def test_markets_are_not_lumped_together_by_date(tmp_path):
    """코인의 기준 봉은 오늘, 주식은 직전 거래일이다.

    날짜로만 묶으면 하루는 '코인 피처만', 다음 하루는 '주식 피처만'
    붙은 것처럼 보여 구성이 매일 뒤집히고, 시계가 매일 0일차가 된다.
    """
    rows = []
    for i in range(20, -1, -1):
        rows.append(_rec(_day(i), "crypto", ["x_btc", "x_funding"]))
        rows.append(_rec(_day(i + 1), "us_stock", ["x_spy", "x_vix"]))
    gen = D._generation_info(_write(tmp_path, rows))
    assert gen["realized"]["since"] == _day(20), (
        f"시장이 섞여 실측 축이 매일 경계를 만든다: {gen['realized']}")
    assert gen["realized"]["n"] == 4, gen["realized"]
    assert set(gen["realized"]["by_market"]) == {"crypto", "us_stock"}


def test_one_market_changing_is_enough_to_reset(tmp_path):
    """코인 입력만 바뀌어도 그날부터는 다른 시스템이다."""
    rows = []
    for i in range(20, -1, -1):
        coin = ["x_btc", "x_funding"] if i <= 2 else ["x_btc"]
        rows.append(_rec(_day(i), "crypto", coin))
        rows.append(_rec(_day(i + 1), "us_stock", ["x_spy"]))
    gen = D._generation_info(_write(tmp_path, rows))
    assert gen["since"] == _day(2), (
        f"한 시장의 입력이 바뀌었는데 시계가 안 멈췄다: {gen['since']}")


# ── 사람에게 닿는가 ────────────────────────────────────────────

def test_the_reason_reaches_the_front_page():
    """시계가 0일차로 돌아간 이유를 사이트가 말해야 한다.

    아무 설명 없이 90일차가 4일차로 떨어지면, 보는 사람은 사고로 읽는다.
    """
    index = (ROOT / "docs" / "index.html").read_text("utf-8")
    assert "g.realized" in index, (
        "실측 피처 구성이 사이트에 안 나온다 — 시계가 왜 다시 시작했는지 "
        "설명이 없다")
