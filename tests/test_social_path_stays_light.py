"""SNS 게시 경로가 **무거운 의존성 없이** 도는가 (감사 102).

`.github/workflows/social-post.yml`에는 `pip install` 단계가 **없다.**
캡션을 만들고 카드를 찍어 커밋하는 게 전부라 numpy·pandas가 필요 없었기
때문이다. 그런데 같은 날 감사 89("종목 수·시작금을 산문에 박지 말고 코드에서
읽어라")를 고치면서 캡션이 이렇게 됐다:

    from quant.live.daily import PORTFOLIO_START_CASH   # daily는 numpy를 쓴다

숫자 하나를 읽으려고 매매 엔진 전체를 끌어온 셈이다. 개발 환경과 CI에는
numpy가 있으니 **1,512개 검사가 전부 통과했고**, 그날 밤 실제 게시만 죽었다:

    File "quant/reporting/social.py", line 135, in build_captions
      from quant.live.daily import PORTFOLIO_START_CASH
    File "quant/live/daily.py", line 20, in <module>
      import numpy as np
    ModuleNotFoundError: No module named 'numpy'

교훈이 둘이다.
  ① 검사 환경이 실행 환경보다 **넉넉하면** 검사는 그 차이를 못 본다.
     "여기서는 되는데"가 CI 규모로 일어난 것이다.
  ② 조용한 폴백이 또 있었다 — `_day_pct_from_history`는 ImportError를
     `except Exception`으로 삼킨다. numpy가 없으면 하루치가 조용히 사라지고
     훅이 "오늘의 장부를 공개합니다"로 바뀐다. 죽지도 않고 말하지도 않는다.

여기서는 **numpy·pandas·sklearn을 실제로 막아 놓고** 캡션 생성을 돌린다.
워크플로가 사는 환경을 그대로 재현하는 것이 유일하게 믿을 수 있는 방법이다.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 게시 워크플로에 설치되지 않는 것들.
HEAVY = ("numpy", "pandas", "sklearn", "scipy", "yfinance", "ccxt", "pykrx")

_BLOCKER = textwrap.dedent(f"""
    import sys
    HEAVY = {HEAVY!r}

    class _Block:
        def find_module(self, name, path=None):
            return self if name.split(".")[0] in HEAVY else None
        def find_spec(self, name, path=None, target=None):
            if name.split(".")[0] in HEAVY:
                raise ModuleNotFoundError(f"No module named '{{name}}'")
            return None

    sys.meta_path.insert(0, _Block())
