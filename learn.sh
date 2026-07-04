#!/usr/bin/env bash
# 맥/리눅스: 이 파일을 더블클릭하거나  ./learn.sh  로 실행하세요.
# (자동 페이퍼 학습 + 감시 대시보드)
cd "$(dirname "$0")"
PY=python3; command -v python3 >/dev/null 2>&1 || PY=python
"$PY" learn.py
