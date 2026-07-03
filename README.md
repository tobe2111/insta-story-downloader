# Quant — 주식·코인 퀀트 자동투자 시스템

Python 기반의 **퀀트 트레이딩 프레임워크**입니다. 코인(암호화폐), 국내주식,
미국주식을 대상으로 **전략 백테스팅 → 페이퍼 트레이딩 → 실거래**를 단계적으로
검증하며 진행할 수 있도록 설계되었습니다.

---

## ⚠️ 먼저 반드시 읽어주세요 (Disclaimer)

- **이 시스템은 "무조건 수익"을 보장하지 않습니다. 세상에 그런 시스템은 없습니다.**
  수익을 100% 보장한다고 광고하는 모든 자동매매 봇은 사기이거나 과최적화된
  결과일 뿐입니다.
- 퀀트 투자에서 장기적으로 살아남는 핵심은 "마법의 예측"이 아니라
  **철저한 리스크 관리와 반복 검증**입니다.
- 이 코드는 **교육 및 연구 목적**이며, 실제 투자 손실에 대한 책임은
  전적으로 사용자 본인에게 있습니다.
- 실거래 전에 반드시 **백테스트 → 페이퍼 트레이딩** 순서로 충분히 검증하세요.

---

## 설계 철학

```
데이터 → 전략(신호) → 리스크관리(사이징/손절) → 백테스트/실행 → 성과분석
```

1. **데이터 계층** (`quant/data`) — 코인/미국/국내 데이터를 동일한 인터페이스로 제공.
   네트워크가 없으면 합성 데이터로 자동 폴백하여 오프라인에서도 검증 가능.
2. **전략 계층** (`quant/strategies`) — 모멘텀, 이동평균 교차, 평균회귀 등.
   전략은 "목표 포지션 비중(-1.0 ~ 1.0)"만 계산합니다.
3. **리스크 계층** (`quant/risk`) — 포지션 사이징, 손절/익절, 최대 낙폭 제한.
   **여기가 실제로 돈을 지키는 가장 중요한 부분입니다.**
4. **백테스트 계층** (`quant/backtest`) — 수수료·슬리피지 반영, 룩어헤드 편향 방지.
   샤프지수, MDD, 승률 등 성과 지표 산출.
5. **브로커/실행 계층** (`quant/broker`, `quant/live`) — 페이퍼 트레이딩과
   실거래(ccxt 등)를 동일한 인터페이스로 연결.

## 설치

```bash
pip install -r requirements.txt
```

## 빠른 시작 (백테스트)

```bash
# 합성 데이터로 즉시 실행 (네트워크 불필요)
python examples/run_backtest.py

# 실제 코인 데이터로 실행
python examples/run_backtest.py --market crypto --symbol BTC/USDT --timeframe 1d

# 미국 주식
python examples/run_backtest.py --market us_stock --symbol AAPL
```

## 고급: 앙상블 · 레짐 필터 · 몬테카를로 검증

진짜 견고한 성과는 파라미터 최적화가 아니라 아래 3가지에서 나옵니다.

**① 전략 앙상블** — 상관이 낮은 전략을 결합해 자본곡선을 매끄럽게 만듭니다.
```python
from quant.strategies import StrategyEnsemble, MovingAverageCross, Breakout, RSIReversion
ens = StrategyEnsemble([MovingAverageCross(), Breakout(), RSIReversion()])
```

**② 레짐 필터** — 약세장/고변동성 구간에서 자동으로 관망해 대낙폭을 회피합니다.
```python
from quant.strategies import RegimeFilter
strat = RegimeFilter(ens, trend_window=200)   # 장기MA 아래면 매매 중단
```

**③ 몬테카를로 신뢰구간** — 샤프지수 하나에 속지 마세요. 수천 번 재추출해
"진짜 실력의 분포"를 봅니다. 하단(5%)이 0 근처면 그건 운입니다.
```python
from quant.robustness import bootstrap_metrics, summarize
print(summarize(bootstrap_metrics(result.returns)))
```

