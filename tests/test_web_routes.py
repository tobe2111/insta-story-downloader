"""웹 조종석의 라우트 표 — 이름이 아니라 **실행**으로 확인한다.

배경: 커버리지를 보니 `do_GET` 79줄이 미실행이었다. 기존 검사(test_web_csrf)는
가드가 막는 403 경로와 /health만 지나가고, 라우트 분기 자체는 한 번도 돌지
않았다.

그 자리에 두 가지 결함이 살 수 있다.

  ① **엉뚱한 핸들러** — `/optimize/run`이 `run_sweep_html`을 부르는 복사·붙여
     넣기 사고. 사장님이 최적화를 눌렀는데 스윕이 돈다. 아무도 모른다.

  ② **보호 목록에서 빠진 상태변경 경로** — 기존 검사는 소스에서
     `parsed.path == "/..."` 를 정규식으로 긁어 **`/run`으로 끝나는 것만**
     `_MUTATING`에 있는지 본다. 새 경로를 `/deposit/add` 같은 이름으로 만들면
     그 그물을 그냥 빠져나가고, CSRF 방어 없이 열린다 — 이 프로젝트에서
     장부 오염은 돈이 나가는 것만큼 나쁘다.

그래서 여기서는 **이름 규칙을 믿지 않는다.** 모든 라우트를 실제로 태워
어떤 함수가 불리는지 보고, 실행(run_*) 계열에 닿는 경로는 반드시 보호
목록에 있어야 한다고 요구한다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.web import server as ws          # noqa: E402

SRC = (ROOT / "quant" / "web" / "server.py").read_text("utf-8")

# 경로 → 그 경로가 불러야 할 app 함수. 새 라우트가 생기면 여기에 적어야 하고,
# 적는 순간 '이게 상태를 바꾸는가'를 결정하게 된다.
EXPECTED = {
    "/": "render_form",
    "/index.html": "render_form",
    "/backtest": "run_backtest_html",
    "/monitor": "render_monitor",
    "/api/state": "state_json",
    "/broadcast": "render_broadcast",
    "/api/candles": "candles_json",
    "/api/broadcast": "broadcast_json",
    # 시세 중계(조회 전용) — 판정 사다리는 워커에만 있고 여기는 넘기기만 한다
    "/api/quotes": "quotes_proxy",
    "/portfolio": "render_portfolio_form",
    "/portfolio/run": "run_portfolio_html",
    "/screener": "render_screener_form",
    "/screener/run": "run_screener_html",
    "/optimize": "render_optimize_form",
    "/optimize/run": "run_optimize_html",
    "/validate": "render_validate_form",
    "/validate/run": "run_validate_html",
    "/deposit": "render_deposit_form",
    "/deposit/run": "run_deposit_html",
    "/sweep": "render_sweep_form",
    "/sweep/run": "run_sweep_html",
    # 내 전략(설치형) — 조회 3, 상태변경 3(아래 POST 표)
    "/ingest": "render_ingest_form",
    "/pins": "render_pins_page",
    "/pin/prepare": "render_pin_prepare",
    # 로그인 화면(2026-08-18 사장님: "모두가 다 접속 가능하면 안되니까")
    "/login": "render_login_form",
}

# POST 전용 — 긴 본문(자료 붙여넣기)과 상태 변경이 있는 경로.
# GET 표와 분리한 이유: 이 셋은 do_GET에서 404여야 한다(쿼리로 상태를
# 바꾸는 경로를 늘리지 않는다 — /deposit/run의 교훈).
EXPECTED_POST = {
    "/ingest/run": "run_ingest_html",
    "/pin/save": "run_pin_save",
    "/pin/unpin": "run_pin_unpin",
    # 로그인 제출 — 비밀번호가 본문에 실리므로 POST 전용(쿼리에 남기지 않는다)
    "/login/run": "run_login",
}

APP_FUNCS = sorted(set(EXPECTED.values()) | set(EXPECTED_POST.values()))


class _Wire(ws.QuantHandler):
    """소켓 없이 do_GET을 끝까지 돌린다."""

    def __init__(self, path, headers=None):  # noqa: D107
        import io
        self.path = path
        self.headers = {"Host": "127.0.0.1:8000", "Content-Length": "0",
                        **(headers or {})}
        self.rfile = io.BytesIO(b"")
        self.sent = []

    def _send(self, body, status=200, content_type="text/html; charset=utf-8"):
        self.sent.append((status, str(body)[:200]))


@pytest.fixture
def drive(monkeypatch):
    """라우트를 태우고 (불린 함수 이름, 상태코드)를 돌려준다."""
    called: list[str] = []

    for name in APP_FUNCS:
        def rec(*_a, _n=name, **_k):
            called.append(_n)
            return "{}" if _n.endswith("_json") else f"<h1>{_n}</h1>"
        monkeypatch.setattr(ws, name, rec)

    def _go(path, method="GET", **headers):
        called.clear()
        w = _Wire(path, headers)
        (w.do_GET if method == "GET" else w.do_POST)()
        status = w.sent[0][0] if w.sent else None
        return (called[0] if called else None), status

    return _go


# ── ① 라우트가 제 핸들러로 간다 ─────────────────────────────────

@pytest.mark.parametrize("path,func", sorted(EXPECTED.items()))
def test_route_dispatches_to_its_own_handler(drive, path, func):
    got, status = drive(path)
    assert got == func, f"{path} 가 {func} 대신 {got} 를 불렀다"
    assert status == 200, (path, status)


def test_unknown_path_is_404(drive):
    _, status = drive("/nope")
    assert status == 404


@pytest.mark.parametrize("path,func", sorted(EXPECTED_POST.items()))
def test_post_route_dispatches_to_its_own_handler(drive, path, func):
    got, status = drive(path, method="POST")
    assert got == func, f"POST {path} 가 {func} 대신 {got} 를 불렀다"
    assert status == 200, (path, status)


@pytest.mark.parametrize("path", sorted(EXPECTED_POST))
def test_post_only_routes_do_not_answer_get(drive, path):
    """상태를 바꾸는 새 경로는 GET으로 열리지 않는다 — 쿼리로 상태를 바꾸는
    경로를 더 늘리지 않는다(/deposit/run의 교훈)."""
    _, status = drive(path)
    assert status == 404, f"GET {path} 가 {status} — POST 전용이어야 한다"


def test_health_needs_no_handler(drive):
    got, status = drive("/health")
    assert status == 200 and got is None


# ── ② 실행 경로는 빠짐없이 CSRF 보호를 받는다 ───────────────────

def _mutating_routes():
    """실행(run_*) 계열에 닿는 경로 — 이름이 아니라 표에서 뽑는다."""
    both = {**EXPECTED, **EXPECTED_POST}
    return sorted(p for p, f in both.items() if f.startswith("run_"))


@pytest.mark.parametrize("path", _mutating_routes())
def test_every_executing_route_is_in_the_protected_list(path):
    """`/run`으로 끝나지 않는 실행 경로도 보호돼야 한다.

    기존 검사는 소스에서 `/run` 접미사만 긁었다 — 새 경로를 `/deposit/add`로
    만들면 그물을 빠져나간다. 여기서는 접미사가 아니라 **무엇을 하는가**로
    본다.
    """
    assert path in ws.QuantHandler._MUTATING, \
        f"{path} 는 실행 경로인데 CSRF 보호 목록에 없다"


@pytest.mark.parametrize("path", _mutating_routes())
def test_every_executing_route_actually_returns_403_cross_site(drive, path):
    """목록에 있는 것과 실제로 막히는 것은 다르다 — 끝까지 태워 확인한다."""
    got, status = drive(path, **{"Sec-Fetch-Site": "cross-site"})
    assert status == 403, f"{path} 가 교차출처에서 실행됐다"
    assert got is None, f"{path} 가 막히기 전에 {got} 를 이미 실행했다"


def test_readonly_routes_are_not_over_blocked(drive):
    """조회 경로까지 막으면 로컬 도구가 못 쓰게 된다(과잉 차단 방지)."""
    for path, func in EXPECTED.items():
        if func.startswith("run_"):
            continue
        _, status = drive(path, **{"Sec-Fetch-Site": "cross-site"})
        assert status != 403, f"조회 경로 {path} 가 막혔다"


# ── ③ 새 라우트가 조용히 늘지 않는다 ───────────────────────────

def test_no_route_escapes_this_table():
    """소스의 라우트와 위 표가 정확히 일치해야 한다.

    새 라우트를 추가하면 이 검사가 먼저 빨개진다 — 그러면 표에 적어야 하고,
    적는 순간 '이게 상태를 바꾸는가(=보호가 필요한가)'를 결정하게 된다.
    그 결정을 강제하는 것이 이 검사의 목적이다.
    """
    found = set(re.findall(r'parsed\.path == "(/[^"]*)"', SRC))
    found |= set(re.findall(r'parsed\.path in \(([^)]*)\)', SRC)[0:1] and
                 re.findall(r'"(/[^"]*)"',
                            re.findall(r'parsed\.path in \(([^)]*)\)', SRC)[0]))
    known = set(EXPECTED) | set(EXPECTED_POST) | {"/health"}
    assert found == known, (
        f"표에 없는 라우트: {sorted(found - known)} / "
        f"소스에 없는 라우트: {sorted(known - found)}")


def test_protected_list_has_no_dead_entries():
    """보호 목록에 존재하지 않는 경로가 남아 있으면 착각을 만든다."""
    dead = set(ws.QuantHandler._MUTATING) - set(EXPECTED) - set(EXPECTED_POST)
    assert not dead, f"없는 경로를 보호하고 있다(오래된 항목?): {sorted(dead)}"
