"""`quant setup` — 구매자가 가장 먼저 치는 명령을 실제로 돌린다.

배경: 커버리지를 보니 `_cmd_setup` 53줄이 **한 번도 실행된 적이 없었다.**
백테스트·페이퍼는 키가 없어도 돌기 때문에 개발 중에 아무도 이 길을 가지
않는다 — 그런데 이건 프로그램을 받은 사람이 **처음 치는 명령**이고, 하는
일이 **API 키를 디스크에 쓰는 것**이다.

특히 중요한 것은 이 명령이 화면에 하는 **보안 약속**이다:

    파일 권한: 600 (본인만 읽기) — 확인됨

결함 ㊾에서 고친 자리가 정확히 여기다. 예전에는 chmod 성공 여부와 무관하게
저 문장을 찍었다 — **지켜지지 않은 보안 약속은 느슨한 권한보다 위험하다.**
사용자가 안심하고 실거래 키를 넣기 때문이다. 그 고침이 CLI 수준에서 진짜
동작하는지는 지금까지 아무도 확인하지 않았다.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant import cli                      # noqa: E402


class Answers:
    """대화형 입력을 흉내 낸다. input()과 getpass()가 같은 대본을 소비한다."""

    def __init__(self, script):
        self.script = list(script)
        self.prompts: list[str] = []
        self.secret_prompts: list[str] = []

    def input(self, prompt=""):
        self.prompts.append(prompt)
        return self.script.pop(0) if self.script else ""

    def getpass(self, prompt=""):
        self.secret_prompts.append(prompt)
        return self.script.pop(0) if self.script else ""


class FakeFrame:
    """get_ohlcv 반환값 흉내 — attrs만 보면 된다."""

    def __init__(self, synthetic=False):
        self.attrs = {"synthetic_fallback": synthetic}


@pytest.fixture
def run_setup(tmp_path, monkeypatch):
    """tmp_path를 작업 디렉터리로 삼아 setup을 돌리고 (.env 경로, 출력)을 준다.

    ⚠️ 거래소·텔레그램 연결 확인은 가짜로 막는다. setup은 키를 넣으면 진짜
    거래소에 붙어 보는데, 검사가 바깥 네트워크에 기대면 남의 서버가 느린 날
    우리 CI가 빨개진다(그리고 그건 우리 결함이 아니라서 아무도 안 고친다).
    """

    def _run(script, env=None, synthetic=False):
        monkeypatch.chdir(tmp_path)
        for k in list(os.environ):
            if k.startswith(("EXCHANGE_", "ALPACA_", "KIS_", "TELEGRAM_",
                             "FRED_", "FMP_")):
                monkeypatch.delenv(k, raising=False)
        for k, v in (env or {}).items():
            monkeypatch.setenv(k, v)

        a = Answers(script)
        monkeypatch.setattr("builtins.input", a.input)
        import getpass as _gp
        monkeypatch.setattr(_gp, "getpass", a.getpass)

        # 바깥 세계를 차단한다 — setup은 키가 들어오면 진짜로 붙어 본다.
        import quant.data as _qd
        a.provider_calls: list[str] = []

        class _P:
            def get_ohlcv(self, *_x, **_k):
                a.provider_calls.append("ohlcv")
                return FakeFrame(synthetic)

        monkeypatch.setattr(_qd, "get_provider", lambda *_x, **_k: _P())

        import quant.live.notifications as _qn
        a.telegram: list[str] = []

        class _T:
            def __init__(self, *_x, **_k):
                pass

            def send(self, msg):
                a.telegram.append(msg)

        monkeypatch.setattr(_qn, "TelegramNotifier", _T)

        out: list[str] = []
        monkeypatch.setattr("builtins.print",
                            lambda *x, **k: out.append(" ".join(str(i) for i in x)))
        cli._cmd_setup(object())
        return tmp_path / ".env", "\n".join(out), a

    return _run


# ── 본체 ────────────────────────────────────────────────────────────

def test_keys_are_written_and_file_is_owner_only(run_setup):
    """키가 .env에 저장되고, posix에서는 실제로 600이다."""
    # 1번 그룹(암호화폐)만 y, 나머지는 엔터로 건너뛴다
    envf, out, _ = run_setup(["y", "KEY-ABC", "SECRET-XYZ", "", "", "", "", ""])

    assert envf.exists(), "setup이 .env를 만들지 않았다"
    text = envf.read_text(encoding="utf-8")
    assert "EXCHANGE_API_KEY=KEY-ABC" in text
    assert "EXCHANGE_SECRET=SECRET-XYZ" in text
    # 빈 입력은 저장하지 않는다(빈 값으로 기존 키를 지우면 안 된다)
    assert "EXCHANGE_PASSWORD" not in text

    if os.name == "posix":
        mode = envf.stat().st_mode
        assert not (mode & (stat.S_IRWXG | stat.S_IRWXO)), \
            f".env가 남에게 열려 있다: {stat.filemode(mode)}"


def test_permission_message_matches_reality(run_setup):
    """화면의 보안 약속이 **실제 파일 권한과 일치**해야 한다(결함 ㊾).

    지켜지지 않은 약속은 느슨한 권한보다 위험하다 — 사용자가 그 문장을 믿고
    실거래 키를 넣는다.
    """
    envf, out, _ = run_setup(["y", "KEY-ABC", "SECRET-XYZ", "", "", "", "", ""])

    claims_600 = "600 (본인만 읽기) — 확인됨" in out
    if os.name != "posix":
        assert not claims_600, "윈도우에서 600을 보장한다고 말했다"
        assert "보장할 수 없습니다" in out
        return

    actually_600 = not (envf.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO))
    assert claims_600 == actually_600, (
        f"화면은 600={claims_600} 이라 했는데 실제는 {actually_600} "
        f"({stat.filemode(envf.stat().st_mode)})")


@pytest.mark.skipif(os.name != "posix", reason="POSIX 권한이 있는 곳에서만 의미 있다")
def test_when_the_promise_cannot_be_kept_it_is_not_made(run_setup, tmp_path,
                                                        monkeypatch):
    """권한을 조이지 못하면 **600이라고 말하지 않고 경고해야 한다**.

    이게 결함 ㊾의 본체다. 위의 '일치' 검사는 정상 경로만 지나가므로,
    약속과 현실을 잇는 배선이 끊겨도(예: 무조건 600이라고 출력) 초록이다.
    여기서는 저장이 느슨하게 끝나게 만들어 **약속을 지킬 수 없는 상황**을 만든다.
    """
    envf = tmp_path / ".env"
    envf.write_text("ALPACA_API_KEY=OLD\n", encoding="utf-8")
    os.chmod(envf, 0o644)                       # 남이 읽을 수 있는 상태

    # ⚠️ 예전에는 여기서 **chmod를 실패시켜** '약속을 못 지키는 상황'을
    #    만들었다. 감사 190에서 저장 방식이 바뀌어(0o600 임시 파일 →
    #    os.replace) chmod를 아예 안 쓰게 됐고, 그래서 chmod를 막아도
    #    파일이 느슨해지지 않는다 — 이 검사의 **전제가 사라진 것**이지
    #    계약이 사라진 건 아니다.
    #
    #    지키려는 계약은 그대로다: **권한을 확인하지 못했으면 "확인됨"이라
    #    말하지 않는다.** 그래서 이제는 저장 자체가 느슨하게 끝나는 상황을
    #    만든다(윈도우처럼 POSIX 권한이 의미 없는 환경도 이 경로로 온다).
    import quant.utils.envfile as _E

    real_write = _E._write_private

    def loose(fp, text):
        real_write(fp, text)
        if Path(fp).name == ".env":
            os.chmod(fp, 0o644)                 # 조여지지 않은 채로 남는다

    monkeypatch.setattr(_E, "_write_private", loose)

    envf2, out, _ = run_setup(["y", "KEY-ABC", "SEC-XYZ", "", "", "", "", ""])

    assert envf2.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO), \
        "이 검사가 성립하려면 파일이 실제로 열려 있어야 한다"
    assert "600 (본인만 읽기) — 확인됨" not in out, \
        "지키지 못한 보안 약속을 지켰다고 말했다 (결함 ㊾ 재발)"
    assert "chmod 600 .env" in out, "사용자에게 직접 조이라고 알려주지 않았다"


def test_secrets_are_read_without_echo(run_setup):
    """시크릿은 getpass로 받는다 — 어깨너머·터미널 로그에 남으면 안 된다."""
    _, _, a = run_setup(["y", "KEY-ABC", "SECRET-XYZ", "PASSPHRASE",
                         "", "", "", ""])
    secret_fields = " ".join(a.secret_prompts)
    assert "EXCHANGE_SECRET" in secret_fields, "시크릿이 화면에 노출되는 input으로 읽혔다"
    assert "EXCHANGE_PASSWORD" in secret_fields
    # 반대로 키 이름 같은 비밀 아닌 값은 평범한 input이어야 한다(가림 과잉 방지)
    assert any("EXCHANGE_API_KEY" in p for p in a.prompts)


def test_declining_everything_writes_nothing(run_setup):
    """전부 건너뛰면 파일을 만들지 않는다(기존 .env를 건드리지도 않는다)."""
    envf, out, _ = run_setup(["", "", "", "", ""])
    assert not envf.exists(), "아무것도 입력하지 않았는데 .env를 만들었다"
    assert "변경 없음" in out


def test_existing_env_is_updated_not_replaced(run_setup, tmp_path):
    """이미 있는 .env의 다른 키를 지우지 않는다."""
    (tmp_path / ".env").write_text(
        "ALPACA_API_KEY=OLD-ALPACA\nFRED_API_KEY=OLD-FRED\n", encoding="utf-8")
    envf, _, _ = run_setup(["y", "KEY-NEW", "SEC-NEW", "", "", "", "", ""])
    text = envf.read_text(encoding="utf-8")
    assert "EXCHANGE_API_KEY=KEY-NEW" in text
    assert "ALPACA_API_KEY=OLD-ALPACA" in text, "무관한 기존 키가 사라졌다"
    assert "OLD-FRED" in text


def test_already_set_keys_are_marked_so_user_can_keep_them(run_setup):
    """이미 설정된 값은 '유지' 안내가 떠야 한다 — 모르고 덮어쓰면 실거래가 멈춘다."""
    _, _, a = run_setup(["y", "", "", "", "", "", "", ""],
                        env={"EXCHANGE_API_KEY": "ALREADY-THERE"})
    marked = [p for p in a.prompts if "EXCHANGE_API_KEY" in p]
    assert marked and "이미 설정됨" in marked[0], marked


def test_every_group_can_be_reached(run_setup):
    """다섯 그룹이 모두 제시된다 — 그룹 하나가 조용히 빠지면 키를 못 넣는다."""
    _, out, _ = run_setup(["", "", "", "", ""])
    for title, _guide, _fields in cli._SETUP_GROUPS:
        assert title in out, f"그룹이 안 보인다: {title}"


def test_exchange_keys_trigger_a_real_connection_check(run_setup):
    """거래소 키를 넣으면 실제로 붙어 본다 — 오타를 그때 잡아야 한다."""
    _, out, a = run_setup(["y", "KEY-ABC", "SEC-XYZ", "", "", "", "", ""])
    assert a.provider_calls, "키를 저장해 놓고 연결 확인을 하지 않았다"
    assert "🔌" in out and "정상" in out


def test_synthetic_fallback_is_reported_as_a_problem_not_success(run_setup):
    """합성 폴백은 '연결 정상'이 아니다.

    폴백은 거래소에 못 붙었다는 뜻인데, 여기서 '정상'이라 말하면 사용자는
    키가 맞다고 믿고 넘어간다 — 오늘 감사 내내 나온 '측정과 보고가 어긋난다'
    계열이다.
    """
    _, out, _ = run_setup(["y", "KEY-ABC", "SEC-XYZ", "", "", "", "", ""],
                          synthetic=True)
    assert "폴백" in out, out
    assert "🔌 거래소 시세 연결: ✅ 정상" not in out


def test_telegram_key_sends_a_test_message(run_setup):
    """알림 키를 넣으면 테스트 메시지를 실제로 쏜다 — 안 오면 그 자리서 안다."""
    # 그룹 순서: 코인(n) → 미국(n) → 한국(n) → 텔레그램(y) → 보조(n)
    _, out, a = run_setup(["", "", "", "y", "BOT-TOKEN", "CHAT-ID", ""])
    assert a.telegram, "텔레그램 키를 저장해 놓고 테스트 발송을 하지 않았다"
    assert "📨" in out


def test_no_secret_value_is_ever_printed(run_setup):
    """저장한 비밀값이 화면에 다시 찍히면 안 된다."""
    _, out, _ = run_setup(["y", "KEY-ABC", "SUPER-SECRET-VALUE", "", "",
                           "", "", ""])
    assert "SUPER-SECRET-VALUE" not in out
    assert "KEY-ABC" not in out
