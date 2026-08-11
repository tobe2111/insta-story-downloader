"""약속한 자산이 전부 붙은 릴리스만 공개한다(draft 해제).

빌드는 세 OS(matrix)가 각자 독립적으로 릴리스를 만들고 자산을 붙인다.
fail-fast: false라 한 OS가 죽어도 나머지는 계속 가고, 그 나머지가 올리는
릴리스 본문에는 **세 파일이 다 있다고 적힌 표**가 그대로 들어간다. 그래서
build는 draft로만 올리고, 이 스크립트가 세 자산을 실제로 확인한 뒤에만
draft를 해제한다.

⚠️ draft 릴리스는 ``GET /releases/tags/<tag>`` 로 찾을 수 없다 (결함 73).
   draft에는 아직 git 태그가 없으므로 그 조회는 404다. v0.17.1에서 세 OS
   빌드가 **모두 성공**했는데도 공개 잡이 "릴리스를 찾을 수 없습니다"로
   오판하고 자산 누락 경보를 쐈다. 목록 조회(``GET /releases``)는 인증된
   호출에 draft를 포함하므로 거기서 tag_name으로 찾는다.

⚠️ 워크플로 heredoc이 아니라 파일로 둔 이유: heredoc은 검사가 문자열밖에
   못 본다. 이 결함이 정확히 그 틈으로 나갔다 — "REQUIRED= 가 있다,
   '빠진 자산' 문구가 있다"는 초록 검사가 **draft를 영원히 못 찾는다**는
   사실을 전혀 건드리지 못했다. 파일로 두면 가짜 API를 물려 진짜로 돌려
   볼 수 있다(tests/test_publish_release.py).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

# 릴리스 본문 표가 약속하는 파일들 — 여기가 곧 사이트 다운로드 버튼과의 계약이다.
# docs/index.html 이 링크하는 이름과 같아야 한다(테스트가 교차 확인).
REQUIRED = (
    "quant-cockpit-windows.exe",
    "quant-cockpit-macos.zip",
    "quant-cockpit-linux.zip",
)

MAX_PAGES = 10          # 릴리스가 1000개를 넘기 전까지는 충분하다


def github_api(repo: str, token: str):
    """실제 GitHub API 호출자. 테스트는 이 자리에 가짜를 끼운다."""

    def call(path: str, method: str = "GET", body: dict | None = None):
        req = urllib.request.Request(
            f"https://api.github.com/repos/{repo}{path}",
            method=method,
            data=json.dumps(body).encode("utf-8") if body is not None else None,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req) as resp:      # noqa: S310 (고정 호스트)
            raw = resp.read()
        return json.loads(raw) if raw else None

    return call


def find_releases(api, version: str) -> list[dict]:
    """tag_name이 version인 릴리스를 **draft 포함**으로 모두 찾는다.

    태그 조회(/releases/tags/<tag>)를 쓰지 않는 것이 이 함수의 존재 이유다 —
    그 경로는 draft를 절대 못 본다.
    """
    hits: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        batch = api(f"/releases?per_page=100&page={page}") or []
        hits += [r for r in batch if r.get("tag_name") == version]
        if len(batch) < 100:
            break
    return hits


def publish(api, repo: str, version: str, required=REQUIRED, log=print) -> int:
    """확인 후 공개. 0=공개(또는 이미 공개), 1=보류(draft로 남김)."""
    hits = find_releases(api, version)

    if not hits:
        log(f"❌ 릴리스 {version} 을 찾을 수 없습니다 — 모든 빌드가 실패했을 수 있습니다.")
        return 1

    if len(hits) > 1:
        # 세 잡이 거의 동시에 붙으면 draft가 갈라져 자산이 분산될 수 있다.
        # 그 상태로 하나만 공개하면 또 반쪽 릴리스가 나간다.
        log(f"❌ 같은 태그({version})의 릴리스가 {len(hits)}개입니다 — 자산이 갈라졌습니다.")
        for r in hits:
            names = " ".join(a.get("name", "?") for a in r.get("assets") or [])
            log(f"   id={r.get('id')} draft={r.get('draft')} 자산=[{names}]")
        log("   사람이 정리해야 합니다 — draft로 남겨 둡니다.")
        return 1

    rel = hits[0]
    have = [a.get("name") for a in rel.get("assets") or []]
    log("붙어 있는 자산: " + (" ".join(have) if have else "(없음)"))

    missing = [f for f in required if f not in have]
    if missing:
        log("❌ 빠진 자산: " + " ".join(missing))
        log("   릴리스를 draft로 남겨 둡니다 — 반쪽 릴리스를 공개하면")
        log("   사이트의 다운로드 버튼이 404가 됩니다(v0.17.0에서 실제로 발생).")
        log("   해당 OS 빌드 로그를 확인한 뒤 이 워크플로를 다시 실행하세요.")
        return 1

    if not rel.get("draft"):
        log(f"이미 공개된 릴리스입니다 — 자산만 확인하고 넘어갑니다: {version}")
        return 0

    api(f"/releases/{rel['id']}", method="PATCH", body={"draft": False})
    log("✅ 세 자산 모두 확인 — 릴리스를 공개합니다.")
    log(f"공개 완료: https://github.com/{repo}/releases/tag/{version}")
    return 0


def main(argv=None) -> int:
    repo = os.environ["REPO"]
    version = os.environ["VERSION"]
    token = os.environ["GH_TOKEN"]
    return publish(github_api(repo, token), repo, version)


if __name__ == "__main__":       # pragma: no cover - 워크플로 진입점
    sys.exit(main())
