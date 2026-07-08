"""사용자 커스텀 전략 온램프 테스트 — register_strategy + 폴더 자동 로딩.

사용자가 소스 수정 없이 자기 전략을 이름으로 꽂을 수 있는지, 그리고 그 전략이
기본 전략과 동등하게(백테스트·검증) 동작하는지 검증한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.strategies import (
    get_strategy,
    list_strategies,
    load_user_strategies,
    register_strategy,
)
from quant.strategies.base import Strategy


class _Flat(Strategy):
    name = "unit_flat"

    def __init__(self, k: int = 1):
        self.k = k

    def generate_signals(self, df):
        return self._finalize(pd.Series(0.0, index=df.index), df.index)


def test_register_and_get():
    register_strategy("unit_flat", _Flat, overwrite=True)
    assert "unit_flat" in list_strategies()
    s = get_strategy("unit_flat", k=3)
    assert isinstance(s, _Flat) and s.k == 3


def test_register_rejects_non_strategy():
    try:
        register_strategy("bad", dict)   # Strategy 하위 아님
        assert False, "TypeError 예상"
    except TypeError:
        pass


def test_register_no_silent_overwrite():
    register_strategy("unit_dup", _Flat, overwrite=True)
    try:
        register_strategy("unit_dup", _Flat)     # overwrite=False → 거부
        assert False, "ValueError 예상"
    except ValueError:
        pass


def test_load_user_strategies_from_folder(tmp_path):
    """폴더의 .py에 정의된 Strategy 하위 클래스가 name으로 자동 등록된다."""
    (tmp_path / "my_zero.py").write_text(
        "import pandas as pd\n"
        "from quant.strategies.base import Strategy\n"
        "class MyZero(Strategy):\n"
        "    name = 'folder_zero'\n"
        "    def generate_signals(self, df):\n"
        "        return self._finalize(pd.Series(0.0, index=df.index), df.index)\n",
        encoding="utf-8")
    (tmp_path / "_ignored.py").write_text("raise RuntimeError('로드되면 안 됨')\n",
                                          encoding="utf-8")
    names = load_user_strategies(str(tmp_path))
    assert "folder_zero" in names
    assert "folder_zero" in list_strategies()
    assert isinstance(get_strategy("folder_zero"), Strategy)


def test_load_user_strategies_direct_register(tmp_path):
    """파일이 register_strategy(...)를 직접 호출하는 방식도 지원한다."""
    (tmp_path / "reg.py").write_text(
        "import pandas as pd\n"
        "from quant.strategies import register_strategy\n"
        "from quant.strategies.base import Strategy\n"
        "class R(Strategy):\n"
        "    def generate_signals(self, df):\n"
        "        return self._finalize(pd.Series(1.0, index=df.index), df.index)\n"
        "register_strategy('reg_direct', R, overwrite=True)\n",
        encoding="utf-8")
    names = load_user_strategies(str(tmp_path))
    assert "reg_direct" in names and "reg_direct" in list_strategies()


def test_load_missing_folder_is_noop():
    assert load_user_strategies("/no/such/dir/xyz") == []


def test_bad_user_file_does_not_break_others(tmp_path):
    """한 파일이 에러여도 나머지는 계속 로드된다(경고만)."""
    (tmp_path / "boom.py").write_text("raise ValueError('의도적 오류')\n",
                                      encoding="utf-8")
    (tmp_path / "ok.py").write_text(
        "import pandas as pd\n"
        "from quant.strategies.base import Strategy\n"
        "class OkStrat(Strategy):\n"
        "    name = 'survives'\n"
        "    def generate_signals(self, df):\n"
        "        return self._finalize(pd.Series(0.0, index=df.index), df.index)\n",
        encoding="utf-8")
    names = load_user_strategies(str(tmp_path))
    assert "survives" in names          # boom.py 실패에도 ok.py는 등록됨


def test_custom_strategy_works_in_backtest():
    """등록된 커스텀 전략이 기본 전략과 동등하게 백테스트된다."""
    from quant.backtest import Backtester
    from quant.data import SyntheticDataProvider

    register_strategy("unit_flat", _Flat, overwrite=True)
    df = SyntheticDataProvider(seed=3).get_ohlcv("C", "1d", limit=200)
    res = Backtester(get_strategy("unit_flat")).run(df)
    assert (res.equity > 0).all()       # 관망 전략 → 자본 보존


def test_example_custom_strategy_importable():
    """examples/custom_strategy.py 의 예시 전략이 실제로 동작한다."""
    import importlib.util

    fp = Path(__file__).resolve().parent.parent / "examples" / "custom_strategy.py"
    spec = importlib.util.spec_from_file_location("ex_custom", fp)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    from quant.data import SyntheticDataProvider

    df = SyntheticDataProvider(seed=7).get_ohlcv("D", "1d", limit=300)
    sig = mod.MySmaSlope(window=50).generate_signals(df)
    assert sig.index.equals(df.index)
    assert sig.max() <= 1.0 + 1e-9 and sig.min() >= 0.0 - 1e-9
