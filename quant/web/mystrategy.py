"""웹 조종석 '내 전략' — 자료 붙여넣기 → 읽기 → 심사 등록 → (원하면) 고정.

설치형 사용자는 비개발자다. 지금까지 이 제품의 핵심 기능 둘(자료에서 전략
뽑기 `ingest`, 심사 무시하고 강제 적용 `pin`)이 터미널 명령어 전용이었다 —
대상 사용자가 쓸 수 없는 곳에 있는 기능은 없는 기능이다.

여기서 지키는 것 — CLI와 **같은 관문, 같은 정직함**:
    · 규칙을 못 찾으면 "못 찾았습니다"가 정상 결과 화면이다.
    · 못 옮긴 문장은 눈에 띄는 경고 상자로 — "반영되지 않았습니다".
    · 고정은 성적표를 먼저 보여주고 **확인 문구를 직접 타이핑**해야 된다.
      웹이라고 버튼 하나로 줄이면 CLI의 관문이 장식이 된다(같은 규칙은
      한 곳에만 — 판정은 전부 quant.ingest / quant.live.pin이 한다.
      이 파일은 화면만 만든다).
"""
from __future__ import annotations

import html

from quant.web.app import _msg_html, _page

STATE_DIR = "state"


def _e(s) -> str:
    return html.escape(str(s or ""))


# ── 자료 → 전략 ────────────────────────────────────────────────────


def render_ingest_form(message: str = "") -> str:
    body = f"""<p class="kicker">My Strategy</p>
<h1>내 전략 — 자료에서 규칙 뽑기</h1>
<p class="sub">책·PDF·유튜브 자막·직접 쓴 글에서 <b>숫자로 적힌 매매 규칙</b>을
찾아 전략으로 만듭니다. 읽을 수 있는 규칙 9종: 이동평균 교차 · RSI ·
가격 vs 이동평균 · 신고가/신저가 · 볼린저밴드 · 거래량 배수 · 연속 양봉/음봉 ·
MACD · 손절/익절 %. <b>규칙이 없으면 "없다"고 말합니다</b> — 없는 규칙을
지어내지 않는 것이 이 기능의 핵심입니다.</p>
{_msg_html(message)}
<form action="/ingest/run" method="post" class="panel">
  <div><label>자료 본문 붙여넣기</label>
    <textarea name="text" rows="10" style="width:100%"
      placeholder="예: 5일 이동평균선이 20일 이동평균선을 위로 돌파하면 매수한다. 손절은 -8%로 잡는다."></textarea>
    <div class="hint">또는 아래에 PDF 파일 경로나 유튜브 주소를 입력하세요
    (둘 다 있으면 경로/주소를 씁니다)</div></div>
  <div class="row" style="margin-top:8px">
    <div><label>PDF 경로 · 유튜브 주소 (선택)</label>
      <input name="ref" placeholder="C:\\자료\\전략.pdf 또는 https://youtu.be/..."></div>
    <div><label>전략 이름 (선택)</label>
      <input name="name" placeholder="비우면 자료 이름"></div>
  </div>
  <button type="submit" style="margin-top:10px">읽어 보기 (아직 저장 안 함)</button>
</form>
<p class="sub" style="margin-top:12px">읽힌 전략은 <b>도전자</b>로 등록됩니다 —
등록만으로는 매매하지 않고, 매일 밤 심사(선발전·결승전)를 이겨야 매매를
맡습니다. 심사와 무관하게 쓰고 싶다면 저장 후 <a href="/pins">고정</a>으로.</p>"""
    return _page("내 전략 — 자료 읽기", body, "/ingest")


