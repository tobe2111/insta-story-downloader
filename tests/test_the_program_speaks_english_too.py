"""프로그램(CLI·조종석)도 영어로 읽히는가 (2026-08-26 감사 326).

사장님 지시: *"서비스 영어로도 만들어줘 홈페이지나 **프로그램이나**."*

■ 이 검사가 지키는 것

  ① **숫자를 건드리지 않는가** — 이게 가장 중요하다. 이 프로그램은 돈
     이야기를 한다. 옮기면서 금액·비율·날짜가 한 자라도 바뀌면 그건
     번역이 아니라 **장부 조작**이다.
  ② **모르는 문장을 지어내지 않는가** — 사전에 없으면 한국어로 남아야
     한다. 기계 번역으로 메우면 숫자 옆에서 사실이 아닌 주장이 된다.
  ③ **한국어를 빼앗지 않는가** — 아무것도 지정하지 않으면 원본(한국어)이다.
     터미널 로케일(LANG=en_US)로 짐작하지 않는다 — 한국 사용자의 터미널이
     영어인 경우가 흔하고, 그때 원본을 잃는 것은 짐작이 아니라 사고다.
  ④ **한계가 살아남는가** — "수익을 보장하지 않습니다"가 영어에서 사라지면
     그건 번역 실수가 아니라 다른 제품이다.
  ⑤ **조종석이 같은 사전을 쓰는가** — 사전을 두 벌로 만들면 같은 날 같은
     문장이 사이트와 조종석에서 다르게 나간다(FROZEN_IDEAS ①).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from quant import i18n

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def english(monkeypatch):
    monkeypatch.setenv("QUANT_LANG", "en")
    return i18n


@pytest.fixture
def korean(monkeypatch):
    monkeypatch.delenv("QUANT_LANG", raising=False)
    return i18n

# ── ① 숫자는 한 자도 바뀌지 않는다 ────────────────────────────

_MONEY = [
    "\n=== ma_cross · BTC/USDT (500봉) ===",
    "  실전 적중 52.1% (25/48건) · 우연 배제 아니오",
    "총수익률   :    -19.11%",
    "초과수익   :    -23.00%  ⚠️ 벤치마크 하회",
    "🏃 장중 도전자 — 자산 1,019.08 USDT (1.91%) · 이번 회차 체결 3건 · "
    "건너뜀 2종목 · 누적 비용 0.42 USDT",
]


@pytest.mark.parametrize("line", _MONEY)
def test_the_numbers_survive_the_translation(english, line):
    """**가장 중요한 검사** — 옮긴 뒤에도 숫자가 글자 그대로 남는가."""
    out = english.t(line)
    assert out != line, f"아예 안 옮겨졌다: {line!r}"
    want = re.findall(r"[-+]?\d[\d,]*(?:\.\d+)?", line)
    got = re.findall(r"[-+]?\d[\d,]*(?:\.\d+)?", out)
    assert want == got, (
        f"번역이 숫자를 바꿨다.\n  ko: {want}\n  en: {got}\n  {out}")


def test_an_unknown_sentence_stays_korean(english):
    """모르면 **지어내지 않는다** — 한국어로 남는다."""
    unknown = "이 문장은 사전에 없습니다. 지어내면 안 됩니다."
    assert english.t(unknown) == unknown


def test_an_unknown_word_inside_a_known_sentence_stays_korean(english):
    """규칙이 잡아 둔 자리에 모르는 말이 오면 그 말만 한국어로 남는다."""
    out = english.t("  실전 적중 52.1% (25/48건) · 우연 배제 뭐라구요")
    assert "Live hit rate" in out, out
    assert "뭐라구요" in out, f"모르는 말을 지어냈다: {out}"

# ── ② 아무것도 안 고르면 한국어(원본)다 ───────────────────────

def test_korean_is_the_default(korean):
    line = "⚠️ 과거 성과는 미래 수익을 보장하지 않습니다."
    assert korean.t(line) == line, "지정하지 않았는데 영어가 됐다"


def test_the_terminal_locale_does_not_take_korean_away(monkeypatch):
    """대조군 — 터미널이 영어라고 원본을 빼앗으면 안 된다.

    한국 사용자의 터미널이 `LANG=en_US.UTF-8`인 경우는 아주 흔하다.
    """
    monkeypatch.delenv("QUANT_LANG", raising=False)
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    monkeypatch.setenv("LC_ALL", "en_US.UTF-8")
    line = "⚠️ 과거 성과는 미래 수익을 보장하지 않습니다."
    assert i18n.t(line) == line, (
        "터미널 로케일만 보고 한국어를 빼앗았다")


def test_a_bad_language_falls_back_to_korean(monkeypatch):
    monkeypatch.setenv("QUANT_LANG", "klingon")
    assert i18n.lang() == "ko"

# ── ③ 정직한 한계는 번역해도 남는다 ───────────────────────────

_LIMITS = [
    ("⚠️ 과거 성과는 미래 수익을 보장하지 않습니다.", "guarantees no future return"),
    ("⚠️ 정확도는 50~55%에서 오르내립니다. 100%로 오르지 않습니다 — 그게 정상입니다.",
     "does not climb to 100%"),
    ("   잃어도 되는 소액으로만 시작하세요. 수익 보장은 없습니다.",
     "afford to lose"),
    ("\n⚠️ 세 검증을 모두 통과해도 미래 수익은 보장되지 않습니다. "
     "다음 단계는 페이퍼 트레이딩(learn)으로 실데이터 검증입니다.",
     "guarantees no future return"),
]


@pytest.mark.parametrize("ko,must", _LIMITS)
def test_the_honest_limits_survive(english, ko, must):
    out = english.t(ko)
    assert must in out, f"한계가 사라졌다: {out}"


def test_the_dictionary_never_promises_returns():
    """'수익 보장'류는 어느 언어로도 쓰지 않는다(사기죄 위험)."""
    from quant import i18n_en
    blob = " ".join(list(i18n_en.STRINGS.values())
                    + [r for _, r in i18n_en.RULES]).lower()
    for banned in ["guaranteed profit", "guaranteed return", "risk-free",
                   "sure profit", "will make money"]:
        assert banned not in blob, f"사전에 '{banned}'가 있다"

# ── ④ 사전이 낡지 않게 ────────────────────────────────────────

def _program_source() -> str:
    """프로그램이 실제로 들고 있는 글자 — 손으로 적힌 것과 만들어진 것을 가른다."""
    out = []
    for name in ("cli.py", "web/app.py", "web/mystrategy.py",
                 "backtest/metrics.py", "backtest/engine.py"):
        try:
            out.append((ROOT / "quant" / name).read_text("utf-8"))
        except OSError:
            pass
    return "\n".join(out)


def test_no_daily_number_is_baked_into_a_key():
    """매일 바뀌는 값이 열쇠에 들어가면 영어는 하루도 못 간다.

    ⚠️ 위험한 것은 숫자 자체가 아니라 **누가 그 글자를 쓰느냐**다. 소스에
       손으로 박아 둔 예시(`예: 2026-08-06`)는 내일도 같은 글자다. 반대로
       실행 때마다 만들어지는 문장은 하루 만에 낡는다 — 그런 것만 빚으로
       센다(사이트의 같은 검사와 같은 판정이다).
    """
    from quant import i18n_en
    src = _program_source()
    bad = [k for k in i18n_en.STRINGS
           if re.search(r"[\d,]{4,}원|\d{4}-\d{2}-\d{2}", k)
           and k not in src]
    assert not bad, f"만들어지는 값이 사전 열쇠에 있다: {bad}"


def test_the_exemption_really_reads_the_source():
    """대조군 — 면제가 아무 글자나 통과시키면 위 검사는 구멍이다."""
    assert "예: 2026-08-06" in _program_source()
    assert "2099-01-01 이런 문장은 소스에 없다" not in _program_source()


def test_every_rule_compiles():
    """대조군 — 깨진 정규식 하나가 그 아래 규칙을 전부 죽인다."""
    from quant import i18n_en
    for pat, _ in i18n_en.RULES:
        re.compile(pat)          # 던지면 실패


def test_the_dictionary_is_not_empty():
    """대조군 — 사전이 비면 위 검사들이 조용히 무의미해진다."""
    from quant import i18n_en
    assert len(i18n_en.STRINGS) >= 150, len(i18n_en.STRINGS)
    assert len(i18n_en.RULES) >= 50, len(i18n_en.RULES)

# ── ⑤ 실제로 실행해 본다 ──────────────────────────────────────

def _run(args, lang=None):
    import os
    env = dict(os.environ)
    env.pop("QUANT_LANG", None)
    if lang:
        env["QUANT_LANG"] = lang
    p = subprocess.run([sys.executable, "-m", "quant", *args],
                       capture_output=True, text=True, cwd=str(ROOT),
                       env=env, timeout=300)
    return p.stdout + p.stderr


def test_the_help_screen_is_english():
    """`--help`가 한국어면 영어권 사용자는 첫 화면에서 닫는다."""
    out = _run(["--help"], lang="en")
    assert "run a strategy backtest" in out, out[:600]
    assert "전략 백테스트 실행" not in out


def test_the_help_screen_is_korean_by_default():
    """대조군 — 지정하지 않으면 원본 그대로여야 한다."""
    out = _run(["--help"])
    assert "전략 백테스트 실행" in out, out[:600]


def test_the_flag_beats_the_environment():
    """`--lang` 은 이번 한 번만 — 환경변수보다 세다."""
    out = _run(["--lang", "en", "--help"])
    assert "run a strategy backtest" in out, out[:600]


def test_a_real_run_reads_in_english():
    """도움말만 영어인 것과 **화면이 영어인 것**은 다른 일이다."""
    out = _run(["--lang", "en", "backtest", "--strategy", "ma_cross",
                "--limit", "120"])
    assert "Total return" in out, out[-800:]
    assert "guarantees no future return" in out, out[-800:]
    left = [ln for ln in out.splitlines() if re.search(r"[가-힣]", ln)]
    assert not left, f"영어로 돌렸는데 한국어가 남았다: {left[:4]}"


def test_the_same_run_is_korean_by_default():
    """대조군 — 이게 없으면 위 검사는 '빈 출력'도 통과한다."""
    out = _run(["backtest", "--strategy", "ma_cross", "--limit", "120"])
    assert "총수익률" in out, out[-500:]

# ── ⑥ 조종석은 사이트와 **같은 사전**을 쓴다 ──────────────────

def test_the_cockpit_carries_the_site_engine():
    """사전을 두 벌로 만들면 같은 문장이 두 화면에서 달라진다."""
    from quant.web import app
    page = app._page("테스트", "<p>안녕하세요</p>")
    assert "QuantI18N" in page, "조종석에 번역 엔진이 실려 있지 않다"
    assert "QUANT_EN" in page, "조종석에 사전이 실려 있지 않다"
    assert 'window.QUANT_I18N_PAGE="cockpit.html"' in page, (
        "조종석이 자기 이름을 밝히지 않는다 — 사이트 첫 화면 기준으로 "
        "'일부만 번역됐다'는 안내가 뜬다")


def test_the_cockpit_has_a_language_button():
    """버튼이 없으면 영어권 사용자에게 조종석은 한국어 전용 프로그램이다."""
    from quant.web import app
    page = app._page("테스트", "<p>안녕하세요</p>")
    assert 'id="qlang"' in page, "조종석에 언어 버튼이 없다"
    assert "QuantI18N.current()" in page, (
        "버튼이 지금 언어를 스스로 판단한다 — 판단은 한 곳에만 있어야 한다")


def test_the_broadcast_screen_carries_it_too():
    """방송 화면도 같은 프로그램의 화면이다."""
    from quant.web import app
    assert "QuantI18N" in app.render_broadcast(), (
        "방송 모드에 번역 엔진이 없다")


def test_the_cockpit_words_are_in_the_shared_dictionary():
    """조종석 탭 이름이 사전에 있는가 — 없으면 상단 바가 한국어로 남는다."""
    dic = (ROOT / "docs" / "assets" / "i18n-en.js").read_text("utf-8")
    from quant.web.app import _NAV_ITEMS
    missing = [label for _, label in _NAV_ITEMS
               if '"%s"' % label not in dic]
    assert not missing, f"조종석 탭 이름이 사전에 없다: {missing}"
