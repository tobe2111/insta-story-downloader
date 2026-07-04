@echo off
REM 윈도우: 이 파일을 더블클릭하세요. (자동 페이퍼 학습 + 감시 대시보드)
cd /d "%~dp0"
python learn.py || py learn.py
pause