def run_ingest_html(params: dict, state_dir: str = STATE_DIR) -> str:
    """읽기(미리보기) → 저장의 2단계. save=1일 때만 파일이 생긴다."""
    from quant.ingest.extract import extract_spec
    from quant.ingest.registry import save_spec
    from quant.ingest.sources import SourceError, load_any

    text = str(params.get("text") or "")
    ref = str(params.get("ref") or "").strip()
    name = str(params.get("name") or "").strip()
    source = {"kind": "web", "ref": name or "붙여넣기"}
    if ref:
        try:
            loaded = load_any(ref)
        except SourceError as exc:
            return render_ingest_form(f"자료를 읽지 못했습니다: {exc}")
        text, source = loaded.text, loaded.source
        name = name or loaded.title
    if not text.strip():
        return render_ingest_form("본문이 비어 있습니다 — 글을 붙여넣거나 "
                                  "경로/주소를 입력하세요.")

    result = extract_spec(text, title=name, source=source)
    if not result.ok:
        # 이것은 오류가 아니라 **정상 결과 중 하나**다 — 화면도 그렇게 말한다.
        reasons = "".join(f"<li>{_e(r)}</li>" for r in result.reasons)
        body = f"""<p class="kicker">My Strategy</p>
<h1>실행 가능한 규칙을 찾지 못했습니다</h1>
<p class="sub">문장 {result.sentences_seen:,}개를 봤습니다. 이것은 고장이
아니라 <b>정직한 판정</b>입니다 — 투자 자료 대부분에는 컴퓨터가 실행할 수
있는 규칙이 없고, 그때 억지로 만들어 내면 그것은 자료의 전략이 아니라
프로그램이 지어낸 전략입니다.</p>
<div class="errbox"><ul style="margin:0 0 0 18px">{reasons}</ul></div>
<p class="sub"><a href="/ingest">← 다른 자료로 다시</a></p>"""
        return _page("규칙 없음", body, "/ingest")

    spec = result.spec
    warn = ""
    if spec.notes:
        items = "".join(f"<li>{_e(n)}</li>" for n in spec.notes)
        warn = (f'<div class="errbox"><b>⚠️ 전부 옮기지는 못했습니다</b>'
                f'<ul style="margin:6px 0 0 18px">{items}</ul></div>')
    quotes = "".join(
        f"<li>“{_e(c.quote[:120])}”</li>"
        for c in list(spec.entry) + list(spec.exit))
    for rule in (spec.stop, spec.target):
        if rule:
            quotes += f"<li>“{_e(str(rule.get('quote', ''))[:120])}”</li>"

    if str(params.get("save") or "") == "1":
        path = save_spec(spec, state_dir=state_dir)
        body = f"""<p class="kicker">My Strategy</p>
<h1>저장됐습니다 — 오늘 밤부터 심사를 받습니다</h1>
<pre class="panel" style="white-space:pre-wrap">{_e(spec.summary())}</pre>
{warn}
<p class="sub">저장 위치: <code>{_e(path)}</code></p>
<p class="sub">이제 매일 밤 재학습에서 <b>도전자로</b> 링에 섭니다. 등록만으로는
매매하지 않습니다 — 다른 후보와 같은 2단계 심사를 이기고 과최적화 검증까지
통과해야 실제 비중을 받습니다. <b>대부분은 떨어집니다.</b> 그것이 이 제품이
파는 것입니다. 심사와 무관하게 지금 바로 쓰려면 → <a href="/pins">고정(pin)</a></p>"""
        return _page("전략 저장됨", body, "/ingest")

    # 미리보기 — 저장 버튼이 같은 내용을 save=1로 다시 보낸다.
    body = f"""<p class="kicker">My Strategy</p>
<h1>이렇게 읽었습니다 (아직 저장 안 됨)</h1>
<pre class="panel" style="white-space:pre-wrap">{_e(spec.summary())}</pre>
{warn}
<details style="margin-top:8px"><summary>근거가 된 원문 문장</summary>
<ul style="margin:6px 0 0 18px">{quotes}</ul></details>
<form action="/ingest/run" method="post" style="margin-top:12px">
  <input type="hidden" name="text" value="{_e(text)}">
  <input type="hidden" name="name" value="{_e(name)}">
  <input type="hidden" name="save" value="1">
  <button type="submit">이대로 저장 (도전자로 등록)</button>
  <a href="/ingest" style="margin-left:10px">다시 쓰기</a>
</form>"""
    return _page("읽은 결과", body, "/ingest")


# ── 고정(pin) ──────────────────────────────────────────────────────


