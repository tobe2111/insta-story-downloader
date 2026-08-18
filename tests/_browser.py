"""화면 검사가 **어디서 돌든** 브라우저를 찾게 한다 (감사 278).

⚠️ 왜 이 파일이 생겼나 (2026-08-17).
   공개 페이지가 진짜로 그려지는가를 보는 검사가 일곱 파일에 있었고,
   전부 이렇게 시작했다.

       CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
       if not Path(CHROME).exists():
           pytest.skip("chromium 없음 — 화면 검사 생략")

   그 경로는 **개발 컨테이너에만 있는 경로**다. GitHub 러너에는 없다.
   그래서 그 검사들은 CI에서 매번 조용히 건너뛰어졌고, 그 사실을 아무도
   몰랐다 — 초록은 초록이니까. 2026-08-17 야간 변이 전수가 그 대가를
   한꺼번에 청구했다: **놓친 21건 중 16건**이 "화면 계약을 지키는 검사가
   실은 안 돌고 있었다"였다. 첫 화면·잔고·금액·보유 대비 성적 — 사장님이
   직접 지적해서 고친 자리들이 전부 무방비였다.

   이 저장소가 스스로 적어 둔 규칙 그대로다: **건너뜀은 통과가 아니다.**

여기서는 브라우저를 세 곳에서 찾는다.

  ① ``PLAYWRIGHT_BROWSERS_PATH`` (이 컨테이너가 쓰는 방식)
  ② ``~/.cache/ms-playwright`` (``playwright install``의 기본 자리 — CI)
  ③ ``/opt/pw-browsers`` (①이 안 걸릴 때의 이 컨테이너 기본값)

부르는 쪽은 ``chrome_exe()``가 아니라 **``chromium_or_skip()``**을 쓴다 —
없을 때 건너뛰는 판단까지 여기서 한다. 왜 그래야 하는지는 그 함수의 설명에
적어 두었다(빈 문자열을 경로로 다루면 ``Path("")``가 현재 디렉터리가 된다).
그 건너뜀이 다시 조용해지지 않도록, 워크플로가 브라우저를 실제로 설치하는지는
``tests/test_the_page_contracts_actually_run.py``가 따로 지킨다.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["chrome_exe", "chromium_or_skip", "block_external",
           "CHROME_SEARCH_ROOTS"]

# 실행 파일 이름은 playwright 판마다 다르다(정식 크롬 / 헤드리스 셸).
_PATTERNS = (
    "chromium-*/chrome-linux/chrome",
    "chromium-*/chrome-linux64/chrome",
    "chromium_headless_shell-*/chrome-linux/headless_shell",
    "chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium",
)

CHROME_SEARCH_ROOTS = ("PLAYWRIGHT_BROWSERS_PATH",
                       "~/.cache/ms-playwright", "/opt/pw-browsers")


def _roots() -> list[Path]:
    out: list[Path] = []
    env = os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or ""
    # "0"은 "패키지 안에 넣어라"라는 playwright의 특수값 — 폴더가 아니다.
    if env and env != "0":
        out.append(Path(env))
    out.append(Path.home() / ".cache" / "ms-playwright")
    out.append(Path("/opt/pw-browsers"))
    return out


def chrome_exe() -> str:
    """이 환경에서 쓸 크로미움 실행 파일. 없으면 빈 문자열.

    같은 뿌리에 여러 판이 있으면 **가장 최근 판**을 쓴다(번호 정렬).
    """
    for root in _roots():
        try:
            if not root.is_dir():
                continue
        except OSError:                      # 권한 없는 경로 등
            continue
        for pat in _PATTERNS:
            hits = sorted(root.glob(pat))
            if hits:
                return str(hits[-1])
    return ""


_LOCAL = ("http://127.0.0.1", "http://localhost",
          "data:", "blob:", "about:")


def block_external(page) -> None:
    """검사가 도는 동안 **바깥 네트워크를 끊는다**.

    ⚠️ 왜 필요한가 (감사 278). 이 개발 컨테이너는 바깥으로 못 나간다.
       그래서 화면 검사는 늘 "시세를 못 받은 상태"의 페이지를 봐 왔다.
       그런데 CI 러너는 바깥이 열려 있다 — 같은 검사가 **다른 페이지**를
       보게 된다. 한쪽에만 있는 결함은 다른 쪽에서 영원히 안 보인다는 것이
       이 저장소가 감사 130에서 이미 배운 것이고, 이번 감사 자체가
       "환경이 다르면 검사가 다른 일을 한다"는 이야기였다.

       그래서 두 환경 모두에서 **바깥은 없다**로 고정한다. 실제 시세가
       필요한 검사는 `page.route()`로 자기 응답을 따로 심는다 — 나중에
       등록한 규칙이 먼저 걸리므로 이 차단보다 우선한다.
    """
    def _handle(route):
        try:
            url = route.request.url
            if url.startswith(_LOCAL):
                route.continue_()
            else:
                route.abort()
        except Exception:                    # 페이지가 먼저 닫힌 경우 등
            pass

    page.route("**/*", _handle)
    # ⚠️ **웹소켓은 `page.route()`에 안 걸린다** (2026-08-18, CI 간헐 실패).
    #    index는 시세를 REST 폴링과 바이낸스 웹소켓 **두 길**로 받는데,
    #    라우팅은 HTTP만 가로챈다. CI 러너는 바깥이 열려 있어 검사가 심은
    #    가짜 시세(36배)를 **진짜 실시간 시세가 웹소켓으로 덮어썼고**,
    #    실제 시세는 장부가와 비슷하니 '그럴듯함' 판정이 나 검사가 무너졌다.
    #    로컬 컨테이너는 웹소켓이 프록시에 막혀 있어 재현조차 안 됐다 —
    #    감사 278이 경고한 "환경이 다르면 검사가 다른 페이지를 본다" 그대로.
    #    WebSocket을 지워 두면 페이지는 스스로 REST 폴링으로 내려가고
    #    (그 경로는 라우팅이 지배한다), 두 환경이 같은 페이지를 본다.
    page.add_init_script("delete window.WebSocket;")


def chromium_or_skip():
    """크로미움 실행 파일 경로. 없으면 **여기서 검사를 건너뛴다.**

    ⚠️ 왜 함수로 만들었나 (2026-08-17 밤, 감사 280 — 내가 낸 사고).
       감사 278에서 경로 찾기를 한 곳으로 모으면서 파일마다 이렇게 남겨 뒀다.

           CHROME = chrome_exe()          # 못 찾으면 ""
           if not Path(CHROME).exists():
               pytest.skip("chromium 없음")

       그런데 **`Path("")`는 `PosixPath('.')`이고, 현재 디렉터리는 언제나
       존재한다.** 그래서 브라우저가 없는 기계에서 이 관문이 통과해 버렸고,
       playwright에게 `executable_path="."`를 넘겨 `spawn . EACCES`로 죽었다.

       그 대가가 컸다. `scripts/ledger_gate.py`가 도는 배치 넷
       (daily-paper · nightly-retrain · kr-live · deposit)은 커밋 **전에**
       장부 검사를 돌리는데, 그 목록에 이 브라우저 검사가 섞여 있었다.
       배치 러너에는 브라우저가 없다 → 관문이 죽는다 → **그날 기록이
       아예 안 남는다.** 2026-08-17 밤 페이퍼·재학습 배치가 그렇게 멈췄다.

       '없음'을 빈 문자열로 표현하면 어딘가에서 반드시 다른 뜻이 된다
       (FROZEN_IDEAS ㊿+㉛ '끄려고 적은 글자가 켜는 결과를 낸다'와 같은 계열).
       그래서 존재 확인과 건너뛰기를 **부르는 쪽에 맡기지 않는다.**
    """
    import pytest

    pytest.importorskip("playwright.sync_api",
                        reason="playwright 없음 — 화면 검사 생략")
    exe = chrome_exe()
    if not exe or not Path(exe).is_file():
        pytest.skip("chromium 없음 — 화면 검사 생략")
    return exe