**통합 실행** — 백테스트 + HTML 리포트 + 몬테카를로를 한 번에:
```bash
python examples/run_config.py --config config/config.yaml
```

## 포트폴리오 백테스트 (다중 종목)

여러 종목에 분산투자하여 변동성을 낮춥니다. 배분 방식: `equal`(균등),
`inverse_vol`(변동성 역가중 ≈ 리스크 패리티).

```bash
python examples/run_portfolio.py --market crypto --symbols BTC/USDT ETH/USDT SOL/USDT
python examples/run_portfolio.py --market us_stock --symbols AAPL MSFT NVDA --allocation inverse_vol
```

## 파라미터 최적화 + 워크포워드 검증

**가장 중요한 도구입니다.** 단순히 과거 수익률을 최대화하면 과최적화됩니다.
워크포워드는 "과거로 최적화 → 보지 않은 미래로 검증"을 반복해 **실전에서
기대할 수 있는 진짜 성과**를 측정합니다.

```bash
python examples/run_optimize.py --market crypto --symbol BTC/USDT --strategy ma_cross
```
> IS(학습) 샤프와 OOS(검증) 샤프의 격차가 크면 그 전략은 과최적화된 것입니다.

## 페이퍼 & 실거래 트레이딩

```bash
# 페이퍼 (안전, 권장)
python examples/run_live.py --paper --market crypto --symbol BTC/USDT --iters 5

# 실거래 — 각 시장별 브로커 (환경변수로 API 키 주입)
python examples/run_live.py --live --market crypto  --symbol BTC/USDT   # ccxt
python examples/run_live.py --live --market us_stock --symbol AAPL       # Alpaca
python examples/run_live.py --live --market kr_stock --symbol 005930     # 한국투자증권
```

실거래 API 키 (환경변수로만 주입, 파일 저장 금지):

| 시장 | 환경변수 |
|------|----------|
| 코인 | `EXCHANGE_API_KEY`, `EXCHANGE_SECRET` |
| 미국주식 (Alpaca) | `ALPACA_API_KEY`, `ALPACA_SECRET` |
| 국내주식 (KIS) | `KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_CANO`, `KIS_ACNT_PRDT_CD` |

## 프로젝트 구조

```
quant/
├── data/         데이터 제공자 (crypto / us_stock / kr_stock / synthetic)
├── strategies/   전략 (MA/모멘텀/평균회귀/RSI/브레이크아웃/MACD/앙상블/레짐필터)
├── risk/         리스크 관리 (사이징, 손절, 익절)
├── backtest/     단일 종목 백테스트 엔진 + 성과 지표
├── portfolio/    다중 종목 포트폴리오 배분 + 백테스트
├── optimize/     그리드 서치 + 워크포워드 검증
├── robustness/   몬테카를로 부트스트랩 (신뢰구간)
├── reporting/    자체 완결형 HTML 리포트 (인라인 SVG 차트)
├── broker/       주문 실행 (페이퍼 / ccxt / Alpaca / 한국투자증권)
├── live/         실시간 트레이딩 루프
└── utils/        로깅, HTTP 유틸
```

## 로드맵

- [x] 백테스트 엔진 + 성과 지표
- [x] 다중 전략 + 리스크 관리
- [x] 페이퍼 트레이딩 + 코인/미국/국내 실거래 연동
- [x] 포트폴리오 다중 종목 배분/백테스트
- [x] 워크포워드 검증 / 파라미터 최적화
- [x] 전략 앙상블 + 레짐 필터 (드로다운 방어)
- [x] 몬테카를로 신뢰구간 + HTML 리포트
- [ ] 실거래 주문 체결/재시도 견고화 (부분체결, 레이트리밋)
- [ ] 실시간 스케줄러 + 라이브 모니터링 대시보드
