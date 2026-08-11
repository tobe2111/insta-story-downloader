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
