"""공개한 글의 아카이브는 조용히 바뀌지 않는다 (감사 86).

`docs/social/<날짜>/` 는 **그날 세상에 내보낸 글**의 기록이다. 그런데
`write_content()`는 아무 경고 없이 덮어썼다. 캡션 코드가 바뀐 뒤 이 명령을
한 번만 돌리면 과거 게시물이 조용히 다른 글로 바뀐다.

가설이 아니라 실제로 일어났다. 2026-08-11 감사 중에 `quant social-content`를
돌렸더니 08-10 폴더가 이렇게 바뀌었다:

    (그날 실제로 나간 글)  "오늘 -0.06%"   ← 누적을 '오늘'이라 부르던 결함
    (재생성한 글)          "오늘 -0.05%"   ← 그 결함을 고친 뒤의 올바른 값

후자로 덮으면 아카이브가 **하지 않은 말을 했다고** 기록한다. 정직성이 유일한
자산인 채널에서 그건 숫자 하나가 틀린 것보다 나쁘다.

원칙은 **"과거를 고치지 않는다"** 이다 — 고칠 것이 있으면 docs/trust.html에
공시한다. 이 검사가 그 원칙을 코드에 묶는다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.reporting.social import (            # noqa: E402
    PublishedContentChanged,
    write_content,
)


def _status(equity=79950.22, day_pct=-0.05, date="2026-08-10"):
    """write_content가 읽는 최소 status.json — 실제 구조(paper/portfolio:ALL)."""
    return {
        "updated": f"{date}T00:00:00Z",
        "paper": {
            "portfolio:ALL": {
                "start_cash": 80000.0,
                "deposits": [],
                "history": [
                    {"date": "2026-08-09", "equity": 79987.94,
                     "return_pct": -0.02, "weight": 0.07, "twr_pct": -0.02,
                     "alloc": {}},
                    {"date": date, "equity": equity, "return_pct": -0.06,
                     "day_pct": day_pct, "weight": 0.0684, "twr_pct": -0.06,
                     "alloc": {"us_stock:AAPL": 0.03}},
                ],
            }
        },
        "retrain_recent": [],
        "symbols": {},
    }


@pytest.fixture
def docs(tmp_path):
    d = tmp_path / "docs"
    (d / "social").mkdir(parents=True)
    def _write(st):
        (d / "status.json").write_text(json.dumps(st, ensure_ascii=False),
                                       encoding="utf-8")
        return str(d)
    return d, _write


# ── 본체 ────────────────────────────────────────────────────────

def test_first_write_creates_the_archive(docs):
    d, write = docs
    write_content(docs_dir=write(_status()), site_url="https://x")
    cap = d / "social" / "2026-08-10" / "caption_threads.txt"
    assert cap.exists() and "79,950" in cap.read_text(encoding="utf-8")


def test_rewriting_the_same_content_is_a_quiet_noop(docs):
    """같은 날 재실행은 정상 흐름 — 내용이 같으면 조용히 지나간다."""
    d, write = docs
    dd = write(_status())
    write_content(docs_dir=dd, site_url="https://x")
    before = (d / "social" / "2026-08-10" / "caption_threads.txt").read_text("utf-8")
    write_content(docs_dir=dd, site_url="https://x")     # 예외가 나면 실패
    after = (d / "social" / "2026-08-10" / "caption_threads.txt").read_text("utf-8")
    assert before == after


def test_changing_a_published_caption_is_refused(docs):
    """숫자가 달라지면 거부한다 — 이게 감사 86의 본체다."""
    d, write = docs
    write_content(docs_dir=write(_status()), site_url="https://x")
    original = (d / "social" / "2026-08-10" / "caption_threads.txt").read_text("utf-8")

    with pytest.raises(PublishedContentChanged) as e:
        write_content(docs_dir=write(_status(day_pct=-9.99)), site_url="https://x")

    assert "trust.html" in str(e.value), "공시하라는 안내가 없다"
    assert (d / "social" / "2026-08-10" / "caption_threads.txt").read_text("utf-8") \
        == original, "거부했다면서 파일은 이미 바뀌어 있다"


def test_force_is_the_only_way_through(docs):
    """정말 바꿔야 할 때는 길이 있어야 한다 — 다만 의도적이어야 한다."""
    d, write = docs
    write_content(docs_dir=write(_status()), site_url="https://x")
    write_content(docs_dir=write(_status(day_pct=-9.99)), site_url="https://x",
                  force=True)
    assert "-9.99" in (d / "social" / "2026-08-10" / "caption_threads.txt") \
        .read_text("utf-8")


def test_a_new_date_is_never_blocked(docs):
    """매일 도는 배치가 막히면 안 된다 — 새 날짜는 항상 통과."""
    d, write = docs
    write_content(docs_dir=write(_status()), site_url="https://x")
    write_content(docs_dir=write(_status(date="2026-08-11")),
                  site_url="https://x")
    assert (d / "social" / "2026-08-11" / "caption_threads.txt").exists()


def test_the_cli_exposes_force_and_fails_loudly():
    """조용히 덮어쓰느니 소리 내어 실패한다."""
    src = (ROOT / "quant" / "cli.py").read_text(encoding="utf-8")
    assert '"--force"' in src and "PublishedContentChanged" in src
    assert "SystemExit" in src.split("_cmd_social_content")[1][:600]


def test_the_workflow_does_not_force():
    """야간 배치가 --force를 달고 다니면 이 방어가 무의미해진다."""
    wf = (ROOT / ".github" / "workflows" / "social-post.yml").read_text("utf-8")
    line = [l for l in wf.splitlines() if "social-content" in l]
    assert line, "워크플로에서 social-content 호출을 찾지 못했다"
    assert not any("--force" in l for l in line), (
        "야간 배치가 --force로 돌면 과거 게시물이 매일 조용히 덮어써진다")
