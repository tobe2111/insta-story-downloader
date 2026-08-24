"""머신러닝 성적표가 정직한가 (감사 311).

사장님 지시(2026-08-24): *"지금까지 계속 투자하면서 머신러닝 잘 돌아가고
있는지 확인해줘"* / *"홈페이지에 머신러닝 전용 페이지도 만들어야겠는데?
히스토리나 검증 결과 등에 대해서도 보이면 좋지 않을까? 어떠한 구조로
머신러닝이 되는지 등 말이야."*

실측해 보니 이랬다(2026-08-24 기준):

    실전(OOS) 적중률   45.8% (49/107) · 95% 구간 36.7~55.2% → 우연과 구별 안 됨
    확신한 판단(≥0.60) 84건 → 실제 상승 45.2%
    부정한 판단(<0.40) 75건 → 실제 상승 52.0%     ← 순서가 뒤집혀 있다
    예측확률 ↔ 결과 상관  −0.093
    검증 게이트          42종목 전부 붙잡힘(10 관망 · 32 절반 · 0 정상)

이건 자랑할 숫자가 아니다. 그래서 **이 검사들의 목적은 화면이 그 사실을
숨기지 못하게 막는 것**이다.

■ 여기서 지키는 것

  · **'아직 모른다'와 '못한다'는 다른 말이다.** 표본이 얇아 신뢰구간이
    50%를 품으면 그건 실패의 증거가 아니라 증거가 없는 것이다. 화면이
    둘을 같은 말로 적으면 거짓이 된다(어느 방향으로든).
  · **인샘플과 실전을 섞지 않는다.** 모델이 이미 본 구간의 성적은 실력의
    증거가 아니다. 합치면 좋은 쪽이 나쁜 쪽을 가린다(감사 240).
  · **확신할수록 덜 맞히는 상태를 화면이 말해야 한다.** 이 시스템은
    확률을 금액으로 바꾼다 — 크게 거는 날일수록 더 자주 틀린다면 그게
    적중률보다 중요한 사실이다.
  · **안전장치가 무엇을 붙잡았는지 숫자로 보인다.** 전부 붙잡힌 상태를
    조용히 넘어가면, 읽는 사람은 모델이 자유롭게 굴리는 줄 안다.
  · **숫자는 장부에서 센다.** 화면이 자기 계산을 시작하면 갈라진다.

⚠️ 아래 검사는 **손으로 지은 장부**를 먹인다. 살아 있는 기록으로 검사하면
   그날 마침 숫자가 좋아 조용히 통과한다 — 매일 바뀌는 값 위에 전제를
   세우면 언젠가 반드시 깨진다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.reporting.ml_health import (  # noqa: E402
    _wilson, drift, insample_accuracy, live_accuracy, report,
)


def _ledger(tmp_path, name, last, history=None):
    """종목 하나의 페이퍼 장부를 손으로 짓는다."""
    d = tmp_path / "paper"
    d.mkdir(parents=True, exist_ok=True)
    h = list(history or []) + [last]
    (d / f"{name}.json").write_text(json.dumps({"history": h},
                                               ensure_ascii=False),
                                    encoding="utf-8")
    return tmp_path


# ══ ① '아직 모른다'와 '못한다'를 구별한다 ═════════════════════════

def test_a_thin_sample_is_not_called_a_failure(tmp_path):
    """4건 중 1건 맞혔어도 '못한다'로 단정하지 않는다.

    표본이 얇으면 신뢰구간이 넓고, 넓은 구간은 아무것도 배제하지 못한다.
    """
    _ledger(tmp_path, "x", {"live_hit": 0.25, "live_hit_n": 4})
    r = live_accuracy(str(tmp_path))
    assert r["hit_rate"] == pytest.approx(0.25)
    assert r["beats_chance"] is False
    assert r["worse_than_chance"] is False, (
        "4건으로 '우연보다 못한다'고 단정했다 — 그건 통계가 아니라 인상이다")


def test_a_thick_bad_sample_is_called_what_it_is(tmp_path):
    """대조군 — 표본이 두꺼우면 나쁜 것을 나쁘다고 말한다.

    이게 없으면 "무조건 판단 유보"도 위 검사를 통과한다.
    """
    _ledger(tmp_path, "x", {"live_hit": 0.25, "live_hit_n": 400})
    r = live_accuracy(str(tmp_path))
    assert r["worse_than_chance"] is True
    assert r["beats_chance"] is False


def test_a_thick_good_sample_is_called_what_it_is(tmp_path):
    """대조군 — 진짜 잘하면 잘한다고 말한다."""
    _ledger(tmp_path, "x", {"live_hit": 0.75, "live_hit_n": 400})
    r = live_accuracy(str(tmp_path))
    assert r["beats_chance"] is True
    assert r["worse_than_chance"] is False


def test_an_empty_book_says_nothing_rather_than_zero(tmp_path):
    """기록이 없으면 적중률은 None이다 — 0%는 '한 번도 못 맞혔다'는 뜻이다."""
    (tmp_path / "paper").mkdir(parents=True)
    r = live_accuracy(str(tmp_path))
    assert r["hit_rate"] is None and r["n"] == 0
    assert r["beats_chance"] is False


@pytest.mark.parametrize("hits,n", [(0, 10), (10, 10), (5, 10)])
def test_the_interval_never_leaves_the_possible_range(hits, n):
    """신뢰구간이 0 아래나 1 위로 삐져나오지 않는다.

    "적중률이 −3%였다"는 문장은 아무 뜻이 없다.
    """
    lo, hi = _wilson(hits, n)
    assert 0.0 <= lo <= hi <= 1.0, (lo, hi)


# ══ ② 인샘플과 실전을 섞지 않는다 ═════════════════════════════════

def test_practice_and_live_are_counted_separately(tmp_path):
    """연습 성적이 좋아도 실전 숫자를 물들이지 않는다."""
    _ledger(tmp_path, "x", {"live_hit": 0.30, "live_hit_n": 10,
                            "hit_rate": 0.90, "hit_n": 1000})
    live = live_accuracy(str(tmp_path))
    prac = insample_accuracy(str(tmp_path))
    assert live["hit_rate"] == pytest.approx(0.30), "실전에 연습이 섞였다"
    assert prac["hit_rate"] == pytest.approx(0.90)
    assert live["n"] == 10 and prac["n"] == 1000


def test_the_portfolio_ledger_is_not_counted_as_a_model(tmp_path):
    """통합 계좌는 종목별 모델 기록이 아니다 — 세면 이중 계산이 된다."""
    _ledger(tmp_path, "portfolio_ALL", {"live_hit": 1.0, "live_hit_n": 999})
    assert live_accuracy(str(tmp_path))["n"] == 0


# ══ ③ 드리프트 ═══════════════════════════════════════════════════

def test_it_counts_how_many_crossed_the_line(tmp_path):
    _ledger(tmp_path, "a", {"drift_psi": 0.10, "drift_grade": "안정"})
    _ledger(tmp_path, "b", {"drift_psi": 0.90, "drift_grade": "심한 드리프트"})
    _ledger(tmp_path, "c", {"drift_psi": 0.40, "drift_grade": "드리프트"})
    d = drift(str(tmp_path))
    assert d["measured"] == 3
    assert d["over_line"] == 2, "기준선을 넘은 종목 수가 틀렸다"
    assert d["worst"][0]["symbol"] == "b", "가장 심한 곳이 앞에 안 온다"


def test_a_calm_book_reports_none_over_the_line(tmp_path):
    """대조군 — 다 안정이면 0이어야 한다. 없으면 '늘 넘었다'도 통과한다."""
    _ledger(tmp_path, "a", {"drift_psi": 0.05, "drift_grade": "안정"})
    assert drift(str(tmp_path))["over_line"] == 0


# ══ ④ 성적표 전체가 한 덩어리로 나온다 ════════════════════════════

def test_the_report_carries_every_section(tmp_path):
    _ledger(tmp_path, "x", {"live_hit": 0.5, "live_hit_n": 8,
                            "hit_rate": 0.52, "hit_n": 100,
                            "drift_psi": 0.3, "drift_grade": "드리프트",
                            "prob_up": 0.6})
    r = report(str(tmp_path), "2026-08-24")
    for k in ("champions", "live", "insample", "calibration", "drift",
              "gate", "limits"):
        assert k in r, f"성적표에 '{k}' 칸이 없다"
    assert r["limits"], "한계를 하나도 안 적었다 — 숫자만 실으면 거짓말이다"


def test_the_report_lands_on_disk(tmp_path):
    """⚠️ 계산이 맞아도 파일로 안 나가면 화면은 아무것도 못 그린다."""
    from quant.reporting.ml_health import write_report
    _ledger(tmp_path, "x", {"live_hit": 0.5, "live_hit_n": 8})
    p = write_report(str(tmp_path / "docs"), str(tmp_path), "2026-08-24")
    d = json.loads(Path(p).read_text("utf-8"))
    assert d["kind"] == "ml-health" and d["live"]["n"] == 8


def test_the_command_the_batch_calls_actually_works(tmp_path):
    """배치가 부르는 그 명령을 그대로 부른다.

    ⚠️ 함수만 검사하면 "명령 이름이 바뀌어 배치가 매일 조용히 실패한다"를
       놓친다. 실제로 감사 289가 그 모양이었다.
    """
    from quant.cli import main
    _ledger(tmp_path, "x", {"live_hit": 0.5, "live_hit_n": 8})
    main(["ml-report", "--docs", str(tmp_path / "docs"),
          "--state", str(tmp_path), "--asof", "2026-08-24"])
    assert (tmp_path / "docs" / "ml.json").exists(), "명령이 파일을 안 만들었다"


# ══ ⑤ 화면이 나쁜 사실을 숨기지 못한다 ════════════════════════════
#
# ⚠️ 여기가 이 파일의 핵심이다. 장부가 정직해도 **화면이 안 그리면**
#    읽는 사람에게는 없는 일이다. 그래서 실제로 브라우저에 띄워 본다.

import functools  # noqa: E402
import http.server  # noqa: E402
import shutil  # noqa: E402
import socketserver  # noqa: E402
import threading  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))


def _page(tmp_path, ledger: dict) -> str:
    """docs 사본에 **우리가 지은 성적표**를 넣고 ml.html을 띄운다."""
    pytest.importorskip("playwright.sync_api",
                        reason="playwright 없음 — 화면 검사 생략")
    from _browser import block_external, chromium_or_skip
    from playwright.sync_api import sync_playwright

    root = tmp_path / "site"
    shutil.copytree(ROOT / "docs", root, dirs_exist_ok=True)
    (root / "ml.json").write_text(json.dumps(ledger, ensure_ascii=False),
                                  encoding="utf-8")

    class _Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    srv = socketserver.TCPServer(
        ("127.0.0.1", 0), functools.partial(_Quiet, directory=str(root)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=chromium_or_skip())
        pg = b.new_page()
        block_external(pg)
        try:
            pg.goto(f"http://127.0.0.1:{srv.server_address[1]}/ml.html")
            pg.wait_for_timeout(1500)
            return pg.locator("body").inner_text()
        finally:
            pg.close()
            b.close()
            srv.shutdown()


def _card(**over) -> dict:
    d = {
        "kind": "ml-health", "asof": "2026-08-24",
        "champions": {"total": 42, "by_strategy": {"ml": 41, "ma_cross": 1},
                      "rows": [], "promotions": 2},
        "live": {"hits": 49, "n": 107, "hit_rate": 0.4579,
                 "ci_lo": 0.3666, "ci_hi": 0.5522,
                 "beats_chance": False, "worse_than_chance": False,
                 "per_symbol": []},
        "insample": {"hit_rate": 0.5264, "n": 3697},
        "calibration": {
            "pairs": 224, "correlation": -0.0927,
            "confident_up": {"n": 84, "actual": 0.4524},
            "confident_down": {"n": 75, "actual": 0.52},
            "table": [{"lo": 0.6, "hi": 0.7, "n": 43, "said": 0.647,
                       "actual": 0.419, "ci_lo": 0.28, "ci_hi": 0.57,
                       "confirmed": True}]},
        "drift": {"grades": {"심한 드리프트": 7, "안정": 12},
                  "worst": [{"symbol": "kr_stock_133690.KS", "psi": 1.66,
                             "grade": "심한 드리프트"}],
                  "notable_line": 0.25, "over_line": 25, "measured": 42},
        "gate": {"rows": [{"key": "us_stock:MSFT", "scale": 0.0,
                           "why": "과최적화 확률(PBO) 91%"}],
                 "halted": 10, "halved": 32, "full": 0},
        "limits": ["가상 자금 시뮬레이션입니다"],
    }
    d.update(over)
    return d


def test_the_page_says_plainly_that_it_cannot_beat_chance(tmp_path):
    """첫 화면이 '우연과 구별되지 않는다'고 말한다 — 묻어 두지 않는다."""
    t = _page(tmp_path, _card())
    assert "우연과 구별되지 않습니다" in t, t[:400]
    assert "45.8%" in t, "실전 적중률을 안 적는다"
    assert "49/107" in t, "표본 크기를 안 적는다 — 숫자만 크게 보이면 오독한다"


def test_the_page_warns_when_confidence_runs_backwards(tmp_path):
    """확신할수록 덜 맞히는 상태를 경고로 띄운다."""
    t = _page(tmp_path, _card())
    assert "확신할수록 덜 맞히고 있습니다" in t, t[:600]
    assert "45.2%" in t and "52.0%" in t, "두 무리의 실제 상승률을 안 적는다"


def test_a_healthy_model_gets_no_backwards_warning(tmp_path):
    """대조군 — 정상일 때 그 경고를 붙이면 거짓말이다."""
    t = _page(tmp_path, _card(calibration={
        "pairs": 224, "correlation": 0.31,
        "confident_up": {"n": 84, "actual": 0.66},
        "confident_down": {"n": 75, "actual": 0.38},
        "table": []}))
    assert "확신할수록 덜 맞히고 있습니다" not in t


def test_the_page_shows_the_calibration_table(tmp_path):
    """이 페이지에서 가장 중요한 표가 실제로 그려진다."""
    t = _page(tmp_path, _card())
    assert "64.7%" in t, "모델이 말한 확률을 안 적는다"
    assert "41.9%" in t, "실제로 오른 비율을 안 적는다"
    assert "확정" in t, "통계로 굳어진 어긋남을 표시하지 않는다"


def test_the_page_admits_every_symbol_is_held_back(tmp_path):
    """안전장치가 전부 붙잡은 상태를 화면이 말한다."""
    t = _page(tmp_path, _card())
    assert "모든 종목이 붙잡혀 있습니다" in t, t[:600]
    assert "10종목" in t and "32종목" in t


def test_a_free_running_model_gets_no_held_back_warning(tmp_path):
    """대조군 — 안 붙잡혔으면 그 경고가 없어야 한다."""
    t = _page(tmp_path, _card(gate={"rows": [], "halted": 0, "halved": 0,
                                    "full": 42}))
    assert "모든 종목이 붙잡혀 있습니다" not in t


def test_the_page_explains_how_the_model_works(tmp_path):
    """구조 설명이 있다 — 사장님이 요청한 "어떠한 구조로 되는지"."""
    t = _page(tmp_path, _card())
    for phrase in ("가격에서 재료를 만든다", "미래를 절대 보여 주지 않습니다",
                   "확률을 금액으로 바꾼다", "매일 다시 배운다"):
        assert phrase in t, f"구조 설명에 '{phrase}'가 없다"


def test_the_page_reads_only_its_own_ledger():
    """자기 장부만 읽는다 — 남의 장부를 읽으면 한 화면에 두 계좌가 섞인다."""
    src = (ROOT / "docs" / "ml.html").read_text("utf-8")
    assert "ml.json" in src
    for other in ("status.json", "intraday.json", "futures.json"):
        assert other not in src, f"ml.html이 {other}을 읽는다"


def test_the_navbar_offers_the_page():
    """상단 바에 없으면 아무도 못 찾는다."""
    nav = (ROOT / "docs" / "assets" / "nav.js").read_text("utf-8")
    assert '"ml.html"' in nav and "머신러닝" in nav
