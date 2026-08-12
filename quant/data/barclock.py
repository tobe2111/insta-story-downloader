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
    if frac is None or frac >= 1.0:
        return None
    return {"elapsed": round(float(frac), 4), "timeframe": timeframe,
            # ⚠️ 2026-08-12 감사 143 — 이 문구가 낡아 있었다. 감사 71에서
            #    "완성된 정보로 판단하고, 지금 가격에 체결한다"로 고친 뒤에도
            #    "결정 시점에 …"라고 적혀 있어서, 장부를 읽는 사람은 여전히
            #    미완성 봉으로 **판단**했다고 읽게 됐다.
            #    동작을 고쳤으면 그 동작을 설명하는 문장도 같이 고쳐야 한다.
            "note": "체결·평가에 쓴 마지막 봉이 아직 만들어지는 중이었다 — "
                    "이 봉의 종가·고저는 확정값이 아니다. 신호·피처는 이 "
                    "봉을 빼고 확정된 봉까지만 봤다(감사 71)."}
