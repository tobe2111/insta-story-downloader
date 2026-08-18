"""조종석 로그인 — 비밀번호는 **해시로만**, 어디에도 평문을 남기지 않는다.

⚠️ 왜 이 파일이 생겼나 (2026-08-18, 사장님 요청).

    "거기에 로그인이 가능해야 하지 않을까? 모두가 다 접속 가능하면 안되니까."

    맞는 요구다. 조종석은 기본이 127.0.0.1 바인딩이라 원래 본인 컴퓨터에서만
    열리지만, 다른 기기에서 보려고 비-로컬 주소에 바인딩하는 순간 같은
    네트워크의 누구나 포지션·손익을 볼 수 있었다(토큰 옵션은 있었지만
    로그인 화면이 없어 사실상 쓰이지 않았다).

⚠️ 보안 원칙 — 이 저장소는 공개다:

    · 평문 비밀번호는 **어떤 파일에도, 어떤 로그에도** 적지 않는다.
      .env에는 PBKDF2 해시만 적히고, .env 자체가 .gitignore에 있다.
    · 아이디·비밀번호를 코드에 하드코딩하지 않는다 — 커밋되는 순간
      전 세계에 공개된다. 자격증명은 사용자가 자기 기계에서
      `python -m quant web-passwd`로 직접 설정한다.
    · 비교는 전부 상수 시간(hmac.compare_digest) — 한 글자씩 맞춰 보는
      타이밍 공격을 막는다.
    · 세션 비밀은 프로세스마다 새로 만든다 — 서버를 재시작하면 다시
      로그인해야 한다. 불편하지만, 훔친 쿠키가 영원히 사는 것보다 낫다.
    · 실패 응답은 "아이디 또는 비밀번호가 다릅니다" 하나다 — 어느 쪽이
      틀렸는지 알려주면 아이디가 맞는지 공짜로 확인시켜 주는 셈이다.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets

PBKDF2_ITERATIONS = 240_000        # OWASP 권고 수준(sha256 기준)
SESSION_TTL_SECONDS = 12 * 3600    # 12시간 — 하루 작업이면 충분하고, 밤새 살진 않는다
COOKIE_NAME = "quant_session"

ENV_USER = "QUANT_WEB_USER"
ENV_HASH = "QUANT_WEB_PASSWORD_HASH"


# ── 비밀번호 해시 ───────────────────────────────────────────────

def hash_password(password: str, salt_hex: str | None = None) -> str:
    """`pbkdf2$반복수$salt$해시` — 평문은 이 함수 밖으로 나가지 않는다."""
    salt_hex = salt_hex or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                             bytes.fromhex(salt_hex), PBKDF2_ITERATIONS)
    return f"pbkdf2${PBKDF2_ITERATIONS}${salt_hex}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """상수 시간 비교 — 틀린 형식은 조용히 False(공격자에게 힌트를 안 준다)."""
    try:
        algo, iters, salt_hex, want = str(stored).split("$", 3)
        if algo != "pbkdf2":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                 bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(dk.hex(), want)
    except (ValueError, TypeError):
        return False


# ── 세션 쿠키 ───────────────────────────────────────────────────

_SESSION_SECRET: bytes | None = None


def _secret() -> bytes:
    global _SESSION_SECRET
    if _SESSION_SECRET is None:
        _SESSION_SECRET = secrets.token_bytes(32)
    return _SESSION_SECRET


def issue_session(now: float) -> str:
    """만료시각.서명 — 서명은 프로세스 비밀로 만든 HMAC."""
    exp = str(int(now) + SESSION_TTL_SECONDS)
    sig = hmac.new(_secret(), exp.encode("ascii"), "sha256").hexdigest()
    return f"{exp}.{sig}"


def check_session(value: str, now: float) -> bool:
    try:
        exp, sig = str(value).split(".", 1)
        want = hmac.new(_secret(), exp.encode("ascii"), "sha256").hexdigest()
        return hmac.compare_digest(sig, want) and float(exp) >= now
    except (ValueError, TypeError):
        return False


def configured() -> bool:
    """아이디와 해시가 둘 다 설정돼 있어야 로그인 관문이 켜진다."""
    return bool(os.environ.get(ENV_USER)) and bool(os.environ.get(ENV_HASH))


# ── 자격증명 저장 (.env — 커밋 금지 목록) ───────────────────────

def set_credentials(user: str, password: str, env_path: str = ".env") -> str:
    """.env에 아이디와 **해시만** 적는다(0o600, 원자적 교체). 해시를 반환.

    기존 .env의 다른 키는 그대로 보존한다 — API 키를 지우면 안 된다.
    """
    from quant.utils.envfile import parse_env_text, write_private

    pairs: dict[str, str] = {}
    try:
        with open(env_path, encoding="utf-8") as fh:
            pairs = parse_env_text(fh.read())
    except OSError:
        pass
    hashed = hash_password(password)
    pairs[ENV_USER] = user.strip()
    pairs[ENV_HASH] = hashed
    text = "".join(f"{k}={v}\n" for k, v in pairs.items())
    write_private(env_path, text)
    os.environ[ENV_USER] = pairs[ENV_USER]
    os.environ[ENV_HASH] = hashed
    return hashed


# ── 화면 ────────────────────────────────────────────────────────

_PAGE = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>로그인 — QUANT 조종석</title><style>
body{{background:#0a0b0e;color:#f4f5f7;font-family:-apple-system,BlinkMacSystemFont,
"Segoe UI","Noto Sans KR",sans-serif;display:flex;align-items:center;
justify-content:center;min-height:100vh;margin:0}}
.box{{background:#0e1013;border:1px solid #262d3f;border-radius:16px;
padding:34px 36px;width:340px}}
h1{{font-size:19px;margin:0 0 6px}} .sub{{color:#9aa3b2;font-size:12.5px;line-height:1.6}}
label{{display:block;font-size:12px;color:#9aa3b2;margin:14px 0 5px}}
input{{width:100%;box-sizing:border-box;background:#131620;color:#f4f5f7;
border:1px solid #262d3f;border-radius:9px;padding:10px 12px;font-size:14px}}
button{{width:100%;margin-top:18px;background:#4f7cff;color:#fff;border:0;
border-radius:9px;padding:11px;font-size:14.5px;font-weight:700;cursor:pointer}}
.err{{color:#f04452;font-size:12.5px;margin-top:12px}}</style></head><body>
<div class="box"><h1>QUANT 조종석</h1>
<div class="sub">본인 확인 후 들어갈 수 있습니다. 비밀번호는 이 컴퓨터에
해시로만 저장돼 있고, 서버를 재시작하면 다시 로그인합니다.</div>
<form method="post" action="/login/run">
<label>아이디</label><input name="user" autocomplete="username" autofocus>
<label>비밀번호</label><input name="password" type="password"
  autocomplete="current-password">
<button>들어가기</button></form>
{err}{setup}</div></body></html>"""


