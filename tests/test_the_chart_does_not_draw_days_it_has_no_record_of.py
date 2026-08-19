"""**기록이 없는 날을 선으로 잇지 않는다** (2026-08-19).

08-15와 08-19 사이 사흘은 배치가 죽어 기록이 없다. 두 점을 직선으로 이으면
**그 사흘도 그렇게 움직였다는 그림**이 된다. 이 사이트가 가장 하지 말아야 할
일이 빈칸을 "그런 일이 없었다"로 보이게 하는 것이고, 첫 화면 경고에도
그렇게 적혀 있다.

⚠️ 값 없는 점(빈칸)만 끼워서는 **안 끊긴다.** 실제로 넣어 보고 확인했다 —
   가로축에 16·17·18일은 생겼는데 선은 그대로 이어졌다. 이 차트 라이브러리는
   빈칸을 건너뛰고 앞뒤를 잇는다. 그래서 **끊긴 구간마다 시리즈를 따로**
   만든다. 소스를 읽어서가 아니라 그려 보고 알아낸 사실이라, 검사도 그려
   보고 확인한다.
"""

from __future__ import annotations

import functools
import http.server
import json
import shutil
import socketserver
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _browser import block_external, chromium_or_skip  # noqa: E402

DOCS = ROOT / "docs"


# 캔버스에서 **선이 몇 토막인가**를 센다. 색은 자산선의 두 색(오름 빨강 ·
# 내림 파랑) 중 하나다. 세로로 훑어 그 색이 있는 x칸을 찾고, 연속한 x칸
# 덩어리 수가 곧 토막 수다.
_PIXEL_RUNS = """()=>{
  const cs=[].slice.call(document.querySelectorAll("#mainchart canvas"));
  if(!cs.length)return {runs:0, canvases:0};
  const c=cs.reduce((a,b)=>(a.width*a.height>=b.width*b.height)?a:b);
  const w=c.width, h=c.height;
  const d=c.getContext("2d").getImageData(0,0,w,h).data;
  const hit=(r,g,b,a)=>a>200&&((r>190&&g<120&&b<130)||(b>190&&r<110&&g<170));
  const on=[];
  for(let x=0;x<w;x++){
    let v=false;
    for(let y=0;y<h;y++){
      const i=(y*w+x)*4;
      if(hit(d[i],d[i+1],d[i+2],d[i+3])){v=true;break}
    }
    on.push(v);
  }
  let runs=0, prev=false, first=-1, last=-1;
  on.forEach(function(v,x){
    if(v&&!prev)runs++;
    if(v){ if(first<0)first=x; last=x; }
    prev=v;
  });
  /* 그려진 구간 안에서 **가장 긴 빈틈**이 전체의 몇 %인가.
     축이 날짜에 비례해야 빈 사흘이 사흘만큼 넓게 보인다 — 좁으면
     "잠깐 끊겼네" 정도로 읽히고 사흘이 사라진 것은 안 보인다. */
  let gap=0, run=0;
  for(let x=first;x<=last&&first>=0;x++){
    if(!on[x]){run++; if(run>gap)gap=run} else run=0;
  }
  const span=(last-first)||1;
  return {runs:runs, canvases:cs.length, w:w,
          gap_pct:Math.round(gap/span*100)};
}"""


