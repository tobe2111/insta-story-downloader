"""봉이 다 만들어졌는가 — 결정에 쓴 마지막 봉의 완성도를 잰다.

2026-08-11 감사 56. 주식 제공자에는 `_drop_unclosed`가 있어 장 마감 전의
'오늘' 봉을 버린다. 코인 제공자에는 그런 장치가 없다 — 코인은 24시간
돌아가므로 UTC 일봉의 '오늘' 봉은 **항상** 진행 중이고, 새벽 배치는 그
진행 중인 봉을 마지막 봉으로 받아 그대로 판단에 쓴다.

스냅샷 실측(2026-08-07~09, 코인 5종목 15봉):

    종가가 확정 봉과 다른 봉 : 15 / 15
    종가 차이               : 평균 66.8bp · 최대 150.8bp
    고저 레인지 축소         : 평균 36.2% · 최대 88.6%
    (같은 기간 주식 28봉은 0/28 — _drop_unclosed가 제대로 막고 있다)

무엇이 문제인가:

  ① 모델은 24시간 봉으로 학습했는데 예측 시점의 마지막 행만 19시간 봉이다.
     ret1·고저 레인지·ATR·GK변동성·볼린저 %b가 전부 학습 분포 밖이다.
     특히 레인지가 36% 짧게 잡히면 변동성 추정이 낮아지고, 변동성 타깃
     사이징의 분모가 작아져 **목표보다 큰 비중**이 실린다.
  ② 오디션(백테스트)은 완성된 봉으로만 평가한다. 즉 선발전은 24시간 봉의
     성적으로 뽑고 실전은 19시간 봉으로 굴린다 — 오디션-현실 격차다.
  ③ 장부의 price가 그날의 일봉 종가가 아니다. 사이트는 "누구든 검증할 수
     있다"고 말하는데, 검증하려는 사람이 공개 차트의 일봉 종가와 대조하면
     매일 어긋난다. 조작이 아닌데 조작처럼 보이는 기록이다.

이 모듈은 그 사실을 **재서 장부에 남긴다**.

⚠️ 2026-08-11 같은 날 판단 쪽은 고쳤다(감사 71): `_signal_frame`이 코인의
   진행 중인 봉을 신호·피처·공분산에서 뺀다. 규칙은 이제
   **"완성된 정보로 판단하고, 지금 가격에 체결한다"**이다.
   그래서 이 값이 말하는 것은 더 이상 '판단에 쓴 봉'이 아니라
   **'체결·평가에 쓴 봉'**의 완성도다 — 장부의 price가 그날 일봉 종가가
   아니라는 사실(위 ③)은 그대로 남아 있고, 그것을 숨기지 않기 위해 계속
   기록한다. (2026-08-12 감사 143에서 이 문구가 낡아 있던 것을 고쳤다.)
"""
from __future__ import annotations

import datetime as dt

# 봉 하나의 길이(초) — 지원하는 타임프레임만.
_TF_SECONDS = {
    "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "4h": 14400, "1d": 86400,
}

# 주식 제공자는 _drop_unclosed로 미완결 봉을 버린다 — 완성도 판정 대상이 아니다.
CONTINUOUS_MARKETS = {"crypto"}


