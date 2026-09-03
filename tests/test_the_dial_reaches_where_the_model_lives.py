"""확신도 눈금이 모델이 실제로 사는 자리까지 닿는가 (감사 310).

사장님 지적(2026-08-23): *"거의 10000달러인데 몇백원씩만 투자 중이야?
미국주식은?"*

맞는 지적이었다. 재 보니 미국주식 실험은 자산 10,000 중 라운드 평균
320달러(3.2%)만 굴리고 있었다. 이유는 크기 규칙의 눈금이 **모델이 절대
가지 않는 자리**에 끝을 두고 있었기 때문이다.

    실제 매수액 = (자산 ÷ 종목 수) × 확신도
    확신도 = (상승확률 − 문턱) / (1 − 문턱)          문턱 0.55

즉 확신도 100%를 받으려면 모델이 상승확률 **1.00**, "반드시 오른다"고
단언해야 한다. 실측한 44건의 상승확률은:

    최소 0.550 · 중앙 0.589 · 최대 0.780 · 0.80 초과 0건

바늘이 눈금의 절반도 가 본 적이 없고, 평소 서 있는 자리는 눈금의 9%다.
터지는 결함이 아니라 **닿을 수 없는 범위에 눈금을 그린** 것이다 — 감사
289(실적 가드가 라이브러리가 없어 한 번도 발동한 적 없던 것)와 같은
종류이고, 이 저장소가 가장 자주 만나는 결함 모양이다.

■ 여기서 지키는 것

  · 눈금의 끝을 상승확률 **0.70**에 둔다. 같은 예측에 3배(문턱 0.55일 때)
    금액이 나간다.
  · **확률에서 온 신호에만** 건다. 규칙 전략(이동평균 교차 등)의 신호는
    확률이 아니다 — 거기에 배수를 곱하면 근거 없이 베팅만 키우는 것이다.
  · **본 계좌(100만 챌린지)는 건드리지 않는다.** 사장님 결정이 '실험만'
    이었다. 그래서 공용 사이저(quant/strategies/ml.py의 _size)를 고치지
    않고 실험 트랙의 신호 경로에서만 곱한다.
  · **조용히 꺼지면 안 된다.** 재보정은 전략 객체의 속성을 읽어 판단하므로
    이름이 바뀌면 아무 말 없이 1.0(무효)으로 돌아갈 수 있다. 그래서
    ① 실제 챔피언이 1.0이 아닌 배수를 받는지 확인하고 ② 회차 기록에
    적용된 배수를 남긴다.
  · **부호를 뒤집지 않는다.** 배수가 음수가 되면 사려던 것을 판다.

⚠️ 이 변경은 **더 버는 장치가 아니다.** 투입이 커지면 손익이 양쪽 다
   커진다. 지금 미국 트랙은 손실 구간(−0.17%)이고, 같은 기간을 새 눈금으로
   돌렸다면 대략 −0.47%였을 것으로 추정된다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.conviction import (  # noqa: E402
    FULL_CONVICTION_PROB, conviction_scale, recalibrate, scale_of, spec_of,
)

OPEN_NOW = "2026-08-19T15:00:00+00:00"       # 수요일 11:00 뉴욕 — 정규장


def _ml(threshold=0.55, sizing="proba"):
    return {"strategy": "ml",
            "params": {"threshold": threshold, "sizing": sizing}}


# ══ ① 눈금의 끝이 0.70이다 ═══════════════════════════════════════════

@pytest.mark.parametrize("threshold", [0.55, 0.60, 0.65])
def test_a_seventy_percent_call_now_fills_the_whole_slice(threshold):
    """정의 그 자체 — 상승확률 0.70이면 그 종목 몫을 다 쓴다.

    문턱이 얼마든 성립해야 한다. 문턱마다 배수가 달라야 하는 이유가
    여기 있다(문턱이 높을수록 남은 폭이 좁으니 배수는 커진다).
    """
    old = (FULL_CONVICTION_PROB - threshold) / (1.0 - threshold)
    assert recalibrate(old, _ml(threshold)) == pytest.approx(1.0)


def test_the_multiplier_grows_with_a_higher_threshold():
    assert conviction_scale(_ml(0.55)) == pytest.approx(3.0)
    assert conviction_scale(_ml(0.60)) == pytest.approx(4.0)


def test_a_call_below_the_threshold_is_still_nothing():
    """대조군 — 재보정은 **관망을 매수로 바꾸지 않는다.**

    이게 없으면 "무조건 3을 곱한다"도 위 검사를 통과하고, 문턱 아래의
    0에 3을 곱해도 0이라 아무도 눈치채지 못한다... 는 아니고, 관망이
    관망으로 남는지가 눈금 재보정의 최소 조건이다.
    """
    assert recalibrate(0.0, _ml()) == pytest.approx(0.0)


def test_it_never_promises_more_than_everything():
    assert recalibrate(0.9, _ml()) == pytest.approx(1.0)


# ══ ② 확률이 아닌 신호는 건드리지 않는다 ═══════════════════════════

def test_a_rule_strategy_is_left_alone():
    """이동평균 교차의 신호는 확률이 아니다 — 배수를 곱할 근거가 없다."""
    assert conviction_scale({"strategy": "ma_cross", "params": {}}) == 1.0
    assert recalibrate(0.2, {"strategy": "ma_cross"}) == pytest.approx(0.2)


def test_binary_sizing_is_left_alone():
    """이진은 이미 0 아니면 1이라 재보정할 눈금이 없다."""
    assert conviction_scale(_ml(0.55, "binary")) == 1.0


@pytest.mark.parametrize("threshold", [0.70, 0.75, 0.95])
def test_a_threshold_past_the_new_top_is_left_alone(threshold):
    """문턱이 새 눈금 끝보다 높으면 손대지 않는다.

    ⚠️ 여기서 계산을 밀어붙이면 배수가 **음수**가 되고, 그러면 사려던
       것을 파는 계좌가 된다 — 조용히 정반대로 도는 사고다.
    """
    s = conviction_scale(_ml(threshold))
    assert s == 1.0, f"문턱 {threshold}에서 배수가 {s}"
    assert recalibrate(0.4, _ml(threshold)) == pytest.approx(0.4)


@pytest.mark.parametrize("junk", [None, "많이", {}, [], float("nan")])
def test_a_spec_it_cannot_read_changes_nothing(junk):
    assert conviction_scale(junk) == 1.0


# ══ ③ 부호와 모르는 값 ═════════════════════════════════════════════

def test_a_short_grows_downward_not_upward():
    """숏도 같은 배수로 커진다 — 부호는 그대로다."""
    assert recalibrate(-0.2, _ml(), allow_short=True) == pytest.approx(-0.6)


def test_a_long_only_track_turns_a_negative_into_sitting_out():
    """롱 전용 트랙에서 음수를 그냥 두면 체결 규칙이 숏을 연다."""
    assert recalibrate(-0.2, _ml()) == pytest.approx(0.0)


@pytest.mark.parametrize("junk", [None, "x", float("nan")])
def test_a_signal_it_cannot_read_is_not_invented(junk):
    """모르는 신호는 None이다 — 0으로 적으면 '판단해서 관망했다'가 된다."""
    assert recalibrate(junk, _ml()) is None


# ══ ④ 장치가 조용히 꺼지지 않는다 ═════════════════════════════════
#
# 재보정은 전략 **객체의 속성**을 읽어 판단한다. 속성 이름이 바뀌면
# 아무 말 없이 1.0으로 돌아간다 — 그게 이 저장소에서 가장 위험한 모양이다.

def test_the_real_champions_actually_receive_a_multiplier():
    """살아 있는 챔피언으로 확인한다 — 이게 이 파일의 가장 중요한 검사다.

    ⚠️ 여기서만 실제 저장소 상태를 읽는다. 챔피언이 규칙 전략으로 바뀌면
       배수가 1.0이 되는 것이 **정상**이므로, "하나라도 받으면 통과"로
       느슨하게 잡는다 — 매일 바뀌는 값 위에 딱 맞는 전제를 세우면
       언젠가 반드시 깨진다.
    """
    from quant.live.retrain import build_strategy, champion_spec
    got = {}
    for sym in ("SPY", "QQQ", "AAPL", "NVDA", "MSFT", "AMZN"):
        try:
            spec = champion_spec("us_stock", sym, "state")
            got[sym] = scale_of(build_strategy(spec))
        except Exception:                       # noqa: BLE001 — 없으면 건너뛴다
            continue
    if not got:
        pytest.skip("미국 챔피언을 못 읽었다 — 이 검사는 저장소 상태가 필요하다")
    assert any(v > 1.0 for v in got.values()), (
        f"살아 있는 챔피언 어느 것도 배수를 못 받았다 {got} — 재보정이 "
        "조용히 꺼졌을 수 있다(전략 객체의 속성 이름이 바뀌었나?)")


def test_it_reads_the_object_that_made_the_signal():
    """신호를 낸 그 객체에게 물어본다 — 장부를 따로 조회하지 않는다."""
    class _Champ:
        threshold = 0.55
        sizing = "proba"
    assert scale_of(_Champ()) == pytest.approx(3.0)
    assert spec_of(_Champ())["params"]["threshold"] == 0.55


def test_an_object_without_a_threshold_is_not_guessed_at():
    """대조군 — 문턱이 없는 객체를 ML로 넘겨짚지 않는다."""
    class _Rule:
        pass
    assert spec_of(_Rule()) == {}
    assert scale_of(_Rule()) == 1.0


# ══ ⑤ 본 계좌(100만 챌린지)는 그대로다 ════════════════════════════

def test_the_shared_sizer_is_untouched():
    """공용 사이저는 옛 눈금 그대로여야 한다 — 실제 원금이 걸린 쪽이다.

    사장님 결정이 '실험만'이었다. 여기가 바뀌면 100만 챌린지의 비중도
    같이 커지고, 진행 중인 90일 판정의 전제도 함께 바뀐다.
    """
    import numpy as np

    from quant.strategies.ml import MLStrategy
    s = MLStrategy(threshold=0.55)
    # 상승확률 0.70 → 옛 눈금에서는 1/3이다(새 눈금이었다면 1.0).
    assert float(s._size(np.array([0.70]))[0]) == pytest.approx(1.0 / 3.0)


# ══ ⑥ 트랙이 실제로 더 굴린다 (행동 검사) ═════════════════════════
#
# ⚠️ 위까지는 전부 계산이 맞는지만 봤다. 계산이 맞아도 **트랙이 그것을
#    부르지 않으면** 굴리는 금액은 그대로다. 그래서 회차를 실제로 돌린다.


def _bars(n=80, freq="1h", end="2026-08-19T14:00:00"):
    idx = pd.date_range(end=end, periods=n, freq=freq)
    px = [100.0 + i * 0.1 for i in range(n)]
    return pd.DataFrame({"open": px, "high": [p * 1.01 for p in px],
                         "low": [p * 0.99 for p in px], "close": px},
                        index=idx)


class _ProbaChampion:
    """확률 사이징 ML 챔피언을 흉내 낸다 — 재보정을 받아야 한다."""
    threshold = 0.55
    sizing = "proba"

    def __init__(self, w=0.1):
        self.w = w

    def generate_signals(self, df):
        return pd.Series(self.w, index=df.index)


class _RuleChampion:
    """규칙 전략 — 문턱이 없으니 재보정을 받지 않아야 한다(대조군)."""

    def __init__(self, w=0.1):
        self.w = w

    def generate_signals(self, df):
        return pd.Series(self.w, index=df.index)


def _us_round(tmp_path, champion) -> dict:
    """회차를 실제로 돌리고 **장부에 적힌 그 회차**를 돌려준다.

    ⚠️ run_us_round가 돌려주는 것은 사람이 읽는 요약(체결 건수 같은 것)
       이지 회차 기록이 아니다. 요약만 보면 "몇 건 샀나"는 알아도
       "얼마어치 샀나"는 모른다 — 이 검사가 재려는 것이 바로 그 금액이다.
    """
    import json

    import quant.live.intraday_us as IU
    IU.run_us_round(
        OPEN_NOW, state_dir=str(tmp_path), docs_dir=str(tmp_path / "docs"),
        data={"AAPL": _bars()}, strategy_factory=lambda sym: champion)
    st = json.loads(
        (Path(tmp_path) / "intraday" / "us_challenger.json").read_text("utf-8"))
    rounds = st.get("rounds") or []
    assert rounds, "회차가 장부에 안 남았다"
    return rounds[-1]


def _bought(rec) -> float:
    return sum(abs(float(t["notional"])) for t in (rec.get("trades") or []))


def test_the_us_track_now_buys_three_times_as_much(tmp_path):
    """같은 예측·같은 시세인데 나가는 금액이 3배여야 한다."""
    new = _bought(_us_round(tmp_path / "ml", _ProbaChampion(0.1)))
    old = _bought(_us_round(tmp_path / "rule", _RuleChampion(0.1)))
    assert old > 0, "대조군이 아무것도 안 샀다 — 비교가 성립하지 않는다"
    assert new == pytest.approx(old * 3.0, rel=0.02), (
        f"확률 챔피언 {new:.2f} vs 규칙 챔피언 {old:.2f} — 재보정이 "
        "트랙까지 닿지 않았다")


def test_the_us_track_leaves_a_rule_champion_alone(tmp_path):
    """대조군 — 규칙 전략에는 배수가 안 붙는다.

    붙으면 확률이 아닌 값을 확률처럼 늘린 것이고, 그건 근거 없이
    베팅만 키운 것이다.
    """
    rec = _us_round(tmp_path, _RuleChampion(0.1))
    # 자산 ÷ 종목 수 × 0.1 이 그대로 나가야 한다.
    import quant.live.intraday_us as IU
    slice_budget = IU.START_CASH_USD / len(IU.universe(str(tmp_path)))
    assert _bought(rec) == pytest.approx(slice_budget * 0.1, rel=0.05)


def test_the_round_records_the_multiplier_it_actually_used(tmp_path):
    """장부가 배수를 말한다 — 조용히 꺼지면 여기가 1.0으로 돌아온다."""
    rec = _us_round(tmp_path, _ProbaChampion(0.1))
    assert rec.get("conviction_scale"), (
        "적용된 배수가 회차 기록에 없다 — 꺼졌는지 켜졌는지 알 방법이 없다")
    assert rec["conviction_scale"]["AAPL"] == pytest.approx(3.0)


def test_a_rule_champion_leaves_no_multiplier_in_the_record(tmp_path):
    """대조군 — 배수가 안 걸렸으면 그 칸이 아예 없다(1.0을 장식으로 적지 않는다)."""
    rec = _us_round(tmp_path, _RuleChampion(0.1))
    assert not rec.get("conviction_scale"), rec.get("conviction_scale")


# ══ ⑦ 규칙이 바뀐 사실이 화면까지 간다 ═════════════════════════════
#
# ⚠️ 실험 도중에 크기 규칙을 바꾸면 곡선의 한 지점부터 성격이 달라진다.
#    그걸 안 적으면 보는 사람은 앞뒤를 같은 것으로 읽는다 — 조용한 골대
#    이동이고, 이 저장소가 판정 시계에서 가장 엄격하게 막는 것이다.

_PAGES = {"us.html": "intraday_us.json",
          "intraday.html": "intraday.json",
          "futures.html": "futures.json"}


def _blank_state():
    """리포트 작성기에 먹일 최소 장부."""
    return {"cash": 10_000.0, "start_cash": 10_000.0, "currency": "USDT",
            "positions": {}, "cost_paid": 0.0, "last_prices": {},
            "risk_scale": 1.0, "rounds": []}


def _ons(report) -> list:
    return [c.get("on") for c in (report.get("rule_changes") or [])]


def test_the_us_ledger_declares_the_change(tmp_path):
    """⚠️ 커밋된 JSON을 읽지 않는다 — **작성기를 부른다.**

    커밋된 파일을 읽으면 작성기를 통째로 망가뜨려도 검사가 통과한다(그
    파일은 이미 디스크에 있으니까). 다음 배치가 도는 순간 기록이 사라지는데
    아무도 모르게 된다.
    """
    from quant.live import intraday_us
    r = intraday_us.write_public_report(_blank_state(), docs_dir=str(tmp_path),
                                        state_dir=str(ROOT / "state"))
    assert "2026-08-23" in _ons(r), f"미국 장부에 눈금 재보정 기록이 없다 {_ons(r)}"


def test_the_coin_ledger_declares_the_change(tmp_path):
    from quant.live import intraday_challenger
    r = intraday_challenger.write_public_report(
        _blank_state(), docs_dir=str(tmp_path), state_dir=str(ROOT / "state"))
    assert "2026-08-23" in _ons(r), f"코인 장부에 기록이 없다 {_ons(r)}"


def test_the_futures_ledger_declares_both_changes():
    """선물은 **둘 다** 적어야 한다 — 배율과 눈금은 곱해지는 별개 장치다.

    하나만 적으면 곡선을 읽는 사람이 그날 무엇이 얼마나 달라졌는지
    절반만 알게 된다.
    """
    from quant.live import futures_challenger
    r = futures_challenger.public_report(_blank_state())
    whats = " ".join(c.get("what", "") for c in (r.get("rule_changes") or []))
    assert "배율" in whats, f"배율을 켠 사실이 없다 {whats!r}"
    assert "눈금" in whats, f"눈금 재보정 사실이 없다 {whats!r}"


@pytest.mark.parametrize("page", sorted(_PAGES))
def test_the_page_shows_the_change_to_a_reader(page):
    """장부에 있어도 **화면이 안 그리면** 아무도 못 본다."""
    import functools
    import http.server
    import json
    import shutil
    import socketserver
    import threading

    pytest.importorskip("playwright.sync_api",
                        reason="playwright 없음 — 화면 검사 생략")
    sys.path.insert(0, str(ROOT / "tests"))
    from _browser import block_external, chromium_or_skip
    from playwright.sync_api import sync_playwright

    import tempfile
    root = Path(tempfile.mkdtemp())
    shutil.copytree(ROOT / "docs", root, dirs_exist_ok=True)
    # 검사용 장부를 손으로 짓는다 — 살아 있는 기록에 기대지 않는다.
    led = json.loads((root / _PAGES[page]).read_text("utf-8"))
    led["rule_changes"] = [{"on": "2026-08-23",
                            "what": "눈금을둘로접었습니다",
                            "why": "검사용문장입니다"}]
    (root / _PAGES[page]).write_text(json.dumps(led, ensure_ascii=False),
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
            pg.goto(f"http://127.0.0.1:{srv.server_address[1]}/{page}")
            pg.wait_for_timeout(1500)
            text = pg.locator("body").inner_text()
        finally:
            pg.close()
            b.close()
            srv.shutdown()
    assert "눈금을둘로접었습니다" in text, f"{page}: 바뀐 규칙을 화면이 안 적는다"
    assert "검사용문장입니다" in text, f"{page}: 왜 바꿨는지를 화면이 안 적는다"


# ══ ⑧ 코인·선물 트랙도 같은 눈금을 쓴다 ═══════════════════════════
#
# ⚠️ 세 트랙이 같은 규칙을 쓴다는 것은 **주장이 아니라 검사할 것**이다.
#    한 트랙만 옛 눈금으로 남으면 트랙끼리의 비교가 크기 규칙 비교로
#    오염된다 — 그러면 "코인이 더 낫다"가 신호 차이인지 눈금 차이인지
#    영영 알 수 없다.

def _coin_bought(tmp_path, champion) -> float:
    import quant.live.intraday_challenger as IC
    idx = pd.date_range(end="2026-08-18T04:00:00", periods=100, freq="h")
    px = [100.0 + i * 0.1 for i in range(100)]
    df = pd.DataFrame({"open": px, "high": px, "low": px, "close": px,
                       "volume": [1.0] * 100}, index=idx)
    IC.run_intraday_round(
        "2026-08-18T04:00:00+00:00", state_dir=str(tmp_path / "state"),
        docs_dir=str(tmp_path / "docs"),
        data={s: df for s in IC.UNIVERSE},
        strategy_factory=lambda s: champion)
    import json
    st = json.loads((Path(tmp_path) / "state" / "intraday" /
                     "challenger.json").read_text("utf-8"))
    rounds = st.get("rounds") or []
    assert rounds, "코인 회차가 장부에 안 남았다"
    return sum(abs(float(t["notional"]))
               for t in (rounds[-1].get("trades") or []))


def test_the_coin_track_uses_the_same_dial(tmp_path):
    new = _coin_bought(tmp_path / "ml", _ProbaChampion(0.1))
    old = _coin_bought(tmp_path / "rule", _RuleChampion(0.1))
    assert old > 0, "대조군이 아무것도 안 샀다"
    assert new == pytest.approx(old * 3.0, rel=0.02), (
        f"코인 트랙: 확률 {new:.2f} vs 규칙 {old:.2f} — 눈금이 갈라졌다")


def _futures_bought(monkeypatch, tmp_path, champion, two_sided=True) -> float:
    import quant.live.futures_challenger as F
    closes = [100.0] * 40
    idx = pd.date_range("2026-01-01", periods=len(closes), freq="h")
    df = pd.DataFrame({"open": closes, "high": closes, "low": closes,
                       "close": closes, "volume": [1.0] * len(closes)},
                      index=idx)
    monkeypatch.setattr(F, "_fetch_real", lambda sym, timeframe=None: df)
    # ⚠️ `**kw`를 받는다 — 진짜 함수가 키워드를 하나 더 받게 됐고
    #    (`allow_two_sided`, 2026-09-03 방향 관문), 가짜가 진짜 서명을 안
    #    따라가면 **가짜 쪽이 터져서** "숏이 안 나갔다"는 엉뚱한 실패가 뜬다.
    monkeypatch.setattr(F, "build_two_sided",
                        lambda sym, state_dir, **kw: (champion, two_sided))
    monkeypatch.setattr(F, "MIN_BARS", 5)
    rec = F.run_futures_round("2026-06-01T00:00:00+09:00",
                              state_dir=str(tmp_path),
                              universe=["BTC/USDT"], per_side=0.0)
    return sum(abs(float(t["notional"])) for t in (rec.get("trades") or []))


def test_the_futures_track_uses_the_same_dial(monkeypatch, tmp_path):
    # ⚠️ 신호를 밴드 위로 잡는다(2026-09-02). 선물 체결기에 리밸런스 밴드가
    #    붙으면서, 비중 0.1짜리 진입은 코인 밴드(0.15)에 걸려 **아예 안 나간다**
    #    — 대조군이 0이 되어 눈금 비교 자체가 성립하지 않는다. 여기서 재는
    #    것은 밴드가 아니라 확신도 눈금이므로, 둘 다 밴드를 넘는 자리에서 잰다.
    new = _futures_bought(monkeypatch, tmp_path / "ml", _ProbaChampion(0.25))
    old = _futures_bought(monkeypatch, tmp_path / "rule", _RuleChampion(0.25))
    assert old > 0, "대조군이 아무것도 안 샀다"
    assert new > old * 2.0, (
        f"선물 트랙: 확률 {new:.2f} vs 규칙 {old:.2f} — 눈금이 안 걸렸다")


def test_a_futures_short_grows_the_same_way(monkeypatch, tmp_path):
    """숏도 같은 배수로 커진다 — 부호를 잃지 않는다.

    여기서 배수가 부호를 뒤집으면 **내림에 걸려던 돈으로 오름에 건다.**
    조용히 정반대로 도는 계좌가 되고, 금액만 보면 눈치채지 못한다.
    """
    import json

    import quant.live.futures_challenger as F
    _futures_bought(monkeypatch, tmp_path, _ProbaChampion(-0.1))
    st = json.loads((Path(tmp_path) / "futures" /
                     "futures.json").read_text("utf-8"))
    qty = float((st.get("positions") or {}).get("BTC/USDT") or 0.0)
    assert qty < 0, f"숏 신호였는데 포지션이 {qty} — 부호가 뒤집혔다"
