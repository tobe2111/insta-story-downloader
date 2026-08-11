"""구매자가 키를 넣는 순간 — 커버리지 0이던 대화형 경로 (감사 76).

`prompt_license`는 배포본을 산 사람이 처음 마주하는 화면이다. 커버리지에서
한 번도 실행된 적이 없었고, 들여다보니 저장 방식에 결함이 있었다:

    (base / _LICENSE_FILE).write_text(...)      # → 0o644

**팔아서 돈을 받은 그 키가 같은 기계의 다른 사용자에게 열려 있었다.**
.env의 API 키는 감사 ㊾에서 0o600으로 조여 놓고, 정작 파는 물건은 열어 둔
셈이다. 키가 새면 그게 곧 무단 복제다.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant import licensing as L          # noqa: E402

OWNER = "buyer@example.com"
SECRET = "test-secret-for-license-tests"


@pytest.fixture
def buyer(tmp_path, monkeypatch):
    """대화형 입력을 흉내 내어 prompt_license를 돌린다."""

    def _run(answers, tty=True):
        monkeypatch.setenv("QUANT_LICENSE_SECRET", SECRET)
        for k in ("QUANT_LICENSE_OWNER", "QUANT_LICENSE_KEY"):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: tty, raising=False)

        script = list(answers)
        monkeypatch.setattr("builtins.input",
                            lambda *_a: script.pop(0) if script else "")
        out: list[str] = []
        monkeypatch.setattr("builtins.print",
                            lambda *x, **k: out.append(" ".join(str(i) for i in x)))
        ok = L.prompt_license(root=str(tmp_path))
        return ok, tmp_path / L._LICENSE_FILE, "\n".join(out)

    return _run


def _good_key():
    return L.generate_key(OWNER, SECRET)


# ── 본체 ────────────────────────────────────────────────────────────

def test_a_valid_key_is_accepted_and_saved(buyer):
    ok, path, out = buyer([OWNER, _good_key()])
    assert ok is True
    assert path.exists(), "정품이라 해놓고 저장하지 않았다"
    owner, key = L._read_license_file(path)
    assert owner == OWNER and key == _good_key()
    assert "정품 확인" in out


@pytest.mark.skipif(os.name != "posix", reason="POSIX 권한이 있는 곳에서만")
def test_the_saved_license_key_is_owner_only(buyer):
    """감사 76 — 팔아서 돈을 받은 키가 남에게 열려 있으면 안 된다."""
    _, path, _ = buyer([OWNER, _good_key()])
    mode = path.stat().st_mode
    assert not (mode & (stat.S_IRWXG | stat.S_IRWXO)), (
        f"license.key가 남에게 열려 있다: {stat.filemode(mode)} — "
        "같은 기계의 다른 사용자가 읽어 그대로 쓸 수 있다")


@pytest.mark.skipif(os.name != "posix", reason="POSIX 권한이 있는 곳에서만")
def test_it_warns_when_it_cannot_protect_the_key(buyer, tmp_path, monkeypatch):
    """조이지 못하면 조용히 넘어가지 말고 알려야 한다(㊾와 같은 원칙)."""
    path = tmp_path / L._LICENSE_FILE
    path.write_text("owner: old\nkey: old\n", encoding="utf-8")
    os.chmod(path, 0o644)

    real = os.chmod
    monkeypatch.setattr(os, "chmod", lambda p, m, *a, **k: (
        (_ for _ in ()).throw(OSError("거부(모의)"))
        if Path(p).name == L._LICENSE_FILE else real(p, m, *a, **k)))

    ok, path2, out = buyer([OWNER, _good_key()])
    assert ok is True
    assert path2.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO), \
        "이 검사가 성립하려면 파일이 실제로 열려 있어야 한다"
    assert "노출될 수 있습니다" in out, "키를 지키지 못했는데 아무 말도 없었다"


def test_a_forged_key_is_refused(buyer):
    ok, path, out = buyer([OWNER, "QUANT-AAAAAA-BBBBBB-CCCCCC-DDDDDD"] * 3)
    assert ok is False, "가짜 키가 통과했다"
    assert not path.exists(), "가짜 키를 저장했다"
    assert "올바르지 않습니다" in out


def test_someone_elses_key_does_not_work(buyer):
    """다른 사람에게 발급된 키를 내 이메일로 쓸 수 없다(1인 1키)."""
    other = L.generate_key("someone.else@example.com", SECRET)
    ok, path, _ = buyer([OWNER, other] * 3)
    assert ok is False, "남의 키가 통과했다 — 1인 1키가 깨졌다"
    assert not path.exists()


def test_non_interactive_does_not_hang(buyer):
    """파이프·서비스에서는 즉시 물러난다 — 조용히 멈추면 안 된다."""
    ok, path, out = buyer([OWNER, _good_key()], tty=False)
    assert ok is False
    assert not path.exists()
    assert out == "", "비대화형인데 화면에 뭔가 찍었다"


def test_the_contact_is_shown_so_a_stuck_buyer_can_reach_us(buyer):
    _, _, out = buyer([OWNER, "QUANT-XXXXXX-XXXXXX-XXXXXX-XXXXXX"] * 3)
    assert L.contact() in out, "키를 못 넣는 구매자에게 연락처를 안 줬다"


def test_saved_key_is_actually_reusable_next_run(buyer, tmp_path, monkeypatch):
    """저장한 파일로 **다음 실행이 통과**해야 한다 — 저장 형식이 곧 계약이다."""
    ok, path, _ = buyer([OWNER, _good_key()])
    assert ok
    monkeypatch.setenv("QUANT_LICENSE_SECRET", SECRET)
    for k in ("QUANT_LICENSE_OWNER", "QUANT_LICENSE_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert L.is_licensed(root=str(tmp_path)), \
        "방금 저장한 파일을 다음 실행이 못 읽는다"
