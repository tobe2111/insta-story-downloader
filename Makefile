.PHONY: install install-all test lint backtest sweep web clean docker docker-up

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

web:              ## 로컬 웹 조종석 실행 (http://127.0.0.1:8000)
	python -m quant web

docker:           ## 도커 이미지 빌드
	docker build -t quant .

docker-up:        ## 도커로 웹+페이퍼봇 실행 (http://localhost:8000)
	docker compose up --build

clean:            ## 캐시/결과물 정리
	rm -rf $$(find . -name __pycache__ -type d) .pytest_cache results
