# 나만의 전략 폴더 (strategies_user/)

이 폴더에 `.py` 파일을 넣으면, 그 안의 전략이 **자동으로 등록**되어
`--strategy <이름>`·`validate`·웹 드롭다운 어디서나 쓸 수 있습니다.
소스 코드를 고칠 필요가 없습니다.

## 시작하기 (30초)

1. `examples/custom_strategy.py` 를 이 폴더로 복사합니다.
2. `generate_signals`를 내 아이디어대로 고칩니다(목표 비중 -1~1 반환).
3. 바로 씁니다:
   ```bash
   python -m quant backtest --strategy my_sma_slope
   python -m quant validate --strategy my_sma_slope --grid '{"window":[20,50,100]}'
   ```

## 규칙

- `Strategy`를 상속하고 `generate_signals(df) -> pd.Series`를 구현합니다.
- 클래스에 `name = "고유한_이름"`을 두면 그 이름으로 등록됩니다(없으면 파일명).
- `__init__` 파라미터는 모두 기본값을 둡니다(이름으로 생성할 때 인자가 없음).
- **미래를 참조하지 마세요.** `tests/test_leakage.py`가 룩어헤드를 CI에서 잡습니다.
- 파일명이 `_`로 시작하면 무시됩니다(헬퍼·초안 보관용).

> 폴더 위치는 환경변수 `QUANT_STRATEGY_DIR`로 바꿀 수 있습니다.
> ⚠️ 좋은 전략이라도 반드시 `validate`(과최적화 검증) → 페이퍼 순서로 확인하세요.
> 이 시스템은 수익을 보장하지 않습니다.

*(이 폴더의 `*.py`만 로드되며, 이 README는 로드 대상이 아닙니다.)*
