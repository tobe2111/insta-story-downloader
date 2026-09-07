"""배치 건강 기록이 종목을 잃지 않고, 굶는 종목에는 빨간불이 뜬다.

2026-09-07. 두 가지를 고친다 — 둘 다 **숫자가 멀쩡해 보이는** 종류의 고장이라
화면에는 아무 이상이 안 뜬다.

■ ① 목록 자르기가 '못 돈 종목'을 부풀린다

    같은 밤의 두 회차를 합칠 때 앞 회차의 결과를 `set(prev["skipped_keys"])`
    로 복원하는데, 그 목록이 20개까지만 저장돼 있었다. 잘려 나간 종목은 그
    순간 사라지고, `not_reached`는 명단에서 빼는 방식으로 구해지므로 그
    종목들이 **'한 번도 손대지 않은 종목'으로 둔갑한다.**

        1회차:  건너뜀 31 · 못 돈 종목 0   (목록에는 20개만 담김)
        2회차:  건너뜀 20 · **못 돈 종목 11**   ← 없던 사고가 생겼다

    2026-09-02에 잡은 UTC 열쇠 사고와 **증상이 똑같다**(못 돈 종목이 부풀려
    진다). 그때는 열쇠가 원인이었고 이번엔 목록 자르기가 원인이다.

■ ② 굶는 종목에 빨간불이 없었다

    작업 #67이 '못 돈 종목' 칸을 만들면서 이렇게 적어 두었다: *"예산이 더
    조여져 한 종목이 계속 뒤로 밀리기 시작하면 그때는 아무 빨간불도 안
    뜬다."* **칸만 만들고 빨간불은 안 붙였다.**

    ⚠️ 한 밤의 `not_reached`로 울리면 안 된다 — 이어달리기는 설계상 한 밤에
       명단을 다 못 돌아서 그 값이 거의 매일 0이 아니다. 매일 울리는 경보는
       꺼진 경보와 같다(감사 99). 물어야 할 것은 "오늘 다 돌았나"가 아니라
       **"이 종목이 마지막으로 심사받은 게 언제인가"**다.

    ⚠️ 그리고 세는 대상은 **지금 명단에 있는 종목만**이다. 장부에는 은퇴한
       챔피언(META·TSLA)이 남아 있어서, 그것까지 세면 17밤짜리 굶주림이
       영원히 잡혀 경보가 처음부터 꺼진 경보가 된다.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.daily import KEYS_CAP, _write_run_health  # noqa: E402
from quant.live.flag_watch import _current_flags  # noqa: E402
from quant.live.retrain import AUDITION_STARVE_NIGHTS, audition_gaps  # noqa: E402


def _health(d: str) -> dict:
    with open(os.path.join(d, "run_health.json"), encoding="utf-8") as f:
        return json.load(f)["retrain"]


# ── ① 목록 자르기 ──────────────────────────────────────────────────────
def test_the_second_run_does_not_turn_skipped_symbols_into_unreached_ones():
    """이 검사가 이 파일의 존재 이유다 — 실제로 재현된 사고를 못 박는다."""
    d = tempfile.mkdtemp()
    roster = [f"us_stock:S{i:02d}" for i in range(40)]
    _write_run_health(d, "retrain", ok=roster[:9], failed={},
                      skipped=roster[9:], roster=roster)
    r1 = _health(d)
    assert r1["skipped"] == 31 and r1["not_reached"] == 0, r1

    # 2회차는 예산이 일찍 끊겨 5종목만 건너뜀으로 보고한다.
    _write_run_health(d, "retrain", ok=[], failed={},
                      skipped=roster[9:14], roster=roster)
    r2 = _health(d)
    assert r2["skipped"] == 31, (
        f"건너뜀이 {r2['skipped']}로 줄었다 — 앞 회차의 종목이 목록에서 "
        "잘려 나가 사라졌다")
    assert r2["not_reached"] == 0, (
        f"못 돈 종목이 {r2['not_reached']}로 늘었다 — 건너뛴 종목이 "
        "'한 번도 손대지 않은 종목'으로 둔갑했다. 없던 사고가 생긴 것이다")


def test_the_count_and_the_list_agree():
    """세는 수와 목록 길이가 어긋나면 안 된다 — 그 어긋남이 사고의 뿌리였다."""
    d = tempfile.mkdtemp()
    roster = [f"us_stock:S{i:02d}" for i in range(40)]
    _write_run_health(d, "retrain", ok=roster[:9], failed={},
                      skipped=roster[9:], roster=roster)
    r = _health(d)
    for count, keys in (("ok", "ok_keys"), ("skipped", "skipped_keys"),
                        ("not_reached", "not_reached_keys")):
        assert r[count] == len(r[keys]), (
            f"{count}={r[count]}인데 {keys}에는 {len(r[keys])}개뿐이다 — "
            "병합이 이 목록을 되읽으므로 그 차이만큼 종목이 사라진다")


def test_a_cap_that_bites_says_so():
    """상한이 걸리면 **걸렸다고 말한다** — 조용히 잃지 않는다.

    상한은 폭주를 막는 안전장치로 남기지만, 걸린 밤은 병합이 종목을 잃을 수
    있으므로 그 사실이 기록에 남아야 한다.
    """
    d = tempfile.mkdtemp()
    big = [f"us_stock:S{i:04d}" for i in range(KEYS_CAP + 5)]
    _write_run_health(d, "retrain", ok=big, failed={}, skipped=[])
    r = _health(d)
    assert r.get("keys_truncated") is True, (
        "상한이 걸렸는데 기록이 아무 말도 안 한다")
    # 평범한 밤에는 그 칸이 없다(있으면 매일 켜진 경고가 된다).
    d2 = tempfile.mkdtemp()
    _write_run_health(d2, "retrain", ok=big[:10], failed={}, skipped=[])
    assert "keys_truncated" not in _health(d2)


def test_the_cap_is_bigger_than_any_realistic_roster():
    """상한이 명단보다 작으면 이 사고가 그대로 돌아온다."""
    assert KEYS_CAP >= 200, KEYS_CAP


# ── ② 굶는 종목 경보 ───────────────────────────────────────────────────
def _ledger(d: str, rows: list[dict], roster: list[str]) -> None:
    with open(os.path.join(d, "retrain_history.jsonl"), "w",
              encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(os.path.join(d, "universe.json"), "w", encoding="utf-8") as f:
        json.dump({"targets": [k.split(":", 1) for k in roster]}, f)


def test_a_symbol_left_behind_for_too_many_nights_is_flagged():
    d = tempfile.mkdtemp()
    rows = []
    for i, night in enumerate(["2026-09-0%d" % n for n in range(1, 9)]):
        # A는 매일, B는 첫날 이후로 한 번도 안 돈다.
        rows.append({"night": night, "market": "us_stock", "symbol": "A"})
        if i == 0:
            rows.append({"night": night, "market": "us_stock", "symbol": "B"})
    _ledger(d, rows, ["us_stock:A", "us_stock:B"])
    g = audition_gaps(d)
    assert g["measured"] and g["starving"] == {"us_stock:B": 7}, g
    flags = _current_flags({"audition_gap": g})
    hit = [v for k, v in flags.items() if k.startswith("audition_starved")]
    assert hit and "us_stock:B" in hit[0], flags


def test_a_healthy_relay_stays_silent():
    """이어달리기가 정상이면 **울리지 않는다** — 매일 울리는 경보는 꺼진 경보다.

    실측(2026-09-07): 명단 40종목의 최악 간격이 2밤이라 오늘은 침묵한다.
    """
    d = tempfile.mkdtemp()
    rows = []
    for night in ["2026-09-0%d" % n for n in range(1, 9)]:
        rows.append({"night": night, "market": "us_stock", "symbol": "A"})
        rows.append({"night": night, "market": "us_stock", "symbol": "B"})
    _ledger(d, rows, ["us_stock:A", "us_stock:B"])
    g = audition_gaps(d)
    assert g["starving"] == {}, g
    flags = _current_flags({"audition_gap": g})
    assert not [k for k in flags if k.startswith("audition_starved")], flags


def test_a_retired_symbol_does_not_starve_forever():
    """명단을 떠난 종목은 세지 않는다.

    장부에는 은퇴한 챔피언(META·TSLA — 2026-08-22 시총 회전)이 남아 있다.
    그것까지 세면 17밤짜리 굶주림이 영원히 잡혀, 경보가 켜지는 첫날부터
    꺼진 경보가 된다.
    """
    d = tempfile.mkdtemp()
    rows = [{"night": "2026-08-21", "market": "us_stock", "symbol": "TSLA"}]
    for night in ["2026-09-0%d" % n for n in range(1, 9)]:
        rows.append({"night": night, "market": "us_stock", "symbol": "A"})
    _ledger(d, rows, ["us_stock:A"])          # TSLA는 명단에 없다
    g = audition_gaps(d)
    assert g["starving"] == {}, g
    assert "us_stock:TSLA" not in (g.get("never_seen") or [])


def test_a_symbol_new_to_the_roster_is_not_called_starving():
    """방금 명단에 들어온 종목은 **간격을 지어내지 않는다.**

    한 번도 안 돈 것과 오래 굶은 것은 다른 사건이다. 지어내면 유니버스를
    넓힌 다음 날 경보가 무더기로 뜨고, 그러면 아무도 안 본다.
    """
    d = tempfile.mkdtemp()
    rows = [{"night": "2026-09-0%d" % n, "market": "us_stock", "symbol": "A"}
            for n in range(1, 9)]
    _ledger(d, rows, ["us_stock:A", "us_stock:NEW"])
    g = audition_gaps(d)
    assert g["starving"] == {}, g
    assert g["never_seen"] == ["us_stock:NEW"], g


def test_not_being_able_to_measure_is_said_out_loud():
    """못 잰 것과 '굶는 종목이 없다'는 다른 사건이다.

    안 적으면 재는 장치가 고장 난 날과 정상인 날이 화면에서 똑같이 조용하다.
    """
    d = tempfile.mkdtemp()                     # 장부도 명단도 없다
    g = audition_gaps(d)
    assert g["measured"] is False and g.get("why"), g
    flags = _current_flags({"audition_gap": g})
    assert "audition_gap_unmeasured" in flags, flags


def test_the_gap_is_counted_by_the_night_key_not_the_bar_date():
    """밤은 `asof`가 아니다.

    `asof`는 그 종목의 마지막 봉 날짜라 시장마다 다르다 — 매일 봉이 생기는
    것은 코인뿐이라 그것으로 밤을 세면 주식 쪽이 통째로 어긋난다(2026-09-01에
    첫 화면 배너가 같은 이유로 "어젯밤 5종목"을 매일 적고 있었다).
    """
    src = (ROOT / "quant" / "live" / "retrain.py").read_text("utf-8")
    i = src.index("def audition_gaps(")
    body = src[i:i + 4000]
    assert 'r.get("night") or r.get("asof")' in body, (
        "밤 열쇠를 안 쓰고 봉 날짜로 세고 있다")


def test_the_threshold_is_above_normal_operation():
    """문턱은 정상 운행보다 위에 있어야 한다 — 실측 최악 간격이 2밤이다."""
    assert AUDITION_STARVE_NIGHTS >= 4, AUDITION_STARVE_NIGHTS


def test_the_status_carries_the_gap_so_the_alarm_can_read_it():
    """배선이 없으면 경보는 영영 안 울린다(장치만 있고 전선이 없는 상태)."""
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert 'status["audition_gap"] = audition_gaps(state_dir)' in src
