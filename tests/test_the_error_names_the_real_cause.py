"""**빈 표를 KRX 탓으로만 말하지 않는다** (감사 290).

2026-08-19 배치 로그는 이렇게 남았다.

    KRX 로그인 실패: KRX_ID 또는 KRX_PW 환경 변수가 설정되지 않았습니다.
    KRX 수급 부착 실패 069500.KS: KRX가 … 구간에 빈 표를 줬다

앞줄은 라이브러리가 찍은 것이고 뒷줄은 **우리가** 적은 것이다. 우리 쪽
설정이 빠져서 빈 표가 온 것인데, 우리 문구는 KRX를 탓했다. 그러면 읽는
사람은 계속 엉뚱한 곳을 의심한다.

`quant/data/krx.py` 머리말이 바로 그 실수를 한 번 겪고 적어 둔 경고다.
같은 일이 한 겹 위에서 또 났다 — 이 저장소가 반복해서 걸리는
"경보가 원인을 잘못 말한다" 계열(감사 264와 같은 병)이다.

⚠️ 단정하지는 않는다. 로그인 없이도 되는 구간이 있을 수 있으므로
   "그럴 수 있다"로 적는다 — 아는 만큼만, 그러나 아는 것은 전부.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.data import krx  # noqa: E402


def _clear(monkeypatch):
    for k in krx._CRED_ENV:
        monkeypatch.delenv(k, raising=False)


def test_a_missing_login_is_named(monkeypatch):
    _clear(monkeypatch)
    hint = krx._credential_hint()
    assert hint, "설정이 빠졌는데 아무 말도 안 한다"
    for k in krx._CRED_ENV:
        assert k in hint, f"어느 설정이 빠졌는지 말하지 않는다: {hint!r}"
    assert "우리 설정" in hint, (
        f"원인이 우리 쪽일 수 있다는 말이 없다 — 그러면 계속 KRX를 의심한다:\n{hint}")


def test_it_does_not_declare_the_cause(monkeypatch):
    """단정하면 다른 원인일 때 이번엔 반대로 틀린다."""
    _clear(monkeypatch)
    hint = krx._credential_hint()
    assert "수 있다" in hint, f"모르는 것을 아는 것처럼 말한다:\n{hint}"


def test_a_configured_login_says_nothing(monkeypatch):
    """대조군 — 설정이 갖춰졌는데 이 말이 붙으면 매번 뜨는 배경음이 된다."""
    for k in krx._CRED_ENV:
        monkeypatch.setenv(k, "값")
    assert krx._credential_hint() == ""


def test_a_half_configured_login_still_warns(monkeypatch):
    """둘 중 하나만 있어도 로그인은 안 된다 — 그 절반도 말해야 한다."""
    monkeypatch.setenv(krx._CRED_ENV[0], "값")
    monkeypatch.delenv(krx._CRED_ENV[1], raising=False)
    hint = krx._credential_hint()
    assert krx._CRED_ENV[1] in hint and krx._CRED_ENV[0] not in hint, hint


def test_blank_values_count_as_missing(monkeypatch):
    """빈 문자열은 '설정했다'가 아니다 — 워크플로가 비밀값을 못 찾으면 빈칸이 온다."""
    for k in krx._CRED_ENV:
        monkeypatch.setenv(k, "   ")
    assert krx._credential_hint(), "빈 값을 설정된 것으로 친다"


def test_both_empty_table_messages_carry_the_hint():
    """수급과 재무 **두 곳 모두** — 한 곳만 고치면 다른 곳이 계속 헷갈린다.

    같은 규칙을 두 곳에 나눠 적으면 언젠가 한 곳이 갈라진다(FROZEN_IDEAS ①).
    """
    src = (ROOT / "quant" / "data" / "krx.py").read_text("utf-8")
    # 설명 주석에 그대로 인용해 둔 줄은 세지 않는다 — 주석은 안 나간다.
    empties = [ln for ln in src.splitlines()
               if not ln.lstrip().startswith("#")
               and ("빈 표를 줬다" in ln or "재무 표를 비워서 줬다" in ln)]
    assert len(empties) == 2, f"빈 표 문구가 둘이 아니다 — 검사가 낡았다: {empties}"
    assert src.count("+ _credential_hint()") == 2, (
        "빈 표를 말하는 두 자리 중 한 곳만 원인을 덧붙인다")