""")


def _run(body: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", _BLOCKER + body],
                          cwd=str(cwd or ROOT), capture_output=True,
                          text=True, timeout=180)


def test_the_blocker_actually_blocks():
    """차단이 안 되면 아래 검사가 전부 조용히 통과한다."""
    r = _run("import numpy")
    assert r.returncode != 0 and "No module named" in r.stderr, (
        f"numpy 차단이 동작하지 않는다 — 이 검사는 아무것도 확인하지 않는다\n{r.stderr}")


def test_captions_build_without_numpy():
    """캡션 생성이 무거운 의존성 없이 끝까지 가야 한다."""
    r = _run(textwrap.dedent("""
        import json
        from quant.reporting.social import build_captions
        st = {"updated": "2026-08-10T21:00:00Z",
              "paper": {"portfolio:ALL": {"history": [
                  {"date": "2026-08-10", "equity": 79950.0, "return_pct": -0.06,
                   "day_pct": -0.05, "weight": 0.07, "risk_scale": 1.0,
                   "applied": {"us_stock:AAPL": 0.012}}]},
                  "us_stock:AAPL": {"history": [
                      {"date": "2026-08-10", "weight": 0.12}]}},
              "symbols": {"us_stock:AAPL": {"name": "애플"}},
              "retrain_recent": []}
        caps = build_captions(st, site_url="https://example.com")
        assert "모의투자" in caps["instagram"]
        assert "오늘 -0.05%" in caps["instagram"], caps["instagram"][:200]
        print("OK")
    """))
    assert r.returncode == 0, (
        "SNS 캡션이 numpy 없이는 만들어지지 않는다 — 게시 워크플로에는 "
        f"numpy가 설치되지 않아 그대로 실패한다\n{r.stderr[-3000:]}")
    assert "OK" in r.stdout


def test_the_day_figure_survives_without_numpy():
    """옛 기록 폴백(day_pct 없음)도 무거운 의존성 없이 계산돼야 한다.

    여기가 조용히 죽으면 훅이 '오늘의 장부를 공개합니다'로 바뀌고, 아무도
    이유를 모른다 — 실패보다 나쁜 종류다.
    """
    r = _run(textwrap.dedent("""
        from quant.reporting.social import _today_numbers
        st = {"updated": "2026-08-10T21:00:00Z",
              "paper": {"portfolio:ALL": {"start_cash": 80000, "history": [
                  {"date": "2026-08-09", "equity": 80000.0},
                  {"date": "2026-08-10", "equity": 79600.0, "return_pct": -0.5,
                   "weight": 0.07, "risk_scale": 1.0}]}}}
        got = _today_numbers(st)["day_pct"]
        assert got == -0.5, got            # (79600/80000-1)*100
        print("OK")
    """))
    assert r.returncode == 0 and "OK" in r.stdout, (
        "day_pct 폴백이 numpy 없이는 조용히 None이 된다 — 훅이 바뀌는데 "
        f"아무 말도 남지 않는다\n{r.stderr[-2000:]}")


def test_the_whole_command_runs_without_numpy(tmp_path):
    """워크플로가 실제로 부르는 명령 그대로 — `python -m quant social-content`."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "status.json").write_text(json.dumps({
        "updated": "2026-08-10T21:00:00Z",
        "paper": {"portfolio:ALL": {"history": [
            {"date": "2026-08-10", "equity": 79950.0, "return_pct": -0.06,
             "day_pct": -0.05, "weight": 0.07, "risk_scale": 1.0}]}},
        "symbols": {}, "retrain_recent": []}), encoding="utf-8")

    r = subprocess.run(
        [sys.executable, "-c", _BLOCKER + textwrap.dedent(f"""
            import sys
            sys.argv = ["quant", "social-content", "--docs-dir", {str(docs)!r},
                        "--site-url", "https://example.com"]
            from quant.cli import main
            main()
        """)],
        cwd=str(ROOT), capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, (
        "게시 워크플로의 첫 단계가 numpy 없이 실패한다\n" + r.stderr[-3000:])
    assert (docs / "social" / "2026-08-10" / "caption_instagram.txt").exists()


def test_the_workflow_still_has_no_install_step():
    """전제가 바뀌면 이 검사의 의미도 바뀐다 — 전제를 고정한다.

    나중에 워크플로에 `pip install`이 생기면 위 검사들은 과한 제약이 된다.
    그때는 이 검사가 먼저 실패해 "전제가 바뀌었다"고 알려준다.
    """
    import yaml
    wf = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "social-post.yml").read_text("utf-8"))
    runs = " ".join(str(s.get("run") or "") for s in wf["jobs"]["social"]["steps"])
    assert "pip install" not in runs, (
        "게시 워크플로에 의존성 설치가 생겼다 — 이 파일의 전제(가벼운 경로)를 "
        "다시 판단할 것")


# ── 입금 경로도 같은 그물에 (2026-08-13) ─────────────────────────
#
# 사장님이 92만원 매칭 입금을 실행했는데 워크플로가 죽었다:
#
#     python -m quant deposit --amount 920000 ...
#     → ModuleNotFoundError: No module named 'numpy'
#
# **감사 102와 똑같은 사고다.** 그때 SNS 게시가 죽어서 이 검사 파일과
# `ledger_basics.py`가 생겼는데, 정작 그 뒤에 추가된 `add_deposit`은 또
# 무거운 `daily.py`에 놓였다. 그리고 `deposit.yml`에는 의존성 설치 단계가
# 아예 없었다.
#
# 규칙을 만드는 것보다 지키는 것이 어렵다 — 그래서 **그물을 넓힌다.**
# 사람이 기억해야 하는 규칙은 언젠가 잊히지만, 검사는 안 잊는다.


