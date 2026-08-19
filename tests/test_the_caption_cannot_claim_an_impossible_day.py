"""방송에 나가는 글은 **계좌로 설명되는 숫자만** 담는다 (감사 288).

2026-08-15 새벽 배치가 만든 캡션이 그대로 나갔다.

    💰 자산 72,488,498원 (누적 +7148.85% · 오늘 +7149.96%)

원금 100만원짜리 페이퍼 계좌다. 하루에 72배가 되는 일은 없었다 — 통화
환산이 한 곳에서 빠져 해외 종목을 달러 가격 그대로 산 것으로 기록됐기
때문이다(감사 254). 장부는 나중에 그 체결을 무효로 되돌려 997,197원으로
정정했지만 **캡션은 이미 나간 뒤였다.**

아픈 것은 이 관문이 이미 있었다는 점이다. 감사 273이 "계좌보다 큰 금액은
사실처럼 적지 않는다"를 만들었고 274·281이 그것을 화면 세 곳에 배선했다.
전부 **사이트**였다. 정작 사이트 밖으로 나가 낯선 사람에게 도달하는 유일한
경로에는 아무 관문도 없었다 — 그리고 캡션은 옆에 설명이 붙지 않으므로
사이트보다 오히려 더 위험하다.

`quant/reporting/social.py`가 이미 세 번 적어 둔 문장 그대로다:
"사이트는 고쳤는데 캡션만 남아 있었다"(감사 218 · 238 · 113/114). 네 번째다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.reporting import social  # noqa: E402

DOCS = ROOT / "docs"
STATUS = json.loads((DOCS / "status.json").read_text("utf-8"))


def _status_with(**patch) -> dict:
    st = json.loads(json.dumps(STATUS))
    st["paper"]["portfolio:ALL"]["history"][-1].update(patch)
    return st


# ── ① 그날의 진짜 숫자로 재현한다 ────────────────────────────────

def test_the_real_2026_08_15_numbers_are_refused():
    """되돌리기 전 값(장부가 `_restated.before`로 남겨 둔 그 값)으로 시험한다."""
    # ⚠️ 정정 기록은 마지막 항목이 아니라 **정정이 있던 그 날**(8-15)에
    #    붙어 있다. 처음에는 history[-1]로 읽었는데, 8-19 배치가 새 기록을
    #    덧붙이자 이 검사가 낡았다 — 표식을 찾아서 읽는다.
    hist = STATUS["paper"]["portfolio:ALL"]["history"]
    rec = next((r for r in reversed(hist) if r.get("_restated")), None)
    before = ((rec or {}).get("_restated") or {}).get("before")
    assert before, "정정 기록이 사라졌다 — 이 검사가 무엇을 재현하는지 알 수 없다"
    with pytest.raises(social.ImpossibleNumbers) as e:
        social.build_captions(_status_with(**before))
    msg = str(e.value)
    assert "7,149.96%" in msg or "7149.96" in msg, msg
    assert "고쳐서 내보내지 않습니다" in msg, (
        f"숫자를 조용히 고치는 길을 열어 두면 안 된다:\n{msg}")


@pytest.mark.parametrize("day_pct", [100.01, -100.01, 7149.96, -999.0])
def test_a_day_bigger_than_the_whole_account_is_refused(day_pct):
    with pytest.raises(social.ImpossibleNumbers):
        social.build_captions(_status_with(day_pct=day_pct))


def test_a_ledger_that_flagged_its_own_amounts_is_refused():
    """장부가 스스로 '이 금액은 계좌와 안 맞는다'고 적은 날(감사 273).

    그 기록으로 만든 캡션은 자산뿐 아니라 **배분 상위 종목**까지 흔들린다.
    """
    bad = {"fills": [{"key": "us_stock:META", "amount": 71_540_000.0}]}
    with pytest.raises(social.ImpossibleNumbers):
        social.build_captions(_status_with(impossible_amounts=bad))


# ── ② 대조군 — 멀쩡한 날은 그대로 나간다 ─────────────────────────
#
# 이게 없으면 "언제나 거부"도 통과하고, 그러면 방송이 영영 멈춘다.
# 늘 막는 관문은 곧 꺼지고, 꺼진 관문은 없는 관문이다.

def test_a_normal_day_still_gets_its_caption():
    caps = social.build_captions(STATUS)
    assert caps["instagram"] and caps["threads"]
    assert social.impossible_reason({"day_pct": -0.26}) == ""


@pytest.mark.parametrize("day_pct", [99.99, -99.99, 0.0, None])
def test_a_big_but_possible_day_is_not_refused(day_pct):
    """레버리지가 잠긴 계좌에서 하루 +99.99%는 드물지만 불가능하지 않다."""
    social.build_captions(_status_with(day_pct=day_pct))


# ── ③ 되돌려진 날의 글은 '오늘 올릴 글'로 내밀지 않는다 ──────────

def test_the_pointer_carries_the_correction(tmp_path):
    """정정문은 폴더에만 두면 폴더를 여는 사람만 본다.

    글을 복사하는 사람은 어드민 카드(=`latest.json`)만 본다.
    """
    root = tmp_path / "social" / "2026-08-15"
    root.mkdir(parents=True)
    (root / "meta.json").write_text(json.dumps({"date": "2026-08-15"}), "utf-8")
    (root / "caption_instagram.txt").write_text("자산 72,488,498원", "utf-8")
    (root / "caption_threads.txt").write_text("자산 72,488,498원", "utf-8")
    (root / social.CORRECTION_FILE).write_text("⚠️ 이 폴더의 숫자는 틀렸습니다.",
                                               "utf-8")
    out = social.refresh_latest(str(tmp_path))
    assert out["correction"].startswith("⚠️"), out
    # 캡션은 **글자 그대로** 남는다 — 다시 만들면 그날 하지 않은 말이 된다.
    assert out["captions"]["instagram"] == "자산 72,488,498원"


def test_a_clean_day_has_no_correction_field(tmp_path):
    """대조군 — 정정문이 없는 날에 경고를 달면 매번 뜨는 배경음이 된다."""
    root = tmp_path / "social" / "2026-08-14"
    root.mkdir(parents=True)
    (root / "meta.json").write_text(json.dumps({"date": "2026-08-14"}), "utf-8")
    (root / "caption_instagram.txt").write_text("자산 999,847원", "utf-8")
    (root / "caption_threads.txt").write_text("자산 999,847원", "utf-8")
    assert "correction" not in social.refresh_latest(str(tmp_path))


def test_the_live_pointer_says_so_today():
    """지금 저장소에 있는 포인터가 실제로 그렇게 돼 있는가.

    2026-08-16·17·18 배치가 연속으로 막혀 `latest.json`은 아직 08-15를
    가리킨다. 그 글은 되돌려진 글이다.
    """
    latest = json.loads((DOCS / "social" / "latest.json").read_text("utf-8"))
    folder = DOCS / "social" / latest["date"]
    if not (folder / social.CORRECTION_FILE).exists():
        pytest.skip(f"{latest['date']}에는 정정문이 없다 — 확인할 것이 없다")
    assert latest.get("correction"), (
        f"{latest['date']} 글은 정정된 글인데 포인터가 그 사실을 말하지 않는다 — "
        "어드민이 그것을 '오늘 올릴 글'로 내민다")


def test_the_admin_card_shows_the_correction_before_the_numbers():
    src = (DOCS / "admin.html").read_text("utf-8")
    blk = src.split("social/latest.json", 1)[1]
    # ⚠️ **낱말이 있는 것과 그리는 것은 다르다.** 조건을 `if(false)`로 바꿔도
    #    경고문을 만드는 줄에는 `d.correction`이 그대로 남아 있어, 낱말만
    #    세는 검사는 조용히 통과한다(감사 278이 같은 함정에 빠졌다).
    #    그리는 것을 결정하는 **조건 자체**를 못 박는다.
    assert "if(d.correction){" in blk, (
        "어드민이 정정 사실을 보고 갈라지지 않는다 — 되돌려진 글이 그대로 복사된다")
    assert "올리지 마세요" in blk, (
        "경고가 무엇을 하라는 말인지 없다 — 읽는 사람은 그냥 복사한다")
    assert blk.index("if(d.correction){") < blk.index("d.captions"), (
        "정정 경고가 캡션보다 뒤에 있다 — 사람은 위부터 읽는다")
