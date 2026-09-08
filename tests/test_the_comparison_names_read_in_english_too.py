"""화면이 코드 안에 들고 있는 **이름표**도 영어로 읽힌다 (2026-09-08).

■ 왜 또 하나가 필요한가

형제 검사 둘은 이미 서 있다 — 브라우저로 페이지를 띄워 한국어가 남았는지
보는 것(`test_the_site_reads_in_english_too.py`)과, 사고가 나야 뜨는 경보를
소스에서 세는 것(`test_the_alarms_read_in_english_too.py`).

그 사이에 **셋째 자리**가 있다: 화면이 소스 안에 이름표 표를 들고 있고,
장부에 그 열쇠가 실려야만 그 줄이 뜨는 자리다. 실기록의 조기 판정 진도표가
그것이다(`SEQ_LABEL`) — 등록된 비교 14개 중 그날 재료가 있는 것만 그려진다.
재료가 없는 비교의 이름표는 **브라우저 검사가 구조적으로 못 본다.**

■ 실측 (2026-09-08)

**같은 날 몇 시간 전에** 내가 붙인 표였다(11:19 병합). 이름표 14개와
딸린 문구가 **전부 사전에 없었다.**
실기록은 완역 대상(DONE)이 아니라 충족률 하한(0.92)으로 관리되는 페이지라
아무 검사도 그것을 요구하지 않았고, 그날 화면에 그려진 6개만 하한 계산에
들어갔다 — 나머지 8개는 아무 데도 안 세어졌다.

⚠️ 같은 날 아침에 배운 교훈을 그 손으로 다시 어겼다 — "자료가 있어야만
   뜨는 화면 줄은 붙인 날 검사가 못 본다"를 쓰고 두 시간 뒤였다.

⚠️ 이 표는 **자란다.** 사전 등록 실험이 늘면 이름표가 늘고, 그때마다 사람이
   사전을 기억해야 한다면 언젠가 반드시 잊는다. 그래서 목록을 손으로 적지
   않고 **소스에서 센다.**
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PAPER = (ROOT / "docs" / "paper.html").read_text("utf-8")
DICT = (ROOT / "docs" / "assets" / "i18n-en.js").read_text("utf-8")


def _norm(text: str) -> str:
    """한글과 공백만 남긴다 — 값(숫자·날짜)은 일부러 열쇠에 안 박기 때문."""
    return re.sub(r"\s+", " ", re.sub(r"[^가-힣\s]", " ", text)).strip()


def comparison_labels() -> list[str]:
    """조기 판정 진도표의 이름표 — `SEQ_LABEL` 표에서 그대로 센다."""
    m = re.search(r"const SEQ_LABEL\s*=\s*\{(.*?)\};", PAPER, re.S)
    assert m, "SEQ_LABEL 표를 못 찾았다 — 화면 짜임새가 바뀌었다면 이 검사도 따라가야 한다"
    return [v for _, v in re.findall(r'"([^"]+)"\s*:\s*"([^"]+)"', m.group(1))]


def test_the_counter_actually_finds_the_labels():
    """세는 장치가 0을 세면 아래 검사가 조용히 통과한다 — 그 길을 막는다."""
    labels = comparison_labels()
    assert len(labels) >= 10, f"이름표를 {len(labels)}개밖에 못 읽었다"


def test_every_comparison_name_can_be_read_in_english():
    """재료가 없어 오늘 안 그려지는 비교의 이름표도 사전에 있어야 한다."""
    flat = _norm(DICT)
    missing = [s for s in comparison_labels() if _norm(s) not in flat]
    assert not missing, (
        f"영어 사전에 없는 비교 이름 {len(missing)}건 — 그 비교가 처음 "
        f"그려지는 날 영어 독자는 한국어로 받는다: {missing[:5]}")