def render_pins_page(message: str = "", state_dir: str = STATE_DIR) -> str:
    from quant.ingest.registry import load_specs
    from quant.live.pin import load_pins
    from quant.markets import AUTO_TARGETS

    try:
        pins = load_pins(state_dir)
    except RuntimeError as exc:
        pins, message = {}, f"{message} {exc}".strip()
    specs, problems = load_specs(state_dir)

    pin_rows = "".join(
        f"<tr><td>📌 {_e(k)}</td><td>{_e(v.get('name'))}</td>"
        f"<td>{_e(v.get('since'))}부터</td>"
        f'<td><form action="/pin/unpin" method="post" style="margin:0">'
        f'<input type="hidden" name="key" value="{_e(k)}">'
        f'<button type="submit">해제</button></form></td></tr>'
        for k, v in sorted(pins.items())) or (
        '<tr><td colspan="4">고정 없음 — 모든 종목이 심사(오디션) 결과를 '
        "따릅니다</td></tr>")

    spec_opts = "".join(f'<option value="{_e(s.name)}">{_e(s.name)}</option>'
                        for s in specs)
    key_opts = "".join(
        f'<option value="{m}:{s}">{m}:{s}</option>' for m, s in AUTO_TARGETS)
    prob_html = ""
    if problems:
        items = "".join(f"<li>{_e(p)}</li>" for p in problems)
        prob_html = (f'<div class="errbox"><b>읽지 못한 전략 파일</b>'
                     f'<ul style="margin:6px 0 0 18px">{items}</ul></div>')

    form = ("<p class='sub'>저장된 전략이 없습니다 — 먼저 "
            "<a href='/ingest'>자료에서 전략을 만들어</a> 주세요.</p>"
            if not specs else f"""
<form action="/pin/prepare" method="get" class="panel">
  <div class="row">
    <div><label>전략</label><select name="name">{spec_opts}</select></div>
    <div><label>종목</label><select name="key">{key_opts}</select></div>
  </div>
  <button type="submit" style="margin-top:10px">성적표 보기 (아직 고정 안 함)</button>
</form>""")

    body = f"""<p class="kicker">My Strategy</p>
<h1>고정(pin) — 심사와 무관하게 내 전략으로 매매</h1>
<p class="sub">자기 계좌에는 자기 전략을 쓸 권리가 있습니다. 대신 셋은
양보하지 않습니다: <b>성적표를 먼저</b> 보여주고, <b>확인 문구를 직접
타이핑</b>해야 하며, 고정해도 <b>브레이크(킬스위치·변동성 목표·검증
게이트·레버리지 금지)는 그대로</b> 걸립니다.</p>
{_msg_html(message)}
{prob_html}
<h2 style="margin-top:14px">지금 고정된 전략</h2>
<div class="panel"><table><tr><th>종목</th><th>전략</th><th>시작</th><th></th></tr>
{pin_rows}</table></div>
<h2 style="margin-top:14px">새로 고정하기</h2>
{form}"""
    return _page("고정(pin)", body, "/ingest")


def render_pin_prepare(params: dict, state_dir: str = STATE_DIR) -> str:
    """성적표 + 확인 문구 입력 — 고정 전의 마지막 화면."""
    from quant.live.pin import ACK_PHRASE, scorecard

    name = str(params.get("name") or "")
    key = str(params.get("key") or "")
    market, _, symbol = key.partition(":")
    if not (name and market and symbol):
        return render_pins_page("전략과 종목을 선택하세요.", state_dir)
    lines = scorecard(market, symbol, name, state_dir=state_dir)
    card = "".join(f"<div>{_e(ln)}</div>" for ln in lines)
    body = f"""<p class="kicker">My Strategy</p>
<h1>고정 전 성적표 — {_e(name)} @ {_e(key)}</h1>
<div class="panel" style="line-height:1.8">{card}</div>
<form action="/pin/save" method="post" class="panel" style="margin-top:12px">
  <input type="hidden" name="name" value="{_e(name)}">
  <input type="hidden" name="key" value="{_e(key)}">
  <div><label>고정하려면 다음 문구를 <b>그대로 입력</b>하세요:</label>
    <div class="hint" style="user-select:none">{_e(ACK_PHRASE)}</div>
    <input name="ack" autocomplete="off" style="width:100%"
           placeholder="위 문구를 직접 타이핑"></div>
  <button type="submit" style="margin-top:10px">고정</button>
  <a href="/pins" style="margin-left:10px">취소</a>
</form>
<p class="sub">문장을 옮겨 적는 것과 버튼을 누르는 것은 다른 행동입니다 —
실전 전환의 '실전' 타이핑과 같은 원리입니다.</p>"""
    return _page("고정 전 성적표", body, "/ingest")


def run_pin_save(params: dict, state_dir: str = STATE_DIR) -> str:
    from quant.live.pin import save_pin

    name = str(params.get("name") or "")
    key = str(params.get("key") or "")
    typed = str(params.get("ack") or "")
    market, _, symbol = key.partition(":")
    try:
        entry = save_pin(market, symbol, name, typed, state_dir=state_dir)
    except (ValueError, RuntimeError) as exc:
        return render_pins_page(f"고정 실패: {exc}", state_dir)
    return render_pins_page(
        f"📌 고정됨: {key} ← {entry['name']} ({entry['since']}부터). "
        "오디션은 계속 돌아 성적표가 매일 갱신되고, 언제든 해제하면 시스템 "
        "판단이 즉시 복귀합니다.", state_dir)


def run_pin_unpin(params: dict, state_dir: str = STATE_DIR) -> str:
    from quant.live.pin import remove_pin

    key = str(params.get("key") or "")
    market, _, symbol = key.partition(":")
    if remove_pin(market, symbol, state_dir=state_dir):
        return render_pins_page(
            f"↩️ 고정 해제: {key} — 다음 실행부터 시스템 챔피언 판단이 "
            "복귀합니다.", state_dir)
    return render_pins_page(f"고정돼 있지 않습니다: {key}", state_dir)