def _serve(root: Path):
    class _Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    srv = socketserver.TCPServer(
        ("127.0.0.1", 0), functools.partial(_Quiet, directory=str(root)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_address[1]}", srv


def _site(base: Path, name: str, dates) -> Path:
    """주어진 날짜만 기록으로 가진 사이트 한 벌."""
    root = base / name
    shutil.copytree(DOCS, root, dirs_exist_ok=True)
    st = json.loads((DOCS / "status.json").read_text("utf-8"))
    pf = st["paper"]["portfolio:ALL"]
    tpl = pf["history"][-1]
    hist = []
    for i, d in enumerate(dates):
        rec = json.loads(json.dumps(tpl))
        rec["date"] = d
        rec["equity"] = 1_000_000.0 + i * 1_000
        rec["price"] = 100.0 + i
        hist.append(rec)
    pf["history"] = hist
    st["updated"] = dates[-1]
    (root / "status.json").write_text(json.dumps(st, ensure_ascii=False), "utf-8")
    return root


@pytest.fixture(scope="module")
def charts(tmp_path_factory):
    pytest.importorskip("playwright.sync_api",
                        reason="playwright 없음 — 화면 검사 생략")
    from playwright.sync_api import sync_playwright

    base = tmp_path_factory.mktemp("charts")
    cases = {
        # 사흘이 비었다 — 선이 끊겨야 한다
        "gap": ["2026-08-13", "2026-08-14", "2026-08-15", "2026-08-19"],
        # 대조군 — 매일 이어진 기록은 한 줄로 그린다
        "solid": ["2026-08-13", "2026-08-14", "2026-08-15", "2026-08-16"],
    }
    out, servers = {}, []
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=chromium_or_skip())
            try:
                for name, dates in cases.items():
                    url, srv = _serve(_site(base, name, dates))
                    servers.append(srv)
                    pg = b.new_page(viewport={"width": 1440, "height": 900})
                    block_external(pg)
                    errs = []
                    pg.on("pageerror", lambda e: errs.append(str(e)))
                    pg.goto(f"{url}/index.html")
                    pg.wait_for_timeout(2600)
                    # ⚠️ **그려진 것을 센다.** 처음엔 여기서 날짜 배열로
                    #    구간 수를 다시 계산했는데, 그건 페이지가 아니라
                    #    **검사 자신의 계산**을 확인하는 것이었다 — 그리는
                    #    코드를 통째로 망가뜨려도 통과했다(변이 시험이
                    #    그대로 잡아냈다). 캔버스 픽셀에서 선이 몇 토막인지
                    #    직접 센다.
                    out[name] = pg.evaluate(_PIXEL_RUNS)
                    assert not errs, f"{name}: 스크립트가 던졌다 — {errs}"
                    pg.close()
            finally:
                b.close()
        yield out
    finally:
        for srv in servers:
            srv.shutdown()


def test_a_gap_is_drawn_as_a_gap(charts):
    """빈 사흘이 있으면 구간이 둘이다 — 한 줄로 이어 그리면 안 된다."""
    assert charts["gap"]["runs"] == 2, charts["gap"]


def test_an_unbroken_ledger_is_one_line(charts):
    """대조군 — 매일 기록이 있으면 끊지 않는다. 늘 끊으면 그것대로 거짓말이다."""
    assert charts["solid"]["runs"] == 1, charts["solid"]


def test_the_gap_is_as_wide_as_the_days_it_covers(charts):
    """빈 사흘은 **사흘만큼 넓게** 비어야 한다.

    가로축이 기록 개수가 아니라 날짜에 비례해야 한다. 안 그러면 사흘이
    하루처럼 좁아져서 "잠깐 끊겼네" 정도로 읽힌다 — 끊긴 사실은 남지만
    얼마나 오래 없었는지는 사라진다.
    """
    assert charts["gap"]["gap_pct"] >= 45, (
        f"빈틈이 너무 좁다 — 축이 날짜에 비례하지 않는다: {charts['gap']}")
    assert charts["solid"]["gap_pct"] <= 10, (
        f"이어진 기록인데 빈틈이 보인다: {charts['solid']}")


def test_the_chart_actually_rendered(charts):
    """캔버스가 없으면 위 검사는 아무것도 확인하지 않은 것이다."""
    for name, got in charts.items():
        assert got["canvases"] > 0, f"{name}: 차트가 안 그려졌다 — {got}"


# ── 그리는 코드가 그 규칙을 갖고 있는가 ─────────────────────────

def test_the_code_splits_the_series_at_gaps():
    """⚠️ 빈칸만 끼우는 방식으로 되돌아가면 선이 다시 이어진다.

    실제로 그렇게 만들어 보고 확인했다 — 축에는 빈 날이 생기는데 선은
    이어졌다. 그 되돌림을 여기서 막는다.
    """
    src = (DOCS / "index.html").read_text("utf-8")
    blk = src.split("const runs=[]", 1)
    assert len(blk) == 2, "구간 나누기가 사라졌다 — 선이 다시 이어진다"
    body = blk[1].split("timeScale().fitContent", 1)[0]
    assert "runs.forEach" in body, "구간마다 그리지 않는다"
    assert "addAreaSeries" in body, "구간별 시리즈를 만들지 않는다"


def test_the_legend_says_what_a_break_means():
    """끊긴 자리를 '고장난 그림'으로 읽지 않게 뜻을 적는다."""
    src = (DOCS / "index.html").read_text("utf-8")
    assert "끊긴 구간" in src and "기록이 없는 날" in src, (
        "선이 끊긴 이유를 화면이 말하지 않는다")
