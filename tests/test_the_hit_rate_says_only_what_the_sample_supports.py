"""적중률이 표본이 감당하지 못하는 단정을 하지 않는지.

⚠️ 왜 이 파일이 생겼나 (2026-08-14, 사장님 지적).

    "64% n=11 솔라나의 적중률은 이런 식으로 잘못 나오고 있어.
     다른 종목도 확인해서 모두 고쳐줘 영구적으로"

운영 20종목을 전부 재 봤다. **19개**의 95% 신뢰구간이 50%를 품고 있었다 —
즉 "동전던지기가 아니다"라고 말할 수 없는 숫자들인데, 화면은 그것을 단정적인
퍼센트로 내보내고 있었다.

    솔라나       58%  n=12  구간 32~81%   ← 아무 말도 할 수 없다
    SK하이닉스   60%  n=81  구간 50~70%   ← 이것도 마찬가지다
    KODEX200     67%  n=63  구간 54~77%   ← 유일하게 구별되는 하나

그때까지의 규칙(감사 111)은 **n<20이면 n을 흐리게 병기**였다. 방향은 맞았지만
기준이 틀렸다 — n=81짜리 60%는 아무 단서 없이 "60%"라는 단정으로 나갔다.
**표본 크기가 아니라 신뢰구간이 판정한다.**

이 파일이 지키는 것은 두 가지다.
  ① 규칙이 옳은가 (값으로 확인)
  ② 규칙이 **모든 화면에 실제로 걸려 있는가** — 한 곳만 고치면 같은 종목이
    페이지에 따라 다른 확신으로 나간다(FROZEN_IDEAS ①).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from quant.robustness.accuracy import (COIN_FLIP, hit_rate_text,
                                       is_conclusive, wilson_ci)

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


# ── ① 규칙 자체 ──────────────────────────────────────────────────

def test_wilson_ci_has_no_sample_no_interval():
    """표본이 없으면 구간도 없다 — 0으로 나누지 않는다.

    explain.py가 자기 사본을 갖고 있었고 그쪽은 n=0에서 터졌다. 사본을
    지우고 이 함수 하나로 모은 이유다.
    """
    lo, hi = wilson_ci(0, 0)
    assert lo != lo and hi != hi          # NaN
    assert is_conclusive(0, 0) is False


def test_wilson_ci_stays_inside_zero_and_one():
    """극단 비율에서도 [0,1]을 안 벗어난다 — 정규근사는 이걸 못 한다."""
    lo, hi = wilson_ci(5, 5)
    assert 0.0 <= lo <= hi <= 1.0 and hi == 1.0
    lo0, hi0 = wilson_ci(0, 5)
    assert lo0 == 0.0 and 0.0 <= hi0 <= 1.0


def test_the_sample_size_is_not_what_decides():
    """**n이 아니라 구간이 판정한다** — 이 파일이 존재하는 이유.

    n=81(60%)은 판정 불가인데 n=63(67%)은 판정된다. 표본이 더 큰 쪽이 판정
    못 하는 이 역전이, 옛 'n<20' 규칙이 왜 틀렸는지를 못 박는다.
    """
    assert is_conclusive(49, 81) is False      # SK하이닉스 60%, 구간 50~70%
    assert is_conclusive(42, 63) is True       # KODEX200 67%, 구간 54~77%
    assert is_conclusive(7, 12) is False       # 솔라나 58%, 구간 32~81%


def test_touching_fifty_percent_is_not_conclusive():
    """구간이 50%에 닿기만 해도 판정하지 않는다 — 경계가 규칙의 정의다."""
    assert is_conclusive(1, 2) is False
    lo, hi = wilson_ci(49, 81)
    assert lo <= COIN_FLIP <= hi


def test_losing_is_also_a_conclusion():
    """'동전던지기보다 못하다'도 결론이다 — 나쁜 쪽이라고 감추지 않는다.

    좋은 숫자만 판정하고 나쁜 숫자는 '판정 불가'로 흘리면, 그게 바로 이
    제품이 하지 않기로 한 편집이다.
    """
    assert is_conclusive(0, 5) is True
    assert wilson_ci(0, 5)[1] < COIN_FLIP


# ── ② 문자열 — 값을 숨기지 않되 단정하지도 않는다 ────────────────

def test_inconclusive_keeps_the_number_and_says_so():
    txt = hit_rate_text({"hit_rate": 7 / 12, "hit_n": 12})
    assert "58%" in txt, "값을 감추지 않는다"
    assert "판정 불가" in txt, "단정하지도 않는다"
    assert "32~81%" in txt and "n=12" in txt, txt


def test_conclusive_still_carries_the_interval():
    txt = hit_rate_text({"hit_rate": 42 / 63, "hit_n": 63})
    assert txt == "67% (54~77% · n=63)", txt


def test_a_rate_without_a_sample_says_so():
    """표본이 기록되지 않은 옛 기록 — 비율만으로는 아무 말도 할 수 없다."""
    assert hit_rate_text({"hit_rate": 0.64}) == "64% (표본 미상)"
    assert hit_rate_text({"hit_rate": 0.64, "hit_n": 0}) == "64% (표본 미상)"


def test_no_scorable_bars_is_not_a_number():
    assert hit_rate_text({}) == "N/A"
    assert hit_rate_text(None) == "N/A"
    assert hit_rate_text({"hit_rate": float("nan"), "hit_n": 9}) == "N/A"
    # bool은 int의 하위형이다 — True가 100%로 새어 나가면 안 된다.
    assert hit_rate_text({"hit_rate": True, "hit_n": 9}) == "N/A"


# ── ③ 두 언어가 같은 답을 내는가 ─────────────────────────────────

def _node() -> str:
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not Path(node).exists():
        pytest.skip("node 없음 — 화면 규칙 실행 검사 생략")
    return node


def test_the_browser_rule_runs_and_is_right():
    """docs/assets/hitrate.js를 **실행해서** 확인한다.

    소스 문자열만 읽는 검사는 "검사는 초록인데 기능은 죽어 있다"를 못 잡는다
    (감사 229). 돈·신뢰가 걸린 계산은 값으로 확인한다.
    """
    r = subprocess.run([_node(), str(ROOT / "tests" / "hitrate_check.mjs")],
                       capture_output=True, text=True, cwd=str(ROOT))
    assert r.returncode == 0, (r.stdout + r.stderr)


def test_python_and_javascript_do_not_drift():
    """같은 규칙을 두 언어로 쓸 수밖에 없다면, **같은 답인지 매번 확인한다.**

    파이썬(알림·조종석 서버)과 자바스크립트(사이트)가 갈라지면 같은 날 같은
    종목이 화면에서는 '판정 불가'인데 알림에서는 '60%'로 나간다. 그게
    FROZEN_IDEAS ①이 말하는 어긋남이고, 여기서 값으로 막는다.
    """
    cases = [(0, 0), (0, 5), (1, 2), (5, 5), (7, 12), (11, 17),
             (42, 63), (49, 81), (12, 12), (3, 100), (97, 100)]
    js = f"""
      import {{ readFileSync }} from "node:fs";
      const src = readFileSync("docs/assets/hitrate.js", "utf8");
      new Function(src)();
      const Q = globalThis.QuantHitRate;
      const out = {json.dumps(cases)}.map(([k, n]) => {{
        const [lo, hi] = Q.wilsonCI(k, n);
        return [lo, hi, Q.isConclusive(k, n)];
      }});
      console.log(JSON.stringify(out));
    """
    r = subprocess.run([_node(), "--input-type=module", "-e", js],
                       capture_output=True, text=True, cwd=str(ROOT))
    assert r.returncode == 0, (r.stdout + r.stderr)
    got = json.loads(r.stdout)
    for (k, n), (jlo, jhi, jsure) in zip(cases, got):
        plo, phi = wilson_ci(k, n)
        if plo != plo:                      # 양쪽 다 NaN이어야 한다
            assert jlo is None or jlo != jlo, f"k={k} n={n}: 파이썬 NaN, JS {jlo}"
        else:
            assert abs(plo - jlo) < 1e-12, f"k={k} n={n} 하한: {plo} ≠ {jlo}"
            assert abs(phi - jhi) < 1e-12, f"k={k} n={n} 상한: {phi} ≠ {jhi}"
        assert is_conclusive(k, n) is jsure, f"k={k} n={n} 판정이 갈린다"


# ── ④ 규칙이 실제로 모든 화면에 걸려 있는가 ──────────────────────

@pytest.mark.parametrize("page", ["index.html", "paper.html"])
def test_every_page_loads_the_rule_before_using_it(page):
    """모듈을 안 싣고 함수만 부르면 화면이 조용히 아무것도 안 한다."""
    src = (DOCS / page).read_text(encoding="utf-8")
    assert 'src="assets/hitrate.js"' in src, f"{page}가 규칙 파일을 싣지 않는다"
    i = src.find("assets/hitrate.js")
    j = src.find("QuantHitRate.format")
    assert 0 < i < j, f"{page}가 규칙을 쓰는 곳보다 뒤에서 싣는다"


@pytest.mark.parametrize("page", ["index.html", "paper.html"])
def test_no_page_formats_the_hit_rate_by_itself(page):
    """화면이 자기 서식을 만들면 그 순간 규칙이 둘이 된다.

    옛 코드는 `(last.hit_rate*100).toFixed(0)+"%"`를 페이지마다 갖고 있었다.
    그 형태가 다시 나타나면 규칙을 우회한 것이다.
    """
    src = (DOCS / page).read_text(encoding="utf-8")
    bad = re.findall(r"hit_rate\s*\*\s*100", src)
    assert not bad, f"{page}가 적중률을 직접 서식한다: {bad}"


def test_the_cockpit_carries_the_same_rule_file():
    """조종석은 정적 경로가 없어 파일을 **읽어서** 싣는다 — 베끼지 않는다."""
    from quant.web import app

    page = app._page("검사", "<div></div>")
    js = (DOCS / "assets" / "hitrate.js").read_text(encoding="utf-8")
    assert "QuantHitRate" in page, "조종석이 규칙을 안 싣는다"
    # 일부만 베낀 게 아니라 **그 파일 그대로**인지 본다.
    assert js.strip() in page, "조종석이 싣는 것이 이 파일이 아니다"
    # 쓰기 전에 실어야 한다 — 순서가 뒤집히면 조용히 아무것도 안 한다.
    assert page.find("QuantHitRate") < page.find("</head>"), "머리 밖에서 싣는다"


def test_the_cockpit_kpi_asks_the_rule():
    """조종석 KPI가 비율을 직접 서식하면 5초마다 규칙이 지워진다.

    서버가 렌더한 값은 맞는데 JS가 덮어써 틀린 값으로 돌아가는 일이 실제로
    있었다(dashboard.py의 경고 주석). 그래서 양쪽을 다 본다.
    """
    src = (ROOT / "quant" / "web" / "app.py").read_text(encoding="utf-8")
    assert "QuantHitRate.format" in src, "조종석 JS가 규칙을 안 부른다"
    assert "(acc*100).toFixed(1)" not in src, "조종석 JS가 자기 서식을 만든다"


def test_the_telegram_summary_does_not_assert_what_it_cannot():
    """알림도 화면과 **같은 문장**을 쓴다 — 값으로 확인한다.

    소스에 함수 이름이 있는지만 보면 "부르긴 하는데 결과를 안 쓴다"를 못
    잡는다. 그래서 요약을 실제로 만들어 문자열을 본다.
    """
    from quant.live.summary import build_daily_summary

    state = {"symbol": "SOL/USDT", "strategy": "ml", "mode": "paper",
             "history": [{"time": "2026-08-14T00:00:00", "equity": 1_000_000.0,
                          "hit_rate": 7 / 12, "n": 12,
                          "recent_hit_rate": 7 / 12, "recent_n": 12}]}
    txt = build_daily_summary(state, "2026-08-14")
    assert "판정 불가" in txt, txt
    assert "58%" in txt and "n=12" in txt, txt
    # 옛 서식(소수 한 자리 퍼센트만)이 되살아나면 여기서 걸린다.
    assert "58.3%" not in txt, txt


def test_the_cockpit_kpi_is_rendered_with_the_rule():
    """서버가 렌더하는 KPI도 같은 문장이어야 한다 — 값으로 확인한다."""
    from quant.reporting import dashboard

    state = {"symbol": "SOL/USDT", "strategy": "ml", "mode": "paper",
             "history": [{"time": "2026-08-14T00:00:00", "equity": 1_000_000.0,
                          "weight": 0.5, "hit_rate": 7 / 12, "n": 12,
                          "recent_hit_rate": 7 / 12, "recent_n": 12}]}
    html = dashboard.build_dashboard_html(state)
    assert "판정 불가" in html, "조종석 KPI가 표본 없이 단정한다"


def test_the_daily_ledger_records_the_verdict():
    """장부에 구간·판정을 남긴다 — 화면이 매번 다시 계산하지 않게.

    남기지 않으면 옛 기록을 읽는 쪽이 각자 계산하고, 그러면 계산이 여러 벌이
    된다. (옛 기록은 화면이 n으로 되계산하되, 그 규칙도 파일 한 곳에 있다.)
    """
    src = (ROOT / "quant" / "live" / "daily.py").read_text(encoding="utf-8")
    for field in ("hit_lo", "hit_hi", "hit_conclusive"):
        assert f'"{field}"' in src, f"장부에 {field}를 안 남긴다"


def test_the_rolling_rate_carries_its_denominator():
    """최근 적중률에도 표본이 따라붙는다 — 없으면 표본 없이 단정하게 된다.

    window=20이어도 관망이 많은 종목은 실제 채점된 봉이 서너 개뿐이다.
    """
    src = (ROOT / "quant" / "live" / "autolearn.py").read_text(encoding="utf-8")
    assert '"recent_n"' in src, "최근 적중률의 분모를 안 남긴다"