def bar_elapsed_fraction(last_bar, timeframe: str = "1d",
                         now: dt.datetime | None = None) -> float | None:
    """마지막 봉이 얼마나 진행됐는지 [0,1]로 돌려준다. 판정 불가면 None.

    1.0 = 이미 닫힌 봉(완성). 0.79 = 79%만 만들어진 봉.
    last_bar는 봉의 **시작** 시각(naive-UTC 또는 tz-aware)이다.
    """
    secs = _TF_SECONDS.get(timeframe)
    if secs is None:
        # ⚠️ **'모름'과 '완성됨'이 같은 답이면 안 된다**(감사 204). 호출부는
        #    None을 "완성된 봉"으로 읽고 미완결 봉 제거를 건너뛴다 — 즉 모르는
        #    타임프레임 하나로 감사 71의 보호가 **조용히 꺼진다.** 24시간
        #    시장에서 그건 항상 진행 중인 봉을 그대로 쓴다는 뜻이다.
        #    판정 불가는 소리를 내고, 아래 bar_status가 보수적으로 처리한다.
        from quant.utils.logging import get_logger
        get_logger("data.barclock").warning(
            "봉 완성도를 잴 수 없습니다 — 모르는 타임프레임 %r (아는 것: %s)",
            timeframe, ", ".join(sorted(_TF_SECONDS)))
        return None
    try:
        start = dt.datetime.fromisoformat(str(last_bar).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if start.tzinfo is not None:
        start = start.astimezone(dt.timezone.utc).replace(tzinfo=None)
    cur = now or dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    if cur.tzinfo is not None:
        cur = cur.astimezone(dt.timezone.utc).replace(tzinfo=None)
    elapsed = (cur - start).total_seconds()
    if elapsed < 0:
        return 0.0                       # 아직 시작도 안 한 봉(유령 봉)
    return min(1.0, elapsed / secs)


def _is_future(last_bar, now: dt.datetime | None = None) -> bool:
    """이 봉의 시작 시각이 아직 오지 않았는가."""
    try:
        start = dt.datetime.fromisoformat(str(last_bar).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    if start.tzinfo is not None:
        start = start.astimezone(dt.timezone.utc).replace(tzinfo=None)
    cur = now or dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    if cur.tzinfo is not None:
        cur = cur.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return start > cur


def bar_status(market: str, last_bar, timeframe: str = "1d",
               now: dt.datetime | None = None) -> dict | None:
    """장부에 남길 '결정 봉 완성도' 기록. 완성됐거나 판정 불가면 None.

    None을 돌려주는 것이 정상이며, 값이 있다는 것 자체가 '이 판단은 아직
    만들어지는 중인 봉으로 내렸다'는 고백이다. 주식에서 이 값이 나오면
    _drop_unclosed가 고장난 것이므로 그 자체가 사건이다.
    """
    if market not in CONTINUOUS_MARKETS:
        return None
    frac = bar_elapsed_fraction(last_bar, timeframe, now)
    if frac is None:
        # 판정 불가 — 24시간 시장에서는 **진행 중으로 취급하는 편이 안전하다**
        # (감사 204). 마지막 봉은 거의 항상 진행 중이고, 완성으로 오판하면
        # 미완결 봉이 그대로 모델에 들어간다(감사 71이 막으려던 바로 그것).
        # elapsed는 숫자를 지어내지 않고 None으로 둔다 — 0.0이라고 적으면
        # '방금 시작한 봉'이라는 없는 사실이 장부에 남는다.
        return {"elapsed": None, "timeframe": timeframe, "undetermined": True,
                "note": "이 봉이 얼마나 만들어졌는지 판정하지 못했다(모르는 "
                        "타임프레임이거나 시각을 읽지 못함). 완성으로 단정하지 "
                        "않고 진행 중으로 보수적으로 처리했다."}
    if frac >= 1.0:
        return None
    if frac <= 0.0 and _is_future(last_bar, now):
        # ⚠️ **미래 봉을 '0% 진행 중'이라고 적지 않는다**(감사 204). 그건
        #    그럴듯한 숫자지 사실이 아니다 — 데이터 소스가 아직 오지 않은
        #    봉을 준 것이고, 그 자체가 사건이다(감사 181에서 status.json에
        #    미래 날짜가 실렸던 것과 같은 계열).
        return {"elapsed": 0.0, "timeframe": timeframe, "future_bar": True,
                "note": "마지막 봉의 시각이 **미래**다 — 아직 시작도 하지 않은 "
                        "봉을 받았다. 데이터 소스나 시계가 어긋난 것이며, 이 "
                        "봉의 값은 확정값이 아니다."}
    return {"elapsed": round(float(frac), 4), "timeframe": timeframe,
            # ⚠️ 2026-08-12 감사 143 — 이 문구가 낡아 있었다. 감사 71에서
            #    "완성된 정보로 판단하고, 지금 가격에 체결한다"로 고친 뒤에도
            #    "결정 시점에 …"라고 적혀 있어서, 장부를 읽는 사람은 여전히
            #    미완성 봉으로 **판단**했다고 읽게 됐다.
            #    동작을 고쳤으면 그 동작을 설명하는 문장도 같이 고쳐야 한다.
            "note": "체결·평가에 쓴 마지막 봉이 아직 만들어지는 중이었다 — "
                    "이 봉의 종가·고저는 확정값이 아니다. 신호·피처는 이 "
                    "봉을 빼고 확정된 봉까지만 봤다(감사 71)."}
