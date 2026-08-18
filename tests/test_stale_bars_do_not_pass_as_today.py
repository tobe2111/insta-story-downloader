"""**묵은 봉이 '오늘 이미 했다'로 읽히고 있었다** (감사 284).

2026-08-16 밤, 코인 5종의 마지막 봉은 **2026-03-04**였다 — 165일 묵은
데이터다(감사 261의 페이지네이션 결함). 그런데 챔피언의 `last_run_asof`도
2026-03-04이라 멱등 가드가 그대로 걸렸고, 로그에는 이렇게 찍혔다.

    [2026-03-04] crypto/BTC/USDT — 오늘 이미 재학습함, 건너뜀

**'오늘'이 아니라 165일 전이었다.** 그 165일 동안 코인 5종은 오디션을 한 번도
열지 못한 채 옛 챔피언으로 **실제 돈을 굴렸고**, 배치는 매일 조용했다.
정체 경보(감사 243)가 뒤늦게 잡아 주긴 했지만 그건 사후 보고다 — 멈춰야 할
자리에서 멈추지 않았다.

"개수를 채웠다"와 "최신까지 받았다"가 다르듯(감사 261), **"같은 봉이다"와
"오늘 것이다"도 다르다.** 데이터가 묵었으면 조용히 건너뛰지 말고 시끄럽게
실패한다 — 그 종목만 실패로 잡히고 나머지는 계속 돈다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live import retrain as R  # noqa: E402


def _frame(last_day: str, n: int = 400) -> pd.DataFrame:
    idx = pd.date_range(end=pd.Timestamp(last_day), periods=n, freq="D")
    rng = np.random.default_rng(3)
    close = 100.0 * np.cumprod(1.0 + rng.normal(0.0005, 0.01, size=n))
    return pd.DataFrame({"open": close, "high": close * 1.01,
                         "low": close * 0.99, "close": close,
                         "volume": 1.0}, index=idx)


class _Provider:
    def __init__(self, df):
        self._df = df

    def get_ohlcv(self, *a, **k):
        return self._df.copy()


@pytest.fixture()
def _serve(monkeypatch):
    def use(df):
        monkeypatch.setattr("quant.data.get_provider", lambda m: _Provider(df))
    return use


# ── ① 나이 계산 자체 ─────────────────────────────────────────────

def test_it_measures_the_real_age():
    assert R._bar_age_days("2026-03-04", "2026-08-16") == 165
    assert R._bar_age_days("2026-08-16", "2026-08-16") == 0
    # 시각이 붙어 있어도 날짜만 본다.
    assert R._bar_age_days("2026-08-14 00:00:00", "2026-08-16") == 2


def test_an_unreadable_date_accuses_nobody():
    """모르는 것과 아닌 것은 다르다 — 못 읽으면 판정하지 않는다."""
    for bad in (None, "", "없음", "2026-13-99"):
        assert R._bar_age_days(bad, "2026-08-16") is None
    # ⚠️ 파이썬 3.11+는 "20260304"(구분자 없는 ISO)도 읽는다 — 못 읽는
    #    값만 None이지, 모양이 낯설다고 버리지는 않는다.
    assert R._bar_age_days("20260304", "2026-08-16") == 165


def test_crypto_is_held_to_a_tighter_limit_than_stocks():
    """코인은 24시간 시장이라 이틀만 비어도 이상하다. 주식은 주말이 있다."""
    assert R.MAX_BAR_AGE_DAYS["crypto"] < R.MAX_BAR_AGE_DAYS[""]
    assert R.MAX_BAR_AGE_DAYS["crypto"] >= 1, "하루도 못 비면 정상 주말에도 터진다"


# ── ② 실제로 멈추는가 ────────────────────────────────────────────

def test_a_stale_feed_stops_loudly(_serve, tmp_path):
    """165일 묵은 봉으로는 챔피언을 다시 뽑지 않는다."""
    _serve(_frame("2026-03-04"))
    with pytest.raises(RuntimeError) as e:
        R.run_retrain("crypto", "BTC/USDT", state_dir=str(tmp_path),
                      require_real_data=True)
    msg = str(e.value)
    assert "묵었" in msg and "2026-03-04" in msg, msg
    assert "시세 공급" in msg, f"사람이 무엇을 확인해야 하는지 안 알려준다: {msg}"


def test_a_fresh_feed_is_not_stopped(_serve, tmp_path):
    """대조군 — 오늘 봉이면 그대로 돌아야 한다.

    이게 없으면 "항상 실패한다"도 위 검사를 통과하고, 그러면 재학습이
    영영 안 돈다.
    """
    _serve(_frame(str(pd.Timestamp.today().date())))
    out = R.run_retrain("crypto", "BTC/USDT", state_dir=str(tmp_path),
                        require_real_data=True)
    assert out and not out.get("skipped"), out


def test_the_offline_path_is_untouched(_serve, tmp_path):
    """`require_real_data=False`(검사·재현용)에서는 옛 날짜로도 돌 수 있어야 한다.

    과거 스냅샷을 재현하는 경로까지 막으면 verify가 죽는다.
    """
    _serve(_frame("2026-03-04"))
    out = R.run_retrain("crypto", "BTC/USDT", state_dir=str(tmp_path),
                        require_real_data=False)
    assert out is not None


def test_the_skip_message_no_longer_claims_today():
    """'오늘 이미 재학습함'은 165일 전 봉에도 찍히던 문장이다."""
    src = (ROOT / "quant" / "live" / "retrain.py").read_text("utf-8")
    # ⚠️ 주석은 그 문장을 **인용**한다(왜 고쳤는지 남기려고). 실제로 찍히는
    #    줄만 본다 — 주석까지 세면 이 검사는 자기 설명에 걸려 넘어진다.
    printed = [ln for ln in src.splitlines()
               if "이미 재학습함" in ln and not ln.lstrip().startswith("#")]
    assert printed, "건너뜀 로그 줄을 못 찾았다 — 검사가 낡았다"
    for ln in printed:
        assert "오늘 이미 재학습함" not in ln, (
            f"묵은 봉에도 '오늘'이라고 적는다: {ln.strip()}")
        assert "같은 봉으로 이미 재학습함" in ln, ln.strip()


# ── ③ 한 종목이 멈춰도 나머지는 돈다 ────────────────────────────

def test_one_stale_symbol_does_not_stop_the_others(monkeypatch, tmp_path):
    """묵은 종목은 **실패**로 잡히고, 멀쩡한 종목은 계속 간다."""
    fresh = _frame(str(pd.Timestamp.today().date()))
    stale = _frame("2026-03-04")

    def provider(market):
        return _Provider(stale if market == "crypto" else fresh)

    monkeypatch.setattr("quant.data.get_provider", provider)
    out = R.run_retrain_all([("crypto", "BTC/USDT"), ("synthetic", "T1")],
                            state_dir=str(tmp_path), require_real_data=True)
    assert "crypto:BTC/USDT" in out["failed"], out
    assert "synthetic:T1" in out["ok"] or "synthetic:T1" in out["skipped"], out
    assert "묵었" in out["failed"]["crypto:BTC/USDT"]
