"""웹 조종석의 '내 전략'이 **CLI와 같은 관문**을 지키는가.

설치형의 대상 사용자는 비개발자다 — 핵심 기능(자료 읽기·고정)이 터미널
전용이면 없는 기능이다. 그래서 웹으로 옮기되, 옮기면서 관문이 얇아지면
안 된다:

  ① 규칙 없는 자료 → "없다"가 정상 결과 화면으로 나온다.
  ② 못 옮긴 문장 경고가 화면에 나온다 — CLI에만 나오고 웹에서 사라지면
     비개발자 사용자일수록 자기 규칙이 다 반영된 줄 안다.
  ③ 저장은 2단계다(읽어 보기 → 저장) — 붙여넣자마자 등록되지 않는다.
  ④ 고정은 성적표를 먼저 보여주고 **확인 문구를 타이핑**해야 된다.
     웹이 문구를 미리 채워 주면 CLI의 관문이 장식이 된다.
  ⑤ 판정은 전부 quant.ingest / quant.live.pin이 한다 — 웹은 화면만.
  ⑥ 상태를 바꾸는 경로(POST)도 GET과 같은 세 관문(Host·교차출처·토큰)을
     지난다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.web import mystrategy as M  # noqa: E402

RULES = ("5일 이동평균선이 20일 이동평균선을 위로 돌파하면 매수한다. "
         "RSI가 70 이상이면 매도한다. 손절은 -8%로 잡는다. "
         "매수는 3번에 나눠 분할매수한다.")


def _saved(tmp_path) -> str:
    M.run_ingest_html({"text": RULES, "name": "웹시험", "save": "1"},
                      state_dir=str(tmp_path))
    f = next((tmp_path / "specs_user").glob("*.json"))
    return json.loads(f.read_text("utf-8"))["name"]


# ── ① 규칙 없음은 정상 결과다 ─────────────────────────────────

def test_no_rules_is_an_honest_page_not_an_error(tmp_path):
    h = M.run_ingest_html({"text": "시장의 흐름을 읽고 과감하게."},
                          state_dir=str(tmp_path))
    assert "찾지 못했습니다" in h
    assert "지어낸" in h, "왜 안 만드는지(지어내지 않는다)를 설명하지 않는다"
    assert not list(tmp_path.glob("**/*.json")), "규칙이 없는데 뭔가 저장됐다"


# ── ② 못 옮긴 문장이 화면에 나온다 ────────────────────────────

def test_untranslated_sentences_reach_the_screen(tmp_path):
    h = M.run_ingest_html({"text": RULES, "name": "웹시험"},
                          state_dir=str(tmp_path))
    assert "옮기지는 못했습니다" in h and "분할" in h, (
        "못 옮긴 문장 경고가 웹 화면에 없다 — CLI에만 있으면 비개발자는 "
        "자기 규칙이 다 반영된 줄 안다")


# ── ③ 저장은 2단계다 ──────────────────────────────────────────

def test_preview_does_not_save(tmp_path):
    h = M.run_ingest_html({"text": RULES, "name": "웹시험"},
                          state_dir=str(tmp_path))
    assert "저장 안 됨" in h
    assert not (tmp_path / "specs_user").exists(), (
        "읽어 보기만 했는데 저장됐다 — 붙여넣자마자 등록되면 실수로 "
        "도전자가 늘어난다")


def test_save_writes_and_says_most_will_fail(tmp_path):
    h = M.run_ingest_html({"text": RULES, "name": "웹시험", "save": "1"},
                          state_dir=str(tmp_path))
    assert "저장됐습니다" in h
    assert "대부분은 떨어집니다" in h, (
        "심사에서 대부분 떨어진다는 사실을 웹에서 숨긴다 — 기대 관리가 "
        "곧 정직함이다")
    assert list((tmp_path / "specs_user").glob("*.json"))


# ── ④ 고정 관문 — 성적표 + 타이핑 ─────────────────────────────

def test_pin_shows_the_scorecard_before_asking(tmp_path):
    name = _saved(tmp_path)
    h = M.render_pin_prepare({"name": name, "key": "crypto:BTC/USDT"},
                             state_dir=str(tmp_path))
    assert "심사를 통과하지 않았습니다" in h
    assert "그대로 입력" in h


def test_the_web_does_not_prefill_the_ack_phrase(tmp_path):
    """입력창에 문구가 미리 채워져 있으면 타이핑 관문이 장식이 된다.

    문구는 안내문으로는 보여주되 input의 value로 넣으면 안 된다.
    """
    name = _saved(tmp_path)
    h = M.render_pin_prepare({"name": name, "key": "crypto:BTC/USDT"},
                             state_dir=str(tmp_path))
    from quant.live.pin import ACK_PHRASE
    import re
    for m in re.finditer(r"<input[^>]*>", h):
        tag = m.group(0)
        if 'name="ack"' in tag:
            assert ACK_PHRASE not in tag, (
                "확인 문구가 입력창에 미리 채워져 있다 — 버튼 클릭과 "
                "문장 타이핑은 다른 행동이어야 한다")


def test_a_wrong_phrase_is_refused_and_a_right_one_pins(tmp_path):
    from quant.live.pin import ACK_PHRASE, load_pins
    name = _saved(tmp_path)
    h = M.run_pin_save({"name": name, "key": "crypto:BTC/USDT",
                        "ack": "네 알겠습니다"}, state_dir=str(tmp_path))
    assert "고정 실패" in h
    assert load_pins(str(tmp_path)) == {}
    h = M.run_pin_save({"name": name, "key": "crypto:BTC/USDT",
                        "ack": ACK_PHRASE}, state_dir=str(tmp_path))
    assert "고정됨" in h
    assert "crypto:BTC/USDT" in load_pins(str(tmp_path))
    h = M.run_pin_unpin({"key": "crypto:BTC/USDT"}, state_dir=str(tmp_path))
    assert "고정 해제" in h and load_pins(str(tmp_path)) == {}


# ── ⑤ 판정은 웹이 하지 않는다 ─────────────────────────────────

def test_the_web_module_restates_no_judgement():
    src = (ROOT / "quant" / "web" / "mystrategy.py").read_text("utf-8")
    body = src.split('"""', 2)[-1]
    for banned in ("re.search", "re.compile", "cross_above", "== ACK_PHRASE",
                   "vol_scale", "_kill_switch"):
        assert banned not in body, (
            f"웹 모듈이 판정({banned})을 직접 한다 — 같은 규칙이 두 곳에 "
            "생기면 언젠가 갈라진다")


# ── ⑥ POST도 같은 관문을 지난다 ───────────────────────────────

def test_post_routes_pass_the_same_three_gates():
    src = (ROOT / "quant" / "web" / "server.py").read_text("utf-8")
    post = src[src.index("def do_POST"):src.index("def log_message")]
    for gate in ("_host_ok", "_same_site_ok", "_authorized"):
        assert gate in post, (
            f"POST가 {gate} 관문을 안 지난다 — 메서드가 다르다고 관문이 "
            "얇아지면 CSRF 방지가 반쪽이 된다")
    start = src.index("_MUTATING")
    mutating = src[start:src.index("def ", start)]
    for path in ("/ingest/run", "/pin/save", "/pin/unpin"):
        assert path in mutating, (
            f"{path}가 상태 변경 목록에 없다 — 교차출처 검사가 안 걸린다")


def test_the_nav_actually_links_the_new_page():
    """만들어 두고 어디서도 못 들어가는 페이지는 없는 페이지다."""
    src = (ROOT / "quant" / "web" / "app.py").read_text("utf-8")
    assert '("/ingest", "내 전략")' in src, "내비게이션에 내 전략이 없다"
