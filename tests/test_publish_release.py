"""릴리스 공개 게이트 — 문자열이 아니라 동작을 검사한다.

배경(결함 73): 세 OS 빌드가 전부 성공한 v0.17.1에서 공개 잡이 "릴리스를
찾을 수 없습니다"로 실패했다. 원인은 draft 릴리스를 ``/releases/tags/<tag>``
로 조회한 것 — draft에는 git 태그가 없어 그 경로는 항상 404다. 즉 이 게이트는
**한 번도 통과할 수 없는 구조**였는데, 당시 검사는 워크플로 YAML 안에
``REQUIRED=`` 와 ``빠진 자산`` 문자열이 있는지만 보고 초록이었다.

그래서 여기서는 가짜 GitHub API를 물려 실제로 돌린다. 특히 가짜 API는
``/releases/tags/`` 요청에 **404를 내도록** 만들어 두었다 — 옛 방식으로
되돌리면 이 파일이 즉시 빨개진다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import publish_release as P          # noqa: E402

VER = "v0.17.1"
ALL_ASSETS = [{"name": n} for n in P.REQUIRED]


class FakeGitHub:
    """진짜 GitHub의 draft 규칙을 흉내 낸다.

    핵심: 태그 조회는 **공개된** 릴리스만 찾는다. draft는 못 찾는다.
    """

    def __init__(self, releases):
        self.releases = [dict(r) for r in releases]
        self.calls: list[tuple[str, str]] = []

    def __call__(self, path, method="GET", body=None):
        self.calls.append((method, path))

        if path.startswith("/releases/tags/"):
            tag = path.rsplit("/", 1)[-1]
            for r in self.releases:
                # draft는 태그가 아직 없다 → 조회 불가 (여기가 결함 73의 자리)
                if r["tag_name"] == tag and not r["draft"]:
                    return r
            raise AssertionError(
                "GitHub는 여기서 404를 낸다 — draft를 태그로 찾으려 했다(결함 73)")

        if path.startswith("/releases?"):
            page = int(path.split("page=")[-1])
            # 인증된 목록 조회는 draft를 포함한다
            return self.releases if page == 1 else []

        if method == "PATCH" and path.startswith("/releases/"):
            rid = int(path.rsplit("/", 1)[-1])
            for r in self.releases:
                if r["id"] == rid:
                    r.update(json.loads(json.dumps(body)))
                    return r
            raise AssertionError(f"없는 릴리스에 PATCH: {rid}")

        raise AssertionError(f"예상 못 한 호출: {method} {path}")

    @property
    def patched(self):
        return [p for m, p in self.calls if m == "PATCH"]


def draft(assets=None, rid=1, tag=VER):
    return {"id": rid, "tag_name": tag, "draft": True,
            "assets": list(ALL_ASSETS if assets is None else assets)}


# ── 본체 ────────────────────────────────────────────────────────────

def test_draft_with_all_assets_gets_published():
    """세 자산이 다 붙은 draft는 공개된다 — v0.17.1이 막혔던 바로 그 경로."""
    gh = FakeGitHub([draft()])
    out = []
    assert P.publish(gh, "o/r", VER, log=out.append) == 0
    assert gh.releases[0]["draft"] is False, "공개되지 않았다"
    assert gh.patched, "draft 해제 PATCH가 나가지 않았다"


def test_finder_never_uses_the_tag_endpoint():
    """draft를 태그로 찾으면 안 된다(그 경로는 draft에 대해 404다)."""
    gh = FakeGitHub([draft()])
    P.publish(gh, "o/r", VER, log=lambda *_: None)
    assert not any(p.startswith("/releases/tags/") for _, p in gh.calls), \
        "태그 조회로 되돌아갔다 — draft를 영원히 못 찾는다"


def test_missing_windows_asset_keeps_it_draft():
    """윈도우가 빠지면 보류한다 — v0.17.0에서 실제로 404를 만든 상황."""
    partial = [a for a in ALL_ASSETS if a["name"] != "quant-cockpit-windows.exe"]
    gh = FakeGitHub([draft(assets=partial)])
    out = []
    assert P.publish(gh, "o/r", VER, log=out.append) == 1
    assert gh.releases[0]["draft"] is True, "반쪽 릴리스가 공개됐다"
    assert not gh.patched
    assert any("quant-cockpit-windows.exe" in m for m in out)


@pytest.mark.parametrize("missing", P.REQUIRED)
def test_any_single_missing_asset_blocks_publication(missing):
    """세 자산 중 무엇이 빠져도 막는다."""
    gh = FakeGitHub([draft(assets=[a for a in ALL_ASSETS if a["name"] != missing])])
    assert P.publish(gh, "o/r", VER, log=lambda *_: None) == 1
    assert gh.releases[0]["draft"] is True


def test_no_release_at_all_is_reported_not_published():
    gh = FakeGitHub([])
    out = []
    assert P.publish(gh, "o/r", VER, log=out.append) == 1
    assert any("찾을 수 없습니다" in m for m in out)


def test_split_drafts_are_refused():
    """세 잡이 각자 draft를 만들어 자산이 갈라지면 공개하지 않는다.

    하나만 골라 공개하면 그게 곧 반쪽 릴리스다.
    """
    a = draft(assets=[{"name": "quant-cockpit-windows.exe"}], rid=1)
    b = draft(assets=[{"name": "quant-cockpit-macos.zip"},
                      {"name": "quant-cockpit-linux.zip"}], rid=2)
    gh = FakeGitHub([a, b])
    out = []
    assert P.publish(gh, "o/r", VER, log=out.append) == 1
    assert not gh.patched
    assert all(r["draft"] for r in gh.releases)
    assert any("갈라졌습니다" in m for m in out)


def test_already_published_release_is_left_alone():
    """재실행이 이미 공개된 릴리스를 건드리지 않는다(멱등)."""
    pub = {"id": 9, "tag_name": VER, "draft": False, "assets": list(ALL_ASSETS)}
    gh = FakeGitHub([pub])
    assert P.publish(gh, "o/r", VER, log=lambda *_: None) == 0
    assert not gh.patched


def test_other_versions_are_not_confused():
    """다른 버전의 릴리스를 잘못 집어 공개하지 않는다."""
    gh = FakeGitHub([draft(rid=1, tag="v0.17.0"), draft(rid=2, tag="v0.16.0")])
    assert P.publish(gh, "o/r", VER, log=lambda *_: None) == 1
    assert not gh.patched


def test_required_list_matches_what_the_site_links():
    """사이트가 링크하는 파일과 공개 조건이 어긋나면 버튼이 404가 된다."""
    site = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    for name in P.REQUIRED:
        assert name in site, f"확인 목록의 {name} 를 사이트가 링크하지 않는다"
    for name in ("quant-cockpit-windows.exe", "quant-cockpit-macos.zip",
                 "quant-cockpit-linux.zip"):
        if name in site:
            assert name in P.REQUIRED, f"사이트는 {name}를 링크하는데 확인하지 않는다"


def test_workflow_calls_the_script_not_an_inline_heredoc():
    """확인 로직이 다시 YAML 안으로 들어가면(=검사 불가) 막는다."""
    y = (ROOT / ".github" / "workflows" / "build-app.yml").read_text("utf-8")
    assert "scripts/publish_release.py" in y
    assert "releases/tags/" not in y, "워크플로가 태그 조회로 되돌아갔다"
