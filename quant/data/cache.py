"""데이터 캐싱 — 반복 백테스트 시 거래소 API 재호출을 줄인다.

같은 (종목·타임프레임·봉수) 요청을 디스크에 CSV로 저장해두고, TTL 안이면
재사용한다. 최신 데이터가 필요한 경우를 위해 TTL(기본 1시간)을 두어 오래된
캐시는 자동으로 새로 받는다. start/end 범위를 지정한 요청은 캐시하지 않는다.

원칙 — **캐시는 투명해야 한다.** 캐시를 거친 프레임은 안 거친 프레임과
값도(비트 단위로) 부가정보(`attrs`)도 같아야 하고, 짧아져서도 안 된다.
셋 다 지켜지지 않고 있었다(감사 162).

오늘 이 캐시를 쓰는 곳은 학습 루프(`learn`)뿐이고 배치는 안 쓴다 —
즉 아래 결함들이 지금 장부를 오염시키고 있지는 않다. 그래도 고친다.
캐시는 "켜면 빨라진다"는 얼굴로 다음 사람을 부르는 스위치인데, 켜는 순간
데이터가 조용히 달라지는 스위치는 덫이다.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from quant.data.base import DataProvider
from quant.utils.logging import get_logger

log = get_logger("data.cache")


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def _provider_id(inner: DataProvider) -> str:
    """캐시 키에 쓸 제공자 식별자. 클래스명 + 거래소/시장 구분자."""
    parts = [type(inner).__name__]
    for attr in ("exchange_id", "market"):
        val = getattr(inner, attr, None)
        if val:
            parts.append(str(val))
    return _safe("-".join(parts))


class CachedDataProvider(DataProvider):
    """임의의 DataProvider를 감싸 디스크 캐시를 추가한다."""

    def __init__(self, inner: DataProvider, cache_dir: str = "data_cache",
                 ttl_seconds: int = 3600, max_files: int = 1000):
        self.inner = inner
        self.cache_dir = Path(cache_dir)
        self.ttl_seconds = ttl_seconds
        # 캐시 파일 수 상한. TTL은 '신선도'만 관리하고 파일을 지우지 않으므로,
        # 여러 종목·타임프레임·봉수를 오래 스윕하면 data_cache/가 무한히 커진다.
        # 상한을 넘으면 오래된 것부터 삭제한다. 0 이하면 무제한(비활성).
        self.max_files = max_files

    def _prune(self) -> None:
        """캐시 파일 수가 상한을 넘으면 mtime이 오래된 것부터 삭제한다."""
        if self.max_files <= 0:
            return
        try:
            files = sorted(self.cache_dir.glob("*.csv"),
                           key=lambda p: p.stat().st_mtime)
        except OSError:
            return
        for p in files[:max(0, len(files) - self.max_files)]:
            try:
                p.unlink()
                self._meta_path(p).unlink(missing_ok=True)    # 짝도 함께
            except OSError:
                pass

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1d",
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 500,
    ) -> pd.DataFrame:
        # 범위 지정 요청은 캐시하지 않는다 (키가 복잡해짐)
        if start is not None or end is not None:
            return self.inner.get_ohlcv(symbol, timeframe, start, end, limit)

        # 캐시 키에 내부 제공자 정체성을 포함한다. 그렇지 않으면 서로 다른
        # 거래소/시장(예: binance vs upbit, us_stock vs kr_stock)이 같은 심볼로
        # 캐시를 덮어써 잘못된 데이터를 반환할 수 있다.
        provider = _provider_id(self.inner)
        path = self.cache_dir / f"{provider}_{_safe(symbol)}_{_safe(timeframe)}_{limit}.csv"
        if path.exists() and (time.time() - path.stat().st_mtime) < self.ttl_seconds:
            try:
                # float_precision="round_trip" — 없으면 캐시를 거친 값이
                # **비트 단위로 달라진다**(최대 1.4e-14, 300칸 중 52칸).
                # 장부 해시(data_sha256)는 '.10g' 정규화 덕에 이 정도로는
                # 안 깨지지만, '같은 입력이면 같은 바이트'는 공짜로 지킬 수
                # 있는 것이니 지킨다.
                df = pd.read_csv(path, index_col=0, parse_dates=True,
                                 float_precision="round_trip")
                df = self._validate(df)
                meta = self._load_meta(path)
                # ⚠️ **짧아진 캐시를 온전한 것처럼 내주면 안 된다**(감사 162).
                #    to_csv는 원자적이지 않아 쓰다가 죽으면 반쪽 파일이 남고,
                #    반쪽 CSV도 문법은 멀쩡해서 read_csv가 조용히 성공한다.
                #    실측(200봉 요청, 파일을 절반으로 자름):
                #        돌려준 봉 99개 · 제공자 재호출 없음
                #        마지막 봉 2025-04-09 (진짜는 2025-07-19)
                #    TTL 동안 계속 그 3개월 묵은 봉이 '오늘'로 쓰인다.
                #    쓰기는 아래에서 원자적으로 바꿨고, 그래도 딴 이유로
                #    잘릴 수 있으니 저장 당시 봉 수와 대조한다.
                rows = meta.get("rows")
                if rows is not None and int(rows) != len(df):
                    raise ValueError(
                        f"캐시 봉 수 불일치(저장 {rows} → 읽기 {len(df)})")
                df.attrs.update(meta.get("attrs") or {})
                return df
            except Exception as exc:  # noqa: BLE001
                log.warning("캐시 로드 실패(%s), 새로 받습니다.", exc)

        df = self.inner.get_ohlcv(symbol, timeframe, None, None, limit)
        # 합성 폴백 데이터(네트워크/거래소 실패 시 제공자가 반환)는 캐시에 저장하지
        # 않는다. 저장하면 실제 제공자 키 아래 더미 시세가 남아 TTL 동안 '진짜 데이터'로
        # 재사용돼, 네트워크가 복구된 뒤에도 계속 가짜 데이터로 백테스트/거래하게 된다.
        # (의도적으로 synthetic을 쓰는 경우 — inner가 SyntheticDataProvider 자체 —
        #  는 폴백이 아니므로 표식이 없고, 기존대로 캐시된다.)
        if df.attrs.get("synthetic_fallback"):
            return df
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._atomic_write(path, df.to_csv())
            self._save_meta(path, df)
            self._prune()      # 무한 성장 방지(오래된 캐시 삭제)
        except Exception as exc:  # noqa: BLE001
            log.warning("캐시 저장 실패(%s).", exc)
        return df

    # ── 원자적 쓰기 ───────────────────────────────────────────
    #
    # ⚠️ `df.to_csv(path)`는 여는 즉시 파일을 비우고 조금씩 흘려 쓴다.
    #    중간에 죽으면(Ctrl-C·디스크 참·OOM) **반쪽짜리 CSV**가 남는데,
    #    반쪽도 문법은 멀쩡해서 다음 실행이 그걸 정상 캐시로 읽는다.
    #    임시 파일에 다 쓴 뒤 os.replace로 갈아끼운다 — 같은 파일시스템
    #    안의 replace는 원자적이라 '반쪽 상태'가 아예 존재하지 않는다.

    @staticmethod
    def _atomic_write(path: Path, text: str) -> None:
        tmp = path.with_name(path.name + f".tmp{os.getpid()}")
        try:
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

    # ── 출처(attrs)와 봉 수 보존 ──────────────────────────────
    #
    # ⚠️ CSV는 값만 저장한다. 그래서 캐시를 거치면 `df.attrs`가 통째로
    #    사라진다(감사 162). 거기에는 감사 135가 넣은 **어느 소스가 이
    #    데이터를 줬는가**(`source`)가 들어 있다. 폴백 소스(무조정가)로
    #    받은 데이터인데 캐시를 지나면 그 사실이 없어져, 배당락·분할 날의
    #    가짜 점프를 아무도 못 알아본다.
    #
    #    옆에 작은 JSON을 나란히 둔다. 저장 당시 봉 수(rows)도 함께 적어
    #    잘린 캐시를 알아본다. 파일이 없거나 깨졌으면 조용히 비운다 —
    #    출처를 모르는 것이 **틀린 출처를 만들어 내는 것**보다 낫다.

    @staticmethod
    def _meta_path(path: Path) -> Path:
        return path.with_suffix(".meta.json")

    def _save_meta(self, path: Path, df: pd.DataFrame) -> None:
        payload = {"attrs": dict(df.attrs), "rows": int(len(df))}
        try:
            self._atomic_write(self._meta_path(path), json.dumps(
                payload, ensure_ascii=False, default=str))
        except OSError as exc:
            log.warning("캐시 메타 저장 실패(%s).", exc)

    def _load_meta(self, path: Path) -> dict:
        fp = self._meta_path(path)
        try:
            if fp.exists():
                got = json.loads(fp.read_text(encoding="utf-8"))
                return got if isinstance(got, dict) else {}
        except (OSError, ValueError) as exc:
            log.warning("캐시 메타 로드 실패(%s) — 출처 미상으로 둡니다.", exc)
        return {}
