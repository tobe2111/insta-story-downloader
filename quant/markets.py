"""시장 관련 공용 상수 — 여러 진입점(CLI·예제·웹)이 공유한다.

같은 상수를 여러 파일에 중복 정의하면 새 시장·전략을 추가할 때 한쪽만 고쳐
드리프트가 난다. 여기 한 곳에 두어 단일 출처로 삼는다. 의존성 0(순수 stdlib)이라
pandas 없는 폼 렌더 경로에서도 안전하게 임포트할 수 있다.
"""
from __future__ import annotations

# 시장 → 실거래 브로커 mode (get_broker에 넘기는 값)
LIVE_BROKER_FOR_MARKET = {
    "crypto": "crypto_live",
    "us_stock": "us_live",
    "kr_stock": "kr_live",
}

# 정규장 시간이 정해진 시장(주식). 코인은 24시간이라 장 시간 가드 대상이 아니다.
SCHEDULED_MARKETS = frozenset({"us_stock", "kr_stock"})

# 야간 자동화(재학습·매일 페이퍼)가 도는 (시장, 종목) 대상 — 단일 출처.
# 여기에 한 줄 추가하면 재학습 대결·만원 챌린지·주간 요약·사이트에 모두 반영된다.
# 늘릴 때의 비용: 야간 잡 시간(종목당 수 분)과 '종목이 많을수록 우연히 좋아
# 보이는 종목도 생긴다'는 해석 주의(각 종목은 독립 챌린지다 — 좋은 것만 골라
# 보여주는 건 부정직하다. 사이트는 전 종목을 항상 다 보여준다).
AUTO_TARGETS = [
    ("crypto", "BTC/USDT"),
    ("crypto", "ETH/USDT"),
    ("crypto", "SOL/USDT"),
    ("us_stock", "SPY"),        # S&P500 ETF
    ("us_stock", "QQQ"),        # 나스닥100 ETF
    ("us_stock", "NVDA"),       # 개별주 표본
    ("kr_stock", "069500.KS"),  # KODEX 200
    ("kr_stock", "005930.KS"),  # 삼성전자
]

# 전략별 기본 파라미터 그리드 — validate(과최적화 검증)와 웹 최적화가 공유한다.
# 작게 유지한다: 그리드가 클수록 '운으로 나올 최대 샤프'(DSR 기준선)만 올라간다.
STRATEGY_GRIDS = {
    "ma_cross": {"fast": [5, 10, 20], "slow": [40, 60, 120]},
    "momentum": {"lookback": [30, 60, 90]},
    "mean_reversion": {"window": [10, 20, 30], "z": [1.5, 2.0, 2.5]},
    "rsi": {"period": [7, 14, 21]},
    "breakout": {"window": [20, 40, 55]},
    "macd": {"fast": [8, 12], "slow": [21, 26]},
    "keltner": {"ema_window": [10, 20], "atr_window": [10, 14], "mult": [1.5, 2.0, 2.5]},
    "stochastic": {"k_period": [10, 14], "oversold": [20, 25], "overbought": [75, 80]},
    "ml": {"model": ["logreg", "gb"], "threshold": [0.53, 0.57]},
}
