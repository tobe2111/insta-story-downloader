"""나만의 전략 만들기 — 복사해서 시작하세요.

방법은 딱 하나: `Strategy`를 상속해 `generate_signals(df)`가 '목표 포지션 비중'
(index는 df와 동일한 pd.Series)을 돌려주게 만들면 됩니다. 값의 의미:
    +1.0 = 자본 100% 롱(매수) · 0.0 = 현금(관망) · -1.0 = 100% 숏
`self._finalize(...)`가 결측 채우기·[-1,1] 클립·숏 미허용 처리를 대신 해줍니다.

한 번 만들면 이 전략은 기본 전략과 완전히 동등합니다 — 백테스트·과최적화 검증
(PBO/CPCV)·페이퍼·실거래·웹 조종석 전부 그대로 쓸 수 있습니다.

▶ 실행:
    python examples/custom_strategy.py            # 이 전략을 바로 백테스트
▶ 이름으로 어디서나 쓰려면 이 파일을 strategies_user/ 폴더에 넣으세요. 그러면
    python -m quant backtest --strategy my_sma_slope
    python -m quant validate --strategy my_sma_slope --grid '{"window":[20,50,100]}'
  처럼 CLI·웹 드롭다운·검증에서 'my_sma_slope' 이름으로 나타납니다.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from quant.strategies.base import Strategy


class MySmaSlope(Strategy):
    """예시: 이동평균의 '기울기'가 양수면 롱, 음수면 관망(추세추종).

    - name: --strategy 로 부를 이름(strategies_user에 넣었을 때). 고유하게.
    - __init__ 파라미터는 전부 기본값을 둬야 합니다(get_strategy가 인자 없이 생성).
      validate의 --grid로 이 파라미터들을 워크포워드 최적화할 수 있습니다.
    """

    name = "my_sma_slope"
    allow_short = False

    def __init__(self, window: int = 50, slope_lookback: int = 5):
        self.window = window
        self.slope_lookback = slope_lookback

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        ma = df["close"].rolling(self.window).mean()
        # 기울기 = 현재 MA − slope_lookback봉 전 MA. 양수면 상승 추세.
        slope = ma - ma.shift(self.slope_lookback)
        signal = (slope > 0).astype(float)   # 1.0(롱) / 0.0(관망)
        # ⚠️ 룩어헤드 금지: 위 계산은 '현재 봉까지'의 값만 씁니다. 미래 값을
        #    참조하면 tests/test_leakage.py 가 CI에서 잡아냅니다.
        return self._finalize(signal, df.index)


# strategies_user/에 넣으면 자동 등록되지만, 코드에서 직접 등록도 가능합니다:
#   from quant.strategies import register_strategy
#   register_strategy("my_sma_slope", MySmaSlope)


def _demo() -> None:
    """이 전략을 합성 데이터로 즉시 백테스트해 본다(네트워크 불필요)."""
    from quant.backtest import Backtester
    from quant.data import SyntheticDataProvider

    df = SyntheticDataProvider(seed=7).get_ohlcv("DEMO", "1d", limit=500)
    result = Backtester(MySmaSlope(window=50)).run(df)
    print("=== 내 전략(my_sma_slope) 백테스트 ===")
    print(result.summary())
    print("\n다음 단계: 이 파일을 strategies_user/ 에 넣고")
    print("  python -m quant validate --strategy my_sma_slope "
          "--grid '{\"window\":[20,50,100]}'")
    print("로 과최적화 검증부터 하세요. ⚠️ 과거 성과는 미래를 보장하지 않습니다.")


if __name__ == "__main__":
    _demo()
