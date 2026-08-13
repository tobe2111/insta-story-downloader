"""아카이브 장부가 표본에 두 번 들어가지 않는다 (감사 227).

배경:
  감사 212의 원화 재액면은 옛 장부를 `*.pre-krw.json`으로 **통째로 사본**
  남긴다("과거를 고치지 않는다"). 그래서 state/paper/ 를 훑는 코드는 전부
  아카이브를 걸러야 하는데, 네 자리 중 **두 자리에만** 가드가 있었다:

      quant/live/daily.py          (2곳)  ✅ 감사 212에서 추가
      quant/web/app.py                    ✅ 감사 212에서 추가
      quant/reporting/fill_gap.py         ❌ 빠짐
      quant/live/daily._all_paper_histories ❌ 빠짐

  fill_gap의 표본은 **실측 체결비용 → 오디션이 무는 비용**과
  **리밸런스 밴드 → 실제 계좌의 매매 빈도**로 흘러간다. 표시용 오차가
  아니라 돈이 도는 쪽 숫자다. 지금은 아카이브가 통합계좌 두 개뿐이라
  이름 규칙에 우연히 걸러지지만, 종목 장부가 한 번이라도 아카이브되는
  순간 같은 체결이 사본 수만큼 표본에 들어간다.

핵심 계약: 아카이브는 어느 스캔에서도 '또 하나의 계좌'가 아니다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.live.daily import _all_paper_histories  # noqa: E402
from quant.live.ledger_basics import is_archive  # noqa: E402
from quant.reporting.fill_gap import fill_gap_report  # noqa: E402


def _history():
    """결정가 대비 체결가가 벌어진 기록 — 갭 표본 1건이 나온다.

    08-10 종가 100원에 '비중 0 → 0.5' 결정, 다음 세션 시가 102원에 체결.
    """
    return [
        {"date": "2026-08-10", "weight": 0.0, "price": 100.0},
        {"date": "2026-08-11", "weight": 0.5, "price": 101.0,
         "fill": {"decided_bar": "2026-08-10", "price": 102.0,
                  "weight": 0.5}},
    ]


def _write(paper: Path, name: str, market: str = "us_stock"):
    (paper / name).write_text(json.dumps(
        {"market": market, "symbol": "SPY", "history": _history()}), "utf-8")


def test_the_archive_mark_is_recognised():
    assert is_archive("us_stock_SPY.pre-krw.json")
    assert not is_archive("us_stock_SPY.json")


def test_fill_gap_counts_a_symbol_once_not_twice(tmp_path):
    """같은 체결이 사본 때문에 두 번 세어지면 안 된다."""
    paper = tmp_path / "paper"
    paper.mkdir()
    _write(paper, "us_stock_SPY.json")
    alone = fill_gap_report(str(tmp_path))
    assert alone and alone["total_fills"] == 1        # 대조군 — 평소엔 1건

    _write(paper, "us_stock_SPY.pre-krw.json")        # 재액면 아카이브 추가
    after = fill_gap_report(str(tmp_path))
    assert after["total_fills"] == 1, (
        "아카이브가 또 하나의 계좌로 세어졌다 — 실측 체결비용과 리밸런스 "
        "밴드가 사본 수만큼 흔들린다")
    assert after == alone


def test_pooled_histories_do_not_double_count_the_archive(tmp_path):
    paper = tmp_path / "paper"
    paper.mkdir()
    _write(paper, "us_stock_SPY.json")
    assert len(_all_paper_histories(str(tmp_path))) == 1   # 대조군

    _write(paper, "us_stock_SPY.pre-krw.json")
    assert len(_all_paper_histories(str(tmp_path))) == 1, (
        "확률대 적중률 표본에 같은 기록이 두 번 들어간다")


def test_the_live_portfolio_ledger_is_still_excluded(tmp_path):
    """통합계좌는 종목 체결과 중복이라 원래부터 제외다 — 그 규칙은 그대로."""
    paper = tmp_path / "paper"
    paper.mkdir()
    _write(paper, "portfolio_ALL.json", market="portfolio")
    assert fill_gap_report(str(tmp_path)) is None
    assert _all_paper_histories(str(tmp_path)) == []


def test_every_paper_directory_scan_filters_archives():
    """네 자리가 같은 규칙을 쓴다 — 한 곳만 빠지면 그 경로로 새어 들어온다.

    ⚠️ 문자열이 아니라 **동작**으로 못 박고 싶지만, '이 저장소에 장부
       스캔이 몇 군데인가'는 구조적 사실이라 여기서만 소스를 본다. 대신
       주석·문서열이 아니라 실제 호출만 보도록 `ast`로 파싱한다(감사 183
       이후 여덟 번째 같은 함정을 피한다).
    """
    import ast

    root = Path(__file__).resolve().parent.parent
    scans = {"quant/live/daily.py": 3,        # listdir 2 + glob 1
             "quant/reporting/fill_gap.py": 1,
             "quant/web/app.py": 1}
    for rel, _ in scans.items():
        tree = ast.parse((root / rel).read_text("utf-8"))
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        assert "is_archive" in (names | attrs), (
            f"{rel}: 장부 디렉터리를 훑으면서 아카이브 가드를 쓰지 않는다")
