.PHONY: install install-all test lint backtest sweep clean

install:          ## 핵심 의존성 설치
	pip install -r requirements.txt

install-all: install  ## 실데이터/시각화 포함 전체 설치
	pip install ccxt yfinance matplotlib

test:             ## 전체 테스트 실행
	pytest -q

lint:             ## 문법 검사
	python -m py_compile $$(find quant examples tests -name "*.py")

backtest:         ## 합성 데이터로 백테스트 데모
	python examples/run_backtest.py --strategy ma_cross

sweep:            ## 파라미터 민감도 히트맵 생성
	python examples/run_sweep.py

clean:            ## 캐시/결과물 정리
	rm -rf $$(find . -name __pycache__ -type d) .pytest_cache results
