"""미국주식 장중 트랙 — 장이 닫히면 펜도 놓는다 (2026-08-19, 사장님 지시).

지켜야 할 약속:
- 미국 정규장 밖에서는 판단도 체결도 **기록도** 없다 — 닫힌 장의 가격으로
  '체결했다'고 적는 것은 실험이 아니라 소설이다.
- 같은 봉 멱등 — 새 정보가 없으면 회차를 쓰지 않는다(밤새 소음 금지).
- 통화는 USD 하나다. 원화 환산 코드가 이 모듈에 등장하는 순간
  감사 254(통화 혼합 사고)의 재발 지점이 생긴다.
- 체결·평가·킬스위치는 코인 트랙의 **같은 함수**를 빌려 쓴다 — 복사하면
  언젠가 두 트랙의 규칙이 갈라져 '미국장 대 코인장' 비교가 오염된다.
- 실데이터가 아니면(합성 폴백) 그 종목은 쉰다.
- 판정 기준은 첫 회차 전에 사전 등록됐다(prereg와 날짜가 일치).
- 배선: 5분 러너(cli)가 try로 감싸 부르고, guard.yml이 공개 JSON을 커밋한다.
- 화면(us.html)이 intraday_us.json에서만 읽는다.
  ⚠️ 2026-08-22(감사 305)에 페이지가 옮겨졌다. 예전에는 코인 페이지
     (intraday.html) 안의 한 섹션이었는데, 사장님 지시로 트랙마다
     페이지를 나누면서 자기 페이지가 생겼다 — "100만원 투자 1페이지,
     코인투자 1페이지, 선물투자 1페이지, 미국주식 1페이지".
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import quant.live.intraday_us as IU                      # noqa: E402

SRC = (ROOT / "quant" / "live" / "intraday_us.py").read_text("utf-8")

OPEN_NOW = "2026-08-19T15:00:00+00:00"    # 수요일 11:00 뉴욕 — 정규장
CLOSED_SAT = "2026-08-22T15:00:00+00:00"  # 토요일 — 휴장
CLOSED_NIGHT = "2026-08-19T02:00:00+00:00"  # 뉴욕 화 22:00 — 장 밖


class _AlwaysLong:
    def generate_signals(self, df):
        return pd.Series(1.0, index=df.index)


def _bars(n=80, freq="1h", end="2026-08-19T14:00:00"):
    """`end`에서 끝나는 봉 n개.

    ⚠️ 예전 판은 고정 시작일(2026-08-10)로 만들어서, 검사 시각(8/19)에는
    봉이 엿새쯤 낡아 있었다. 그때는 아무 관문도 없어서 통과했지만 —
    실제로 그 상태가 첫 회차에서 벌어졌다(어제 봉으로 매수). 이제 낡은
    봉은 판단에서 빠지므로, 검사도 **살아 있는 봉**으로 한다.
    """
    idx = pd.date_range(end=end, periods=n, freq=freq)
    px = [100.0 + i * 0.1 for i in range(n)]
    return pd.DataFrame({"open": px, "high": [p * 1.01 for p in px],
                         "low": [p * 0.99 for p in px], "close": px},
                        index=idx)


def _run(tmp_path, now, data=None):
    return IU.run_us_round(
        now, state_dir=str(tmp_path), docs_dir=str(tmp_path / "docs"),
        data=data if data is not None else {"AAPL": _bars()},
        strategy_factory=lambda sym: _AlwaysLong())


def test_no_round_outside_regular_hours(tmp_path):
    for closed in (CLOSED_SAT, CLOSED_NIGHT):
        v = _run(tmp_path, closed)
        assert v.get("skipped") == "미국장 휴장", v
    assert not (tmp_path / "intraday" / "us_challenger.json").exists(), (
        "장 밖인데 장부가 생겼다 — 닫힌 장의 체결은 소설이다")


def test_a_round_trades_inside_the_session(tmp_path):
    v = _run(tmp_path, OPEN_NOW)
    assert "equity" in v and v["trades"] >= 1, v   # 회차가 실제로 돌았다
    st = json.loads(
        (tmp_path / "intraday" / "us_challenger.json").read_text("utf-8"))
    assert st["currency"] == "USD"
    assert st["positions"].get("AAPL", 0) > 0
    pub = json.loads((tmp_path / "docs" / "intraday_us.json")
                     .read_text("utf-8"))
    assert pub["kind"] == IU.KIND and "가상" in pub["label"]


def test_same_bar_is_idempotent(tmp_path):
    _run(tmp_path, OPEN_NOW)
    v2 = _run(tmp_path, "2026-08-19T15:05:00+00:00")   # 5분 뒤, 새 봉 없음
    assert v2.get("skipped") == "같은 봉 재실행", v2
    st = json.loads(
        (tmp_path / "intraday" / "us_challenger.json").read_text("utf-8"))
    assert len(st["rounds"]) == 1, "같은 봉으로 두 회차를 썼다 — 소음이다"


def test_the_ladder_runs_its_own_ledger(tmp_path):
    data = {"AAPL": _bars(),
            "15m": {"AAPL": _bars(freq="15min", end="2026-08-19T14:45:00")},
            "5m": {}}
    _run(tmp_path, OPEN_NOW, data=data)
    t15 = json.loads(
        (tmp_path / "intraday" / "us_track_15m.json").read_text("utf-8"))
    assert t15["currency"] == "USD" and len(t15["rounds"]) == 1


def test_the_currency_seal_no_krw_in_this_module():
    for banned in ("usdkrw", "to_krw", "fx_usdkrw", "원화 환산을 한다"):
        assert banned not in SRC.replace("원화 환산을 하지 않는다", ""), (
            f"모듈에 '{banned}' — USD 봉인이 깨졌다(감사 254 재발 지점)")


def test_the_rules_are_borrowed_not_copied():
    assert "from quant.live.intraday_challenger import" in SRC
    assert "_execute_targets" in SRC, "체결 규칙을 빌려 쓰지 않는다"
    assert "_kill_switch_scale" in SRC, "킬스위치를 빌려 쓰지 않는다"
    assert "def _execute_targets" not in SRC, (
        "체결 규칙을 복사했다 — 두 트랙의 규칙이 갈라질 길을 만들었다")
    assert 'synthetic_fallback' in SRC and 'attrs.get("source")' in SRC, (
        "합성 시세 방어가 없다 — 가짜 체결의 문이 열렸다")


def test_the_goalposts_match_the_registry():
    from quant.live import prereg
    exp = prereg.PREREGISTERED["intraday_us"]
    assert exp["start"] == "2026-08-19" and exp["judge_on"] == "2026-11-17"
    assert IU.PREREGISTERED_JUDGEMENT["registered_on"] == exp["start"], (
        "트랙 내 사본과 사전 등록 원장의 등록일이 어긋난다")


def test_the_wiring_cannot_kill_the_coin_track():
    cli = (ROOT / "quant" / "cli.py").read_text("utf-8")
    i = cli.find("run_us_round")
    assert i > 0, "5분 러너가 미국 트랙을 부르지 않는다"
    assert "try:" in cli[max(0, i - 300):i], (
        "미국 트랙이 예외 방벽 없이 코인 트랙 뒤에 있다")
    guard = (ROOT / ".github" / "workflows" / "guard.yml").read_text("utf-8")
    assert "docs/intraday_us.json" in guard, "공개 JSON이 커밋되지 않는다"


def test_the_screen_reads_the_ledger_only():
    page = (ROOT / "docs" / "us.html").read_text("utf-8")
    assert "intraday_us.json" in page and "us-sum" in page, (
        "미국 트랙 화면이 없다 — 공개되지 않는 실험은 실험이 아니다")


# ── 무료 시세를 조르지 않는다 (2026-08-19) ──────────────────────
#
# 장중 감시는 5분마다 돈다. 1시간 트랙은 한 시간에 한 번만 새 판단거리가
# 생기므로, 나머지 열한 번은 같은 봉을 다시 받아 같은 결론을 내고 버린다.
# 코인(거래소 공개 API)에서는 공짜였지만 미국 무료 시세는 그 헛걸음에
# 차단으로 답한다 — 차단당한 실험은 매 회차 조용히 비는 트랙이 된다.

def _bars_ending(end="2026-08-19T14:00", n=80, freq="1h"):
    """마지막 닫힌 봉이 **지금 직전**인 봉들 — 실제 장중 상황과 같은 모양."""
    idx = pd.date_range(end=end, periods=n, freq=freq)
    px = [100.0 + i * 0.1 for i in range(n)]
    return pd.DataFrame({"open": px, "high": [p * 1.01 for p in px],
                         "low": [p * 0.99 for p in px], "close": px},
                        index=idx)


def test_no_new_bar_means_no_request(tmp_path, monkeypatch):
    # 14:00 봉까지 판단한 상태(15:00 회차) — 실제 장중과 같은 배치
    _run(tmp_path, OPEN_NOW, data={"AAPL": _bars_ending()})
    st = json.loads(
        (tmp_path / "intraday" / "us_challenger.json").read_text("utf-8"))
    assert not IU.bar_could_have_closed(st, "1h", "2026-08-19T15:30:00+00:00"), (
        "30분 뒤인데 새 봉이 닫혔다고 본다 — 헛걸음 요청이 열린다")
    assert IU.bar_could_have_closed(st, "1h", "2026-08-19T18:30:00+00:00"), (
        "세 시간 뒤인데 새 봉이 없다고 본다 — 트랙이 영영 멈춘다")

    # 관문이 실제로 **네트워크를 막는가** — 부르면 검사가 터지게 심어 둔다.
    def _boom(*a, **k):
        raise AssertionError("새 봉이 없는데 시세를 불렀다")
    monkeypatch.setattr(IU, "_fetch_real", _boom)
    v = IU.run_us_round("2026-08-19T15:30:00+00:00", state_dir=str(tmp_path),
                        docs_dir=str(tmp_path / "docs"),
                        strategy_factory=lambda s: _AlwaysLong())
    assert "새 봉" in str(v.get("skipped")), v


def test_the_first_round_always_asks():
    """기록이 없으면 막지 않는다 — '모름'을 '아님'으로 읽으면 첫 회차가 없다."""
    assert IU.bar_could_have_closed({}, "1h", OPEN_NOW)
    assert IU.bar_could_have_closed({"rounds": [{}]}, "1h", OPEN_NOW)


def test_the_experiment_yields_before_the_safety_net(tmp_path, monkeypatch):
    """시세가 느린 날 실험이 먼저 물러난다 — 감시·킬스위치가 인질이 아니다."""
    monkeypatch.setattr(IU, "FETCH_BUDGET_SEC", -1.0)   # 예산을 다 쓴 상태
    monkeypatch.setattr(IU, "_fetch_real",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("예산 초과인데 시세를 불렀다")))
    _p, _s, _b, skipped, _d = IU._judge_symbols(
        ["AAPL"], OPEN_NOW, "1h", None, lambda s: _AlwaysLong())
    assert "시간 초과" in skipped["AAPL"], skipped


def test_the_limit_shadow_runs_here_too(tmp_path):
    """주식은 호가 간격이 코인과 달라 '기다리는 체결'의 값이 다를 수 있다."""
    _run(tmp_path, OPEN_NOW)
    st = json.loads(
        (tmp_path / "intraday" / "us_challenger.json").read_text("utf-8"))
    assert st.get("limit_shadow"), "지정가 그림자가 활성화되지 않았다"
    pub = json.loads((tmp_path / "docs" / "intraday_us.json")
                     .read_text("utf-8"))
    assert pub.get("limit_shadow"), "공개 요약에 그림자가 없다"
    src = (ROOT / "quant" / "live" / "intraday_us.py").read_text("utf-8")
    assert "def _limit_shadow_round" not in src, (
        "체결 판정을 복사했다 — 두 트랙의 '지정가'가 갈라질 길을 만들었다")


# ── 공식 시세로 갈아탈 수 있는가 (2026-08-19, 사장님 "알파카로 하고") ──
#
# 키는 저장소에 없다(깃허브 시크릿에만). 그래서 "있으면 쓰고 없으면 하던
# 대로"가 유일하게 정직한 구조다 — 키를 전제로 짜면 키 없는 곳에서 조용히
# 죽고, 야후만 전제로 짜면 키가 있어도 안 쓴다.

def test_the_official_source_leads_only_when_keyed(monkeypatch):
    from quant.data.stock import StockDataProvider
    for k in ("ALPACA_KEY_ID", "ALPACA_SECRET_KEY"):
        monkeypatch.delenv(k, raising=False)
    names = [n for n, _ in StockDataProvider("us_stock")._sources()]
    assert names[0] == "yfinance" and "alpaca" not in names, (
        f"키가 없는데 알파카를 시도한다: {names}")

    monkeypatch.setenv("ALPACA_KEY_ID", "test-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test-secret")
    names = [n for n, _ in StockDataProvider("us_stock")._sources()]
    assert names[0] == "alpaca", f"키가 있는데 안 쓴다: {names}"
    assert "yfinance" in names, "공식 소스가 죽었을 때 물러설 곳이 없다"
    # 한국 주식은 알파카가 다루지 않는다 — 엉뚱한 소스를 앞에 세우지 않는다.
    kr = [n for n, _ in StockDataProvider("kr_stock")._sources()]
    assert "alpaca" not in kr, f"한국 시장에 미국 소스를 붙였다: {kr}"


def test_the_five_minute_track_returns_with_the_key(monkeypatch):
    for k in ("ALPACA_KEY_ID", "ALPACA_SECRET_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert IU.ladder_timeframes() == ["15m"], (
        "무료 공개 시세인데 5분 트랙을 돌린다 — 막혀서 기록이 빈다")
    monkeypatch.setenv("ALPACA_KEY_ID", "test-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test-secret")
    assert IU.ladder_timeframes() == ["15m", "5m"], (
        "공식 시세 키가 있는데 5분 트랙이 돌아오지 않는다")


def test_the_screen_says_which_source_it_ran_on(monkeypatch, tmp_path):
    """어느 시세로 돈 기록인지 화면이 말해야 한다 — 출처가 곧 신뢰도다."""
    _run(tmp_path, OPEN_NOW)
    pub = json.loads((tmp_path / "docs" / "intraday_us.json")
                     .read_text("utf-8"))
    assert pub.get("quote_source"), "장부가 시세 출처를 안 남긴다"
    page = (ROOT / "docs" / "us.html").read_text("utf-8")
    assert "u.quote_source" in page, (
        "화면이 출처를 장부에서 읽지 않는다 — 산문에 박으면 어긋난다")


def test_the_key_never_leaves_the_environment():
    """키는 환경에서만 읽고 어디에도 복사하지 않는다(동의로도 못 푸는 보안선)."""
    src = (ROOT / "quant" / "data" / "stock.py").read_text("utf-8")
    # 헤더를 만드는 한 함수 밖에서 환경변수를 읽으면 안 된다.
    outside = [ln for ln in src.splitlines()
               if "ALPACA_SECRET_KEY" in ln and "_ALPACA_ENV" not in ln
               and "os.environ.get(" in ln]
    assert len(outside) <= 1, (
        f"시크릿을 여러 곳에서 읽는다 — 새는 길이 늘어난다: {outside}")
    for leak in ("log.info", "log.warning", "log.error"):
        for ln in src.splitlines():
            if leak in ln and "ALPACA" in ln:
                raise AssertionError(f"키가 로그로 나갈 수 있다: {ln}")
    guard = (ROOT / ".github" / "workflows" / "guard.yml").read_text("utf-8")
    assert "secrets.ALPACA_KEY_ID" in guard, (
        "감시 작업에 키가 전달되지 않는다 — 시크릿을 넣어도 안 쓰인다")


# ── 낡은 봉으로는 판단하지 않는다 (2026-08-19 첫 회차 실측에서 나온 관문) ──
#
# 첫 회차(13:52Z, 개장 22분 뒤)가 **어제 19:30Z 봉**으로 세 종목을 샀다.
# 장은 열려 있었고 시세도 '받아졌으니' 어떤 관문에도 안 걸렸다 — 조용히
# 어제를 오늘처럼 쓴 것이다. 장이 열렸다는 것과 시세가 오늘 것이라는 건
# 다른 이야기다.


def test_a_stale_bar_does_not_get_traded(tmp_path):
    """어제 봉이 최신으로 와도 사지 않는다 — 그리고 왜 쉬었는지 남긴다."""
    stale = {"AAPL": _bars(end="2026-08-18T19:30:00")}   # 하루 전 봉
    v = _run(tmp_path, OPEN_NOW, data=stale)
    assert v.get("trades", 0) == 0, "18시간 낡은 봉으로 체결했다"
    st = json.loads(
        (tmp_path / "intraday" / "us_challenger.json").read_text("utf-8"))
    reason = (st["rounds"][-1].get("skipped") or {}).get("AAPL", "")
    assert "낡" in reason, f"쉰 사유가 장부에 없다: {reason}"
    assert not st.get("positions"), "안 샀다면서 보유가 생겼다"


def test_a_fresh_bar_still_trades(tmp_path):
    """관문이 생겼다고 정상 회차까지 막으면 실험이 죽는다."""
    v = _run(tmp_path, OPEN_NOW)          # 기본 데이터 = 살아 있는 봉
    assert v.get("trades", 0) >= 1, v


def test_the_staleness_line_is_measured_in_bar_lengths():
    """봉 길이가 다르면 허용 나이도 달라야 한다 — 고정 분(分)이 아니다."""
    now = "2026-08-19T15:00:00+00:00"
    # 15분봉 기준 40분 전 봉은 살아 있고(3배=45분), 1시간봉 기준으로도 산다.
    assert not IU.bar_is_stale("2026-08-19 14:20:00", "15m", now)
    assert not IU.bar_is_stale("2026-08-19 14:20:00", "1h", now)
    # 2시간 전 봉은 15분봉엔 낡았고, 1시간봉엔(3배=3시간) 아직 산다.
    assert IU.bar_is_stale("2026-08-19 13:00:00", "15m", now)
    assert not IU.bar_is_stale("2026-08-19 13:00:00", "1h", now)


def test_it_does_not_refetch_yesterdays_bar_all_morning(tmp_path):
    """개장 직후 스로틀 — 어제 봉을 5분마다 다시 받으면 차단당한다.

    어제 마지막 봉 + 봉 길이 2배는 새벽에 이미 지나 있다. 그 식만 쓰면
    개장 직후부터 매 회차 시세를 부른다. 오늘 첫 봉은 **개장 + 봉 길이**에야
    닫히므로 그 전에는 부를 이유가 없다.
    """
    st = {"rounds": [{"bar_times": {"AAPL": "2026-08-18 19:30:00"}}]}
    # 개장(13:30Z) 직후 — 1시간봉은 14:30Z에야 첫 봉이 닫힌다
    assert not IU.bar_could_have_closed(st, "1h", "2026-08-19T13:52:00+00:00")
    assert IU.bar_could_have_closed(st, "1h", "2026-08-19T14:35:00+00:00")
    # 15분봉은 13:45Z면 닫힌다
    assert IU.bar_could_have_closed(st, "15m", "2026-08-19T13:52:00+00:00")
