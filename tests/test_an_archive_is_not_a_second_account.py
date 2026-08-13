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


_LISTING_CALLS = {"listdir", "scandir", "glob", "iglob", "iterdir"}


def _modules_that_list_the_paper_dir():
    """장부 디렉터리를 **직접** 훑는 모듈을 소스에서 찾아낸다.

    ⚠️ 왜 목록을 손으로 적지 않는가(감사 228): 처음에는 아는 자리 세 개를
       적어 뒀다. 그래서 **제가 놓친 네 번째**(`portfolio_vol.edge_proven`)를
       이 검사가 잡아주지 못했다 — 아는 것만 열거하는 완전성 검사는 완전성을
       검사하지 않는다. 이제 검사가 저장소를 직접 뒤진다.

    주석·독스트링은 애초에 AST에 없다(감사 183 이후 같은 함정 여덟 번).
    """
    import ast

    root = Path(__file__).resolve().parent.parent
    found: dict = {}
    for path in sorted((root / "quant").rglob("*.py")):
        tree = ast.parse(path.read_text("utf-8"))
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            inner = list(ast.walk(fn))
            lists = any(
                isinstance(n, ast.Call)
                and ((isinstance(n.func, ast.Attribute)
                      and n.func.attr in _LISTING_CALLS)
                     or (isinstance(n.func, ast.Name)
                         and n.func.id in _LISTING_CALLS))
                for n in inner)
            paper = any(isinstance(n, ast.Constant) and n.value == "paper"
                        for n in inner)
            if lists and paper:
                found.setdefault(str(path.relative_to(root)), []).append(fn.name)
    return found


def test_the_paper_directory_is_listed_in_exactly_one_place():
    """장부 목록을 만드는 자리는 하나다 — 여섯 곳이면 언젠가 하나가 갈라진다.

    실제로 갈라졌다: 감사 212가 세 곳에 가드를 넣고 주석에 "세 곳"이라
    적었는데 실제로는 여섯 곳이었고, 감사 227이 네 곳까지 맞춘 뒤에도 하나가
    남아 있었다. 하필 그 하나가 목표 변동성을 12%→20%로 올릴지 판정하는
    자리(`portfolio_vol.edge_proven`)였다.
    """
    found = _modules_that_list_the_paper_dir()
    extra = {k: v for k, v in found.items()
             if k != "quant/live/ledger_basics.py"}
    assert not extra, (
        "장부 디렉터리를 직접 훑는 자리가 ledger_files 말고 또 있다 — "
        "보관본 필터가 그 경로에서 빠질 수 있다:\n  "
        + "\n  ".join(f"{k}: {', '.join(v)}" for k, v in extra.items()))
    assert "quant/live/ledger_basics.py" in found, (
        "목록을 만드는 자리 자체가 사라졌다 — 검사가 헛돌고 있다")


# ── 감사 228 — 사본이 '엣지 입증'을 만들어낸다 ─────────────────


def _edge_history(n: int, hit_rate: float):
    """적중률이 정확히 hit_rate인 (prob_up, 다음 봉 방향) 기록을 만든다."""
    recs, price = [], 100.0
    for i in range(n + 1):
        up = i < round(n * hit_rate)          # 앞쪽 i건은 예측대로 오른다
        recs.append({"date": f"2026-01-{i % 28 + 1:02d}", "price": price,
                     "prob_up": 0.9})
        price = price * 1.01 if up else price * 0.99
    return recs


def test_a_duplicate_ledger_cannot_manufacture_a_proven_edge(tmp_path,
                                                             monkeypatch):
    """보관본이 표본에 섞이면 n만 두 배가 되고 윌슨 하한이 올라간다.

        적중 55.0%, n=200 → 95% 하한 48.08%  (미입증)
        적중 55.0%, n=400 → 95% 하한 50.10%  (**입증**)

    즉 사본 하나가 "동전과 구별 불가"를 "엣지 입증"으로 뒤집고, 그 판정이
    곧장 목표 변동성을 연 12%에서 20%로 올린다 — 우리가 그토록 걸러낸
    '운 좋은 승자'를 표본 복사로 만들어내는 셈이다.
    """
    from quant.live import daily as D
    from quant.risk import portfolio_vol as V

    monkeypatch.setattr(D, "_generation_info",
                        lambda sd: {"days": 999, "target_days": 90,
                                    "feature_set": "fs8"})
    paper = tmp_path / "paper"
    paper.mkdir()
    hist = _edge_history(200, 0.55)
    (paper / "us_stock_SPY.json").write_text(json.dumps(
        {"market": "us_stock", "symbol": "SPY", "history": hist}), "utf-8")

    proven, why = V.edge_proven(str(tmp_path))
    assert proven is False, why           # 대조군 — 원본만으로는 미입증
    assert "n=200" in why

    # 재액면 보관본을 그대로 옆에 둔다(감사 212가 실제로 만드는 파일)
    (paper / "us_stock_SPY.pre-krw.json").write_text(json.dumps(
        {"market": "us_stock", "symbol": "SPY", "history": hist}), "utf-8")
    proven2, why2 = V.edge_proven(str(tmp_path))
    assert proven2 is False, (
        f"사본이 엣지를 만들어냈다 — 노출이 12%→20%로 올라간다: {why2}")
    assert "n=200" in why2, f"표본이 사본만큼 부풀었다: {why2}"
