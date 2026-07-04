@echo off
REM 윈도우: 이 파일을 더블클릭하세요. (최신 버전으로 업데이트)
cd /d "%~dp0"
python update.py || py update.py
pause
