"""사이트 자바스크립트가 **문법적으로 성립하는가** (감사 101).

이 저장소의 공개 사이트는 전부 `docs/*.html` 안의 인라인 스크립트로 돈다.
`fetch("status.json").then(...)` 하나가 화면 전체를 그린다. 그런데 그
스크립트에 오타가 하나 있으면:

  · 파이썬 검사는 전부 통과한다(HTML은 텍스트로만 읽는다)
  · CI도 초록이다
  · 사이트는 **"불러오는 중…"에서 영원히 멈춘다**

즉 사이트가 통째로 죽어도 아무도 모른다. 오늘 하루에만 감사 89·91·94·
95·96·98·99·100이 이 파일들을 고쳤다 — 그동안 문법을 확인해 준 것은
아무것도 없었다.

여기서는 각 인라인 스크립트를 실제 자바스크립트 엔진에 넣어 **파싱만**
시킨다(실행하지 않는다 — 브라우저 API가 없어도 문법 오류는 잡힌다).

⚠️ node가 없으면 **건너뛰지 않고 실패한다.** 오늘 배운 것이다:
   '건너뜀은 통과가 아니다.' 조용히 건너뛰면 이 검사는 있으나 마나다.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

# 손으로 쓰지 않은 산출물(단일 파일 배포본)은 대상이 아니다.
SKIP = {"index-standalone.html"}

INLINE = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S)


def _blocks() -> list[tuple[str, int, str]]:
    out = []
    for p in sorted(DOCS.glob("*.html")):
        if p.name in SKIP:
            continue
        src = p.read_text("utf-8")
        for m in INLINE.finditer(src):
            line = src[:m.start()].count("\n") + 1
            out.append((p.name, line, m.group(1)))
    return out


def _node() -> str:
    exe = shutil.which("node")
    assert exe, (
        "node를 찾지 못했습니다. 이 검사는 **건너뛰지 않습니다** — 사이트 "
        "자바스크립트의 문법을 확인하는 유일한 검사이고, 조용히 건너뛰면 "
        "오타 하나로 공개 사이트가 통째로 멈춰도 CI가 초록이 됩니다. "
        "GitHub Actions 러너에는 node가 기본 설치돼 있습니다.")
    return exe


def test_there_are_scripts_to_check():
    """검사 대상이 0개면 아래 검사가 조용히 전부 통과한다."""
    blocks = _blocks()
    assert len(blocks) >= 5, f"인라인 스크립트를 {len(blocks)}개만 찾았다"
    names = {f for f, _l, _c in blocks}
    for must in ("index.html", "paper.html", "sns_card.html"):
        assert must in names, f"{must}의 스크립트를 찾지 못했다"


# ⚠️ 입력은 **stdin으로** 넘긴다. `node -e ... -- payload`는 `--`가 먹혀
#    process.argv가 밀리고, 그러면 JSON.parse가 터져 검사가 '고장난 채'
#    돌아간다(처음에 그렇게 짰다가 자기 검사에 걸렸다).
_PARSE_JS = textwrap.dedent("""
    let raw = "";
    process.stdin.on("data", d => raw += d);
    process.stdin.on("end", () => {
      const bad = [];
      for (const b of JSON.parse(raw)) {
        try { new Function(b.c); }
        catch (e) { bad.push(`${b.f}:${b.l} — ${e.message}`); }
      }
      process.stdout.write(JSON.stringify(bad));
    });
""")


def _check(blocks) -> list[str]:
    payload = json.dumps([{"f": f, "l": ln, "c": c} for f, ln, c in blocks])
    r = subprocess.run([_node(), "-e", _PARSE_JS], input=payload,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout or "[]")


def test_every_inline_script_parses():
    bad = _check(_blocks())
    assert not bad, (
        "사이트 자바스크립트에 문법 오류가 있다 — 이대로 배포하면 해당 "
        "페이지가 '불러오는 중…'에서 멈춘다:\n  " + "\n  ".join(bad))


def test_the_checker_would_actually_catch_an_error():
    """검사 자신을 검사한다 — 통과가 '확인했다'는 뜻이어야 한다."""
    bad = _check([("fake.html", 1, "var x = ;")])
    assert len(bad) == 1 and bad[0].startswith("fake.html:1"), (
        f"일부러 깨뜨린 코드를 통과시켰다 — 이 검사는 아무것도 확인하지 않는다 ({bad})")
    assert _check([("ok.html", 1, "var x = 1;")]) == [], (
        "멀쩡한 코드를 오류라고 한다 — 반대로 고장난 검사다")


def test_pages_tell_the_reader_when_the_ledger_cannot_be_loaded():
    """장부를 못 읽었을 때 **빈 화면이 아니라 말**이 나와야 한다.

    이것도 같은 계열이다: 실패가 조용하면 아무도 모른다.
    """
    for name in ("index.html", "paper.html", "today.html", "weekly.html"):
        p = DOCS / name
        if not p.exists():
            continue
        src = p.read_text("utf-8")
        if "status.json" not in src:
            continue
        assert ".catch(" in src, (
            f"{name}: status.json을 못 읽으면 아무 말 없이 멈춘다 "
            "— .catch로 사용자에게 알릴 것")
