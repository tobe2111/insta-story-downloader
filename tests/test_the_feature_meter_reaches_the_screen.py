"""장부에 남긴 피처 건강 칸은 **읽는 자리**가 있어야 한다 (2026-09-07).

■ 왜 이 검사가 있나 — 같은 병의 네 번째 얼굴

이 저장소는 같은 모양의 고장을 이미 세 번 잡았다:

  · 감사 105 — 장부는 ``feature_health``를 매일 남기는데 **화면 어디에도
    없었다.** 2026-08-11 기록은 선택 피처가 **전부** 안 붙은 상태였고,
    모델은 그대로 돌고 사이트도 평소 얼굴이었다.
  · 감사 106 — 그 계측기 자체가 **존재하지 않는 컬럼 이름**을 세고 있었다.
    고장난 계측기와 보이지 않는 계측기가 서로를 가려 줬다.
  · 2026-09-07(같은 날 아침) — 계측기가 **이름만** 세어, 800봉 중 31봉만
    들어온 재료를 '붙어 있음'으로 보고했다.

그리고 그 셋째를 고치면서 **넷째를 새로 만들었다**: 채움률 칸(``thin``)을
장부와 경보에는 붙이고 **화면에는 안 붙였다.** 감사 105가 남긴 자리를 그날
그대로 되풀이한 것이다. 같은 날 훑어보니 ``thinnest``는 저장소 어느 곳에서도
읽히지 않고 있었다(소비자 0곳).

■ 장치는 이미 있었는데 **한 겹만 보고 있었다**

감사 98이 만든 계약(``test_ledger_fields_reach_the_screen``)이 이미 돌고
있다 — "장부에 쓰는 필드는 화면에 나오거나, 왜 안 나와도 되는지 적히거나".
그 검사는 오늘도 초록이었다. ``feature_health``가 **최상위 칸**이고 화면이
그 이름을 읽으니 계약을 지킨 것으로 보였기 때문이다.

    record["feature_health"] = {...}      ← 계약이 여기까지만 본다
                               └ thin · thinnest …  ← 아무 계약도 없다

그래서 그 안에서는 칸이 조용히 늘어났고, 오늘 실측으로 **둘이 아무에게도
안 읽히고 있었다**. 여기서는 같은 계약을 **한 겹 더 안쪽**에 건다.

⚠️ 왜 모든 중첩 칸이 아니라 이 하나인가 — 정직하게 적는다. 기록에는 중첩
   딕셔너리가 여럿이고 전부에 이 계약을 걸면 수십 개의 사유를 한꺼번에
   요구하게 된다. 그건 검토를 강제하는 것이 아니라 사유 목록을 부풀리는
   일이다. ``feature_health``를 먼저 고른 이유는 **이 칸의 존재 이유가
   '보여지는 것'이기 때문**이고(감사 105), 실제로 세 번 고장 난 자리다.

⚠️ '읽는 자리'는 화면만이 아니다. 경보(``flag_watch``)도 사람에게 닿는
   길이므로 읽는 자리로 센다 — ``why_missing``이 그 경우다. 다만 **장부에만
   남는 것은 읽는 자리가 아니다**: 그것이 감사 105의 정의 그 자체다.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DAILY = ROOT / "quant" / "live" / "daily.py"
INDEX = ROOT / "docs" / "index.html"
FLAGS = ROOT / "quant" / "live" / "flag_watch.py"
I18N = ROOT / "docs" / "assets" / "i18n-en.js"


def _recorded_fields() -> list[str]:
    """배치가 ``feature_health``에 실제로 적는 칸 — 손 목록이 아니라 소스에서."""
    tree = ast.parse(DAILY.read_text("utf-8"))

    def keys_of(d: ast.Dict) -> list[str]:
        out: list[str] = []
        for k, v in zip(d.keys, d.values):
            if k is None:                      # ``**({...} if ... else {})``
                for n in ast.walk(v):
                    if isinstance(n, ast.Dict):
                        out += keys_of(n)
                        break
            elif isinstance(k, ast.Constant) and isinstance(k.value, str):
                out.append(k.value)
        return out

    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign)
                and any(getattr(t, "id", None) == "feat_health"
                        for t in node.targets)
                and isinstance(node.value, ast.Dict)):
            return keys_of(node.value)
    raise AssertionError("daily.py에서 feat_health 기록을 못 찾았다 — "
                         "이름이 바뀌었다면 이 검사도 따라가야 한다")


def test_the_extractor_actually_finds_the_fields():
    """세는 장치가 0을 세면 이 파일 전체가 조용히 통과한다 — 그 길을 막는다."""
    got = _recorded_fields()
    assert len(got) >= 6, f"{got} — 칸을 못 읽었다(세는 장치가 고장났다)"
    assert "thin" in got and "coverage" in got, got


def test_every_recorded_field_has_someone_who_reads_it():
    """장부에만 남는 칸은 없다 — 있으면 그 칸은 아무 일도 하지 않는다."""
    screen = INDEX.read_text("utf-8")
    alarm = FLAGS.read_text("utf-8")
    orphan = [f for f in _recorded_fields()
              if f"fh.{f}" not in screen
              and f'"{f}"' not in screen
              and f'"{f}"' not in alarm]
    assert not orphan, (
        f"{orphan} — 매일 적는데 화면도 경보도 읽지 않는 칸이다. "
        "감사 105·106과 같은 모양: 기록과 표시는 다른 일이고, 보이지 않는 "
        "계측기는 고장나도 아무 빨간불이 안 뜬다")


def test_the_thin_block_is_on_the_screen():
    """오늘 실제로 뚫려 있던 구멍 — 이 검사가 이 파일의 존재 이유다."""
    src = INDEX.read_text("utf-8")
    assert "fh.thin" in src, "얇은 재료 칸을 화면이 읽지 않는다"
    assert "거의 비어 있는 보조 지표" in src, "읽기만 하고 말하지 않는다"
    # 값이 실제로 화면에 나오는가 — 이름만 나열하면 '얼마나 얇은가'를 잃는다.
    assert "thin.features[c]" in src and "thin.floor" in src, (
        "채움률과 문턱을 안 보여준다 — 이름만 보면 3.9%와 49%가 같아 보인다")


def test_the_thin_line_is_silent_on_a_clean_day():
    """깨끗한 날에는 그 칸이 장부에 아예 없다 — 화면도 조용해야 한다.

    매일 켜져 있는 표시는 표시가 아니다(이 저장소의 경보 규약).
    """
    src = INDEX.read_text("utf-8")
    i = src.index("const thin=fh&&fh.thin;")
    guard = src[i:i + 200]
    assert "Object.keys(thin.features).length" in guard, (
        "빈 목록에도 문장을 띄운다 — 항상 켜진 경고등은 꺼진 것과 같다")


def test_the_worst_symbol_is_named_by_its_name_not_its_key():
    """장부 키(``us_stock:AAPL``)를 그대로 띄우면 비개발자 화면이 아니다."""
    src = INDEX.read_text("utf-8")
    assert "fh.thinnest" in src, "가장 빈약한 종목 칸을 아무도 안 읽는다"
    i = src.index("const tn=fh.thinnest||null;")
    body = src[i:i + 600]
    assert "syms[tn.key]" in body, (
        "종목 이름 대신 장부 키를 띄운다 — 화면의 다른 자리는 모두 "
        "`(syms[k]||{}).name` 을 먼저 본다")


# ── 영어도 끝까지 간다 ────────────────────────────────────────────────
def _patterns() -> list[str]:
    return re.findall(r'\["\^(.+?)\$",', I18N.read_text("utf-8"))


def test_english_carries_the_thin_lines():
    """새 문장이 한국어로만 남으면 영어 화면에서 그 경보는 없는 것과 같다.

    ⚠️ 사전 열쇠에 **값을 박지 않는다** — 이름 목록도 채움률도 장부에서
       오므로, 값을 박으면 다음 측정에 만료된다(2026-08-26에 배운 병).
    """
    pats = _patterns()
    head = "거의 비어 있는 보조 지표 2개"
    tail = ("— 자리는 붙어 있는데 값이 실제로 들어온 봉이 50% 미만입니다"
            "(x_kimchi 25.0% · x_oi_chg5 3.9%). 빈 자리는 0으로 채워 "
            "학습하므로, 모델은 '못 받았다'를 '안 변했다'로 배웁니다")
    for text in (head, tail):
        assert any(re.match(p.replace("\\\\", "\\") + "$", text)
                   for p in pats), f"영어 사전이 이 문장을 못 받는다: {text}"


def test_no_dictionary_key_pins_a_measured_value():
    """실측 숫자가 사전 열쇠에 박히면 다음 측정에 영어가 사라진다."""
    src = I18N.read_text("utf-8")
    i = src.index("거의 비어 있는 보조 지표")
    block = src[i - 200:i + 900]
    assert "3.9%" not in block and "x_oi_chg5" not in block, (
        "오늘의 실측값이 사전에 박혀 있다 — 채움률이 바뀌는 날 영어가 사라진다")
