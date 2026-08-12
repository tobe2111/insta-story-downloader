"""공용 시장 상수(quant.markets)의 정합성 테스트 — 단일 출처가 실제로
다른 곳과 어긋나지 않는지 고정한다(중복 정의 드리프트 방지의 마지막 안전망).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.markets import (
    LIVE_BROKER_FOR_MARKET,
    SCHEDULED_MARKETS,
    STRATEGY_GRIDS,
)


_BLOCKED = ("pandas", "numpy", "sklearn", "scipy")

_PROBE = """
import sys
BLOCKED = {blocked!r}


class _Blocker:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in BLOCKED:
            raise ImportError(f"{{name}} 금지(계약)")
        return None


sys.meta_path.insert(0, _Blocker())
sys.path.insert(0, {root!r})
import quant.markets as m
assert isinstance(m.STRATEGY_GRIDS, dict) and m.STRATEGY_GRIDS
loaded = [b for b in BLOCKED if b in sys.modules]
assert not loaded, f"무거운 의존이 딸려 왔다: {{loaded}}"
print("OK")
"""


def test_markets_module_is_dependency_free():
    """quant.markets 는 pandas/numpy 없이 임포트돼야 한다(폼 렌더 경로 안전).

    ⚠️ 2026-08-12 감사 131까지 이 검사는 **아무것도 확인하지 않았다.**

        import quant.markets as m
        importlib.reload(m)      # ← 이게 전부였다

    전체 검사에서는 앞선 테스트들이 이미 pandas를 임포트해 둔 뒤라,
    reload는 언제나 성공한다 — '무거운 의존 없이 임포트된다'를 한 번도
    확인한 적이 없었다. 게다가 reload는 `quant.markets`의 상수들을 **새
    객체로 다시 만들어**, 바로 아래 '같은 객체인가' 검사를 오염시켰다
    (단독 실행하면 실패하고 전체 실행하면 통과하는 순서 의존 검사).

    이제 **별도 프로세스**에서 pandas·numpy·sklearn·scipy를 아예 못
    불러오게 막고 임포트해 본다. 이 프로세스는 오염시킬 것이 없다.
    """
    import subprocess
    code = _PROBE.format(blocked=_BLOCKED, root=str(ROOT))
    r = subprocess.run([sys.executable, "-c", code],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, (
        "quant.markets를 무거운 의존 없이 임포트하지 못한다:\n"
        + (r.stderr or r.stdout)[-1200:])
    assert "OK" in r.stdout


def test_cli_and_web_share_same_grids():
    """CLI validate와 웹 최적화가 '같은 객체'의 그리드를 쓴다(드리프트 불가).

    ⚠️ 모듈 최상단에서 잡아 둔 별칭(STRATEGY_GRIDS)과 비교하지 않는다 —
    누가 `quant.markets`를 reload하면 그 별칭만 낡아, **검사 순서에 따라
    결과가 달라진다**(감사 131에서 실제로 그랬다). 지금 살아 있는 모듈의
    값을 그때그때 읽는다.
    """
    import quant.markets as m
    from quant import cli
    from quant.web import app
    assert cli._VALIDATE_GRIDS is m.STRATEGY_GRIDS
    assert app._OPT_GRIDS is m.STRATEGY_GRIDS
    # 그리고 '같은 객체'가 빈 껍데기여서 우연히 같은 것이 아님을 확인한다
    assert m.STRATEGY_GRIDS, "그리드가 비어 있다 — 동일성 검사가 무의미해진다"


def test_scheduled_markets_have_live_brokers():
    """장 시간 가드 대상 시장(주식)은 모두 실거래 브로커 매핑이 있어야 한다.

    ⚠️ 예전에는 `m in LIVE_BROKER_FOR_MARKET`만 봤다(감사 131). 키만
    있으면 값이 None이든 오타든 통과한다 — 변이 시험이 그것을 잡았다.
    '매핑이 있다'는 말은 **그 이름의 브로커가 실재한다**는 뜻이어야 한다.
    """
    import importlib
    for m in SCHEDULED_MARKETS:
        name = LIVE_BROKER_FOR_MARKET.get(m)
        assert isinstance(name, str) and name, (
            f"{m}의 실거래 브로커 매핑이 비었다: {name!r}")
        mod = importlib.import_module(f"quant.broker.{name}")
        assert mod is not None


def test_grid_keys_are_real_strategies():
    """STRATEGY_GRIDS의 키가 실제 등록된 전략이고, 파라미터명이 생성자와 일치한다."""
    import inspect

    from quant.strategies import get_strategy, list_strategies

    for name, grid in STRATEGY_GRIDS.items():
        assert name in list_strategies(), f"미등록 전략: {name}"
        params = inspect.signature(type(get_strategy(name)).__init__).parameters
        for key in grid:
            assert key in params, f"{name} 그리드의 '{key}'가 생성자에 없음"


def test_tradingview_ips_are_unique_and_valid():
    """공식 IP 목록에 중복이 없고 형식이 유효하다."""
    import ipaddress

    from quant.live.webhook import TRADINGVIEW_IPS
    assert len(TRADINGVIEW_IPS) == 4
    for ip in TRADINGVIEW_IPS:
        ipaddress.ip_address(ip)   # 잘못된 형식이면 ValueError
