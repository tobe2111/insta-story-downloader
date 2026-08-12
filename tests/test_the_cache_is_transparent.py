"""캐시를 켜면 데이터가 조용히 달라진다 (감사 162).

`CachedDataProvider`는 "켜면 빨라진다"는 얼굴을 한 스위치다. 그런데 켜는
순간 세 가지가 달라지고 있었다.

    ① 출처가 사라진다
       CSV는 값만 저장한다. 감사 135가 넣은 `attrs["source"]`
       (야후냐 · 무조정가인 보조 소스냐)가 캐시를 지나면 통째로 없어진다.
       배당락·분할 날의 가짜 점프를 아무도 못 알아본다.

    ② 값이 비트 단위로 달라진다
       pandas의 빠른 CSV 파서는 왕복 정확도를 보장하지 않는다.
       실측 300칸 중 52칸이 최대 1.4e-14 어긋났다.

    ③ **잘린 캐시를 온전한 것처럼 내준다** ← 이게 진짜 무서운 것
       `to_csv`는 원자적이지 않다. 쓰다가 죽으면(Ctrl-C·디스크 참) 반쪽
       CSV가 남는데, 반쪽도 문법은 멀쩡해서 `read_csv`가 조용히 성공한다.
       실측(200봉 요청, 파일을 절반으로 자름):

           돌려준 봉 99개 · 제공자 재호출 없음
           마지막 봉 2025-04-09  (진짜는 2025-07-19)

       TTL 동안 계속 그 **3개월 묵은 봉**이 '오늘'로 쓰인다.

──────────────────────────────────────────────────────────────
지금 터지고 있는 일인가 — 아니다. 정직하게 적는다.

캐시를 실제로 켜는 곳은 학습 루프(`learn`)뿐이고, 새벽 배치(daily·retrain)는
캐시 없이 제공자를 직접 부른다. 그래서 ①은 오늘 장부를 오염시키지 않고,
②도 장부 해시(`data_sha256`)가 `.10g`로 정규화돼 있어 안 깨진다.

그래도 고친다. 캐시는 다음 사람이 배치에 켜 볼 스위치이고, 켜는 순간
데이터가 달라지는 스위치는 덫이다. 검사하는 것은 결과가 아니라 **계약**이다
— 캐시를 거친 프레임은 안 거친 프레임과 같아야 한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.data.base import DataProvider  # noqa: E402
from quant.data.cache import CachedDataProvider  # noqa: E402
from quant.utils.repro import data_sha256  # noqa: E402

SOURCE = "stooq"          # 무조정가 보조 소스 — 이 사실이 사라지면 안 된다


class _Provider(DataProvider):
    """호출 횟수를 세는 제공자. 값은 딱 떨어지지 않는 실수여야 한다 —
    100.0, 101.0 같은 값은 CSV 왕복에서 절대 안 깨져서 ②를 못 잡는다."""

    market = "us_stock"

    def __init__(self) -> None:
        self.calls = 0

    def get_ohlcv(self, symbol, timeframe="1d", start=None, end=None,
                  limit=500) -> pd.DataFrame:
        self.calls += 1
        rng = np.random.default_rng(7)
        idx = pd.date_range("2025-01-01", periods=limit, freq="D")
        close = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.013, limit)))
        df = pd.DataFrame({"open": close, "high": close * 1.004,
                           "low": close * 0.996, "close": close,
                           "volume": rng.uniform(1e6, 2e6, limit)}, index=idx)
        df = self._validate(df)
        df.attrs["source"] = SOURCE
        return df


def _cache(tmp_path, **kw) -> tuple[CachedDataProvider, _Provider]:
    inner = _Provider()
    return CachedDataProvider(inner, cache_dir=str(tmp_path), **kw), inner


def _csv(tmp_path) -> Path:
    return next(Path(tmp_path).glob("*.csv"))


# ── 대조군: 캐시가 캐시로서 작동하는가 ────────────────────────


def test_the_second_call_is_actually_served_from_disk(tmp_path):
    """이게 깨지면 아래 검사들이 전부 헛돈다 — 늘 새로 받으면 당연히 같다."""
    c, inner = _cache(tmp_path)
    c.get_ohlcv("AAPL", "1d", limit=60)
    c.get_ohlcv("AAPL", "1d", limit=60)
    assert inner.calls == 1, f"캐시가 안 먹었다(제공자 {inner.calls}회 호출)"


# ── ① 출처가 살아남는가 ───────────────────────────────────────


def test_the_source_survives_the_cache(tmp_path):
    c, _ = _cache(tmp_path)
    fresh = c.get_ohlcv("AAPL", "1d", limit=60)
    cached = c.get_ohlcv("AAPL", "1d", limit=60)
    assert fresh.attrs.get("source") == SOURCE, "전제가 깨졌다(원본에 출처 없음)"
    assert cached.attrs.get("source") == SOURCE, (
        f"캐시를 지나며 출처가 사라졌다: {dict(cached.attrs)} — "
        "무조정가로 받았다는 사실이 없어지면 분할·배당 날 가짜 점프를 못 잡는다")


def test_a_broken_sidecar_leaves_the_source_unknown_not_invented(tmp_path):
    """출처를 **모르는 것**이 틀린 출처를 지어내는 것보다 낫다."""
    c, _ = _cache(tmp_path)
    fresh = c.get_ohlcv("AAPL", "1d", limit=60)
    CachedDataProvider._meta_path(_csv(tmp_path)).write_text("{깨진 json")
    cached = c.get_ohlcv("AAPL", "1d", limit=60)
    assert "source" not in cached.attrs, dict(cached.attrs)
    assert cached.equals(fresh), "메타가 깨졌다고 시세까지 잃으면 안 된다"


# ── ② 값이 비트 단위로 같은가 ─────────────────────────────────


def test_the_cached_frame_is_bit_identical(tmp_path):
    c, _ = _cache(tmp_path)
    fresh = c.get_ohlcv("AAPL", "1d", limit=60)
    cached = c.get_ohlcv("AAPL", "1d", limit=60)
    assert fresh.equals(cached), (
        "캐시를 거친 값이 비트 단위로 다르다 — 최대 차이 %.3e" % float(
            (fresh - cached).abs().to_numpy().max()))
    assert data_sha256(fresh) == data_sha256(cached)


def test_the_test_data_could_have_caught_the_drift(tmp_path):
    """전제 고정 — 딱 떨어지는 값(100.0)만 쓰면 ②는 절대 안 잡힌다.

    float_precision 없이 읽으면 실제로 어긋나는 데이터인지 여기서 확인한다.
    """
    c, _ = _cache(tmp_path)
    fresh = c.get_ohlcv("AAPL", "1d", limit=60)
    naive = DataProvider._validate(
        pd.read_csv(_csv(tmp_path), index_col=0, parse_dates=True))
    assert not fresh.equals(naive), (
        "이 데이터는 기본 파서로도 왕복이 정확하다 — 이 검사가 헛돈다")


# ── ③ 잘린 캐시를 내주지 않는가 ───────────────────────────────


def test_a_truncated_cache_is_refetched_not_served(tmp_path):
    """감사 162의 본체 — 3개월 묵은 봉이 '오늘'이 되는 경로."""
    c, inner = _cache(tmp_path)
    full = c.get_ohlcv("AAPL", "1d", limit=200)
    p = _csv(tmp_path)
    raw = p.read_text()
    p.write_text(raw[:len(raw) // 2])        # 쓰다가 죽은 상황

    got = c.get_ohlcv("AAPL", "1d", limit=200)
    assert len(got) == len(full), (
        f"200봉을 요청했는데 {len(got)}봉을 온전한 캐시인 양 돌려준다")
    assert got.index[-1] == full.index[-1], (
        f"마지막 봉이 {got.index[-1].date()} — 진짜는 {full.index[-1].date()}")
    assert inner.calls == 2, "잘린 것을 알아채고도 새로 받지 않았다"


def test_a_crash_during_the_write_leaves_no_cache_file(tmp_path, monkeypatch):
    """반쪽 파일이 **애초에 안 생기는가** — 쓰기가 원자적인가.

    ⚠️ 처음에 이걸 `"os.replace" in src`로 썼다가 변이를 놓쳤다. 저장 경로를
       `df.to_csv(path)`로 되돌려도 `_atomic_write` 헬퍼는 파일에 그대로
       남아 있어서(죽은 코드가 되어) 그 검사는 통과한다. 부품이 있는지가
       아니라 **배선이 그 부품을 지나는지**를 봐야 한다(FROZEN_IDEAS ㉑).

    그래서 갈아끼우기를 실패시킨다. 원자적으로 쓰면 목적지 파일은 아예
    안 생긴다. 곧바로 쓰면 반쪽이 남는다.
    """
    import quant.data.cache as cache_mod

    c, _ = _cache(tmp_path)

    def _boom(src, dst):
        raise OSError("디스크가 찼다")

    monkeypatch.setattr(cache_mod.os, "replace", _boom)
    df = c.get_ohlcv("AAPL", "1d", limit=60)
    monkeypatch.undo()

    assert len(df) == 60, "캐시 저장에 실패했다고 시세 조회까지 깨지면 안 된다"
    assert not list(Path(tmp_path).glob("*.csv")), (
        "쓰기가 끝까지 못 갔는데 CSV가 남았다 — "
        "다음 실행이 그 반쪽을 정상 캐시로 읽는다")
    assert not list(Path(tmp_path).glob("*.tmp*")), "임시 파일이 남았다"


def test_a_normal_write_leaves_no_temp_files(tmp_path):
    """대조군 — 평시에 임시 파일이 쌓이면 그것도 무한 성장이다."""
    c, _ = _cache(tmp_path)
    c.get_ohlcv("AAPL", "1d", limit=60)
    assert sorted(p.suffix for p in Path(tmp_path).glob("*")) == [".csv", ".json"]


def test_a_missing_sidecar_does_not_block_the_cache(tmp_path):
    """메타가 없으면 봉 수를 대조할 수 없다 — 그렇다고 캐시를 못 쓰면 안 된다."""
    c, inner = _cache(tmp_path)
    fresh = c.get_ohlcv("AAPL", "1d", limit=60)
    CachedDataProvider._meta_path(_csv(tmp_path)).unlink()
    cached = c.get_ohlcv("AAPL", "1d", limit=60)
    assert inner.calls == 1 and cached.equals(fresh)


# ── 곁다리 정리 ───────────────────────────────────────────────


def test_pruning_takes_the_sidecar_with_it(tmp_path):
    """CSV만 지우고 메타를 남기면 data_cache/가 JSON으로 무한히 큰다."""
    c, _ = _cache(tmp_path, max_files=2)
    for sym in ("AAA", "BBB", "CCC", "DDD"):
        c.get_ohlcv(sym, "1d", limit=20)
    csvs = list(Path(tmp_path).glob("*.csv"))
    metas = list(Path(tmp_path).glob("*.meta.json"))
    assert len(csvs) == 2, csvs
    assert len(metas) == 2, f"짝 잃은 메타가 남았다: {metas}"
    assert {p.stem for p in csvs} == {p.name.split(".meta")[0] for p in metas}


def test_a_synthetic_fallback_is_never_written_to_disk(tmp_path):
    """기존 계약 — 더미 시세가 실제 제공자 키로 저장되면 TTL 동안 '진짜'가 된다."""
    class _Fallback(_Provider):
        def get_ohlcv(self, *a, **kw):
            df = super().get_ohlcv(*a, **kw)
            df.attrs["synthetic_fallback"] = True
            return df

    c = CachedDataProvider(_Fallback(), cache_dir=str(tmp_path))
    df = c.get_ohlcv("AAPL", "1d", limit=30)
    assert df.attrs.get("synthetic_fallback")
    assert not list(Path(tmp_path).glob("*")), "합성 폴백이 디스크에 남았다"


def test_who_actually_turns_the_cache_on(tmp_path):
    """배선 검사 — 이 감사가 '지금은 안 터진다'고 말한 근거를 고정한다.

    배치가 캐시를 켜게 되면 이 검사가 깨진다. 그때 위 계약들이 이미
    지켜지고 있어야 한다는 것이 이 파일의 존재 이유다.
    """
    for name in ("daily.py", "retrain.py"):
        src = (ROOT / "quant" / "live" / name).read_text("utf-8")
        assert "cached=True" not in src, (
            f"{name}이 캐시를 켰다 — 이제 감사 162의 결함들이 장부에 닿는다")
