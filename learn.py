#!/usr/bin/env python3
"""더블클릭 실행기 — 자동 페이퍼 학습 (머신러닝).

이 파일을 실행하면:
    1) 필요한 라이브러리를 (처음 한 번) 자동 설치하고
    2) 백그라운드에서 '자동 페이퍼 학습'을 시작하고
       (매 주기마다 최신 데이터로 재학습 → 가짜 돈으로 매매 → 정확도 기록)
    3) 브라우저에 감시 대시보드를 열어 자산·정확도를 실시간으로 보여줍니다.

터미널에 익숙하지 않아도 됩니다. 윈도우는 learn.bat, 맥/리눅스는 learn.sh 를
더블클릭하거나, 어디서든  python learn.py  로 실행하세요.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ 정직한 안내: 이 프로그램은 '정확도를 100%로 올리는' 마법이 아닙니다.
   방향 예측 정확도는 대개 50~55% 사이에서 오르내립니다. 이 화면의 목적은
   그 현실을 '숨기지 않고 보여주는' 것입니다. 페이퍼(가짜 돈)로 충분히
   관찰한 뒤에만, 잃어도 되는 소액으로 실거래를 고려하세요.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

설정을 바꾸려면 같은 폴더에 learn_config.yaml 을 두세요(선택). 예:
    market: crypto
    symbol: BTC/USDT
    strategy: ml
    timeframe: 1h
    interval: 900      # 사이클 간격(초)
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import webbrowser

HOST = "127.0.0.1"
PORT = 8000
STATE = os.path.join("results", "state.json")   # 웹 감시 탭이 자동으로 읽는 경로

# 기본 설정 (learn_config.yaml 이 있으면 덮어씀)
DEFAULTS = {
    "market": "crypto",
    "symbol": "BTC/USDT",
    "strategy": "ml",
    "timeframe": "1h",
    "lookback": 500,
    "accuracy_window": 60,
    "interval": 900,
    "cash": 10_000.0,
    "use_fear_greed": False,   # True + strategy=ml 이면 공포탐욕지수를 피처로 추가
}

_FROZEN = getattr(sys, "frozen", False)
_ROOT = os.path.dirname(sys.executable) if _FROZEN \
    else os.path.dirname(os.path.abspath(__file__))


def _ensure_deps() -> None:
    """핵심 라이브러리(ML 포함)가 없으면 requirements.txt로 자동 설치한다."""
    if _FROZEN:
        return
    try:
        import numpy  # noqa: F401
        import pandas  # noqa: F401
        import sklearn  # noqa: F401
        import yaml  # noqa: F401
        return
    except ImportError:
        print("📦 필요한 라이브러리를 설치합니다 (처음 한 번, 1~3분 걸릴 수 있어요)...")
        req = os.path.join(_ROOT, "requirements.txt")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", req])
        print("✅ 설치 완료.\n")


def _load_config() -> dict:
    cfg = dict(DEFAULTS)
    path = os.path.join(_ROOT, "learn_config.yaml")
    if os.path.exists(path):
        try:
            import yaml
            with open(path, encoding="utf-8") as f:
                user = yaml.safe_load(f) or {}
            cfg.update({k: user[k] for k in user if k in DEFAULTS})
            print(f"⚙️  learn_config.yaml 적용: {user}")
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️ 설정 파일을 읽지 못해 기본값으로 진행합니다: {exc}")
    return cfg


def _open_browser(url: str, delay: float = 2.5) -> None:
    time.sleep(delay)
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001
        pass


def _start_learner(cfg: dict) -> None:
    """백그라운드 스레드에서 자동 페이퍼 학습을 무기한 돌린다."""
    from quant.broker import PaperBroker
    from quant.data import get_provider
    from quant.live import AutoLearner
    from quant.risk import RiskManager
    from quant.strategies import default_ensemble, get_strategy

    strat = default_ensemble() if cfg["strategy"] == "ensemble" \
        else get_strategy(cfg["strategy"])
    # 선택: 공포탐욕지수를 ML 외부 피처로 추가 (크립토, 무료 API)
    if cfg.get("use_fear_greed") and getattr(strat, "name", "") == "ml":
        from quant.data import fear_greed_frame
        fg = fear_greed_frame()
        if not fg.empty:
            strat.extra_features = fg
            print(f"🧭 공포탐욕지수 {len(fg)}일치를 ML 피처로 추가했습니다.")
        else:
            print("🧭 공포탐욕지수를 받지 못해 기본 피처로 진행합니다.")
    learner = AutoLearner(
        data=get_provider(cfg["market"], cached=True),
        strategy=strat,
        broker=PaperBroker(cash=float(cfg["cash"])),
        risk=RiskManager(),
        symbol=cfg["symbol"],
        timeframe=cfg["timeframe"],
        lookback=int(cfg["lookback"]),
        accuracy_window=int(cfg["accuracy_window"]),
        state_path=os.path.join(_ROOT, STATE),
    )
    learner.run(cycles=None, interval_sec=int(cfg["interval"]))


def main() -> None:
    os.chdir(_ROOT)
    sys.path.insert(0, _ROOT)
    _ensure_deps()
    cfg = _load_config()

    print("━" * 60)
    print(f"🔁 자동 페이퍼 학습 시작: {cfg['strategy']} · {cfg['market']} · {cfg['symbol']}")
    print(f"   주기 {cfg['interval']}초마다 재학습 + 매매 + 정확도 기록 (무기한)")
    print("⚠️ 정확도는 50~55%에서 오르내립니다. 100%로 오르지 않는 게 정상입니다.")
    print("   종료하려면 이 창에서 Ctrl+C 를 누르세요.")
    print("━" * 60)

    # 학습 루프는 백그라운드, 웹 감시 대시보드는 전면
    threading.Thread(target=_start_learner, args=(cfg,), daemon=True).start()

    url = f"http://{HOST}:{PORT}/monitor"
    threading.Thread(target=_open_browser, args=(url,), daemon=True).start()
    print(f"🌐 브라우저에서 감시 대시보드가 열립니다: {url}")

    from quant.web.server import run_server
    run_server(HOST, PORT)


if __name__ == "__main__":
    main()