def test_deposit_works_without_the_heavy_stack():
    """입금은 날짜·JSON·산술이 전부다 — numpy가 있어야 할 이유가 없다."""
    r = _run(
        "import json, pathlib, tempfile\n"
        "d = pathlib.Path(tempfile.mkdtemp())\n"
        "(d / 'paper').mkdir()\n"
        "(d / 'paper' / 'portfolio_ALL.json').write_text(json.dumps({\n"
        "    'market': 'portfolio', 'symbol': 'ALL', 'start_cash': 80000.0,\n"
        "    'cash': 80000.0, 'positions': {}, 'base_prices': {},\n"
        "    'last_bar': None, 'history': [], 'deposits': []}),\n"
        "    encoding='utf-8')\n"
        "from quant.live.ledger_basics import add_deposit\n"
        "out = add_deposit(920000, '테스트', state_dir=str(d))\n"
        "assert out['principal'] == 1_000_000, out\n"
        "st = json.loads((d / 'paper' / 'portfolio_ALL.json')"
        ".read_text(encoding='utf-8'))\n"
        "assert st['cash'] == 1_000_000 and len(st['deposits']) == 1, st\n"
        "print('OK')\n")
    assert r.returncode == 0 and "OK" in r.stdout, (
        "입금이 numpy 없이는 되지 않는다 — 입금 워크플로에는 그런 것이 "
        f"없다(2026-08-13 실제로 죽었다)\n{r.stderr[-1500:]}")


def test_the_deposit_command_does_not_reach_for_the_engine():
    """CLI의 입금 명령이 무거운 모듈을 부르지 않는가.

    `quant.live.daily`에서 가져오면 매매 엔진 전체가 딸려 온다. 함수를
    옮겨 놔도 부르는 쪽이 옛 경로를 쓰면 그대로 죽는다 — 실제로 그랬다.
    """
    src = (ROOT / "quant" / "cli.py").read_text(encoding="utf-8")
    i = src.index("def _cmd_deposit(")
    body = src[i:i + 800]
    assert "from quant.live.ledger_basics import add_deposit" in body, body[:300]
    assert "from quant.live.daily import add_deposit" not in body


def test_the_deposit_workflow_installs_what_it_needs():
    """워크플로에 의존성 설치 단계가 있는가 — 이게 아예 없었다.

    입금 자체는 가벼워졌지만, 같은 잡의 `write_docs_status()`는 사이트를
    통째로 다시 만드는 일이라 pandas·numpy가 진짜로 필요하다. 둘 다
    고쳐야 끝난다.

    ⚠️ 이 검사를 처음엔 **글자 위치**로 비교했다가 제 발에 걸렸다 — 고친
       이유를 설명하려고 워크플로 주석에 적어 둔 `python -m quant deposit`
       한 줄이 실행 단계보다 앞에 있어서 "설치가 뒤에 있다"고 잘못 잡았다.
       감사 183·199·204에서 반복해 겪은 자리다. **글자가 아니라 구조를
       봐야 하면 파싱한다.**
    """
    import yaml

    wf = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "deposit.yml").read_text("utf-8"))
    steps = wf["jobs"]["deposit"]["steps"]
    runs = [str(s.get("run") or "") for s in steps]
    install = next((i for i, r in enumerate(runs)
                    if "pip install" in r and "requirements.txt" in r), None)
    use = next((i for i, r in enumerate(runs)
                if "quant deposit" in r or "write_docs_status" in r), None)
    assert install is not None, "입금 워크플로에 의존성 설치 단계가 없다"
    assert use is not None, "전제가 깨졌다 — 입금을 실행하는 단계가 없다"
    assert install < use, (
        f"설치({install}번 단계)가 실행({use}번 단계)보다 뒤에 있다")
