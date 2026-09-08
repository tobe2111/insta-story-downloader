"""선물 공개 자료에 **아무도 안 읽는 칸**을 두지 않는다 (2026-09-08).

■ 감사 105의 다섯 번째 얼굴

이 저장소가 반복해서 잡아 온 병이다 — *"장부는 매일 남기는데 화면 어디에도
없었다."* 오늘 선물 공개 자료에서 두 개를 더 찾았다(실측: 소비자 0곳):

    fee_window              7일 창의 회차 수 · 수수료 · **수수료 빼기 전 손익**
    direction_gate.age_nights   그 판정이 며칠 전 밤 것인가

앞의 것은 **정확성 검사까지 붙어 있었다**(비율로 적지 말라는 검사까지).
만들어 놓고 눈금을 안 단 계측기였다. 뒤의 것은 더 나쁘다 — 판정은 7밤이
지나면 효력을 잃는데, 화면은 어젯밤 판정과 엿새 된 판정을 **똑같이** 그렸다.

■ 재는 방법

공개 자료의 칸 이름을 **화면·경보 소스에서 찾는다.** 값이 종목 이름인
칸(`positions.BTC/USDT` 같은 것)은 이름으로 읽는 것이 아니라 돌면서 읽으므로
세지 않는다 — 그 목록은 **자료 자신에서 뽑는다**(손 명단 금지).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REPORT = ROOT / "docs" / "futures.json"
#: 읽는 쪽 — 화면 전부와 공용 자산, 그리고 경보.
#:
#: ⚠️ 처음에는 선물 화면 하나만 봤다가 **거짓 경보 17건**을 봤다. 공용
#:    자산(`docs/assets/*.js`)이 여러 페이지를 대신 그리므로, 읽는 쪽을
#:    좁게 잡으면 "아무도 안 읽는다"가 "내가 안 봤다"가 된다.
READERS = "\n".join(
    q.read_text("utf-8")
    for q in [*sorted((ROOT / "docs").glob("*.html")),
              *sorted((ROOT / "docs" / "assets").glob("*.js")),
              ROOT / "quant" / "live" / "flag_watch.py"])

#: 값이 아니라 **이름이 자료인** 칸 — 화면은 이 칸을 돌면서 읽지, 이름으로
#: 읽지 않는다. 목록은 자료 자신에서 뽑는다.
def _data_names(d: dict) -> set[str]:
    out: set[str] = set()
    for block in ("positions", "rebalance_bands", "entries", "marks"):
        v = d.get(block)
        if isinstance(v, dict):
            out |= set(v)
    return out


def _fields(o, data: set[str], path: str = ""):
    if isinstance(o, dict):
        for k, v in o.items():
            if k in data:
                continue                       # 이름이 자료인 칸
            yield (f"{path}.{k}" if path else k), k
            yield from _fields(v, data, f"{path}.{k}" if path else k)
    elif isinstance(o, list) and o:
        yield from _fields(o[0], data, path + "[]")


def published():
    d = json.loads(REPORT.read_text("utf-8"))
    return list(_fields(d, _data_names(d)))


def test_the_counter_actually_finds_the_fields():
    """세는 장치가 0을 세면 아래 검사가 조용히 통과한다 — 그 길을 막는다."""
    got = published()
    assert len(got) >= 60, f"공개 자료 칸을 {len(got)}개밖에 못 읽었다"


def test_every_published_field_has_a_reader():
    """공개 자료에 싣는 칸은 화면이나 경보 중 한 곳이 읽어야 한다."""
    dead = [path for path, name in published()
            if not re.search(rf'["\'\.]{re.escape(name)}\b', READERS)]
    assert not dead, (
        "선물 공개 자료에 싣기만 하고 아무도 안 읽는 칸이 있다 — 만들어 "
        f"놓고 눈금을 안 단 계측기다(감사 105): {dead}")


def test_the_two_fields_found_today_are_actually_on_screen():
    """오늘 찾은 둘은 **이름만 읽히는 것으로는 부족하다** — 화면이 그린다.

    ⚠️ 이름이 소스 어딘가에 있다는 것과 화면이 그것을 말한다는 것은 다르다.
       그래서 이 둘만은 화면 파일에서 직접 확인한다.
    """
    page = (ROOT / "docs" / "futures.html").read_text("utf-8")
    assert "fee_window" in page, "7일 창의 속살이 화면에 없다"
    assert "age_nights" in page, "방향 관문 판정의 나이가 화면에 없다"
    assert "max_age_nights" in page, (
        "판정의 유효 기간을 화면이 자료에서 안 읽고 있다 — 손으로 적으면 "
        "관문의 값을 바꾸는 날 화면만 옛말을 한다")
