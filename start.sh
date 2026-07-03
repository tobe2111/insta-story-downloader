#!/usr/bin/env bash
# 맥/리눅스: 이 파일을 더블클릭하거나  ./start.sh  로 실행하세요.
cd "$(dirname "$0")"
PY=python3; command -v python3 >/dev/null 2>&1 || PY=python
"$PY" start.py