def render_login_form(error: str = "") -> str:
    setup = ""
    if not configured():
        setup = ('<div class="sub" style="margin-top:14px">아직 로그인이 설정되지 '
                 '않았습니다 — 터미널에서 <b>python -m quant web-passwd</b> 로 '
                 '아이디·비밀번호를 만든 뒤 서버를 다시 켜세요.</div>')
    err = f'<div class="err">{error}</div>' if error else ""
    return _PAGE.format(err=err, setup=setup)


def run_login(params: dict, out_headers: dict) -> str:
    """로그인 시도 — 성공이면 세션 쿠키를 심고 첫 화면으로 보낸다.

    실패는 1초 늦게, 한 문장으로만 답한다(무차별 대입·계정 탐색 방지).
    """
    import time

    if not configured():
        return render_login_form()
    user = str(params.get("user") or "")
    password = str(params.get("password") or "")
    good_user = hmac.compare_digest(user, os.environ.get(ENV_USER, ""))
    good_pass = verify_password(password, os.environ.get(ENV_HASH, ""))
    if not (good_user and good_pass):
        time.sleep(1.0)            # 실패 비용 — 초당 수천 번 시도를 막는다
        return render_login_form("아이디 또는 비밀번호가 다릅니다.")
    out_headers["Set-Cookie"] = (
        f"{COOKIE_NAME}={issue_session(time.time())}; "
        "HttpOnly; SameSite=Strict; Path=/")
    return ('<!doctype html><meta charset="utf-8">'
            '<meta http-equiv="refresh" content="0;url=/">'
            '<a href="/">들어가는 중…</a>')
